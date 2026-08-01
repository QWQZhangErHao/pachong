"""Pachong CLI — Typer application with subcommands."""

from __future__ import annotations

import asyncio

import typer

from pachong import __version__

app = typer.Typer(name="pachong", help="World-class distributed e-commerce scraping system")


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"pachong v{__version__}")


@app.command()
def check() -> None:
    """Check configuration and connectivity to all services."""
    typer.echo("Checking configuration...")
    # Will be implemented with actual health checks
    typer.echo("OK: configuration loaded")


@app.command()
def scheduler() -> None:
    """Start the scheduler process."""
    typer.echo("Starting scheduler...")
    asyncio.run(_run_scheduler())


@app.command()
def worker() -> None:
    """Start a worker process."""
    typer.echo("Starting worker...")
    asyncio.run(_run_worker())


@app.command()
def api() -> None:
    """Start the REST API server."""
    import uvicorn

    typer.echo("Starting API server on http://localhost:8000")
    uvicorn.run("pachong.api.app:app", host="0.0.0.0", port=8000, reload=True)


@app.command()
def submit(
    urls: list[str] = typer.Option([], "--url", "-u", help="URL to crawl (repeat for multiple)"),
    file: str = typer.Option(None, "--file", "-f", help="File with URLs, one per line"),
    priority: int = typer.Option(0, "--priority", "-p", help="Priority 0-100 (0=auto)"),
    engine: str = typer.Option("http", "--engine", "-e", help="Engine: http, playwright, lightpanda, nodriver"),
) -> None:
    """Submit URLs for crawling."""
    asyncio.run(_run_submit(list(urls), file, priority, engine))


@app.command()
def status(
    task_id: str = typer.Option(None, "--task-id", "-t", help="Task ID to check"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of recent tasks to show"),
) -> None:
    """Check task status."""
    asyncio.run(_run_status(task_id, limit))


async def _run_scheduler() -> None:
    from pachong.core.settings import Settings
    from pachong.scheduler.engine import SchedulerEngine

    settings = Settings.load()
    typer.echo(f"  Environment: {settings.env}")
    typer.echo(f"  Kafka brokers: {settings.queue.kafka_brokers}")
    typer.echo("  Batch size: 200, Poll interval: 500ms")
    engine = SchedulerEngine(settings)
    await engine.run()


async def _run_worker() -> None:
    from pachong.cli.worker import WorkerEngine
    from pachong.core.settings import Settings

    settings = Settings.load()
    typer.echo(f"  Environment: {settings.env}")
    typer.echo(f"  Consumer group: {settings.queue.consumer_group}")
    engine = WorkerEngine(settings)
    await engine.run()


async def _run_submit(urls: list[str], file: str | None, priority: int, engine: str) -> None:
    from pachong.api.routes._task_service import create_task

    all_urls: list[str] = list(urls)
    if file:
        from pathlib import Path
        path = Path(file)
        if path.exists():
            all_urls.extend(path.read_text(encoding="utf-8").strip().splitlines())
        else:
            typer.echo(f"File not found: {file}")
            return

    if not all_urls:
        typer.echo("No URLs provided. Use --url or --file.")
        raise typer.Exit(1)

    typer.echo(f"Submitting {len(all_urls)} URL(s)...\n")
    for u in all_urls:
        u = u.strip()
        if not u:
            continue
        result = await create_task(url=u, priority=priority, engine_hint=engine)
        flag = "+" if result["status"] == "created" else "-"
        typer.echo(f"  [{flag}] {result['task_id'][:8]}...  pri={result['priority']:3d}  {u}")
    typer.echo("\nDone.")


async def _run_status(task_id: str | None, limit: int) -> None:
    from pachong.api.routes._task_service import get_task, list_tasks

    if task_id:
        task = await get_task(task_id)
        if task is None:
            typer.echo(f"Task not found: {task_id}")
            return
        typer.echo(f"Task:      {task['task_id']}")
        typer.echo(f"URL:       {task['url']}")
        typer.echo(f"Domain:    {task['domain']}")
        typer.echo(f"Status:    {task['status']}")
        typer.echo(f"Priority:  {task['priority']}")
        typer.echo(f"Created:   {task.get('created_at', 'N/A')}")
        if task.get("error"):
            typer.echo(f"Error:     {task['error']}")
        if task.get("result"):
            typer.echo(f"Result:    {task['result']}")
    else:
        result = await list_tasks(limit=limit)
        typer.echo(f"Recent tasks ({result['total']} total):\n")
        typer.echo(f"{'Task ID':40s} {'Status':12s} {'Pri':>4s}  URL")
        typer.echo("-" * 90)
        for t in result["tasks"]:
            tid = t["task_id"][:36]
            typer.echo(f"{tid:40s} {t['status']:12s} {t['priority']:>4d}  {t['url'][:50]}")


if __name__ == "__main__":
    app()
