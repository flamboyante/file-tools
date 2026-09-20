# -*- coding: utf-8 -*-
"""双通道镜像验证：模拟 self(重构) 与 debug(心跳) 两路流量，
在同一进程内起 UDP 监听线程，确认两个通道的事件都能被独立收到并区分。

不依赖任何硬件。用于回答：「watch_serial 窗口能否同时看到两个串口的交互」。
"""
import json
import socket
import sys
import threading
import time

sys.path.insert(0, r"V:\MY\PYQT\pythonProjectV3.3.0_beta")

from bmu_testkit.mirror import attach_mirror
from bmu_testkit.transport.fake_transport import FakeTransport

PORT = 39527
events = []
stop = threading.Event()


def listener():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("127.0.0.1", PORT))
    s.settimeout(0.3)
    while not stop.is_set():
        try:
            data, _ = s.recvfrom(65535)
        except socket.timeout:
            continue
        try:
            events.append(json.loads(data.decode("utf-8", "replace")))
        except Exception:
            pass
    s.close()


th = threading.Thread(target=listener, daemon=True)
th.start()
time.sleep(0.4)

# ---- 两路假串口，都挂镜像、都广播到同一 UDP 端口 ----
self_t = attach_mirror(FakeTransport(name="self"), udp_port=PORT)
debug_t = attach_mirror(FakeTransport(name="debug"), udp_port=PORT)
self_t.open()
debug_t.open()

HB_REQ = bytes.fromhex("EB 90 01 80 C0 00 00 01 00 1D FE A0")
HB_ACK = bytes.fromhex("1A CF 01 87 C0 00 00 01 00 1F FE 97")
BEGIN = bytes.fromhex("EB 90 01 80 C0 00 00 10 01 55 18 FB 06 FA A6")

print("=== 注入流量 ===")
print("  debug 通道：心跳请求 + 应答")
debug_t.write(HB_REQ)
time.sleep(0.15)
debug_t.read_some(timeout=0.5)

print("  self 通道：升级 begin 请求")
self_t.write(BEGIN)
time.sleep(0.15)
self_t.read_some(timeout=0.5)

self_t.close()
debug_t.close()
time.sleep(0.8)
stop.set()
th.join(timeout=2)

print()
print("=== 监听端收到的事件（= watch_serial 窗口会显示的内容）===")
by_src = {}
for e in events:
    src = e.get("src", "?")
    by_src.setdefault(src, []).append(e)
    d = e.get("dir", "??")
    arrow = "TX ->" if d == "TX" else "RX <-"
    print("  %s  [%-6s] %s %5dB  %s"
          % (e.get("ts", "?"), src, arrow, e.get("n", 0), e.get("hex", "")[:60]))

print()
print("=== 按通道汇总 ===")
for src in sorted(by_src):
    evs = by_src[src]
    tx = sum(1 for e in evs if e.get("dir") == "TX")
    rx = sum(1 for e in evs if e.get("dir") == "RX")
    print("  通道 %-6s : %d 个事件 (TX %d / RX %d)" % (repr(src), len(evs), tx, rx))

print()
print("结论：", end="")
if len(by_src) == 2 and all(
        sum(1 for e in v if e.get("dir") == "TX") >= 1 for v in by_src.values()):
    print("两个通道的事件都到达了同一个窗口，且能用 src 字段区分 -> 窗口方案可行")
else:
    print("通道事件不全，需排查")
