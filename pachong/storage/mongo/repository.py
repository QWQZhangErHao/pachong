"""MongoDB-specific operations for lightweight JSON results."""

from __future__ import annotations

from typing import Any

from pachong.storage.mongo.client import get_collection

COLLECTION_RESULTS = "scraping_results"
COLLECTION_PRODUCTS = "products"


async def insert_result(result: dict[str, Any]) -> str:
    """Insert a scraping result, returns the document ID string."""
    col = get_collection(COLLECTION_RESULTS)
    doc = await col.insert_one(result)
    return str(doc.inserted_id)


async def find_results(task_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """Query results, optionally filtered by task_id."""
    col = get_collection(COLLECTION_RESULTS)
    query = {"task_id": task_id} if task_id else {}
    cursor = col.find(query).sort("created_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


async def upsert_product(product: dict[str, Any]) -> str:
    """Insert or update a product by source_url. Returns document ID."""
    col = get_collection(COLLECTION_PRODUCTS)
    result = await col.update_one(
        {"source_url": product.get("source_url")},
        {"$set": product},
        upsert=True,
    )
    if result.upserted_id:
        return str(result.upserted_id)
    # Find existing doc
    doc = await col.find_one({"source_url": product["source_url"]})
    return str(doc["_id"]) if doc else ""


async def count_results(**filters: Any) -> int:
    """Count results matching filters."""
    col = get_collection(COLLECTION_RESULTS)
    return await col.count_documents(filters)


async def create_indices() -> None:
    """Create recommended indices."""
    results = get_collection(COLLECTION_RESULTS)
    products = get_collection(COLLECTION_PRODUCTS)
    await results.create_index("task_id")
    await results.create_index("created_at")
    await results.create_index("domain")
    await products.create_index("source_url", unique=True)
    await products.create_index("domain")
    await products.create_index("sku")
