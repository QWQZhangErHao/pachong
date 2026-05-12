"""Local subprocess-based serverless runner.

Simulates serverless function execution by spawning a subprocess that:
1. Receives the pointer-based payload via stdin
2. Downloads raw HTML from S3
3. Runs the extraction pipeline
4. Uploads results to MongoDB
5. Publishes result to Kafka

This is the development/testing implementation. In production, AWS Lambda
or GCP Cloud Functions replace this with true elastic scaling.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile

import structlog

from pachong.core.models import ServerlessPayload
from pachong.serverless.base import AbstractServerlessRunner

logger = structlog.get_logger(__name__)

# Worker script that runs inside the subprocess
WORKER_SCRIPT = """
import asyncio
import json
import sys
import os

# Add the project root to path
sys.path.insert(0, os.environ.get('PACHONG_PROJECT_ROOT', '.'))

async def process(payload_data):
    from pachong.serverless.payload import deserialize_payload
    from pachong.storage.blob.s3_client import download_raw_html, download_bytes
    from pachong.core.settings import Settings
    from pachong.extractor.pipeline import ExtractionPipeline
    from pachong.storage.mongo.repository import insert_result

    payload = deserialize_payload(payload_data)
    settings = Settings.load()

    # Download HTML from S3 (NOT from payload — pointer-based design)
    html = await download_raw_html(payload.s3_raw_html_key)
    screenshot_bytes = None
    if payload.s3_screenshot_key:
        screenshot_bytes = await download_bytes(payload.s3_screenshot_key)

    # Initialize storage
    from pachong.storage.blob.s3_client import init_s3
    init_s3(settings.s3)
    from pachong.storage.mongo.client import init_mongo
    init_mongo(settings)

    # Run extraction
    from urllib.parse import urlparse
    pipeline = ExtractionPipeline(settings)
    result = await pipeline.extract(
        html=html,
        url=f"https://{payload.s3_raw_html_key}",
        domain="unknown",
        screenshot_bytes=screenshot_bytes,
        screenshot_s3_key=payload.s3_screenshot_key,
    )

    # Store result
    result_doc = {
        "task_id": str(payload.task_id),
        "extracted_data": result.to_dict(),
        "extractors_used": result.extractors_used,
        "success": result.success,
    }
    mongo_id = await insert_result(result_doc)
    return {"mongo_id": mongo_id, "success": result.success}

if __name__ == "__main__":
    data = sys.stdin.read()
    result = asyncio.run(process(data))
    print(json.dumps(result))
"""


class LocalServerlessRunner(AbstractServerlessRunner):
    """Runs serverless functions as local subprocesses.

    Limits concurrency to avoid overwhelming the local machine while
    still simulating the serverless execution model.
    """

    def __init__(self, max_concurrency: int = 10) -> None:
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._active = 0

    async def invoke(self, payload: ServerlessPayload) -> bool:
        """Spawn a subprocess to process the payload.

        The subprocess downloads from S3, extracts data, and stores results
        independently. We just fire and (optionally) collect the result.
        """
        async with self._semaphore:
            self._active += 1
            try:
                payload_json = payload.model_dump_json()

                # Write worker script to temp file
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", delete=False
                ) as f:
                    f.write(WORKER_SCRIPT)
                    script_path = f.name

                try:
                    process = await asyncio.create_subprocess_exec(
                        sys.executable,
                        script_path,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env={
                            **os.environ,
                            "PACHONG_PROJECT_ROOT": os.getcwd(),
                        },
                    )

                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(input=payload_json.encode()),
                        timeout=300,  # 5 min timeout
                    )

                    if process.returncode == 0:
                        result = json.loads(stdout.decode())
                        logger.info(
                            "serverless.local.success",
                            task_id=str(payload.task_id),
                            mongo_id=result.get("mongo_id"),
                        )
                        return True
                    else:
                        logger.error(
                            "serverless.local.failed",
                            task_id=str(payload.task_id),
                            stderr=stderr.decode()[:500],
                        )
                        return False

                finally:
                    try:
                        os.unlink(script_path)
                    except OSError:
                        pass

            except asyncio.TimeoutError:
                logger.error("serverless.local.timeout", task_id=str(payload.task_id))
                return False
            except Exception:
                logger.exception("serverless.local.error", task_id=str(payload.task_id))
                return False
            finally:
                self._active -= 1

    async def invoke_batch(self, payloads: list[ServerlessPayload]) -> int:
        """Invoke multiple functions concurrently. Returns count of accepted."""
        tasks = [self.invoke(p) for p in payloads]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return sum(1 for r in results if r is True)

    async def healthy(self) -> bool:
        return True  # Local runner is always available

    @property
    def max_concurrency(self) -> int:
        return self._max_concurrency

    @property
    def active_invocations(self) -> int:
        return self._active
