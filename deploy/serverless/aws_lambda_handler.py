"""AWS Lambda handler for Pachong serverless worker.

Receives event with S3 pointers, downloads data, runs extraction,
and publishes results.

Deploy:
  zip -r pachong-lambda.zip pachong/ deploy/serverless/aws_lambda_handler.py
  aws lambda create-function --function-name pachong-worker --runtime python3.12 \
      --handler aws_lambda_handler.handler --role <role-arn> --timeout 300 --memory 1024
"""

from __future__ import annotations

import asyncio
import json
import os


async def process_event(event: dict) -> dict:
    """Process a single serverless invocation event.

    Event format (pointer-based — no DOM in payload):
    {
        "task_id": "uuid",
        "s3_bucket": "pachong-raw",
        "s3_raw_html_key": "raw/2024/05/09/abc.html",
        "s3_screenshot_key": "screenshots/2024/05/09/abc.png",
        "extraction_rules": [...],
        "callback_topic": "pachong.results"
    }
    """
    from pachong.core.settings import Settings
    from pachong.extractor.pipeline import ExtractionPipeline
    from pachong.storage.blob.s3_client import download_raw_html, init_s3
    from pachong.storage.mongo.client import init_mongo
    from pachong.storage.mongo.repository import insert_result

    settings = Settings.load()

    # Initialize S3 client (reads credentials from Lambda env)
    init_s3(settings.s3)

    # Download HTML from S3
    html = await download_raw_html(event["s3_raw_html_key"])

    # Initialize MongoDB
    init_mongo(settings)

    # Run extraction pipeline
    pipeline = ExtractionPipeline(settings)
    result = await pipeline.extract(
        html=html,
        url=f"s3://{event['s3_bucket']}/{event['s3_raw_html_key']}",
        domain=event.get("domain", "unknown"),
    )

    # Store result
    doc = {
        "task_id": event["task_id"],
        "extracted_data": result.to_dict(),
        "extractors_used": result.extractors_used,
        "success": result.success,
        "lambda_request_id": os.environ.get("AWS_REQUEST_ID", ""),
    }
    mongo_id = await insert_result(doc)

    return {
        "task_id": event["task_id"],
        "mongo_id": mongo_id,
        "success": result.success,
    }


def handler(event: dict, context) -> dict:
    """AWS Lambda entry point (synchronous).

    AWS Lambda will call this function for each invocation.
    """
    return asyncio.run(process_event(event))


# For SQS batch processing
def sqs_handler(event: dict, context) -> dict:
    """AWS Lambda entry point for SQS batch events."""
    records = event.get("Records", [])
    results = []

    async def process_all():
        for record in records:
            body = json.loads(record["body"])
            result = await process_event(body)
            results.append(result)

    asyncio.run(process_all())

    return {"batch_size": len(records), "results": results}
