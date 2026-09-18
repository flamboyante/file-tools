# -*- coding: utf-8 -*-
"""Console —— 给任意文本流加「等关键字」能力。

**通用机制，不含任何具体用例或业务关键字。** 关键字、超时、顺序全部由调用方给出。

## 解决什么问题

自动化判据最容易出的错不是"报错"，而是**假通过**：
若每次都从收到的全部输出里搜索关键字，那么上一次留下的打印会把这一次判成通过
（固件明明没响应，测试却亮绿灯）。

本模块用**只前进的游标**根治：

    [旧打印 A][旧打印 B]  ← 游标停在这里
                 ↑ 发出新指令
    [新打印 C]                      ← 只在这之后搜索，A/B 永远不会被再次命中

## 三个基本能力

1. `wait_for(关键字)`        —— 等一句话出现
2. `wait_for_sequence([...])` —— 按顺序等多句
3. `wait_silent(秒)`          —— 断言"这段时间内什么都不该打印"

## 用法

    c = Console(debug_transport)
    can.send(bytes.fromhex("9A1C550B"))
    if c.wait_for("[CAN]: Current Monitor Open", timeout=1.0):
        print("通过")
"""

import time
from dataclasses import dataclass


@dataclass
class Match:
    """一次命中。"""

    keyword: str
    start: int          # 在缓冲区中的起始位置
    end: int            # 结束位置（游标已推进到 end）
    elapsed: float      # 从开始等待到命中的耗时（秒）
    text: str           # 命中的那一段

    def __str__(self):
        return f"命中 {self.keyword!r} @{self.start} 用时 {self.elapsed:.3f}s"


class Console:
    """文本流的「等关键字」封装。

    transport 只需提供 `read_some(timeout) -> bytes`；也可传 None 并改用
    `feed()` 手动喂数据 —— 便于脱离硬件做离线测试。
    """

    def __init__(self, transport=None, encoding="utf-8", errors="replace",
                 max_buffer=64 * 1024, poll_interval=0.005, on_log=None):
        self.t = transport
        self.encoding = encoding
        self.errors = errors
        self.max_buffer = max_buffer
        self.poll_interval = poll_interval
        self.on_log = on_log or (lambda m: None)
        self._buf = ""
        self._cursor = 0
        self._bytes_in = 0

    # ---------------- 数据输入 ----------------
    def feed(self, text: str):
        """手动喂入文本（离线测试，或对接非串口的数据源）。"""
        if not text:
            return
        self._buf += text
        self._trim()

    def pump(self, timeout=0.0) -> int:
        """从 transport 拉一次数据，返回新增**字符**数。"""
        if self.t is None:
            return 0
        chunk = self.t.read_some(timeout)
        if not chunk:
            return 0
        self._bytes_in += len(chunk)
        text = chunk.decode(self.encoding, self.errors)
        self.feed(text)
        return len(text)

    def _trim(self):
        """缓冲过长时丢弃最老部分，并同步回退游标，避免游标越界。"""
        if len(self._buf) <= self.max_buffer:
            return
        cut = len(self._buf) - self.max_buffer
        self._buf = self._buf[cut:]
        self._cursor = max(0, self._cursor - cut)

    def _idle(self, remaining):
        """没有新数据时的小睡，避免忙等。"""
        time.sleep(self.poll_interval if remaining is None
                   else max(0.001, min(self.poll_interval, remaining)))

    # ---------------- 等待 ----------------
    def wait_for(self, keyword: str, timeout=None) -> Match:
        """等待 keyword 出现；命中返回 Match，超时返回 None。

        **只在当前游标之后搜索**，因此不会命中上一次留下的旧打印。
        """
        started = time.monotonic()
        while True:
            idx = self._buf.find(keyword, self._cursor)
            if idx >= 0:
                end = idx + len(keyword)
                self._cursor = end                      # 游标只前进
                return Match(keyword, idx, end,
                             time.monotonic() - started, self._buf[idx:end])
            remaining = None if timeout is None else timeout - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                return None
            if self.pump(self.poll_interval) == 0:
                self._idle(remaining)

    def wait_for_any(self, keywords, timeout=None) -> Match:
        """等待任意关键字出现，返回**位置最靠前**的那个。"""
        started = time.monotonic()
        while True:
            best = None
            for kw in keywords:
                idx = self._buf.find(kw, self._cursor)
                if idx >= 0 and (best is None or idx < best[0]):
                    best = (idx, kw)
            if best is not None:
                idx, kw = best
                end = idx + len(kw)
                self._cursor = end
                return Match(kw, idx, end,
                             time.monotonic() - started, self._buf[idx:end])
            remaining = None if timeout is None else timeout - (time.monotonic() - started)
            if remaining is not None and remaining <= 0:
                return None
            if self.pump(self.poll_interval) == 0:
                self._idle(remaining)

    def wait_for_sequence(self, keywords, timeout=None) -> bool:
        """按顺序等待全部关键字（各自推进游标）。全部命中返回 True。"""
        for kw in keywords:
            if self.wait_for(kw, timeout=timeout) is None:
                return False
        return True

    def wait_silent(self, duration: float) -> str:
        """等待 duration 秒，返回期间收到的新文本。

        返回**空字符串**表示这段窗口内确实没有任何输出（可用于"不该有打印"的断言）；
        非空则把不该出现的内容一并带回，便于定位。

        基准是**调用时刻的缓冲末尾**（而不是游标）—— 只统计这段窗口内新到达的内容，
        否则会把"上一次匹配后同一行的残留"误算成本次输出。
        """
        mark = len(self._buf)
        deadline = time.monotonic() + duration
        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            self.pump(min(0.02, max(0.001, deadline - now)))
        new = self._buf[mark:]
        self._cursor = len(self._buf)      # 检查完把这段视为已消费
        return new

    # ---------------- 诊断 ----------------
    def snapshot(self) -> str:
        """全部缓冲内容。"""
        return self._buf

    def unconsumed(self) -> str:
        """游标之后尚未被匹配的内容 —— 失败现场通常看它。"""
        return self._buf[self._cursor:]

    def tail(self, n: int = 500) -> str:
        return self._buf[-n:]

    def reset(self):
        """清空缓冲、游标归零。**会重新暴露旧打印**，仅在明确需要时用。"""
        self._buf = ""
        self._cursor = 0

    def rewind(self):
        """只把游标退回开头。**同样会暴露旧打印**，慎用。"""
        self._cursor = 0

    @property
    def cursor(self) -> int:
        return self._cursor

    @property
    def bytes_in(self) -> int:
        return self._bytes_in

    def __str__(self):
        return (f"Console(缓冲 {len(self._buf)} 字符, 游标 {self._cursor}, "
                f"累计收 {self._bytes_in} 字节)")
