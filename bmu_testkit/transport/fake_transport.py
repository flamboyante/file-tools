# -*- coding: utf-8 -*-
"""假串口通道（自测用，无需硬件）。

按 422 协议的真实应答形状回应：begin 请求 → `1A CF ... 5A`，
数据帧 → `8A`，结束帧 → `BB`。用于在没有 BMU 硬件时验证镜像层与
监视窗口链路是否通。

应答帧按实测样本构造（12/13 字节，帧头 `1A CF`，末两字节为校验和）：

    心跳应答     1A CF 01 87 C0 00 00 01 00 1F FE 97
    begin 应答   1A CF 01 87 C0 07 00 02 01 5A 00 FE 53
    finish 应答  1A CF 01 87 C0 06 00 02 01 BB 00 FD F3
"""

import time

from .base import Transport


def _checksum(body: bytes) -> int:
    """422 校验和：从 index 2 起逐字节累加 → 取反 → 低 16 位（大端）。"""
    acc = 0
    for b in body:
        acc += b
    return (~acc) & 0xFFFF


def _make_ack(type_code: int, seq: int = 0x00) -> bytes:
    """构造一个 13 字节应答帧（数据域 3 字节）。"""
    frame = bytearray([0x1A, 0xCF, 0x01, 0x87, 0xC0, seq, 0x00, 0x02,
                       0x01, type_code, 0x00])
    cs = _checksum(frame[2:])
    frame.append((cs >> 8) & 0xFF)
    frame.append(cs & 0xFF)
    return bytes(frame)


class FakeTransport(Transport):
    """内存里的假串口：按请求帧类型返回对应应答。"""

    # 请求帧特征（下标 8、9）→ 应答类型码，按实测帧布局判定
    #   begin  eb 90 01 80 c0 00 00 10 [01 55] ...     → 0x5A
    #   finish eb 90 01 80 c0 xx 00 01 [01 AA]         → 0xBB
    #   data   eb 90 01 8f 4x xx 0x?? [00 03] ...      → 0x8A
    _REQ_SIGNATURES = {
        (0x01, 0x55): 0x5A,
        (0x01, 0xAA): 0xBB,
    }

    def __init__(self, name: str = "FAKE", latency: float = 0.01,
                 fail_at: int = 0):
        super().__init__(name=name)
        self.latency = latency
        self.fail_at = fail_at          # 第 N 次应答返回异常结果码（0 = 不注入）
        self._buf = bytearray()
        self._rx_count = 0
        self._opened = False
        self._seq = 0

    @property
    def is_open(self) -> bool:
        return self._opened

    def open(self):
        self._opened = True

    def close(self):
        self._opened = False

    def write(self, data: bytes) -> int:
        if not self._opened:
            raise IOError("通道未打开")
        self._rx_count += 1
        if self.latency:
            time.sleep(self.latency)
        # 判定请求类型：按实测帧布局的特征字节
        sig = (data[8], data[9]) if len(data) >= 10 else (0, 0)
        type_code = self._REQ_SIGNATURES.get(sig, 0x8A)
        ack = bytearray(_make_ack(type_code))
        if self.fail_at and self._rx_count == self.fail_at:
            ack[10] = 0xFF          # 注入异常结果码
        self._seq = (self._seq + 1) & 0xFF
        ack[5] = self._seq
        self._buf += ack
        return len(data)

    def read_some(self, timeout=None) -> bytes:
        if not self._buf:
            if timeout:
                time.sleep(min(timeout, 0.02))
            return b""
        # 模拟真实串口：一次只返回一个应答帧（按帧头切分）
        head = self._buf.find(b"\x1A\xCF", 2)
        if head < 0:
            out = bytes(self._buf)
            self._buf.clear()
            return out
        out = bytes(self._buf[:head])
        del self._buf[:head]
        return out

    def drain_input(self) -> int:
        n = len(self._buf)
        self._buf.clear()
        return n

    def describe(self) -> str:
        return "FAKE (自测用假串口)"
