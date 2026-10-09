# -*- coding: utf-8 -*-
"""B 方案基准：QWebEngineView + QWebChannel 做同一批「指令卡片」。

与 bench_fluent.py 的负载完全等价：
    T1  创建 N 张卡片
    T2  N 张卡片文本刷新 ROUNDS 轮
    T3  N 个开关切换 ROUNDS 轮

两个维度分开量，这是本方案的关键指标：
    rtt_ms  —— Python 发起 -> JS 回调回到 Python 的完整往返（含通道开销）
    js_ms   —— JS 内部 performance.now() 实测的执行时间（不含通道开销）
    overhead = rtt - js，即「跨语言通道的代价」

结果以 "RESULT_JSON {..}" 单行打印，跑完自动退出。
"""
import json
import os
import subprocess
import sys
import time

T_START = time.perf_counter()          # 进程内最早的时间戳

# 必须在 QApplication 之前导入
from PyQt5.QtCore import QUrl, QTimer, QEventLoop, pyqtSlot, QObject
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout

N_CARDS = 200
ROUNDS_TEXT = 10
ROUNDS_SWITCH = 5

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "card_page.html")


class Bridge(QObject):
    def __init__(self):
        super(Bridge, self).__init__()
        self.ready_flag = False
        self.pending_tag = None
        self.pending_val = None
        self.loop = None

    @pyqtSlot()
    def ready(self):
        self.ready_flag = True
        if self.loop is not None:
            self.loop.quit()

    @pyqtSlot(str, float)
    def report(self, tag, js_ms):
        if self.pending_tag == tag:
            self.pending_val = js_ms
            if self.loop is not None:
                self.loop.quit()


class BenchWin(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(u"B 方案 · WebEngine")
        self.resize(560, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self.view = QWebEngineView(self)
        lay.addWidget(self.view)

        self.bridge = Bridge()
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.boot_ms = None
        self.result = {}

    # ---------- 等 JS 回调 ----------
    def call_and_wait(self, js, tag, timeout_ms=180000):
        self.bridge.pending_tag = tag
        self.bridge.pending_val = None
        loop = QEventLoop()
        self.bridge.loop = loop
        QTimer.singleShot(timeout_ms, loop.quit)
        t0 = time.perf_counter()
        self.view.page().runJavaScript(js)
        loop.exec_()
        rtt = (time.perf_counter() - t0) * 1000.0
        self.bridge.loop = None
        self.bridge.pending_tag = None
        return rtt, self.bridge.pending_val

    def wait_ready(self, timeout_ms=180000):
        loop = QEventLoop()
        self.bridge.loop = loop
        QTimer.singleShot(timeout_ms, loop.quit)
        while not self.bridge.ready_flag and loop.isRunning():
            loop.exec_()
        self.bridge.loop = None
        return self.bridge.ready_flag

    def run(self):
        self.show()
        self.view.load(QUrl.fromLocalFile(PAGE))
        ok = self.wait_ready()
        self.boot_ms = (time.perf_counter() - T_START) * 1000.0
        if not ok:
            print("RESULT_JSON " + json.dumps(
                {"scheme": "B_webengine", "ok": False, "error": "channel not ready",
                 "boot_ms": round(self.boot_ms, 1)}, ensure_ascii=False))
            return

        r1, j1 = self.call_and_wait("buildCards(%d)" % N_CARDS, "build")
        r2, j2 = self.call_and_wait("burstText(%d)" % ROUNDS_TEXT, "text")
        r3, j3 = self.call_and_wait("burstSwitch(%d)" % ROUNDS_SWITCH, "switch")

        n_text = N_CARDS * ROUNDS_TEXT
        n_sw = N_CARDS * ROUNDS_SWITCH
        self.result = {
            "scheme": "B_webengine",
            "ok": True,
            "cards": N_CARDS,
            "qtwebengine": _qwe_version(),
            "boot_ms": round(self.boot_ms, 1),
            "T1_rtt_ms": round(r1, 2),
            "T1_js_ms": round(j1 or -1, 2),
            "T1_per_card_js_ms": round((j1 or 0) / N_CARDS, 4),
            "T2_rtt_ms": round(r2, 2),
            "T2_js_ms": round(j2 or -1, 2),
            "T2_text_ops": n_text,
            "T2_text_us_per_op_js": round((j2 or 0) * 1000.0 / n_text, 2),
            "T3_rtt_ms": round(r3, 2),
            "T3_js_ms": round(j3 or -1, 2),
            "T3_switch_ops": n_sw,
            "T3_switch_us_per_op_js": round((j3 or 0) * 1000.0 / n_sw, 2),
            "overhead_T2_ms": round(r2 - (j2 or 0), 2),
            "overhead_T3_ms": round(r3 - (j3 or 0), 2),
            "qwe_processes": _count_qwe_procs(),
            "rss_mb": _rss_mb(),
        }
        print("RESULT_JSON " + json.dumps(self.result, ensure_ascii=False))
        sys.stdout.flush()


def _qwe_version():
    try:
        from PyQt5.QtCore import QT_VERSION_STR
        return "PyQtWebEngine 5.15.7 / Qt " + QT_VERSION_STR
    except Exception:
        return "unknown"


def _count_qwe_procs():
    """QtWebEngine 是 Chromium 多进程模型，数一下起了几个进程。"""
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq QtWebEngineProcess.exe", "/NH"],
            capture_output=True, text=True, timeout=20)
        return out.stdout.lower().count("qtwebengineprocess.exe")
    except Exception:
        return None


def _rss_mb():
    try:
        import ctypes, ctypes.wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.wintypes.DWORD),
                        ("PageFaultCount", ctypes.wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return round(pmc.WorkingSetSize / 1024.0 / 1024.0, 1)
    except Exception:
        return None


def main():
    app = QApplication(sys.argv)
    win = BenchWin()
    win.run()
    QTimer.singleShot(300, app.quit)
    rc = app.exec_()
    sys.exit(rc)


if __name__ == "__main__":
    main()
