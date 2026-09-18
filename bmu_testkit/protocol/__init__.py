# -*- coding: utf-8 -*-
"""L2 指令层 —— 「现在这套指令格式」的唯一归属地。

换协议时只改这里，L1 transport 不动。
"""

from .ycyk422 import (
    Ycyk422Protocol,
    HEARTBEAT_CMD,
    HEARTBEAT_ACK,
    RESPONSE_LABELS,
)

__all__ = [
    "Ycyk422Protocol",
    "HEARTBEAT_CMD",
    "HEARTBEAT_ACK",
    "RESPONSE_LABELS",
]
