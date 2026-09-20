# -*- coding: utf-8 -*-
"""console_session · BMU debug console 会话（无渲染）。

协议细节（与旧 BmuConsoleThread 对齐，2026-09-20 核对）：
- 发送：`cmd + '\\r'`（CR 结尾，BMU shell 以回车为一行结束，不是 LF）
- 接收：原始字节流，`utf-8` + `replace` 解码成文本（console 是文本协议，
  不组帧——设备回显 + 打印输出，边界未知，用 replace 容错）

与旧实现的差异（有意为之）：
- 不用 QThread.terminate()（旧代码暴力杀线程，资源不回收）
- 不在会话层做读循环——SerialLink 的读线程已经干了，这里只订阅 rx
"""
from collections import deque

from PyQt5.QtCore import QObject, pyqtSignal

from uicmp.guicore.serial_link import SerialLink

LINE_ENDING = b'\r'          # BMU shell 行结束符
HISTORY_MAX = 100


class ConsoleSession(QObject):
    """console 会话：字节进、字节出。

    ⚠️ 会话层**不做 utf-8 解码**——原始字节原样上抛。解码/显示（文本
    还是 hex）是 UI 的展示决策：console 吐的可能是 shell 文本也可能是
    二进制日志，在 session 层 decode 会把非文本字节替换成 U+FFFD，
    hex 模式永远拿不到真字节（实测踩过：b'\\x1a\\xcf' 变成替换字符）。
    """

    received = pyqtSignal(bytes)        # 原始收字节（一段一批）
    opened = pyqtSignal()
    closed = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, link=None, parent=None):
        super(ConsoleSession, self).__init__(parent)
        self._link = link if link is not None else SerialLink()
        self._link.rx.connect(self._on_rx)
        self._link.opened.connect(self.opened)
        self._link.closed.connect(self.closed)
        self._link.error.connect(self.error)
        self._history = deque(maxlen=HISTORY_MAX)
        self._hist_idx = None           # None = 不在历史浏览态

    # ------------------------------------------------------------ 状态
    @property
    def is_open(self):
        return self._link.is_open

    @property
    def link(self):
        return self._link

    # ------------------------------------------------------------ 开 / 关
    def open(self, port, baud=115200, media=None):
        """media：测试注入口，透传给 SerialLink（生产传 None）。"""
        return self._link.open(port, baud=baud, media=media)

    def close(self):
        self._link.close()

    # ------------------------------------------------------------ 收 / 发
    def _on_rx(self, data):
        self.received.emit(bytes(data))

    def send_command(self, cmd):
        """发送一行命令（自动补 CR，进历史）。返回 False = 链路未开。"""
        if not cmd:
            return False
        if not self.is_open:
            self.error.emit('console 链路未打开')
            return False
        self._history.append(cmd)
        self._hist_idx = None
        return self._link.send(cmd.encode('utf-8') + LINE_ENDING)

    # ------------------------------------------------------------ 历史
    def history_prev(self):
        """↑：往旧翻一条。返回命令文本；到底返回 None。"""
        if not self._history:
            return None
        if self._hist_idx is None:
            self._hist_idx = len(self._history) - 1
        elif self._hist_idx > 0:
            self._hist_idx -= 1
        return self._history[self._hist_idx]

    def history_next(self):
        """↓：往新翻一条。翻出尽头返回 ''（清空输入行）。"""
        if self._hist_idx is None or not self._history:
            return None
        if self._hist_idx < len(self._history) - 1:
            self._hist_idx += 1
            return self._history[self._hist_idx]
        self._hist_idx = None
        return ''
