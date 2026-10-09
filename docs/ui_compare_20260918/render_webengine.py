# -*- coding: utf-8 -*-
"""B 方案视觉渲染：QWebEngineView 加载页面并截图（浅色 + 深色）。

由于本机 loadFinished 不回传（见 probe_variants / probe_flags 结论），
这里用固定延时等渲染，不依赖 loadFinished。

用法：
    python render_webengine.py card_page_five.html  out_webengine
    python render_webengine.py <abs_or_rel_html>    <out_prefix>
"""
import json
import os
import sys
import time

T_START = time.perf_counter()
HERE = os.path.dirname(os.path.abspath(__file__))

from PyQt5.QtCore import QUrl, QTimer, Qt
from PyQt5.QtWidgets import QApplication

QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
app = QApplication(sys.argv)

from PyQt5.QtWebEngineWidgets import QWebEngineView

SETTLE_MS = 5000          # 首屏等渲染
DARK_SETTLE_MS = 2000     # 切深色后等重绘


def main():
    rel = sys.argv[1] if len(sys.argv) > 1 else "card_page_five.html"
    prefix = sys.argv[2] if len(sys.argv) > 2 else "out_webengine"
    page = rel if os.path.isabs(rel) else os.path.join(HERE, rel)
    if not os.path.exists(page):
        print("PAGE NOT FOUND: %s" % page)
        sys.exit(2)

    view = QWebEngineView()
    view.resize(660, 470)
    view.setWindowTitle("B 方案 · WebEngine")
    view.show()

    t_boot0 = time.perf_counter()
    view.load(QUrl.fromLocalFile(page))

    state = {"shot": []}

    def grab(tag):
        pm = view.grab()
        out = os.path.join(HERE, "%s_%s.png" % (prefix, tag))
        pm.save(out, "PNG")
        state["shot"].append(out)
        sys.stderr.write("SAVED %s %dx%d\n" % (out, pm.width(), pm.height()))
        sys.stderr.flush()

    def step_light():
        grab("light")
        # 切深色：mockup 的 .dark 类挂在 body 上
        view.page().runJavaScript(
            "document.body.classList.add('dark');"
            "document.documentElement.classList.add('dark');")
        QTimer.singleShot(DARK_SETTLE_MS, step_dark)

    def step_dark():
        grab("dark")
        _report()
        QTimer.singleShot(200, app.quit)

    QTimer.singleShot(SETTLE_MS, step_light)
    app.exec_()


def _report():
    import subprocess
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq QtWebEngineProcess.exe", "/NH"],
            capture_output=True, text=True, timeout=20)
        nproc = out.stdout.lower().count("qtwebengineprocess.exe")
    except Exception:
        nproc = None
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
        rss = round(pmc.WorkingSetSize / 1024.0 / 1024.0, 1)
    except Exception:
        rss = None
    rec = {"scheme": "B_webengine", "qwe_processes": nproc, "rss_mb": rss,
           "total_ms": round((time.perf_counter() - T_START) * 1000, 1)}
    print("RESULT_JSON " + json.dumps(rec, ensure_ascii=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
