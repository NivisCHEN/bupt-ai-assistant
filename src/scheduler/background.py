"""Background scheduler for asynchronous memory maintenance tasks.

Handles periodic memory compression, session timeout detection, and
user profile extraction following the UML "异步记忆维护 Background" design.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger

if TYPE_CHECKING:
    from src.embedding.service import EmbeddingService
    from src.memory.manager import MemoryManager


class BackgroundScheduler:
    """Runs periodic memory maintenance jobs in the background.

    Jobs registered by :meth:`setup`:
    - **Memory compression**: weekly (every 7 days) for all users.
    - **Session timeout check**: every 5 minutes.
    - **User profile extraction**: daily.
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        embedding_service: EmbeddingService,
        session_timeout: int = 1800,
    ) -> None:
        """Initialise the background scheduler.

        Args:
            memory_manager: The high-level memory manager facade.
            embedding_service: Service for computing text embeddings.
            session_timeout: Seconds of inactivity before a session is
                considered timed-out (default 1800 = 30 min).
        """
        self.memory_manager = memory_manager
        self.embedding_service = embedding_service
        self.session_timeout: int = session_timeout

        self._scheduler = AsyncIOScheduler()

        # Tracks active sessions: user_id -> last activity unix timestamp
        self.active_sessions: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def setup(self) -> None:
        """Register all recurring jobs with the scheduler."""

        # Weekly memory compression (every 7 days)
        self._scheduler.add_job(
            self.run_weekly_compression,
            "interval",
            days=7,
            id="weekly_compression",
            name="Weekly memory compression",
            replace_existing=True,
        )

        # Session timeout check (every 5 minutes)
        self._scheduler.add_job(
            self.check_session_timeouts,
            "interval",
            minutes=5,
            id="session_timeout_check",
            name="Session timeout check",
            replace_existing=True,
        )

        # Daily user profile extraction
        self._scheduler.add_job(
            self.run_daily_profile_extraction,
            "interval",
            days=1,
            id="daily_profile_extraction",
            name="Daily user profile extraction",
            replace_existing=True,
        )

        logger.info("Background scheduler jobs registered")

    # ------------------------------------------------------------------
    # Memory maintenance (per-user)
    # ------------------------------------------------------------------

    async def run_memory_maintenance(self, user_id: str) -> dict:
        """Run a full memory maintenance cycle for a single user.

        Follows the UML flow:
        1. Get today's conversations from the memory store.
        2. Extract user profile from those conversations.
        3. Compute an embedding for the profile summary.
        4. Update the user's FAISS index.

        Args:
            user_id: The target user.

        Returns:
            A stats dict describing what was done.
        """
        logger.info("Running memory maintenance for user {}", user_id)

        try:
            # Step 1: Get today's conversations
            from src.models import MemoryType

            conversations = self.memory_manager.store.get_all_memories(
                user_id, MemoryType.SHORT_TERM
            )
            conversation_count = len(conversations)

            if conversation_count == 0:
                logger.debug("No conversations found for user {}, skipping", user_id)
                return {
                    "user_id": user_id,
                    "conversations_processed": 0,
                    "profile_updated": False,
                    "index_rebuilt": False,
                }

            # Step 2: Extract user profile
            profile = await self.memory_manager.extract_user_profile(
                user_id, conversations
            )
            profile_summary = profile.get("summary", "")

            # Step 3: Get embedding for the profile summary
            profile_updated = False
            if profile_summary:
                _embedding = self.embedding_service.encode([profile_summary])
                profile_updated = True
                logger.debug(
                    "Computed profile embedding for user {} (dim={})",
                    user_id,
                    _embedding.shape[-1] if _embedding.size > 0 else 0,
                )

            # Step 4: Rebuild user FAISS index
            self.memory_manager.store._build_user_index(user_id)
            logger.info("FAISS index rebuilt for user {}", user_id)

            stats = {
                "user_id": user_id,
                "conversations_processed": conversation_count,
                "profile_updated": profile_updated,
                "profile_summary": profile_summary[:200] if profile_summary else "",
                "index_rebuilt": True,
            }
            logger.info("Memory maintenance complete for user {}: {}", user_id, stats)
            return stats

        except Exception:
            logger.exception("Memory maintenance failed for user {}", user_id)
            return {
                "user_id": user_id,
                "conversations_processed": 0,
                "profile_updated": False,
                "index_rebuilt": False,
                "error": True,
            }

    # ------------------------------------------------------------------
    # Session timeout check
    # ------------------------------------------------------------------

    async def check_session_timeouts(self) -> None:
        """Check all active sessions and trigger maintenance for timed-out ones.

        A session is considered timed-out when the elapsed time since the
        last activity exceeds :attr:`session_timeout` seconds.
        """
        now = time.time()
        timed_out_users: list[str] = []

        for user_id, last_activity in list(self.active_sessions.items()):
            if now - last_activity > self.session_timeout:
                timed_out_users.append(user_id)

        if not timed_out_users:
            return

        logger.info(
            "Detected {} timed-out sessions, running maintenance",
            len(timed_out_users),
        )

        for user_id in timed_out_users:
            try:
                await self.run_memory_maintenance(user_id)
            except Exception:
                logger.exception(
                    "Maintenance after session timeout failed for user {}", user_id
                )
            finally:
                # Remove from active sessions regardless of success
                self.active_sessions.pop(user_id, None)

    # ------------------------------------------------------------------
    # Weekly compression
    # ------------------------------------------------------------------

    async def run_weekly_compression(self) -> None:
        """Run memory compression for all known users.

        Iterates over every user that has stored memories and triggers
        the full :meth:`MemoryManager.run_maintenance` cycle.
        """
        all_user_ids = list(self.memory_manager.store._memories.keys())
        logger.info(
            "Starting weekly compression for {} users", len(all_user_ids)
        )

        for user_id in all_user_ids:
            try:
                stats = await self.memory_manager.run_maintenance(user_id)
                logger.info(
                    "Weekly compression for user {}: {}", user_id, stats
                )
            except Exception:
                logger.exception(
                    "Weekly compression failed for user {}", user_id
                )

    # ------------------------------------------------------------------
    # Daily profile extraction
    # ------------------------------------------------------------------

    async def run_daily_profile_extraction(self) -> None:
        """Extract and update user profiles for all known users."""
        all_user_ids = list(self.memory_manager.store._memories.keys())
        logger.info(
            "Starting daily profile extraction for {} users",
            len(all_user_ids),
        )

        for user_id in all_user_ids:
            try:
                await self.run_memory_maintenance(user_id)
            except Exception:
                logger.exception(
                    "Daily profile extraction failed for user {}", user_id
                )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background scheduler."""
        self.setup()
        self._scheduler.start()
        logger.info("Background scheduler started")

    def stop(self) -> None:
        """Shut down the background scheduler gracefully."""
        self._scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")

    # ------------------------------------------------------------------
    # Session tracking helpers
    # ------------------------------------------------------------------

    def touch_session(self, user_id: str) -> None:
        """Update the last activity timestamp for a user session.

        Args:
            user_id: The user whose session is being refreshed.
        """
        self.active_sessions[user_id] = time.time()
