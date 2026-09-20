# -*- coding: utf-8 -*-
"""端到端自测：真实 FileTransfer + 镜像层 + 监视窗口（无硬件）。

用假串口喂真实的上层流程（FileTransfer），验证监视窗口能看到
一轮完整的文件传输过程。这是最接近真机使用的一次验证。

用法：python -m bmu_testkit.tools.selftest_e2e
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from bmu_testkit.core.filetransfer import FileTransfer
from bmu_testkit.mirror import attach_mirror_custom
from bmu_testkit.transport.fake_transport import FakeTransport
from bmu_testkit.watch_serial import SerialMonitorWindow

PORT = 39603
SHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "monitor_e2e.png")
LOG = os.path.join(tempfile.gettempdir(), "mirror_e2e.log")


def run_transfer(log_lines):
    """跑一轮真实文件传输流程。"""
    # 造一个 2KB 的待传文件
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
    tmp.write(bytes((i * 7) % 256 for i in range(2048)))
    tmp.close()

    inner = FakeTransport(latency=0.0)
    t = attach_mirror_custom(inner, log_path=LOG, udp_port=PORT)
    ft = FileTransfer(t, on_log=lambda m: log_lines.append(m))
    t.open()
    r = ft.transfer(tmp.name, flash=0xFB, mem=0x06,
                    frame_len=1024, frame_num=4,
                    require_confirm=False, timeout=2, do_refactor=True)
    t.close()
    os.unlink(tmp.name)
    return r


def main():
    app = QApplication(sys.argv[:1])
    win = SerialMonitorWindow(port=PORT, truncate=30)
    win.show()

    logs = []
    state = {}

    def on_start():
        try:
            state["result"] = run_transfer(logs)
        except Exception as e:
            state["error"] = e

    def on_shot():
        win.grab().save(SHOT)
        print("\n" + "=" * 60)
        r = state.get("result")
        if r is not None:
            print("传输结果: %s" % r)
        if "error" in state:
            print("异常: %r" % state["error"])
        print("流程日志:")
        for line in logs:
            print("   " + line)
        print("=" * 60)
        print("监视窗口状态: %s" % win.label_status.text())
        print("预览图: %s" % SHOT)
        print("镜像日志: %s" % LOG)
        app.quit()

    QTimer.singleShot(300, on_start)
    QTimer.singleShot(2000, on_shot)
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
