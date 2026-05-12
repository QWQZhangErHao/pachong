"""Generic async repository pattern for PostgreSQL."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pachong.storage.postgres.engine import get_session

T = TypeVar("T")


class Repository:
    """Async repository with common CRUD operations."""

    def __init__(self, model: type[T]):
        self.model = model

    async def get(self, **kwargs: Any) -> T | None:
        session: AsyncSession = await get_session()
        try:
            stmt = select(self.model).filter_by(**kwargs).limit(1)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
        finally:
            await session.close()

    async def get_all(
        self, limit: int = 100, offset: int = 0, order_by: Any = None, **kwargs: Any
    ) -> Sequence[T]:
        session: AsyncSession = await get_session()
        try:
            stmt = select(self.model).filter_by(**kwargs).limit(limit).offset(offset)
            if order_by is not None:
                stmt = stmt.order_by(order_by)
            result = await session.execute(stmt)
            return result.scalars().all()
        finally:
            await session.close()

    async def create(self, instance: T) -> T:
        session: AsyncSession = await get_session()
        try:
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return instance
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def update(self, instance: T, **values: Any) -> T:
        session: AsyncSession = await get_session()
        try:
            for key, value in values.items():
                setattr(instance, key, value)
            await session.commit()
            await session.refresh(instance)
            return instance
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def update_where(self, filters: dict[str, Any], values: dict[str, Any]) -> int:
        """Bulk update rows matching filters. Returns count of updated rows."""
        session: AsyncSession = await get_session()
        try:
            stmt = update(self.model).filter_by(**filters).values(**values)
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def delete(self, instance: T) -> None:
        session: AsyncSession = await get_session()
        try:
            await session.delete(instance)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def count(self, **kwargs: Any) -> int:
        session: AsyncSession = await get_session()
        try:
            from sqlalchemy import func

            stmt = select(func.count()).select_from(self.model).filter_by(**kwargs)
            result = await session.execute(stmt)
            return result.scalar_one()
        finally:
            await session.close()

    async def exists(self, **kwargs: Any) -> bool:
        return await self.count(**kwargs) > 0

    async def batch_insert(self, instances: list[T], batch_size: int = 20) -> int:
        """Insert instances in batches using bulk_insert_mappings for speed."""
        if not instances:
            return 0
        session: AsyncSession = await get_session()
        total = 0
        try:
            for i in range(0, len(instances), batch_size):
                batch = instances[i:i + batch_size]
                mappings = [
                    {c.name: getattr(inst, c.name) for c in self.model.__table__.columns}
                    for inst in batch
                ]
                await session.execute(self.model.__table__.insert(), mappings)
                total += len(batch)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
        return total

    async def bulk_create(self, instances: list[T]) -> list[T]:
        session: AsyncSession = await get_session()
        try:
            session.add_all(instances)
            await session.commit()
            for instance in instances:
                await session.refresh(instance)
            return instances
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
