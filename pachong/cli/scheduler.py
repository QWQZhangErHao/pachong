"""Scheduler process entry point."""

from __future__ import annotations

import asyncio
import signal

import structlog
import typer

from pachong.core.settings import Settings

logger = structlog.get_logger(__name__)


def main() -> None:
    """Run the scheduler process."""
    settings = Settings.load()
    typer.echo(f"Scheduler starting [env={settings.env}, batch=200]")

    from pachong.scheduler.engine import SchedulerEngine

    engine = SchedulerEngine(settings)

    loop = asyncio.new_event_loop()
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("scheduler.shutdown_signal")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Windows doesn't support add_signal_handler

    async def _run():
        await engine.start()
        try:
            while not stop_event.is_set():
                dispatched = await engine._poll_and_dispatch()
                if dispatched == 0:
                    await asyncio.sleep(engine.poll_interval_ms / 1000)
        finally:
            await engine.stop()

    try:
        loop.run_until_complete(_run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
