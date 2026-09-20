# -*- coding: utf-8 -*-
"""SerialTransport 读取路径自测（假串口，无需硬件）。

重点验证 `read_some` 的重配缺陷已消除：
  - 读循环期间 `self._ser.timeout` **从不被赋值**（这是不触发
    pyserial `_reconfigure_port()` 的充要条件）
  - 超时 / 阻塞 / 负值 三种语义正确
  - 上层 `read_exact` / `read_until_idle` 行为不回归

    D:\\Anaconda3\\envs\\pyqt_side_all_0328\\python.exe -u bmu_testkit\\tools\\selftest_serial_read.py
"""

from __future__ import print_function

import io
import os
import sys
import threading
import time

if sys.version_info[0] >= 3:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bmu_testkit.transport.base import TransportTimeout  # noqa: E402
from bmu_testkit.transport.serial_transport import (  # noqa: E402
    SerialTransport,
    _READ_TIMEOUT,
)

PASS, FAIL = [], []


def check(desc, ok, detail=""):
    (PASS if ok else FAIL).append(desc)
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", desc,
                           ("  " + detail) if detail else ""))


class FakeSerial(object):
    """替身 serial：模拟 pyserial 的 timeout 属性行为。

    `_set_timeout()` 显式记录每次赋值 —— 读循环若碰 timeout 就会被抓到。
    （不用 __setattr__ 覆写：那会让 `is_open` 等普通属性也走记录路径，
    逻辑绕且容易出错。这里直接提供 setter 方法，由测试代码显式调用。）
    """

    def __init__(self):
        self.is_open = True
        self._timeout = 0.05
        self.timeout_writes = []
        self._buf = bytearray()
        self._lock = threading.Lock()

    # --- 模拟 pyserial 的 timeout property ---
    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self._timeout = value
        self.timeout_writes.append(value)

    # --- 数据 ---
    def feed(self, data):
        with self._lock:
            self._buf += data

    @property
    def in_waiting(self):
        with self._lock:
            return len(self._buf)

    def read(self, n=1):
        """阻塞至多 timeout 秒，最多返回 n 字节。"""
        deadline = None if self._timeout is None else time.monotonic() + self._timeout
        while True:
            with self._lock:
                if self._buf:
                    take = bytes(self._buf[:n])
                    del self._buf[:n]
                    return take
            if deadline is not None and time.monotonic() >= deadline:
                return b""
            time.sleep(0.002)


def make_transport(fake):
    """绕过真串口 open，注入替身。"""
    t = SerialTransport(port="FAKE", timeout=None)
    t._ser = fake
    return t


def main():
    print("=" * 68)
    print("SerialTransport 读取路径自测（假串口，无硬件）")
    print("=" * 68)

    # ---------- 1. 内核读超时为定值 ----------
    print("\n[1] 内核读超时为定值（与构造参数无关）")
    fake = FakeSerial()
    t = make_transport(fake)
    t._apply_params()
    check("_apply_params 设定 _READ_TIMEOUT",
          fake.timeout == _READ_TIMEOUT, "timeout=%r" % (fake.timeout,))

    t2 = SerialTransport(port="FAKE2", timeout=3.0)
    t2._ser = FakeSerial()
    t2._apply_params()
    check("构造传 timeout=3.0 仍不改内核超时",
          t2._ser.timeout == _READ_TIMEOUT, "timeout=%r" % (t2._ser.timeout,))

    # ---------- 2. ★ 读循环不碰 timeout ----------
    print("\n[2] ★ 读循环期间 timeout 从不被赋值（不触发 _reconfigure_port）")
    fake = FakeSerial()
    fake.feed(b"\x01\x02\x03")
    t = make_transport(fake)
    fake.timeout_writes = []                    # 清掉 _apply_params 的痕迹
    data = t.read_some(timeout=0.2)
    check("读到数据", data == b"\x01\x02\x03", "got=%s" % data.hex())
    check("有数据路径：timeout 未被赋值",
          fake.timeout_writes == [], "写入记录 %r" % (fake.timeout_writes,))

    fake = FakeSerial()
    t = make_transport(fake)
    fake.timeout_writes = []
    t0 = time.monotonic()
    data = t.read_some(timeout=0.15)
    el = time.monotonic() - t0
    check("无数据超时返回空", data == b"", "got=%r" % data)
    check("超时约 0.15s", 0.10 <= el <= 0.45, "elapsed=%.3fs" % el)
    check("超时路径：timeout 未被赋值",
          fake.timeout_writes == [], "写入记录 %r" % (fake.timeout_writes,))

    # ---------- 3. 上层封装回归 ----------
    print("\n[3] 上层 read_exact / read_until_idle 行为")
    fake = FakeSerial()
    fake.feed(b"\xeb\x90\x01\x80")
    t = make_transport(fake)
    fake.timeout_writes = []
    got = t.read_exact(4, timeout=0.5)
    check("read_exact 读满 4 字节", got == b"\xeb\x90\x01\x80", got.hex())
    check("read_exact 未改写 timeout", fake.timeout_writes == [])

    fake = FakeSerial()
    fake.feed(b"\x1a\xcf\x00\x18")
    t = make_transport(fake)
    fake.timeout_writes = []
    t0 = time.monotonic()
    got = t.read_until_idle(idle=0.1, timeout=1.0)
    el = time.monotonic() - t0
    check("read_until_idle 收到 4 字节", got == b"\x1a\xcf\x00\x18", got.hex())
    check("read_until_idle 在 idle 后退出", 0.05 <= el <= 0.8, "elapsed=%.3fs" % el)
    check("read_until_idle 未改写 timeout",
          fake.timeout_writes == [], "写入记录 %r" % (fake.timeout_writes,))

    # 分片到达（间隔 < idle 应合并）
    fake = FakeSerial()
    t = make_transport(fake)
    fake.timeout_writes = []

    def late_feed():
        time.sleep(0.03)
        fake.feed(b"AAA")
        time.sleep(0.03)
        fake.feed(b"BBB")

    th = threading.Thread(target=late_feed)
    th.start()
    got = t.read_until_idle(idle=0.15, timeout=1.0)
    th.join()
    check("分片数据被合并", got == b"AAABBB", repr(got))
    check("分片场景未改写 timeout", fake.timeout_writes == [])

    # ---------- 4. 超时异常信息 ----------
    print("\n[4] read_exact 超时异常信息完整")
    fake = FakeSerial()
    fake.feed(b"\x01\x02")
    t = make_transport(fake)
    try:
        t.read_exact(8, timeout=0.2)
        check("应抛 TransportTimeout", False)
    except TransportTimeout as exc:
        check("抛 TransportTimeout", True)
        check("携带 partial", exc.partial == b"\x01\x02", repr(exc.partial))
        check("携带 expected", exc.expected == 8, str(exc.expected))
        check("异常文本含已收字节数", "2/8" in str(exc), str(exc))

    # ---------- 5. 边界：timeout<=0 ----------
    print("\n[5] 边界：timeout=0 / 负值 按'等到有'处理")
    for label, tv in (("timeout=0", 0), ("timeout=-1", -1)):
        fake = FakeSerial()
        t = make_transport(fake)
        th = threading.Thread(target=lambda f=fake: (time.sleep(0.06), f.feed(b"Z")))
        th.start()
        got = t.read_some(timeout=tv)
        th.join()
        check("%s 仍等到数据" % label, got == b"Z", repr(got))

    # ---------- 6. 多次连续读不累积 timeout 写入 ----------
    print("\n[6] 连续 10 次读：timeout 写入次数为 0")
    fake = FakeSerial()
    t = make_transport(fake)
    fake.timeout_writes = []
    for i in range(10):
        fake.feed(b"\x00")
        t.read_some(timeout=0.05)
    check("10 次读后 timeout 写入为 0 次",
          len(fake.timeout_writes) == 0, "写入 %d 次" % len(fake.timeout_writes))

    # ---------- 汇总 ----------
    print("\n" + "=" * 68)
    print("结果: %d/%d 通过" % (len(PASS), len(PASS) + len(FAIL)))
    if FAIL:
        print("失败项:")
        for f in FAIL:
            print("  - %s" % f)
    print("=" * 68)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
