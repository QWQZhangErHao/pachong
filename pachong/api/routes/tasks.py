"""Task management API endpoints — submit, list, check status."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ── Request/Response models ──────────────────────────────────────────────────

class SubmitTaskRequest(BaseModel):
    url: HttpUrl
    priority: int = Field(default=0, ge=0, le=100)
    engine_hint: str = Field(default="http", pattern="^(http|playwright|lightpanda|nodriver)$")
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout_ms: int = Field(default=30_000, ge=1_000, le=300_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SubmitTaskResponse(BaseModel):
    task_id: str
    url: str
    domain: str
    priority: int
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    url: str
    domain: str
    status: str
    priority: int
    created_at: str | None
    result: dict[str, Any] | None
    error: str | None


class TaskListResponse(BaseModel):
    tasks: list[TaskStatusResponse]
    total: int
    offset: int
    limit: int


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/submit", response_model=SubmitTaskResponse)
async def submit_task(req: SubmitTaskRequest, bg: BackgroundTasks,
                      deep: bool = Query(False, description="Enable Playwright deep rendering")) -> SubmitTaskResponse:
    """Submit a single URL. Use deep=true for JS-heavy sites (slower but more accurate)."""
    from pachong.api.routes._task_service import create_task, _process_in_background

    result = await create_task(url=str(req.url), priority=req.priority,
        engine_hint=req.engine_hint, max_retries=req.max_retries,
        timeout_ms=req.timeout_ms, metadata=req.metadata)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    bg.add_task(_process_in_background, result["task_id"], str(req.url), result["domain"], deep=deep)
    return SubmitTaskResponse(**result)


@router.post("/submit/batch", response_model=dict)
async def submit_tasks_batch(req: list[SubmitTaskRequest], bg: BackgroundTasks,
                             deep: bool = Query(False)) -> dict:
    """Submit multiple URLs. batched processing with max 5 concurrent, domain-cached."""
    from pachong.api.routes._task_service import create_task, _batch_process

    tasks_created = []
    for item in req:
        r = await create_task(url=str(item.url), priority=item.priority,
            engine_hint=item.engine_hint, max_retries=item.max_retries,
            timeout_ms=item.timeout_ms)
        if r.get("status") == "created":
            tasks_created.append({"task_id": r["task_id"], "url": str(item.url), "domain": r["domain"]})
    bg.add_task(_batch_process, tasks_created, deep=deep)
    return {"accepted": len(tasks_created), "skipped": len(req)-len(tasks_created),
            "task_ids": [t["task_id"] for t in tasks_created]}


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Get the status and result of a specific task."""
    from pachong.api.routes._task_service import get_task

    result = await get_task(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskStatusResponse(**result)


@router.get("/", response_model=TaskListResponse)
async def list_tasks(
    status: str | None = Query(None, description="Filter by status: pending, queued, running, success, failed"),
    domain: str | None = Query(None, description="Filter by domain"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> TaskListResponse:
    """List tasks with optional filters."""
    from pachong.api.routes._task_service import list_tasks as _list

    result = await _list(status=status, domain=domain, limit=limit, offset=offset)
    return TaskListResponse(**result)
