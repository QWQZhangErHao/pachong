#!/bin/bash
# Initialize all databases for pachong development
set -e

echo "=== Pachong Database Initialization ==="

# PostgreSQL: Run Alembic migrations
echo "[1/3] Running PostgreSQL migrations..."
cd "$(dirname "$0")/.."
python -m alembic upgrade head
echo "  PostgreSQL migrations complete."

# MinIO: Create bucket
echo "[2/3] Creating MinIO bucket..."
python -c "
from pachong.core.settings import Settings
from pachong.storage.blob.s3_client import init_s3, ensure_bucket
import asyncio

async def main():
    settings = Settings.load()
    init_s3(settings.s3)
    await ensure_bucket()
    print('  MinIO bucket ready:', settings.s3.bucket)

asyncio.run(main())
"

# MongoDB: Create indices
echo "[3/3] Creating MongoDB indices..."
python -c "
from pachong.core.settings import Settings
from pachong.storage.mongo.client import init_mongo
from pachong.storage.mongo.repository import create_indices
import asyncio

async def main():
    settings = Settings.load()
    init_mongo(settings)
    await create_indices()
    print('  MongoDB indices created.')

asyncio.run(main())
"

echo "=== All databases initialized ==="
