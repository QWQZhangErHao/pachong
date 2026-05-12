"""Google Cloud Function handler for Pachong serverless worker.

Receives HTTP request with S3 pointer payload, downloads from S3 (or GCS),
runs extraction, and returns result.

Deploy:
  gcloud functions deploy pachong-worker --runtime python312 \
      --trigger-http --allow-unauthenticated --timeout=300s --memory=1024MB
"""

from __future__ import annotations

import asyncio
import json

from flask import Request, jsonify


async def process(payload: dict) -> dict:
    """Process a single serverless invocation."""
    from pachong.core.settings import Settings
    from pachong.extractor.pipeline import ExtractionPipeline
    from pachong.storage.blob.s3_client import download_raw_html, init_s3
    from pachong.storage.mongo.client import init_mongo
    from pachong.storage.mongo.repository import insert_result

    settings = Settings.load()
    init_s3(settings.s3)
    html = await download_raw_html(payload["s3_raw_html_key"])
    init_mongo(settings)

    pipeline = ExtractionPipeline(settings)
    result = await pipeline.extract(
        html=html,
        url=f"s3://{payload['s3_bucket']}/{payload['s3_raw_html_key']}",
        domain=payload.get("domain", "unknown"),
    )

    doc = {
        "task_id": payload["task_id"],
        "extracted_data": result.to_dict(),
        "extractors_used": result.extractors_used,
        "success": result.success,
    }
    mongo_id = await insert_result(doc)

    return {"task_id": payload["task_id"], "mongo_id": mongo_id, "success": result.success}


def handler(request: Request):
    """GCP Cloud Function HTTP entry point."""
    if request.method != "POST":
        return jsonify({"error": "POST required"}), 405

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    result = asyncio.run(process(payload))
    return jsonify(result), 200
