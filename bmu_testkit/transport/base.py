# -*- coding: utf-8 -*-
"""L1 传输层抽象 —— 只搬运 bytes，不认识任何协议。"""

import time
from abc import ABC, abstractmethod


class TransportError(Exception):
    """传输层基础异常。"""


class TransportTimeout(TransportError):
    """等待超时。

    刻意携带 partial 与 elapsed：排查现场问题时要知道「等了多久、已经收到了什么」，
    而不是只看到一句 timeout。
    """

    def __init__(self, message, partial: bytes = b"", elapsed: float = 0.0,
                 expected: int = 0):
        super().__init__(message)
        self.partial = partial
        self.elapsed = elapsed
        self.expected = expected

    def __str__(self):
        return (f"{super().__str__()} (等了 {self.elapsed:.3f}s, "
                f"已收 {len(self.partial)}/{self.expected} 字节, "
                f"partial={self.partial.hex(' ')})")


class WaitStats:
    """等待耗时统计 —— 用于「历史计时」与问题定位。"""

    def __init__(self):
        self.wait_count = 0        # 等待次数（每次 read 算一次）
        self.total_wait = 0.0      # 累计等待秒数
        self.max_wait = 0.0        # 单次最长等待
        self.bytes_read = 0        # 累计读到的字节数

    def record(self, elapsed: float, nbytes: int):
        self.wait_count += 1
        self.total_wait += elapsed
        self.max_wait = max(self.max_wait, elapsed)
        self.bytes_read += nbytes

    @property
    def avg_wait(self) -> float:
        return self.total_wait / self.wait_count if self.wait_count else 0.0

    def as_dict(self):
        return {
            "wait_count": self.wait_count,
            "total_wait_s": round(self.total_wait, 4),
            "max_wait_s": round(self.max_wait, 4),
            "avg_wait_s": round(self.avg_wait, 4),
            "bytes_read": self.bytes_read,
        }

    def __str__(self):
        return (f"等待 {self.wait_count} 次 / 累计 {self.total_wait:.3f}s / "
                f"最长 {self.max_wait:.3f}s / 均值 {self.avg_wait:.3f}s / "
                f"{self.bytes_read} 字节")


class Transport(ABC):
    """任意字节流通道。

    timeout 语义：
        None  -> 一直等（默认）。用户要求先不设超时，以便观察真实耗时与发现问题。
        数值  -> 最多等这么多秒，超时抛 TransportTimeout。
    """

    def __init__(self, name: str = ""):
        self.name = name
        self.stats = WaitStats()

    @property
    @abstractmethod
    def is_open(self) -> bool:
        ...

    @abstractmethod
    def open(self):
        ...

    @abstractmethod
    def close(self):
        ...

    @abstractmethod
    def write(self, data: bytes) -> int:
        """发送任意字节流，返回实际发出字节数。"""

    @abstractmethod
    def read_some(self, timeout=None) -> bytes:
        """读当前可用的数据；没有则等到有（或超时）。不保证读满多少。"""

    def read_exact(self, n: int, timeout=None) -> bytes:
        """读满 n 字节；超时抛 TransportTimeout（带 partial 与耗时）。"""
        if n <= 0:
            return b""
        buf = bytearray()
        deadline = None if timeout is None else time.monotonic() + timeout
        started = time.monotonic()
        while len(buf) < n:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                elapsed = time.monotonic() - started
                self.stats.record(elapsed, len(buf))
                raise TransportTimeout(
                    f"read_exact 超时：期望 {n} 字节",
                    partial=bytes(buf), elapsed=elapsed, expected=n)
            chunk = self.read_some(remaining)
            if chunk:
                buf += chunk
        elapsed = time.monotonic() - started
        self.stats.record(elapsed, len(buf))
        return bytes(buf)

    def read_until_idle(self, idle: float = 0.2, max_bytes: int = 4096,
                        timeout=None) -> bytes:
        """一直读，直到「连续 idle 秒没有新数据」为止。

        不知道对端会回多长时用它最合适（比如第一次探测心跳应答）。
        """
        buf = bytearray()
        started = time.monotonic()
        deadline = None if timeout is None else started + timeout
        last_rx = started
        while len(buf) < max_bytes:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                break
            slot = idle if remaining is None else min(idle, remaining)
            chunk = self.read_some(slot)
            now = time.monotonic()
            if chunk:
                buf += chunk
                last_rx = now
            elif now - last_rx >= idle:
                break
        elapsed = time.monotonic() - started
        self.stats.record(elapsed, len(buf))
        return bytes(buf)

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
