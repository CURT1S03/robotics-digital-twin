"""Tests for the mock ROS 2 pub/sub layer."""

from __future__ import annotations

import asyncio

import pytest

from ros_mock.topic import TopicRegistry
from ros_mock.node import Node, Publisher
from ros_mock.messages import OdometryMsg, PerformanceMetricsMsg


# ─── TopicRegistry ──────────────────────────────────────────────────────────── #

def test_registry_creates_topic():
    reg = TopicRegistry()
    topic = reg.get_or_create("/dt/odometry")
    assert topic.name == "/dt/odometry"


def test_registry_returns_same_topic():
    reg = TopicRegistry()
    a = reg.get_or_create("/dt/test")
    b = reg.get_or_create("/dt/test")
    assert a is b


def test_registry_clear():
    reg = TopicRegistry()
    reg.get_or_create("/dt/foo")
    reg.clear()
    assert reg.list_topics() == []


# ─── Topic pub/sub ──────────────────────────────────────────────────────────── #

@pytest.mark.asyncio
async def test_single_subscriber_receives_message():
    reg = TopicRegistry()
    topic = reg.get_or_create("/test/single")
    queue = topic.subscribe()

    msg = OdometryMsg(x=1.0, y=2.0)
    topic.publish(msg)

    received = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert received.x == 1.0
    assert received.y == 2.0


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_message():
    reg = TopicRegistry()
    topic = reg.get_or_create("/test/multi")
    q1 = topic.subscribe()
    q2 = topic.subscribe()

    topic.publish(OdometryMsg(x=5.0))

    r1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    r2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert r1.x == 5.0
    assert r2.x == 5.0


@pytest.mark.asyncio
async def test_topic_isolation():
    """Messages on one topic should not appear on another topic's queues."""
    reg = TopicRegistry()
    t1 = reg.get_or_create("/test/iso/a")
    t2 = reg.get_or_create("/test/iso/b")
    q2 = t2.subscribe()

    t1.publish(OdometryMsg(x=99.0))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(q2.get(), timeout=0.1)


def test_unsubscribe_removes_queue():
    reg = TopicRegistry()
    topic = reg.get_or_create("/test/unsub")
    q = topic.subscribe()
    assert topic.subscriber_count == 1
    topic.unsubscribe(q)
    assert topic.subscriber_count == 0


# ─── Node ───────────────────────────────────────────────────────────────────── #

class _CollectorNode(Node):
    def __init__(self):
        super().__init__("collector")
        self.received: list = []
        self.create_subscription("/test/node_topic", self._on_msg)

    def _on_msg(self, msg):
        self.received.append(msg)


@pytest.mark.asyncio
async def test_node_subscription_receives_messages():
    from ros_mock.topic import registry

    registry.clear()
    node = _CollectorNode()
    node.start()

    pub_topic = registry.get_or_create("/test/node_topic")
    pub_topic.publish(OdometryMsg(x=3.14))

    await asyncio.sleep(0.05)
    node.destroy()

    assert len(node.received) == 1
    assert node.received[0].x == pytest.approx(3.14)


@pytest.mark.asyncio
async def test_node_timer_fires():
    from ros_mock.topic import registry

    registry.clear()

    tick_count = {"n": 0}

    class TickNode(Node):
        def __init__(self):
            super().__init__("tick")
            self.create_timer(0.05, self._tick)

        def _tick(self):
            tick_count["n"] += 1

    node = TickNode()
    node.start()
    await asyncio.sleep(0.18)
    node.destroy()

    assert tick_count["n"] >= 2


# ─── Message types ──────────────────────────────────────────────────────────── #

def test_odometry_defaults():
    msg = OdometryMsg()
    assert msg.x == 0.0
    assert msg.yaw == 0.0
    assert msg.run_id == 0


def test_performance_metrics_defaults():
    msg = PerformanceMetricsMsg(run_id=5, goal_reached=True)
    assert msg.run_id == 5
    assert msg.goal_reached is True
    assert msg.collision_count == 0
