# -*- coding: utf-8 -*-
"""镜像输出端（sink）。

一个 sink 的职责只有一件：拿到事件就输出，输出失败就静默。
**任何 sink 异常都不允许影响串口业务** —— 观察是旁路，不是链路的一部分。

事件负载统一为一行 UTF-8 文本（`parse_event()` 负责反向解析），因此
文件与 UDP 用同一份格式化逻辑，监视窗口只需实现一次解析。
"""

import json
import os
import socket
import threading
import time

# ---------- 方向 ----------
TX = "TX"
RX = "RX"


class Direction:
    """方向常量（用类而非 Enum，便于窗口侧直接比较字符串）。"""

    TX = TX
    RX = RX


def format_event(direction: str, data: bytes, note: str = "", source: str = "",
                 elapsed: float = None) -> str:
    """把一次收发格式化成一行事件文本。

    采用 JSON 行（JSONL）：字段固定，窗口解析不依赖分隔符，
    且天然容纳字符串内的任意字符（HEX 带空格、note 含中文）。
    """
    obj = {
        "ts": time.strftime("%H:%M:%S") + ".%03d" % (time.time() % 1 * 1000),
        "wall": time.time(),
        "dir": direction,
        "n": len(data),
        "hex": data.hex(" "),
        "src": source,
    }
    if note:
        obj["note"] = note
    if elapsed is not None:
        obj["elapsed"] = round(elapsed, 4)
    return json.dumps(obj, ensure_ascii=False)


def parse_event(line: str) -> dict:
    """把一行事件文本解析回 dict；非事件行返回 None。"""
    line = (line or "").strip()
    if not line or not line.startswith("{"):
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) and "dir" in obj else None


class Sink:
    """输出端基类。`emit()` 由镜像层调用，**绝不允许抛异常**。"""

    def emit(self, line: str):
        raise NotImplementedError

    def close(self):
        pass


class FileSink(Sink):
    """追加写入日志文件（UTF-8，每行一个事件）。

    用行缓冲 + 显式 flush，保证 agent 进程还在跑时，人用编辑器
    打开文件也能看到最新内容。
    """

    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = open(path, "a", encoding="utf-8")

    def emit(self, line: str):
        with self._lock:
            self._fh.write(line + "\n")
            self._fh.flush()

    def close(self):
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass


class UdpSink(Sink):
    """把事件以 UDP 包发到本机端口，供独立的监视窗口实时接收。

    UDP 是无连接的：窗口没开时包直接丢弃，不报错、不阻塞。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 39527):
        self.addr = (host, port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def emit(self, line: str):
        self._sock.sendto(line.encode("utf-8", "replace"), self.addr)

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


class NullSink(Sink):
    """丢弃一切（用于不需要输出时占位）。"""

    def emit(self, line: str):
        pass
