# -*- coding: utf-8 -*-
"""最小探针：QWebEngineView 在本机到底能不能起来。

分阶段打日志到 stderr，硬超时自动退出，结果写入 probe_result.json。
任何一步卡住都能从日志看出来卡在哪。
"""
import json
import os
import sys
import time
import traceback

T0 = time.perf_counter()
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "probe_result.json")
LOG = []


def log(msg):
    line = "[%7.0fms] %s" % ((time.perf_counter() - T0) * 1000, msg)
    LOG.append(line)
    sys.stderr.write(line + "\n")
    sys.stderr.flush()
    _dump()


def _dump(extra=None):
    try:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({"log": LOG, "result": extra or {}}, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def main():
    log("start, python %s" % sys.version.split()[0])

    # 0) 二进制在不在
    try:
        import PyQt5
        base = os.path.dirname(PyQt5.__file__)
        log("PyQt5 dir = %s" % base)
    except Exception as e:
        log("PyQt5 import failed: %r" % e)

    try:
        import PyQt5.QtWebEngineWidgets as w
        log("import QtWebEngineWidgets OK -> %s" % getattr(w, "__file__", "?"))
    except Exception as e:
        log("import QtWebEngineWidgets FAILED: %r" % e)
        _dump({"stage": "import_failed"})
        return

    from PyQt5.QtCore import QUrl, QTimer, Qt
    from PyQt5.QtWidgets import QApplication

    log("creating QApplication")
    try:
        QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    except Exception as e:
        log("setAttribute warn: %r" % e)
    app = QApplication(sys.argv)
    log("QApplication OK")

    from PyQt5.QtWebEngineWidgets import QWebEngineView
    log("creating QWebEngineView")
    view = QWebEngineView()
    log("QWebEngineView OK")

    state = {"loaded": False, "pct": -1, "procs": None}

    def on_load(ok):
        state["loaded"] = bool(ok)
        log("loadFinished ok=%s" % ok)

    def on_prog(p):
        if p != state["pct"]:
            state["pct"] = p
            log("loadProgress %d%%" % p)

    view.loadFinished.connect(on_load)
    view.loadProgress.connect(on_prog)

    html = os.path.join(HERE, "card_page.html")
    log("loading %s" % html)
    view.resize(500, 600)
    view.show()
    view.load(QUrl.fromLocalFile(html))

    # 硬超时 45s
    def bail():
        log("HARD TIMEOUT, loaded=%s pct=%s" % (state["loaded"], state["pct"]))
        _final(app, state)

    QTimer.singleShot(45000, bail)

    def check():
        if state["loaded"]:
            log("loaded, waiting 1.5s for render")
            QTimer.singleShot(1500, lambda: _final(app, state))

    t = QTimer()
    t.timeout.connect(check)
    t.start(200)

    app.exec_()


def _final(app, state):
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq QtWebEngineProcess.exe", "/NH"],
            capture_output=True, text=True, timeout=20)
        state["procs"] = out.stdout.lower().count("qtwebengineprocess.exe")
        log("QtWebEngineProcess count = %s" % state["procs"])
    except Exception as e:
        log("proc count failed: %r" % e)
    log("total elapsed %.0fms" % ((time.perf_counter() - T0) * 1000))
    _dump({"stage": "done", "loaded": state["loaded"], "pct": state["pct"],
           "procs": state["procs"], "total_ms": round((time.perf_counter() - T0) * 1000, 1)})
    app.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("EXCEPTION:\n" + traceback.format_exc())
        _dump({"stage": "exception"})
