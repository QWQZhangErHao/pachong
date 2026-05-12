"""Result query endpoints — fetch extraction results."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("/{task_id}")
async def get_result(task_id: str) -> dict:
    """Get extraction result for a task."""
    from pachong.api.routes._task_service import get_task

    task = await get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task_id,
        "status": task.get("status"),
        "result": task.get("result"),
        "error": task.get("error"),
    }


@router.get("/")
async def list_results(
    domain: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0),
) -> dict:
    """List completed results."""
    from pachong.api.routes._task_service import list_tasks

    result = await list_tasks(status="success", domain=domain, limit=limit, offset=offset)
    return result
