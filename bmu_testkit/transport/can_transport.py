# -*- coding: utf-8 -*-
"""CAN 传输实现（L1）—— 包装 JiangCan_Tools.ECAN（ctypes 调 ECanVci64.dll）。

CAN 与串口不同：它是**帧**设备，每帧最多 8 字节数据、带 29 位 ID。
因此本类提供两套接口：

  1. Transport 字节流接口（write / read_some）—— 复用默认 ID，自动按 8 字节切分，
     满足 L1「能发任意字节流」的通用约定
  2. CAN 帧级接口（send_frame / recv_frame）—— 需要指定 ID 时用这个，
     上层 L2 指令层构造 CAN ID 后走这条路

注意：ECAN 的 is_open / dll 是**类属性**（整卡共享），两条通道共用一个设备句柄。
"""

import os
import sys
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from JiangCan_Tools.ECAN import (  # noqa: E402
    CAN_OBJ,
    ECAN,
    BaudRate,
    Channel1,
    Channel2,
    STATUS_OK,
)

from .base import Transport

DEFAULT_DLL = os.path.join(_ROOT, "dist", "Can_Frame_Deal", "ECanVci64.dll")
MAX_FRAME_DATA = 8          # CAN 单帧最大数据长度
POLL_INTERVAL = 0.002       # 接收轮询间隔（秒）
# 发送超时：实测底层 Transmit 在总线无 ACK 时会**永久阻塞**，必须有兜底
DEFAULT_TX_TIMEOUT = 2.0


class CanMedia(Transport):
    """CAN 通道。channel 0 = CAN A，1 = CAN B。"""

    def __init__(self, channel: int = 0, baud=BaudRate.BAUD_500K,
                 dll_path: str = None, dev_type: int = 0, dev_index: int = 0,
                 default_id: int = 0, name: str = ""):
        super().__init__(name=name or f"CAN{channel}")
        self.channel = Channel1 if channel == 0 else Channel2
        self.channel_idx = channel
        self.baud = baud
        self.dll_path = dll_path or DEFAULT_DLL
        self.dev_type = dev_type
        self.dev_index = dev_index
        self.default_id = default_id     # 字节流接口（write）使用的 ID
        self.dev = None

    @property
    def is_open(self) -> bool:
        return bool(ECAN.is_open and self.dev is not None)

    def open(self):
        if not os.path.isfile(self.dll_path):
            raise FileNotFoundError(f"CAN DLL 不存在: {self.dll_path}")
        if not ECAN.is_open:
            ECAN.open(self.dev_type, self.dev_index, self.dll_path)
            if not ECAN.is_open:
                raise IOError("CAN 设备打开失败（OpenDevice 未返回成功）")
        self.dev = ECAN(self.channel)
        if not self.dev.config(self.baud):
            raise IOError(f"CAN 通道 {self.channel_idx} 初始化失败（InitCAN）")
        if not self.dev.start():
            raise IOError(f"CAN 通道 {self.channel_idx} 启动失败（StartCAN）")

    def close(self):
        # ECAN 是类级设备句柄，这里关闭整卡
        if ECAN.is_open:
            ECAN.close()
        self.dev = None

    # ---------- 帧级接口（CAN 特有） ----------
    def send_frame(self, can_id: int, data: bytes, extern: bool = True,
                   remote: bool = False, send_type: int = 0,
                   timeout: float = DEFAULT_TX_TIMEOUT) -> bool:
        """发送一帧。data 不超过 8 字节。

        send_type（CAN_OBJ.SendType）：
            0 正常发送（无节点应答时会一直重发，可能阻塞）
            1 单次发送（不自动重发 —— 总线无节点时用它可避免卡死）
            2 自发自收（自检用）
            3 单次自发自收（自检用，推荐，不需要外部节点）

        ⚠️ 实测：底层 Transmit 在总线异常（无 ACK）时会**永久阻塞不返回**。
        这里用线程包一层做超时兜底，超时返回 False，绝不把调用方挂死。
        """
        if len(data) > MAX_FRAME_DATA:
            raise ValueError(
                f"CAN 单帧最多 {MAX_FRAME_DATA} 字节，实际 {len(data)}")
        obj = CAN_OBJ()
        obj.ID = int(can_id)
        obj.DataLen = len(data)
        for i, b in enumerate(data):
            obj.data[i] = b
        obj.RemoteFlag = 1 if remote else 0
        obj.ExternFlag = 1 if extern else 0
        obj.SendType = int(send_type)

        box = {}

        def _tx():
            try:
                box["ret"] = self.dev.transmit(obj)
            except Exception as e:      # pragma: no cover - 取决于 DLL 行为
                box["err"] = e

        t = threading.Thread(target=_tx, daemon=True)
        t.start()
        t.join(timeout)
        if t.is_alive():
            # 超时：线程无法强杀，但它是 daemon，进程退出时随之结束
            return False
        if "err" in box:
            raise box["err"]
        return box.get("ret") == STATUS_OK

    def recv_frame(self, timeout=None, max_frames: int = 50):
        """接收帧，返回 [(id, data), ...]；超时或无数据返回空列表。"""
        started = time.monotonic()
        deadline = None if timeout is None else started + timeout
        while True:
            frames = self._poll(max_frames)
            if frames:
                n = sum(len(d) for _fid, d in frames)
                self.stats.record(time.monotonic() - started, n)
                return frames
            if deadline is not None and time.monotonic() >= deadline:
                self.stats.record(time.monotonic() - started, 0)
                return []
            time.sleep(POLL_INTERVAL)

    def _poll(self, max_frames: int = 50):
        length, objs, ret = self.dev.receive(max_frames)
        if ret is None or ret <= 0:
            return []
        out = []
        for i in range(min(ret, length)):
            o = objs[i]
            n = min(int(o.DataLen), MAX_FRAME_DATA)
            out.append((int(o.ID), bytes(bytearray(o.data[:n]))))
        return out

    def get_err_info(self) -> str:
        try:
            return self.dev.get_err_info()
        except Exception as e:
            return f"(读取错误失败: {e})"

    # ---------- Transport 字节流接口（复用默认 ID） ----------
    def write(self, data: bytes, timeout: float = DEFAULT_TX_TIMEOUT) -> int:
        """按 8 字节自动切分成多帧发送，返回已发送字节数。

        需要指定 ID 时请直接用 send_frame()。
        """
        total = 0
        for i in range(0, len(data), MAX_FRAME_DATA):
            chunk = data[i:i + MAX_FRAME_DATA]
            if not self.send_frame(self.default_id, chunk, timeout=timeout):
                break
            total += len(chunk)
        return total

    def read_some(self, timeout=None) -> bytes:
        """读一批帧，把各帧数据拼接成字节流返回。"""
        started = time.monotonic()
        frames = self.recv_frame(timeout=timeout)
        if not frames:
            self.stats.record(time.monotonic() - started, 0)
            return b""
        buf = bytearray()
        for _fid, data in frames:
            buf += data
        self.stats.record(time.monotonic() - started, len(buf))
        return bytes(buf)

    def describe(self) -> str:
        return f"{self.name} @ {self.baud.name} (dll={os.path.basename(self.dll_path)})"
