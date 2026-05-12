"""Motor async MongoDB client."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from pachong.core.settings import Settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def init_mongo(settings: Settings) -> AsyncIOMotorDatabase:
    """Initialize MongoDB connection. Returns the database handle."""
    global _client, _db
    _client = AsyncIOMotorClient(
        settings.database.mongo_uri,
        minPoolSize=settings.database.mongo_pool_min,
        maxPoolSize=settings.database.mongo_pool_max,
    )
    _db = _client[settings.database.mongo_db_name]
    return _db


def get_db() -> AsyncIOMotorDatabase:
    """Get the MongoDB database handle."""
    if _db is None:
        raise RuntimeError("MongoDB not initialized. Call init_mongo() first.")
    return _db


def get_collection(name: str):
    """Get a collection by name."""
    return get_db()[name]


async def close_mongo() -> None:
    """Close MongoDB connection."""
    if _client:
        _client.close()
