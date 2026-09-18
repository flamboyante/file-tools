# -*- coding: utf-8 -*-
"""串口传输实现（L1）。

现场实测参数（用户 2026-09-17 确认）：
    BMU debug : 115200, 8 数据位, 无校验, 1 停止位
    self 422  : 921600, 8 数据位, 奇校验, 1 停止位
    SC 422    : 921600, 8 数据位, 奇校验, 1 停止位
"""

import serial

from .base import Transport


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
    """串口通道。timeout=None 时阻塞等待（默认，便于观测真实耗时）。"""

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
        self._ser.timeout = self.timeout

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
        """读当前可用数据；无数据时按 timeout 等待（None = 阻塞）。"""
        old = self._ser.timeout
        if timeout is not None:
            self._ser.timeout = timeout
        try:
            first = self._ser.read(1)      # 阻塞到有 1 字节（或超时）
            if not first:
                return b""
            waiting = self._ser.in_waiting or 0
            if waiting:
                return first + self._ser.read(waiting)
            return first
        finally:
            if timeout is not None:
                self._ser.timeout = old

    def drain_input(self) -> int:
        """丢弃输入缓冲区里的残留数据，返回丢弃的字节数。"""
        n = self._ser.in_waiting or 0
        if n:
            self._ser.reset_input_buffer()
        return n

    def describe(self) -> str:
        return (f"{self.port} @ {self.baudrate} "
                f"{self.bytesize}{self.parity}{self.stopbits}")
