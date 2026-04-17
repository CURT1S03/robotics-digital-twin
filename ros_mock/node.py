"""Base Node class mimicking the rclpy.node.Node interface.

Provides ``create_publisher``, ``create_subscription``, and ``create_timer``
exactly as rclpy does, backed by the asyncio-based ``TopicRegistry``.

Example::

    class OdomPublisher(Node):
        def __init__(self):
            super().__init__("odom_pub")
            self._pub = self.create_publisher("/dt/odometry")
            self.create_timer(0.05, self._tick)

        def _tick(self):
            self._pub.publish(OdometryMsg(x=1.0, y=0.5))

    node = OdomPublisher()
    node.start()          # begins timer + subscription tasks
    ...
    node.destroy()        # cancels all background tasks
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from ros_mock.topic import registry, Topic

logger = logging.getLogger(__name__)


# ── Publisher ───────────────────────────────────────────────────────────────── #

class Publisher:
    """Wraps a ``Topic`` so callers use the same API regardless of transport."""

    def __init__(self, topic: Topic) -> None:
        self._topic = topic

    def publish(self, msg: Any) -> None:
        self._topic.publish(msg)

    @property
    def topic_name(self) -> str:
        return self._topic.name


# ── Subscription ────────────────────────────────────────────────────────────── #

class Subscription:
    """Asyncio task that drains a subscriber queue and calls *callback*."""

    def __init__(self, topic: Topic, callback: Callable[[Any], None], node_name: str) -> None:
        self._queue = topic.subscribe()
        self._callback = callback
        self._task: asyncio.Task | None = None
        self._node_name = node_name
        self._topic_name = topic.name

    def start(self) -> None:
        self._task = asyncio.ensure_future(self._consume())

    async def _consume(self) -> None:
        while True:
            try:
                msg = await self._queue.get()
                try:
                    self._callback(msg)
                except Exception:
                    logger.exception(
                        "[%s] callback raised on topic '%s'",
                        self._node_name,
                        self._topic_name,
                    )
            except asyncio.CancelledError:
                break

    def destroy(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        # Return the queue slot to the topic
        # (topic lookup done via registry if needed — omit for simplicity)


# ── Timer ────────────────────────────────────────────────────────────────────── #

class Timer:
    """Fixed-period asyncio timer that calls *callback* every *period* seconds."""

    def __init__(self, period: float, callback: Callable[[], None], node_name: str) -> None:
        self._period = period
        self._callback = callback
        self._task: asyncio.Task | None = None
        self._node_name = node_name

    def start(self) -> None:
        self._task = asyncio.ensure_future(self._loop())

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._period)
                try:
                    self._callback()
                except Exception:
                    logger.exception("[%s] timer callback raised", self._node_name)
            except asyncio.CancelledError:
                break

    def cancel(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    def destroy(self) -> None:
        self.cancel()


# ── Node ─────────────────────────────────────────────────────────────────────── #

class Node:
    """Base class mirroring ``rclpy.node.Node``.

    Subclasses call ``create_publisher``, ``create_subscription``, and
    ``create_timer`` in ``__init__``, then ``start()`` to activate.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._publishers: list[Publisher] = []
        self._subscriptions: list[Subscription] = []
        self._timers: list[Timer] = []
        self._started = False

    # ── Properties ─────────────────────────────────────────────────────── #

    @property
    def name(self) -> str:
        return self._name

    # ── Factory helpers ─────────────────────────────────────────────────── #

    def create_publisher(self, topic_name: str) -> Publisher:
        """Create a publisher on *topic_name* (topic is created if absent)."""
        topic = registry.get_or_create(topic_name)
        pub = Publisher(topic)
        self._publishers.append(pub)
        return pub

    def create_subscription(
        self, topic_name: str, callback: Callable[[Any], None]
    ) -> Subscription:
        """Subscribe to *topic_name*; *callback* is invoked for every message."""
        topic = registry.get_or_create(topic_name)
        sub = Subscription(topic, callback, self._name)
        self._subscriptions.append(sub)
        return sub

    def create_timer(self, period: float, callback: Callable[[], None]) -> Timer:
        """Create a periodic timer with *period* seconds between calls."""
        timer = Timer(period, callback, self._name)
        self._timers.append(timer)
        return timer

    # ── Lifecycle ───────────────────────────────────────────────────────── #

    def start(self) -> None:
        """Activate all subscriptions and timers."""
        if self._started:
            return
        self._started = True
        for sub in self._subscriptions:
            sub.start()
        for timer in self._timers:
            timer.start()
        logger.info(
            "Node '%s' started (%d sub(s), %d timer(s))",
            self._name,
            len(self._subscriptions),
            len(self._timers),
        )

    def destroy(self) -> None:
        """Cancel all background asyncio tasks belonging to this node."""
        for sub in self._subscriptions:
            sub.destroy()
        for timer in self._timers:
            timer.destroy()
        self._started = False
        logger.info("Node '%s' destroyed", self._name)
