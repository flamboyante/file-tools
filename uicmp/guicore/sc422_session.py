# -*- coding: utf-8 -*-
"""sc422_session · SC 422 口原始 hex 收发会话（含定时重复发送）。

职责边界（刻意窄）：
- 只管「原始字节」：hex 文本解析、发送、定时重复、计数
- **不做协议解析**——本页定位是通用 hex 调试台，不预设 422 帧结构
- 视图格式化（hex / ascii）做成纯函数，便于单测与复用到其他页

ascii 口径沿用观测层（bmu_testkit/AGENT_INTERFACE.md §4.5）：
只放行 0x20~0x7E 与 TAB，其余（含 \\r \\n 与高位字节）一律显示 `.`。

SC 422 通道参数（实测）：921600 8O1 —— 由 ConnectionBar 预设负责，
本模块不硬编码串口参数。
"""
import re
import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

_STRIP = re.compile(r'\s+')
_BAD = re.compile(r'[^0-9a-fA-F]')


# ---------------------------------------------------------------- 纯函数
def parse_hex(text):
    """宽松解析 hex 文本 → bytes。

    容忍：空格/换行/制表符分隔、`0x` 前缀、大小写混合。
    非容忍（抛 ValueError，带人话原因）：空、非法字符、奇数位。
    """
    s = text or ''
    s = s.replace('0x', '').replace('0X', '')
    s = _STRIP.sub('', s)
    if not s:
        raise ValueError('内容为空')
    bad = sorted(set(_BAD.findall(s)))
    if bad:
        raise ValueError('含非法字符 %s' % ' '.join(bad))
    if len(s) % 2:
        raise ValueError('十六进制位数需为偶数（当前 %d 位）' % len(s))
    return bytes.fromhex(s)


def format_hex(data):
    return ' '.join('%02X' % b for b in data)


def format_ascii(data):
    """ascii 视图口径：只放行 0x20~0x7E 与 TAB，其余显示 '.'（逐字节判定）。"""
    return ''.join(chr(b) if (0x20 <= b <= 0x7E or b == 0x09) else '.'
                   for b in data)


def now_stamp():
    """毫秒级时间戳 'HH:MM:SS.mmm'。"""
    t = time.time()
    lt = time.localtime(t)
    return '%02d:%02d:%02d.%03d' % (lt.tm_hour, lt.tm_min, lt.tm_sec,
                                    int((t - int(t)) * 1000))


# ---------------------------------------------------------------- 会话
class Sc422Session(QObject):
    """原始收发会话：发送 / 定时重复 / 计数。

    信号：
        sent(bytes)      已入发送队列（UI 据此记 TX 行）
        failed(str)      解析失败 / 链路未打开 / 链路异常（UI 记错误行）
        timer_state(bool) 定时器开或关
    """

    sent = pyqtSignal(bytes)
    failed = pyqtSignal(str)
    timer_state = pyqtSignal(bool)

    MIN_INTERVAL_MS = 10        # 定时下限，防手滑填 0 打爆链路

    def __init__(self, link, parent=None):
        super(Sc422Session, self).__init__(parent)
        self._link = link
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._provider = None
        self.sent_count = 0
        link.error.connect(self.failed)

    @property
    def link(self):
        return self._link

    @property
    def is_timing(self):
        return self._timer.isActive()

    @property
    def interval_ms(self):
        return self._timer.interval()

    # ------------------------------------------------------------ 发送
    def send_hex(self, text):
        """解析 + 发送。返回 True 表示已入队（False 时 failed 已发信号）。"""
        try:
            payload = parse_hex(text)
        except ValueError as e:
            self.failed.emit('hex 解析失败：%s' % e)
            return False
        return self.send_bytes(payload)

    def send_bytes(self, payload):
        payload = bytes(payload)
        if not payload:
            self.failed.emit('内容为空，未发送')
            return False
        # 未打开时 link.send 会 emit error（已透传到 self.failed），不再重复报
        if not self._link.send(payload):
            return False
        self.sent_count += 1
        self.sent.emit(payload)
        return True

    # ------------------------------------------------------------ 定时
    def start_timer(self, interval_ms, provider):
        """provider: 每次到点取文本的回调 —— 定时期间改输入立即生效。"""
        if not self._link.is_open:
            self.failed.emit('链路未打开，无法开始定时发送')
            return False
        try:
            interval = max(self.MIN_INTERVAL_MS, int(interval_ms))
        except (TypeError, ValueError):
            self.failed.emit('定时间隔非法：%r' % (interval_ms,))
            return False
        self._provider = provider
        self._timer.start(interval)
        self.timer_state.emit(True)
        return True

    def stop_timer(self):
        if self._timer.isActive():
            self._timer.stop()
        self._provider = None
        self.timer_state.emit(False)

    def _on_tick(self):
        # 定时期间文本可能被清空/改坏：失败只报一次原因，不中断定时
        text = self._provider() if self._provider else ''
        if text.strip():
            self.send_hex(text)
