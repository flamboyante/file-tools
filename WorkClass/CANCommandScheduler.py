"""新 CAN 窗口的调度器与数据模型（不依赖 UI，可单测）。

指令模型：一条指令 CanCommand = 用户视角一行。
- 变长由 frames 决定（每帧一个外部给好的完整 29bit ID + 8B payload）。
- 定时发送由单一 heartbeat 到期表驱动，支持每条独立间隔(>=10ms)与次数(<=0 表示无限)。
"""
import time
import copy

MIN_INTERVAL_MS = 10
INFINITE = -1  # count 语义：<=0 表示一直发


def parse_hex_bytes(s):
    """'00 23 aa bb' 或 '0023aabb' -> list[int]；非法返回 None。"""
    if s is None:
        return None
    s = s.strip().replace(",", " ").replace("0x", "").replace("0X", "")
    if not s:
        return []
    parts = s.split()
    if len(parts) == 1 and len(parts[0]) % 2 == 0 and len(parts[0]) >= 2:
        parts = [parts[0][i:i + 2] for i in range(0, len(parts[0]), 2)]
    try:
        return [int(p, 16) for p in parts]
    except ValueError:
        return None


class CanFrame(object):
    """单个物理 CAN 帧：ID 外部提供完整值（11/29bit），数据需 <=8B。"""
    __slots__ = ("id", "data")

    def __init__(self, fid, data):
        self.id = int(fid)
        if isinstance(data, (bytes, bytearray)):
            self.data = list(data)
        else:
            self.data = list(data)
        if len(self.data) > 8:
            raise ValueError("单帧数据不能超过 8 字节")

    def to_dict(self):
        return {"id": self.id, "data": " ".join("%02X" % b for b in self.data)}

    @classmethod
    def from_dict(cls, d):
        data = parse_hex_bytes(d.get("data", ""))
        if data is None or len(data) > 8:
            raise ValueError("帧数据格式错误: %r" % (d.get("data"),))
        return cls(d["id"], data)


class CanCommand(object):
    """一条可定时发送的指令（用户视角一行）。"""

    def __init__(self, name="", channel="A", interval_ms=500, count=INFINITE,
                 enabled=False, frames=None):
        self.name = name
        self.channel = channel if channel in ("A", "B") else "A"
        self.interval_ms = max(MIN_INTERVAL_MS, int(interval_ms or 0))
        self.count = int(count) if int(count or INFINITE) > 0 else INFINITE
        self.enabled = bool(enabled)
        self.frames = frames if frames is not None else []

    @property
    def is_infinite(self):
        return self.count <= 0

    def to_dict(self):
        return {
            "name": self.name,
            "channel": self.channel,
            "interval_ms": self.interval_ms,
            "count": self.count,
            "enabled": self.enabled,
            "frames": [f.to_dict() for f in self.frames],
        }

    @classmethod
    def from_dict(cls, d):
        frames = [CanFrame.from_dict(f) for f in d.get("frames", [])]
        return cls(
            name=d.get("name", ""),
            channel=d.get("channel", "A"),
            interval_ms=d.get("interval_ms", 500),
            count=d.get("count", INFINITE),
            enabled=d.get("enabled", False),
            frames=frames,
        )

    def copy(self):
        return CanCommand.from_dict(self.to_dict())

    def __repr__(self):
        return "<CanCommand %s ch=%s intv=%dms cnt=%s frames=%d>" % (
            self.name, self.channel, self.interval_ms, self.count, len(self.frames))


# --------------------------------------------------------------------------
# 预设库（把现有 CanWindow 的固定测试指令按新模型表达）
#   STAR / ATTITUDE / TIME / SLOW1..3 / BUS / STAR_WGS84
#   CAN ID 编码方式沿用 ycyk_422 现有拼接：完整 29bit ID 由外部字段拼好直接给。
# --------------------------------------------------------------------------
def _id29(prio, src, grp, dst, pkt=0x3, seq=0, func=1):
    return int(((prio & 0x3) << 27) | ((src & 0x3F) << 21) | ((grp & 0x3) << 19)
               | ((dst & 0x3F) << 13) | ((pkt & 0x3) << 11) | ((seq & 0x3F) << 5) | (func & 0x1F))


def _mkframes(start_id_factory, payload, chunk=8):
    out = []
    for off in range(0, len(payload), chunk):
        seg = payload[off:off + chunk]
        pkt, seq = (0x1, off // chunk) if len(payload) > 8 else (0x3, 0)
        if len(payload) > 8:
            if off == 0:
                pkt, seq = 0x1, 0
            elif off + chunk >= len(payload):
                pkt, seq = 0x2, off // chunk
            else:
                pkt, seq = 0x0, off // chunk
        out.append(CanFrame(start_id_factory(pkt, seq), seg))
    return out


# 单帧指令: 完整 id 用 _id29(1,0,0,dst, pkt=3, seq=0, func=1)
PRESETS_A = [
    CanCommand("快遥 FAST", "A", 500, INFINITE, False,
               [CanFrame(_id29(0, 0, 0, 0x18), [0x00, 0x5A, 0x5A])]),
    CanCommand("慢遥 SLOW1", "A", 500, INFINITE, False,
               [CanFrame(_id29(0, 0, 0, 0x18), [0x00, 0xAA, 0x51, 0xFB])]),
    CanCommand("慢遥 SLOW2", "A", 500, INFINITE, False,
               [CanFrame(_id29(0, 0, 0, 0x18), [0x00, 0xAA, 0x52, 0xFC])]),
    CanCommand("慢遥 SLOW3", "A", 500, INFINITE, False,
               [CanFrame(_id29(0, 0, 0, 0x18), [0x00, 0xAA, 0x53, 0xFD])]),
    CanCommand("时间同步 TIME", "A", 1000, INFINITE, False,
               [CanFrame(_id29(1, 0, 3, 0x3F), [0, 0, 0, 0, 0, 0, 0, 0])]),
    CanCommand("姿态 ATTITUDE", "A", 500, INFINITE, False,
               _mkframes(lambda p, s: _id29(1, 0, 1, 0x3F, pkt=p, seq=s),
                         [0x00, 0x25, 0x00, 0x02, 0x00, 0x01, 0x02, 0x03,
                          0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b,
                          0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13,
                          0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b,
                          0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x55])),
    CanCommand("星敏感器 STAR", "A", 100, INFINITE, False,
               _mkframes(lambda p, s: _id29(1, 0, 1, 0x15, pkt=p, seq=s),
                         [0x00, 0x23, 0x00, 0x01, 0x20, 0x1f, 0x1e, 0x1d,
                          0x1c, 0x1b, 0x1a, 0x19, 0x18, 0x17, 0x16, 0x15,
                          0x14, 0x13, 0x12, 0x11, 0x10, 0x0f, 0x0e, 0x0d,
                          0x0c, 0x0b, 0x0a, 0x09, 0x08, 0x07, 0x06, 0x05,
                          0x04, 0x03, 0x02, 0x01, 0x00, 0x11])),
    CanCommand("星敏感器 WGS84", "A", 100, INFINITE, False,
               _mkframes(lambda p, s: _id29(1, 0, 1, 0x15, pkt=p, seq=s),
                         [0x00, 0x23, 0x00, 0x04, 0x20, 0x1f, 0x1e, 0x1d,
                          0x1c, 0x1b, 0x1a, 0x19, 0x18, 0x17, 0x16, 0x15,
                          0x14, 0x13, 0x12, 0x11, 0x10, 0x0f, 0x0e, 0x0d,
                          0x0c, 0x0b, 0x0a, 0x09, 0x08, 0x07, 0x06, 0x05,
                          0x04, 0x03, 0x02, 0x01, 0x00, 0x11])),
]

PRESETS_B = [
    CanCommand("BUS 总线帧", "B", 500, INFINITE, False,
               [CanFrame(_id29(1, 0, 0, 0x18), [0x00, 0x25, 0x25])]),
    CanCommand("星敏感器 STAR", "B", 100, INFINITE, False,
               _mkframes(lambda p, s: _id29(1, 0, 1, 0x15, pkt=p, seq=s),
                         [0x00, 0x23, 0x00, 0x01, 0x20, 0x1f, 0x1e, 0x1d,
                          0x1c, 0x1b, 0x1a, 0x19, 0x18, 0x17, 0x16, 0x15,
                          0x14, 0x13, 0x12, 0x11, 0x10, 0x0f, 0x0e, 0x0d,
                          0x0c, 0x0b, 0x0a, 0x09, 0x08, 0x07, 0x06, 0x05,
                          0x04, 0x03, 0x02, 0x01, 0x00, 0x11])),
    CanCommand("姿态 ATTITUDE", "B", 500, INFINITE, False,
               _mkframes(lambda p, s: _id29(1, 0, 1, 0x3F, pkt=p, seq=s),
                         [0x00, 0x25, 0x00, 0x02, 0x00, 0x01, 0x02, 0x03,
                          0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b,
                          0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13,
                          0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b,
                          0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x55])),
]


# --------------------------------------------------------------------------
# 调度器：单 QTimer 心跳 + 到期表（A/B 由 UI 注入发送函数）
# --------------------------------------------------------------------------
class CANCommandScheduler(object):
    """纯 Python 调度器，不依赖 Qt 线程；由外部以固定节拍调用 tick()。"""

    def __init__(self):
        self._entries = {}       # id -> cmd  (同一份对象引用，供 UI 展示状态)
        self._last = {}          # id -> monotonic 上次发送时刻
        self._remaining = {}     # id -> 剩余次数（对有限指令）
        self._on_due = None      # callable(cmd) 发送回调
        self._just_finished = [] # 本次 tick 次数用尽自动停的指令 id 列表

    def set_callback(self, cb):
        self._on_due = cb

    def set_commands(self, cmds):
        self._entries = {id(c): c for c in cmds}
        self._last = {id(c): 0.0 for c in cmds}
        self._remaining = {}
        for c in cmds:
            if not c.is_infinite and c.count > 0:
                self._remaining[id(c)] = c.count

    def reset_runtime(self):
        self._last = {i: 0.0 for i in self._entries}
        self._remaining = {}
        for c in self._entries.values():
            if not c.is_infinite and c.count > 0:
                self._remaining[id(c)] = c.count

    def add(self, cmd):
        self._entries[id(cmd)] = cmd
        self._last[id(cmd)] = 0.0
        if not cmd.is_infinite and cmd.count > 0:
            self._remaining[id(cmd)] = cmd.count

    def remove(self, cmd):
        self._entries.pop(id(cmd), None)
        self._last.pop(id(cmd), None)
        self._remaining.pop(id(cmd), None)

    def clear(self):
        self._entries.clear()
        self._last.clear()
        self._remaining.clear()

    def count_active(self):
        return sum(1 for c in self._entries.values() if c.enabled)

    def tick(self):
        self._just_finished = []
        if not self._on_due:
            return
        now = time.monotonic()
        for c in list(self._entries.values()):
            if not c.enabled:
                continue
            remain = self._remaining.get(id(c))
            if remain is not None and remain <= 0:
                c.enabled = False
                continue
            last = self._last.get(id(c), 0.0)
            if (now - last) >= c.interval_ms / 1000.0:
                self._last[id(c)] = now
                if remain is not None:
                    self._remaining[id(c)] = remain - 1
                    if remain - 1 <= 0:
                        c.enabled = False
                        self._just_finished.append(id(c))
                self._on_due(c)

    def take_just_finished(self):
        """返回并清空"本次 tick 中因次数用尽而自动停止"的指令对象列表。"""
        out = [self._entries.get(i) for i in self._just_finished]
        self._just_finished = []
        return [c for c in out if c is not None]

    # 供 UI 显示剩余
    def remaining_of(self, cmd):
        return self._remaining.get(id(cmd))

    def finish_silently(self):
        """停止所有但不改数据（停止按钮用）。"""
        for c in self._entries.values():
            if c.enabled:
                c.enabled = False
        self._last = {i: 0.0 for i in self._entries}


def serialize_commands(cmds):
    return [c.to_dict() for c in cmds]


def deserialize_commands(items):
    return [CanCommand.from_dict(d) for d in items]
