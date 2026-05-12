"""PostgreSQL CRUD for browser identities."""

from __future__ import annotations

import uuid

from pachong.core.models import BrowserIdentity
from pachong.storage.postgres.engine import get_session
from pachong.storage.postgres.models import BrowserIdentityModel
from pachong.storage.postgres.repository import Repository


class IdentityStore:
    """CRUD operations for BrowserIdentity persistence."""

    def __init__(self) -> None:
        self.repo = Repository(BrowserIdentityModel)

    async def save(self, identity: BrowserIdentity) -> BrowserIdentityModel:
        """Save a BrowserIdentity to PostgreSQL."""
        model = BrowserIdentityModel(
            identity_id=identity.identity_id,
            name=identity.name,
            timezone=identity.timezone,
            locale=identity.locale,
            languages=identity.languages,
            platform=identity.platform,
            user_agent=identity.user_agent,
            browser_name=identity.browser_name,
            browser_version=identity.browser_version,
            screen_width=identity.screen_width,
            screen_height=identity.screen_height,
            canvas_hash=identity.canvas_hash,
            webgl_vendor=identity.webgl_vendor,
            webgl_renderer=identity.webgl_renderer,
            audio_hash=identity.audio_hash,
            tls_ja4_hash=identity.tls_ja4_hash,
            success_rate=identity.success_rate,
            ban_score=identity.ban_score,
        )
        return await self.repo.create(model)

    async def get(self, identity_id: uuid.UUID) -> BrowserIdentityModel | None:
        return await self.repo.get(identity_id=identity_id)

    async def list_active(self, limit: int = 50) -> list[BrowserIdentityModel]:
        """Get identities ordered by success rate (best first)."""
        session = await get_session()
        try:
            from sqlalchemy import select

            stmt = (
                select(BrowserIdentityModel)
                .order_by(BrowserIdentityModel.success_rate.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        finally:
            await session.close()

    async def update_stats(
        self,
        identity_id: uuid.UUID,
        success: bool,
        ban_hit: bool = False,
    ) -> None:
        """Update identity success rate with exponential moving average."""
        current = await self.get(identity_id)
        if not current:
            return
        alpha = 0.1
        new_rate = current.success_rate
        if success:
            new_rate = current.success_rate * (1 - alpha) + alpha * 1.0
        else:
            new_rate = current.success_rate * (1 - alpha) + alpha * 0.0

        ban_score = current.ban_score
        if ban_hit:
            ban_score = min(1.0, ban_score + 0.1)

        await self.repo.update(current, success_rate=new_rate, ban_score=ban_score)
