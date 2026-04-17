"""ROS 2-style topic registry using asyncio queues.

Each ``Topic`` is a named pub/sub channel. Subscribers receive an
``asyncio.Queue`` that is filled whenever a message is published on
that topic. Multiple subscribers are supported; each gets an independent
copy of every message.

The module-level ``registry`` singleton is the runtime hub used by all
``Node`` instances.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_QUEUE_SIZE = 256


class Topic:
    """A named pub/sub channel backed by per-subscriber asyncio queues."""

    def __init__(self, name: str, queue_size: int = _DEFAULT_QUEUE_SIZE) -> None:
        self.name = name
        self._queue_size = queue_size
        self._subscribers: list[asyncio.Queue] = []

    # ── Subscription management ─────────────────────────────────────────── #

    def subscribe(self) -> asyncio.Queue:
        """Create and register a new subscriber queue.

        Returns the queue; the caller is responsible for consuming from it.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.append(q)
        logger.debug("Topic '%s': new subscriber (total=%d)", self.name, len(self._subscribers))
        return q

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Remove a previously registered subscriber queue."""
        try:
            self._subscribers.remove(queue)
            logger.debug("Topic '%s': subscriber removed (total=%d)", self.name, len(self._subscribers))
        except ValueError:
            pass

    # ── Publishing ──────────────────────────────────────────────────────── #

    def publish(self, message: Any) -> None:
        """Deliver *message* to every subscriber queue (non-blocking).

        If a queue is full the message is dropped for that subscriber and a
        warning is logged — the publisher never blocks.
        """
        dropped = 0
        for q in self._subscribers:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                dropped += 1
        if dropped:
            logger.warning(
                "Topic '%s': dropped %d message(s) — subscriber queue(s) full",
                self.name,
                dropped,
            )

    # ── Introspection ───────────────────────────────────────────────────── #

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def __repr__(self) -> str:
        return f"<Topic '{self.name}' subscribers={self.subscriber_count}>"


class TopicRegistry:
    """Global registry — lazily creates and returns topics by name."""

    def __init__(self) -> None:
        self._topics: dict[str, Topic] = {}

    def get_or_create(self, name: str) -> Topic:
        """Return the existing topic with *name* or create it."""
        if name not in self._topics:
            self._topics[name] = Topic(name)
            logger.debug("Created topic: %s", name)
        return self._topics[name]

    def get(self, name: str) -> Topic | None:
        """Return the topic or ``None`` if it does not exist."""
        return self._topics.get(name)

    def list_topics(self) -> list[str]:
        return list(self._topics.keys())

    def clear(self) -> None:
        """Destroy all topics (useful for test isolation)."""
        self._topics.clear()

    def __repr__(self) -> str:
        return f"<TopicRegistry topics={self.list_topics()}>"


# ── Module-level singleton used by all Node instances ──────────────────────── #
registry = TopicRegistry()
