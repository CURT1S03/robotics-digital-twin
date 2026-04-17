"""Mock ROS 2 pub/sub layer.

Provides a lightweight asyncio-based pub/sub system that mirrors standard
rclpy semantics (Node, Publisher, Subscription, Timer) without requiring a
ROS 2 installation.

Usage::

    from ros_mock import Node, registry
    from ros_mock.messages import OdometryMsg

    class PosePublisher(Node):
        def __init__(self):
            super().__init__("pose_publisher")
            self._pub = self.create_publisher("/dt/odometry")
            self.create_timer(0.1, self._publish_pose)

        def _publish_pose(self):
            self._pub.publish(OdometryMsg(x=1.0, y=2.0))
"""

from ros_mock.topic import TopicRegistry, registry
from ros_mock.node import Node, Publisher, Subscription, Timer
from ros_mock import messages

__all__ = [
    "Node",
    "Publisher",
    "Subscription",
    "Timer",
    "TopicRegistry",
    "registry",
    "messages",
]
