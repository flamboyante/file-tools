# -*- coding: utf-8 -*-
"""串口流量镜像（观测层）。

把 `Transport` 包一层，收发都投一份给 sink；sink 独立于业务，
挂掉不影响通信。用于在 agent 操作串口时，人能在另一个进程里实时观察。

用法：
    from bmu_testkit.mirror import MirroredTransport, FileSink, UdpSink

    t = MirroredTransport(SerialTransport(...), sinks=[FileSink(path), UdpSink()])
"""

from .sinks import Direction, FileSink, Sink, UdpSink, parse_event
from .transport import (
    DEFAULT_UDP_PORT,
    MirroredTransport,
    attach_mirror,
    attach_mirror_custom,
)

__all__ = [
    "MirroredTransport", "attach_mirror", "attach_mirror_custom",
    "DEFAULT_UDP_PORT",
    "Sink", "FileSink", "UdpSink", "Direction", "parse_event",
]
