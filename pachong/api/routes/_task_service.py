"""Task service — shared logic between API and CLI for task CRUD.

Can operate in two modes:
- With PostgreSQL: full persistence, scheduler picks up tasks
- Without PostgreSQL (in-memory): for development/demo, tasks stored in a dict
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from pachong.core.models import TaskStatus
from pachong.scheduler.priority import score_url

logger = structlog.get_logger(__name__)

# In-memory fallback for development (no PostgreSQL needed)
_memory_store: dict[str, dict] = {}


async def create_task(
    url: str,
    priority: int = 0,
    engine_hint: str = "http",
    max_retries: int = 3,
    timeout_ms: int = 30_000,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """Create a task and persist it. Auto-extracts domain and scores priority."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    domain = parsed.hostname or "unknown"

    # Auto-score priority if not explicitly set
    if priority == 0:
        priority = score_url(url)

    task_id = uuid.uuid4()
    now = datetime.now(UTC).isoformat()

    try:
        # Try PostgreSQL first
        from pachong.core.settings import Settings
        from pachong.storage.postgres.engine import get_session, init_postgres
        from pachong.storage.postgres.models import TaskModel

        settings = Settings.load()
        await init_postgres(settings)

        session = await get_session()
        try:
            task = TaskModel(
                task_id=task_id,
                url=url,
                domain=domain,
                priority=priority,
                status=TaskStatus.PENDING.value,
                engine_hint=engine_hint,
                max_retries=max_retries,
                timeout_ms=timeout_ms,
                metadata_=metadata or {},
            )
            session.add(task)
            await session.commit()
        finally:
            await session.close()

        logger.info("task.created", task_id=str(task_id), domain=domain, priority=priority)
        return {
            "task_id": str(task_id),
            "url": url,
            "domain": domain,
            "priority": priority,
            "status": "created",
            "message": f"Task created: {task_id}",
        }

    except Exception as e:
        # Fallback to in-memory store for development
        logger.warning("task.fallback_memory", reason=str(e)[:100])

        _memory_store[str(task_id)] = {
            "task_id": str(task_id),
            "url": url,
            "domain": domain,
            "status": TaskStatus.PENDING.value,
            "priority": priority,
            "engine_hint": engine_hint,
            "max_retries": max_retries,
            "created_at": now,
            "result": None,
            "error": None,
        }

        # Processing is triggered by the API endpoint via BackgroundTasks,
        # or by CLI submit tools via explicit call to _process_in_background.
        # This avoids double-processing.

        return {
            "task_id": str(task_id),
            "url": url,
            "domain": domain,
            "priority": priority,
            "status": "created",
            "message": f"Task created (standalone mode): {task_id}",
        }


async def _process_in_background(task_id: str, url: str, domain: str, deep: bool = False) -> None:
    """Process a task in the background."""
    try:
        from pachong.api.routes._processor import process_task_now
        await process_task_now(task_id, url, domain, deep=deep)
    except Exception as e:
        logger.error("proc.failed", task_id=task_id, error=str(e))
        if task_id in _memory_store:
            _memory_store[task_id]["status"] = "failed"
            _memory_store[task_id]["error"] = str(e)


_batch_registry: dict[str, dict] = {}
_BATCH_FILE: Path | None = None


async def _batch_process(tasks: list[dict], deep: bool = False) -> None:
    """Process multiple tasks concurrently, with auto-save for resume."""
    for t in tasks:
        _batch_registry[t["task_id"]] = {"url": t["url"], "domain": t["domain"], "status": "queued"}
    _save_batch_state()

    try:
        from pachong.api.routes._processor import process_batch
        await process_batch(tasks, deep=deep)
    except Exception as e:
        logger.error("batch.failed", error=str(e))

    for t in tasks:
        if t["task_id"] in _batch_registry:
            _batch_registry[t["task_id"]]["status"] = "processed"
    _save_batch_state()


def _save_batch_state():
    try:
        from pathlib import Path
        pending = {k: v for k, v in _batch_registry.items() if v.get("status") == "queued"}
        if pending:
            import json
            f = Path(__file__).parent.parent.parent.parent / "batch_state.json"
            f.write_text(json.dumps(list(pending.values()), ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def load_batch_state() -> list[dict]:
    """Load pending batch tasks from disk (for resume after restart)."""
    try:
        from pathlib import Path
        f = Path(__file__).parent.parent.parent.parent / "batch_state.json"
        if f.exists():
            import json
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def clear_batch_state():
    try:
        from pathlib import Path
        f = Path(__file__).parent.parent.parent.parent / "batch_state.json"
        if f.exists():
            f.unlink()
    except Exception:
        pass


async def get_task(task_id: str) -> dict | None:
    """Get task status and result."""
    try:
        from sqlalchemy import select

        from pachong.core.settings import Settings
        from pachong.storage.postgres.engine import get_session, init_postgres
        from pachong.storage.postgres.models import TaskModel

        settings = Settings.load()
        await init_postgres(settings)

        session = await get_session()
        try:
            stmt = select(TaskModel).where(TaskModel.task_id == uuid.UUID(task_id))
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()

            if task:
                return {
                    "task_id": str(task.task_id),
                    "url": task.url,
                    "domain": task.domain,
                    "status": task.status,
                    "priority": task.priority,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "result": None,
                    "error": task.error_message,
                }
        finally:
            await session.close()

    except Exception:
        pass

    # Fallback to memory store
    if task_id in _memory_store:
        return _memory_store[task_id]

    return None


async def list_tasks(
    status: str | None = None,
    domain: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List tasks with optional filtering."""
    try:
        from sqlalchemy import func, select

        from pachong.core.settings import Settings
        from pachong.storage.postgres.engine import get_session, init_postgres
        from pachong.storage.postgres.models import TaskModel

        settings = Settings.load()
        await init_postgres(settings)

        session = await get_session()
        try:
            stmt = select(TaskModel)
            count_stmt = select(func.count(TaskModel.task_id))

            if status:
                stmt = stmt.where(TaskModel.status == status)
                count_stmt = count_stmt.where(TaskModel.status == status)
            if domain:
                stmt = stmt.where(TaskModel.domain == domain)
                count_stmt = count_stmt.where(TaskModel.domain == domain)

            stmt = stmt.order_by(TaskModel.created_at.desc()).offset(offset).limit(limit)

            result = await session.execute(stmt)
            rows = result.scalars().all()

            count_result = await session.execute(count_stmt)
            total = count_result.scalar()

            tasks = [
                {
                    "task_id": str(r.task_id),
                    "url": r.url,
                    "domain": r.domain,
                    "status": r.status,
                    "priority": r.priority,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "result": None,
                    "error": r.error_message,
                }
                for r in rows
            ]

            return {"tasks": tasks, "total": total, "offset": offset, "limit": limit}

        finally:
            await session.close()

    except Exception:
        pass

    # Fallback to memory store — only include real task entries
    all_tasks = [v for v in _memory_store.values() if isinstance(v, dict) and "task_id" in v]
    if status:
        all_tasks = [t for t in all_tasks if t.get("status") == status]
    if domain:
        all_tasks = [t for t in all_tasks if t.get("domain") == domain]

    all_tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {
        "tasks": all_tasks[offset:offset + limit],
        "total": len(all_tasks),
        "offset": offset,
        "limit": limit,
    }
