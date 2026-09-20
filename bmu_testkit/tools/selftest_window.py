# -*- coding: utf-8 -*-
"""监视窗口端到端自测（无硬件）。

启动真实窗口，用假串口灌入一轮完整流量，截图确认显示效果后退出。

用法：python -m bmu_testkit.tools.selftest_window
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from bmu_testkit.mirror import MirroredTransport, UdpSink
from bmu_testkit.transport.fake_transport import FakeTransport
from bmu_testkit.watch_serial import SerialMonitorWindow

PORT = 39601
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "monitor_preview.png")


def feed():
    """灌入一轮流量：一次正常传输 + 一次异常应答 + 一个大帧（验证截断）。"""
    inner = FakeTransport(latency=0.0)
    inner.open()
    t = MirroredTransport(inner, sinks=[UdpSink(port=PORT)])

    # 1) begin（大帧，验证 30 字节截断）
    begin = bytearray([0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x10,
                       0x01, 0x55, 0x18, 0xFB, 0x06])
    begin += bytes(range(100, 240))          # 填充到 ~153 字节
    t.write(bytes(begin))

    # 2) 两个大帧（模拟文件数据帧）
    for i in range(2):
        frame = bytearray([0xEB, 0x90, 0x01, 0x80, 0xC0, 0x01, 0x0B, 0xE8,
                           0x00, 0x03, 0x11, 0x22])
        frame += bytes((i * 37 + j) % 256 for j in range(1000))
        t.write(bytes(frame))

    # 3) 正常应答 + 异常应答（验证着色）
    inner._buf += bytes.fromhex("1A CF 01 87 C0 07 00 02 01 8A 00 FE 53")
    inner._buf += bytes.fromhex("1A CF 01 87 C0 08 00 02 01 5A FF FB A2")
    while inner._buf:
        t.read_some(timeout=0)

    t.close_sinks()


def main():
    app = QApplication(sys.argv[:1])
    win = SerialMonitorWindow(port=PORT, truncate=30)
    win.show()

    def on_start():
        feed()

    def on_shot():
        win.grab().save(SHOT)
        print("预览图已保存: %s" % SHOT)
        print("状态栏: %s" % win.label_status.text())
        app.quit()

    QTimer.singleShot(200, on_start)
    QTimer.singleShot(1200, on_shot)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
