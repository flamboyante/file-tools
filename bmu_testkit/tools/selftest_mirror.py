# -*- coding: utf-8 -*-
"""镜像链路自测（无需硬件）。

验证三件事：
  1. MirroredTransport 不改行为：包与不包，收发的字节完全一致
  2. 收发都被投递到 sink（文件与 UDP 都能收到）
  3. sink 抛异常时业务不受影响

用法：python -m bmu_testkit.tools.selftest_mirror
"""

import json
import os
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from bmu_testkit.mirror import FileSink, MirroredTransport, UdpSink, parse_event
from bmu_testkit.transport.fake_transport import FakeTransport

HEARTBEAT = bytes.fromhex("EB 90 01 80 C0 00 00 01 00 1D FE A0")


def _check(label, ok, detail=""):
    print("  [%s] %s %s" % ("PASS" if ok else "FAIL", label, detail))
    return ok


def test_passthrough():
    """不包装 vs 包装：返回值与读到的字节必须一致。"""
    print("\n[1] 透传一致性（包装不改变行为）")
    plain = FakeTransport(name="plain")
    plain.open()
    n1 = plain.write(HEARTBEAT)
    r1 = plain.read_some(timeout=0)

    wrapped_inner = FakeTransport(name="wrapped")
    wrapped = MirroredTransport(wrapped_inner, sinks=[])
    wrapped.open()
    n2 = wrapped.write(HEARTBEAT)
    r2 = wrapped.read_some(timeout=0)

    ok = True
    ok &= _check("write 返回字节数一致", n1 == n2, "%d vs %d" % (n1, n2))
    ok &= _check("read 内容一致", r1 == r2, r1.hex(" "))
    ok &= _check("应答是 13 字节 0x8A", len(r1) == 13 and r1[9] == 0x8A,
                 "%dB type=0x%02X" % (len(r1), r1[9] if len(r1) > 9 else 0))
    ok &= _check("属性透传 is_open", wrapped.is_open == wrapped_inner.is_open)
    ok &= _check("describe 透传", "FAKE" in wrapped.describe())
    return ok


def test_file_sink():
    """文件 sink：TX/RX 各一行，能解析回事件。"""
    print("\n[2] 文件 sink")
    tmpdir = tempfile.mkdtemp(prefix="mirror_test_")
    path = os.path.join(tmpdir, "trace.log")

    inner = FakeTransport()
    inner.open()
    t = MirroredTransport(inner, sinks=[FileSink(path)])
    t.write(HEARTBEAT)
    t.read_some(timeout=0)
    t.close_sinks()

    with open(path, "r", encoding="utf-8") as fh:
        lines = [l for l in fh.read().splitlines() if l.strip()]

    events = [parse_event(l) for l in lines]
    events = [e for e in events if e]
    ok = True
    ok &= _check("写出 2 行", len(events) == 2, "实际 %d 行" % len(events))
    if len(events) == 2:
        ok &= _check("第 1 行是 TX", events[0]["dir"] == "TX")
        ok &= _check("TX 长度 12", events[0]["n"] == 12, str(events[0]["n"]))
        ok &= _check("TX HEX 正确", events[0]["hex"] == HEARTBEAT.hex(" "))
        ok &= _check("第 2 行是 RX", events[1]["dir"] == "RX")
        ok &= _check("RX 长度 13", events[1]["n"] == 13, str(events[1]["n"]))
    print("      日志样例: %s" % (lines[0] if lines else "(空)"))
    return ok


def test_udp_sink():
    """UDP sink：本机监听端口能收到事件包。"""
    print("\n[3] UDP sink")
    port = 39599
    recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv.bind(("127.0.0.1", port))
    recv.settimeout(1.0)

    inner = FakeTransport()
    inner.open()
    t = MirroredTransport(inner, sinks=[UdpSink(port=port)])
    t.write(HEARTBEAT)
    t.read_some(timeout=0)

    got = []
    try:
        for _ in range(2):
            data, _addr = recv.recvfrom(65535)
            got.append(parse_event(data.decode("utf-8")))
    except socket.timeout:
        pass
    finally:
        recv.close()
        t.close_sinks()

    ok = True
    ok &= _check("收到 2 个包", len(got) == 2, "实际 %d" % len(got))
    if len(got) == 2:
        ok &= _check("方向为 TX / RX",
                     got[0]["dir"] == "TX" and got[1]["dir"] == "RX")
    return ok


def test_sink_failure_isolation():
    """sink 抛异常时，业务必须照常完成。"""
    print("\n[4] sink 故障隔离")

    class BrokenSink:
        def emit(self, line):
            raise RuntimeError("模拟 sink 崩溃")

        def close(self):
            pass

    inner = FakeTransport()
    inner.open()
    t = MirroredTransport(inner, sinks=[BrokenSink()])

    ok = True
    try:
        n = t.write(HEARTBEAT)
        r = t.read_some(timeout=0)
        ok &= _check("write 未被 sink 异常影响", n == len(HEARTBEAT))
        ok &= _check("read 未被 sink 异常影响", len(r) == 13)
    except Exception as e:
        ok &= _check("sink 异常不得外泄", False, repr(e))
    return ok


def test_lazy_sink():
    """串口打不开时不得创建 sink（不留空日志）。"""
    print("\n[5] 延迟建 sink")

    created = {"n": 0}

    def factory():
        created["n"] += 1
        return [], None

    class FailOpen(FakeTransport):
        def open(self):
            raise IOError("模拟串口打不开")

    inner = FailOpen()
    t = MirroredTransport(inner, sink_factory=factory)
    try:
        t.open()
    except IOError:
        pass

    ok = _check("open 失败时未建 sink", created["n"] == 0,
                "建了 %d 次" % created["n"])
    return ok


def main():
    print("=" * 62)
    print("镜像链路自测（假串口，无硬件）")
    print("=" * 62)
    results = [
        test_passthrough(),
        test_file_sink(),
        test_udp_sink(),
        test_sink_failure_isolation(),
        test_lazy_sink(),
    ]
    print("\n" + "=" * 62)
    passed = sum(1 for r in results if r)
    print("结果: %d/%d 项通过" % (passed, len(results)))
    print("=" * 62)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
