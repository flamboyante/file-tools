# -*- coding: utf-8 -*-
"""串口传输实现（L1）。

现场实测参数（用户 2026-09-17 确认）：
    BMU debug : 115200, 8 数据位, 无校验, 1 停止位
    self 422  : 921600, 8 数据位, 奇校验, 1 停止位
    SC 422    : 921600, 8 数据位, 奇校验, 1 停止位
"""

import time

import serial

from .base import Transport


# 内核读超时（秒）：只在 open() 时设定一次，之后**永不修改**。
# 为什么固定不改：pyserial 的 `SerialBase.timeout` setter 在 `is_open` 为真时
# 会调用 `_reconfigure_port()`；在 Windows 上它会对已打开的句柄重新
# `SetCommState`。设备被拔掉 / 复位重枚举（STLink、BL 跳 App）时，该调用会抛
# `SerialException: PermissionError(13, '连到系统上的设备没有发挥作用。')`。
# 更隐蔽的是：即使设备健在，反复重配也会给收发引入时序抖动 ——
# 对一个以"观测真实时序"为目标的工具来说，这本身就是污染。
# 因此读超时改由 Python 侧自行计时，pyserial 侧保持定值。
_READ_TIMEOUT = 0.05


PARITY_MAP = {
    "N": serial.PARITY_NONE,
    "O": serial.PARITY_ODD,
    "E": serial.PARITY_EVEN,
    "M": serial.PARITY_MARK,
    "S": serial.PARITY_SPACE,
}

BYTESIZE_MAP = {5: serial.FIVEBITS, 6: serial.SIXBITS,
                7: serial.SEVENBITS, 8: serial.EIGHTBITS}

STOPBITS_MAP = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE,
                2: serial.STOPBITS_TWO}


class SerialTransport(Transport):
    """串口通道。

    `timeout`（构造参数）是**上层等待语义的默认值**，由 `read_some` 自行计时实现，
    **不会**传给 pyserial —— pyserial 侧的内核读超时固定为 `_READ_TIMEOUT`。
    这样做是为了避免反复触发 `_reconfigure_port()`（详见 `_READ_TIMEOUT` 注释）。

    `timeout=None` 时阻塞等待（默认，便于观测真实耗时）。
    """

    def __init__(self, port: str, baudrate: int = 115200, bytesize: int = 8,
                 parity: str = "N", stopbits: float = 1, timeout=None,
                 name: str = ""):
        super().__init__(name=name or port)
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity.upper()
        self.stopbits = stopbits
        self.timeout = timeout
        if self.parity not in PARITY_MAP:
            raise ValueError(f"不支持的校验位: {parity}（可用 N/O/E/M/S）")
        self._ser = serial.Serial()
        self._apply_params()

    def _apply_params(self):
        self._ser.port = self.port
        self._ser.baudrate = self.baudrate
        self._ser.bytesize = BYTESIZE_MAP[self.bytesize]
        self._ser.parity = PARITY_MAP[self.parity]
        self._ser.stopbits = STOPBITS_MAP[self.stopbits]
        # 固定内核读超时，不用 self.timeout —— 超时语义由 read_some 自己实现。
        # 见文件头 _READ_TIMEOUT 的说明。
        self._ser.timeout = _READ_TIMEOUT

    @property
    def is_open(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    def open(self):
        if not self.is_open:
            self._apply_params()
            self._ser.open()

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def write(self, data: bytes) -> int:
        n = self._ser.write(data)
        self._ser.flush()
        return n

    def read_some(self, timeout=None) -> bytes:
        """读当前可用数据；无数据时按 timeout 等待（None = 阻塞）。

        超时由本方法自行计时，**全程不修改 `self._ser.timeout`** ——
        否则每次循环都会触发 pyserial 的 `_reconfigure_port()`，
        设备重枚举时会抛 PermissionError（详见文件头 `_READ_TIMEOUT` 说明）。

        内核侧超时为定值 `_READ_TIMEOUT`：先阻塞等 1 字节，等到就一次性
        把缓冲区里其余字节全部取走，减少上层循环次数。
        """
        if timeout is not None and timeout <= 0:
            timeout = None                          # 负值/0 统一按"等到有"处理
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            first = self._ser.read(1)               # 阻塞至多 _READ_TIMEOUT
            if first:
                waiting = self._ser.in_waiting or 0
                return first + self._ser.read(waiting) if waiting else first
            if deadline is None:
                continue
            if time.monotonic() >= deadline:
                return b""

    def drain_input(self) -> int:
        """丢弃输入缓冲区里的残留数据，返回丢弃的字节数。"""
        n = self._ser.in_waiting or 0
        if n:
            self._ser.reset_input_buffer()
        return n

    def describe(self) -> str:
        return (f"{self.port} @ {self.baudrate} "
                f"{self.bytesize}{self.parity}{self.stopbits}")
