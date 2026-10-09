# -*- coding: utf-8 -*-
"""用不同 Chromium flag 组合试探，找出让 loadFinished 能正常回传的配置。

用法：
    python probe_flags.py           # 父进程：逐个组合起子进程
    python probe_flags.py child     # 子进程：跑一次最小加载，打印结果

子进程最小化：setHtml('<h1>hello</h1>')，12s 硬超时。
只要 loadFinished 触发就算 PASS。
"""
import json
import os
import subprocess
import sys
import time

CHILD_TIMEOUT = 40          # 子进程 wall-clock 上限（秒）
LOAD_TIMEOUT_S = 12         # 页内等待 loadFinished 的上限

COMBOS = [
    ("baseline", ""),
    ("disable-gpu", "--disable-gpu"),
    ("no-sandbox", "--no-sandbox"),
    ("gpu+nosandbox", "--disable-gpu --no-sandbox"),
    ("single-process", "--single-process"),
    ("gpu+nosandbox+single", "--disable-gpu --no-sandbox --single-process"),
    ("in-process-gpu", "--disable-gpu --in-process-gpu --no-sandbox"),
    ("sw-raster-off", "--disable-gpu --disable-software-rasterizer --no-sandbox"),
]


def child():
    from PyQt5.QtCore import QUrl, QTimer, QEventLoop, Qt
    from PyQt5.QtWidgets import QApplication

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication([])
    from PyQt5.QtWebEngineWidgets import QWebEngineView

    view = QWebEngineView()
    view.resize(400, 300)
    view.show()

    st = {"fin": False, "ok": None, "prog": -1, "js": "no-callback"}
    loop = QEventLoop()

    def on_fin(ok):
        st["fin"] = True
        st["ok"] = bool(ok)
        loop.quit()

    def on_prog(p):
        st["prog"] = p

    view.loadFinished.connect(on_fin)
    view.loadProgress.connect(on_prog)
    QTimer.singleShot(LOAD_TIMEOUT_S * 1000, loop.quit)
    view.setHtml(u"<h1>hello</h1>", QUrl("about:blank"))
    loop.exec_()

    # JS 回调能不能回来
    got = []
    view.page().runJavaScript("1+1", lambda v: (st.update({"js": v}), got.append(1)))
    q = QEventLoop()
    QTimer.singleShot(4000, q.quit)
    while not got and q.isRunning():
        q.exec_()

    print("CHILD_RESULT " + json.dumps({"loadFinished": st["fin"], "ok": st["ok"],
                                        "progress": st["prog"], "js": st["js"]},
                                       ensure_ascii=False))
    sys.stdout.flush()
    QTimer.singleShot(100, app.quit)
    app.exec_()


def parent():
    me = os.path.abspath(__file__)
    py = sys.executable
    results = []
    for name, flags in COMBOS:
        env = dict(os.environ)
        if flags:
            env["QTWEBENGINE_CHROMIUM_FLAGS"] = flags
        else:
            env.pop("QTWEBENGINE_CHROMIUM_FLAGS", None)
        # 抑制 Chromium 的啰嗦日志
        env["QTWEBENGINE_CHROMIUM_FLAGS"] = (env.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
                                             + " --log-level=3").strip()
        t0 = time.perf_counter()
        status = "?"
        payload = ""
        try:
            p = subprocess.run([py, me, "child"], capture_output=True, text=True,
                               timeout=CHILD_TIMEOUT, env=env)
            out = (p.stdout or "") + (p.stderr or "")
            for line in out.splitlines():
                if line.startswith("CHILD_RESULT "):
                    payload = line[len("CHILD_RESULT "):]
            status = "exit=%d" % p.returncode
        except subprocess.TimeoutExpired:
            status = "TIMEOUT"
        wall = (time.perf_counter() - t0) * 1000
        rec = {"combo": name, "flags": flags or "(none)", "status": status,
               "wall_ms": round(wall, 1)}
        if payload:
            try:
                rec.update(json.loads(payload))
            except Exception:
                rec["raw"] = payload
        results.append(rec)
        sys.stderr.write(">> %-22s %-8s fin=%-5s prog=%-4s js=%-12s %.0fms\n" % (
            name, status, rec.get("loadFinished"), rec.get("progress"),
            rec.get("js"), wall))
        sys.stderr.flush()

    with open(os.path.join(os.path.dirname(me), "flag_matrix.json"), "w",
              encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("FLAG_MATRIX_DONE")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "child":
        child()
    else:
        parent()
