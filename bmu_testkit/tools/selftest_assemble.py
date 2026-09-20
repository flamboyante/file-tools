# -*- coding: utf-8 -*-
"""文本按行组装自测（无需 GUI、无需硬件）。

复现真实场景：串口把一条 BL 日志切成多块返回，窗口按读取块分行 →
「按行组装」开启后应拼回整行。

用到的样本直接取自 2026-09-20 03:58 真机监视窗口观察到的碎片。

    D:\\Anaconda3\\envs\\pyqt_side_all_0328\\python.exe -u bmu_testkit\\tools\\selftest_assemble.py
"""

from __future__ import print_function

import io
import os
import sys

if sys.version_info[0] >= 3:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

from bmu_testkit.mirror.sinks import format_event, parse_event  # noqa: E402

PASS, FAIL = [], []


def check(desc, ok, detail=""):
    (PASS if ok else FAIL).append(desc)
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", desc,
                           ("  " + detail) if detail else ""))


# ---------- 从 watch_serial 抽取组装逻辑（保证测的是真代码） ----------
def load_emitter(assemble=True):
    import ast
    import re

    path = os.path.join(os.path.dirname(HERE), "watch_serial.py")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()

    wanted = ("_emit_events", "_make_asm_event")
    blocks = []
    for name in wanted:
        m = re.search(r"    def %s\b.*?(?=\n    def )" % name, src, re.S)
        if not m:
            raise RuntimeError("在 watch_serial.py 里找不到 %s" % name)
        blocks.append(m.group(0))

    import time as _time
    ns = {"ASSEMBLE_FLUSH": 0.3, "time": _time}
    stub = ("class Stub(object):\n"
            "    def __init__(self, assemble):\n"
            "        self.assemble = assemble\n"
            "        self._asm_buf = bytearray()\n"
            "        self._asm_meta = None\n"
            + "".join(blocks))
    # 去掉注解里的 forward ref 影响（本项目 3.8，注解按字符串处理没问题）
    exec(compile(stub, "<extracted>", "exec"), ns)
    return ns["Stub"](assemble)


def evt_from(data: bytes, direction="RX", wall=None, elapsed=None):
    """用真实 sinks.format_event 造事件，再 parse 回来（走完整链路）。"""
    line = format_event(direction, data, elapsed=elapsed)
    e = parse_event(line)
    if wall is not None:
        e["wall"] = wall
    return e


def bodies(events):
    """跑一遍组装，返回渲染出的行正文列表（按 ascii 口径）。"""
    out = []
    for e in events:
        d = bytes.fromhex(e["hex"])
        out.append("".join(chr(b) if 0x20 <= b <= 0x7E or b == 9 else "."
                           for b in d))
    return out


def main():
    print("=" * 70)
    print("文本按行组装自测")
    print("=" * 70)

    # ---------- 1. 真机碎片复现 ----------
    print("\n[1] 复现 03:58 真机碎片（一条日志被切成多块）")
    chunks = [
        b"[BL] heartbeat",
        b" at 0x001D -",
        b"> reply 0x001",
        b"F\r\n",
    ]
    events = [evt_from(c) for c in chunks]

    # 关组装：4 块 → 4 行
    em = load_emitter(assemble=False)
    raw = bodies(list(em._emit_events(events)))
    check("关组装时保持原样（4 块 4 行）", len(raw) == 4,
          "得到 %d 行: %r" % (len(raw), raw))

    # 开组装：4 块 → 1 行
    em = load_emitter(assemble=True)
    asm = bodies(list(em._emit_events([evt_from(c) for c in chunks])))
    check("开组装后合成 1 行", len(asm) == 1, "得到 %d 行: %r" % (len(asm), asm))
    if asm:
        want = "[BL] heartbeat at 0x001D -> reply 0x001F.."
        check("内容正确", asm[0] == want,
              "got=%r\n%swant=%r" % (asm[0], " " * 10, want))

    # ---------- 2. 一次事件里的多行 ----------
    print("\n[2] 一个事件内含多个换行 → 拆成多行")
    em = load_emitter(assemble=True)
    one = [evt_from(b"line1\r\nline2\r\nline3\r\n")]
    got = bodies(list(em._emit_events(one)))
    check("3 行被拆开", len(got) == 3, "得到 %d 行: %r" % (len(got), got))
    if len(got) == 3:
        check("第 1 行内容", got[0] == "line1..", repr(got[0]))
        check("第 3 行内容", got[2] == "line3..", repr(got[2]))

    # ---------- 3. 跨 flush 保持半行 ----------
    print("\n[3] 跨两次刷新：半行被保留，下次续上")
    em = load_emitter(assemble=True)
    first = list(em._emit_events([evt_from(b"[BL] hel")]))
    check("未遇换行不产出", len(first) == 0, "得到 %d 行" % len(first))
    check("半行留在缓冲区", bytes(em._asm_buf) == b"[BL] hel",
          repr(bytes(em._asm_buf)))
    second = bodies(list(em._emit_events([evt_from(b"lo world\r\n")])))
    check("续上后产出 1 行", len(second) == 1, "得到 %d 行" % len(second))
    if second:
        check("拼接内容正确", second[0] == "[BL] hello world..", repr(second[0]))
    check("缓冲已清空", len(em._asm_buf) == 0, repr(bytes(em._asm_buf)))

    # ---------- 4. 半行超时兜底 ----------
    print("\n[4] 半行超时兜底（无换行的日志也能显示）")
    import time as _t
    em = load_emitter(assemble=True)
    old = evt_from(b"no newline here", wall=_t.time() - 1.0)   # 1 秒前
    got = bodies(list(em._emit_events([old])))
    check("超时后强制吐出", len(got) == 1, "得到 %d 行: %r" % (len(got), got))
    if got:
        check("兜底内容正确", got[0] == "no newline here", repr(got[0]))
    check("兜底后缓冲清空", len(em._asm_buf) == 0)

    # 未超时则不吐
    em = load_emitter(assemble=True)
    fresh = evt_from(b"fresh", wall=_t.time())                  # 刚刚
    got = bodies(list(em._emit_events([fresh])))
    check("未超时不吐出（避免把完整行拆散）", len(got) == 0,
          "得到 %d 行" % len(got))

    # ---------- 5. 混合：多行 + 尾部半行 ----------
    print("\n[5] 混合场景：完整行 + 尾部半行")
    em = load_emitter(assemble=True)
    evts = [evt_from(b"AAA\r\nBBB\r\nCC")]
    got = bodies(list(em._emit_events(evts)))
    check("产出 2 行（尾部半行留着）", len(got) == 2,
          "得到 %d 行: %r" % (len(got), got))
    if got:
        check("第 1 行 = AAA", got[0] == "AAA..", repr(got[0]))
        check("第 2 行 = BBB", got[1] == "BBB..", repr(got[1]))
    check("尾部 'CC' 留在缓冲", bytes(em._asm_buf) == b"CC",
          repr(bytes(em._asm_buf)))

    # ---------- 6. 元信息取自首段 ----------
    print("\n[6] 组装行的元信息（时间戳/方向）取自首段")
    em = load_emitter(assemble=True)
    e1 = evt_from(b"[BL] ", direction="RX")
    e1["ts"] = "03:58:42.056"
    e2 = evt_from(b"done\r\n", direction="RX")
    e2["ts"] = "03:58:42.365"
    out = list(em._emit_events([e1, e2]))
    check("产出 1 行", len(out) == 1)
    if out:
        check("时间戳取首段", out[0].get("ts") == "03:58:42.056",
              out[0].get("ts"))
        check("标记 assembled", out[0].get("assembled") is True)
        check("n 为总字节数", out[0].get("n") == len(b"[BL] done\r\n"),
              str(out[0].get("n")))

    # ---------- 汇总 ----------
    print("\n" + "=" * 70)
    print("结果: %d/%d 通过" % (len(PASS), len(PASS) + len(FAIL)))
    if FAIL:
        print("失败项:")
        for f in FAIL:
            print("  - %s" % f)
    print("=" * 70)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
