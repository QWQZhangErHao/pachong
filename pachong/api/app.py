"""FastAPI application for management API + Web GUI."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Pachong API",
    version="0.1.0",
    docs_url="/docs",
    description="Distributed e-commerce scraping system management API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ─────────────────────────────────────────────────────────────

_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


# ── Web GUI (root page) ──────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def gui() -> str:
    """Serve the Pachong web console GUI."""
    gui_path = Path(__file__).parent / "static" / "app.html"
    if gui_path.exists():
        return gui_path.read_text(encoding="utf-8")
    return "<h2>Pachong API is running. GUI not found.</h2>"


# ── Register routers ─────────────────────────────────────────────────────────

from pachong.api.routes.results import router as results_router
from pachong.api.routes.tasks import router as tasks_router

app.include_router(tasks_router)  # /api/tasks/*
app.include_router(results_router)  # /api/results/*

# API v1 — versioned alias, same routes under /api/v1/
v1_tasks = APIRouter(prefix="/api/v1/tasks", tags=["tasks-v1"])
v1_results = APIRouter(prefix="/api/v1/results", tags=["results-v1"])

# Copy endpoint functions from original routers
for route in tasks_router.routes:
    v1_tasks.add_api_route(route.path, route.endpoint, methods=route.methods, response_model=route.response_model)
for route in results_router.routes:
    v1_results.add_api_route(route.path, route.endpoint, methods=route.methods, response_model=route.response_model)

app.include_router(v1_tasks)
app.include_router(v1_results)


# ── Health & Metrics ─────────────────────────────────────────────────────────


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/stats")
async def domain_stats_endpoint() -> dict:
    """Get per-domain processing statistics + adaptive concurrency state."""
    from pachong.api.routes._processor import _domain_cache, _get_sem, get_domain_stats
    sem = _get_sem()
    return {
        "domains": get_domain_stats(),
        "concurrency": {"current": sem.current, "max": sem.max, "min": sem.min},
        "dns_cache_size": len(_domain_cache),
    }


@app.get("/api/batch/resume")
async def resume_batch_state() -> dict:
    """Get pending batch tasks that can be resumed after restart."""
    from pachong.api.routes._task_service import load_batch_state
    pending = load_batch_state()
    return {"pending": len(pending), "urls": pending}


@app.post("/api/batch/clear")
async def clear_batch_endpoint() -> dict:
    """Clear saved batch state."""
    from pachong.api.routes._task_service import clear_batch_state
    clear_batch_state()
    return {"status": "cleared"}


@app.get("/metrics")
async def metrics_endpoint() -> PlainTextResponse:
    """Prometheus metrics endpoint."""
    from pachong.resilience.metrics import get_metrics
    return PlainTextResponse(content=get_metrics(), media_type="text/plain; version=0.0.4")
