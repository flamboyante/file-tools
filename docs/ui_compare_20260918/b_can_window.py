# -*- coding: utf-8 -*-
"""B 方案宿主：PyQt5 + QWebEngineView + QWebChannel，承载 b_can_window.html。

模式：
    python b_can_window.py            # 交互运行（给人看）
    python b_can_window.py --bench    # 效率测试，打印 RESULT_JSON 后退出
    python b_can_window.py --shot     # 截图浅色/深色

⚠️ 无交互式桌面的会话必须禁用 TSF，否则 Chromium 渲染进程会
   FATAL:tsf_text_store.cc(52) Failed to initialize CategoryMgr 直接崩溃。
   正常桌面环境不需要，故仅在未显式设置时才注入。

⚠️ 两条 QWebChannel 硬约束（实测踩出来的）：
   1. JS -> Python 的方法调用**拿不到返回值**（qwebchannel.js 只发 invokeMethod
      消息，不同步等回包）。所有「JS 要数据」必须走 Python 用 signal 回推。
   2. Python 侧调 runJavaScript 必须发生在**事件循环内部**，循环外调用会被丢弃。
"""
import json
import os
import subprocess
import sys
import time

T_START = time.perf_counter()
HERE = os.path.dirname(os.path.abspath(__file__))
MODE = " ".join(sys.argv[1:])

if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--disable-features=TSFImeSupport --disable-gpu --no-sandbox")

from PyQt5.QtCore import QUrl, QTimer, QEventLoop, pyqtSlot, QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QApplication

QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
app = QApplication(sys.argv)

from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView

# ---------------- 假指令数据（40 条，模拟真实规模）----------------
BASE = [
    ("快遥 FAST", "A", "1 帧", "IRCode 00 5A", 500),
    ("慢遥 SLOW1", "A", "1 帧", "IRCode 00 AA", 500),
    ("慢遥 SLOW2", "A", "1 帧", "IRCode 00 AB", 500),
    ("慢遥 SLOW3", "A", "1 帧", "IRCode 00 AC", 500),
    ("时间同步 TIME", "A", "1 帧", "ID 0x1E7E0000", 1000),
    ("姿态 ATTITUDE", "A", "6 帧", "ID 0x1E2E0000", 500),
    ("星敏感器 STAR", "A", "5 帧", "ID 0x1E160000", 100),
    ("星敏感器 WGS84", "A", "5 帧", "ID 0x1E160000", 100),
    ("BUS 总线帧", "B", "1 帧", "IRCode 00 25 25", 500),
    ("星敏感器 STAR", "B", "5 帧", "ID 0x1E160000", 100),
    ("姿态 ATTITUDE", "B", "6 帧", "ID 0x1E2E0000", 500),
    ("慢遥 SLOW1", "B", "1 帧", "IRCode 00 AA", 500),
]


def build_commands(n=40):
    out, i = [], 0
    while len(out) < n:
        name, ch, frames, ircode, iv = BASE[i % len(BASE)]
        if i >= len(BASE):
            name = "%s #%d" % (name, i // len(BASE) + 1)
        enabled = (len(out) % 7 == 0)
        badge, cls = (("运行中", "run") if enabled else
                      ("失败", "err") if len(out) % 11 == 5 else
                      ("待发送", "pend") if len(out) % 5 == 3 else ("已停止", "gray"))
        out.append({"name": name, "channel": ch,
                    "sub": "ch=%s · 无限次 · %dms" % (ch, iv),
                    "chips": ["间隔 %dms" % iv, frames, ircode],
                    "badge": badge, "badge_cls": cls, "enabled": enabled})
        i += 1
    return out


COMMANDS = build_commands(40)


class Bridge(QObject):
    framePushed = pyqtSignal(str)       # Python -> JS
    commandsReady = pyqtSignal(str)     # Python -> JS

    def __init__(self):
        super(Bridge, self).__init__()
        self.n_cmd = 0
        self.ready_flag = False
        self._loop = None
        self._wait_tag = None
        self._js_ms = None
        # JS -> Python 吞吐计数
        self._ping_n = 0
        self._ping_got = 0

    # ---- 供 JS 调用（注意：无返回值可用）----
    @pyqtSlot()
    def requestCommands(self):
        self.commandsReady.emit(json.dumps(COMMANDS, ensure_ascii=False))

    @pyqtSlot(int)
    def ready(self, n):
        self.n_cmd = n
        self.ready_flag = True
        if self._loop is not None:
            self._loop.quit()

    @pyqtSlot(str, float)
    def report(self, tag, js_ms):
        if self._wait_tag == tag:
            self._js_ms = js_ms
            if self._loop is not None:
                self._loop.quit()

    @pyqtSlot()
    def ping(self):
        self._ping_got += 1
        if self._ping_got >= self._ping_n and self._loop is not None:
            self._loop.quit()

    @pyqtSlot(str, bool)
    def onToggle(self, name, on):
        pass

    @pyqtSlot(str)
    def onSendOnce(self, name):
        pass

    @pyqtSlot()
    def onStartAll(self):
        pass

    @pyqtSlot()
    def onStopAll(self):
        pass


class App:
    def __init__(self):
        self.view = QWebEngineView()
        self.view.resize(1200, 720)
        self.view.setWindowTitle(u"B 方案 · BMU CAN 指令控制台（WebEngine）")
        self.bridge = Bridge()
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

    # ---------- 基础：在事件循环内执行 JS 并等回调 ----------
    def _spin(self, setup, tag=None, timeout_ms=120000):
        """setup() 在事件循环内部被调用；返回 (wall_ms, js_ms)。"""
        b = self.bridge
        b._wait_tag = tag
        b._js_ms = None
        b._ping_got = 0
        loop = QEventLoop()
        b._loop = loop
        t0 = time.perf_counter()
        QTimer.singleShot(0, setup)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec_()
        wall = (time.perf_counter() - t0) * 1000.0
        b._loop = None
        b._wait_tag = None
        return wall, b._js_ms

    def boot(self):
        self.view.show()
        self.view.load(QUrl.fromLocalFile(os.path.join(HERE, "b_can_window.html")))
        loop = QEventLoop()
        self.bridge._loop = loop
        QTimer.singleShot(60000, loop.quit)
        while not self.bridge.ready_flag and loop.isRunning():
            loop.exec_()
        self.bridge._loop = None
        return self.bridge.ready_flag

    # ---------- 效率测试 ----------
    def bench(self):
        ok = self.boot()
        boot_ms = (time.perf_counter() - T_START) * 1000.0
        res = {"scheme": "B_webengine", "ok": bool(ok), "commands": self.bridge.n_cmd,
               "boot_ms": round(boot_ms, 1)}
        if not ok:
            res["note"] = "JS ready 未回调"
            print("RESULT_JSON " + json.dumps(res, ensure_ascii=False))
            return

        # T1 渲染全部卡片（JS 侧自计）
        r1, j1 = self._spin(lambda: self.view.page().runJavaScript("render()"), "render")

        # T2 批量推 500 帧：一次调用（推荐的工程做法）
        r2, j2 = self._spin(
            lambda: self.view.page().runJavaScript("pushFrames(500,'18:39:02.118')"),
            "pushFrames")

        # T3 逐帧推 500 帧：500 次独立 runJavaScript（最坏情况）
        r3, j3 = self._spin(
            lambda: self.view.page().runJavaScript("burstBegin(500)"), None, 5000)
        r3, j3 = self._spin(
            lambda: [self.view.page().runJavaScript("appendOne(%d)" % i)
                     for i in range(500)], "calls", 120000)

        # T4 JS -> Python：500 次 ping
        self.bridge._ping_n = 500
        r4, _ = self._spin(
            lambda: self.view.page().runJavaScript("pingPy(500)"), None, 60000)

        res.update({
            "T1_render_rtt_ms": round(r1, 2), "T1_render_js_ms": round(j1 or -1, 2),
            "T2_batch500_rtt_ms": round(r2, 2), "T2_batch500_js_ms": round(j2 or -1, 2),
            "T2_per_frame_js_us": round((j2 or 0) * 1000.0 / 500.0, 2),
            "T2_channel_overhead_ms": round(r2 - (j2 or 0), 2),
            "T3_500calls_rtt_ms": round(r3, 2), "T3_500calls_js_ms": round(j3 or -1, 2),
            "T3_per_frame_ms": round(r3 / 500.0, 3),
            "T4_jstopython_500_rtt_ms": round(r4, 2),
            "T4_per_event_ms": round(r4 / 500.0, 3),
            "qwe_processes": _procs(), "rss_mb": _rss(),
        })
        print("RESULT_JSON " + json.dumps(res, ensure_ascii=False))
        sys.stdout.flush()

    # ---------- 截图 ----------
    def shot(self):
        self.boot()
        QTimer.singleShot(800, self._push_demo)
        QTimer.singleShot(2600, self._shot1)

    def _push_demo(self):
        self.view.page().runJavaScript("pushFrames(14,'18:39:02.118')")
        self.view.page().runJavaScript("updateCounter(1842)")

    def _shot1(self):
        p = os.path.join(HERE, "out_b_light.png")
        self.view.grab().save(p, "PNG")
        sys.stderr.write("SAVED %s\n" % p)
        self.view.page().runJavaScript("setDark(true)")
        QTimer.singleShot(1600, self._shot2)

    def _shot2(self):
        p = os.path.join(HERE, "out_b_dark.png")
        self.view.grab().save(p, "PNG")
        sys.stderr.write("SAVED %s\n" % p)
        print("RESULT_JSON " + json.dumps(
            {"scheme": "B_webengine", "boot_ok": self.bridge.ready_flag,
             "commands": self.bridge.n_cmd, "qwe_processes": _procs()},
            ensure_ascii=False))
        sys.stdout.flush(); sys.stderr.flush()
        os._exit(0)


def _procs():
    try:
        o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq QtWebEngineProcess.exe", "/NH"],
                           capture_output=True, text=True, timeout=20, errors="replace").stdout
        return o.lower().count("qtwebengineprocess.exe")
    except Exception:
        return None


def _rss():
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
        pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return round(pmc.WorkingSetSize / 1024.0 / 1024.0, 1)
    except Exception:
        return None


_PY_FALLBACK = False


def _rss_procs_only():
    try:
        o = subprocess.run("tasklist /FI \"IMAGENAME eq python.exe\" /NH",
                           capture_output=True, text=True, timeout=20, errors="replace",
                           shell=True).stdout
        return len([l for l in o.splitlines() if "python.exe" in l.lower()])
    except Exception:
        return None


def main():
    a = App()
    if "--bench" in MODE:
        a.bench()                      # 走与 --shot 相同的路径（已验证可行）
        sys.stdout.flush(); sys.stderr.flush()
        os._exit(0)
    elif "--shot" in MODE:
        a.shot()
        QTimer.singleShot(40000, lambda: os._exit(0))
        QApplication.exec_()
    else:
        a.view.show()
        a.view.load(QUrl.fromLocalFile(os.path.join(HERE, "b_can_window.html")))
        QApplication.exec_()


if __name__ == "__main__":
    main()
