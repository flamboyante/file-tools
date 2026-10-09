# -*- coding: utf-8 -*-
"""定位 loadFinished 不触发的根因：三种页面形态逐一试。

V1  setHtml 最小页面（无任何外部资源）
V2  setHtml + qrc 加载 qwebchannel.js
V3  file:// 加载 card_page.html（完整版）
V4  file:// 加载 card_page_nocore.html（去掉 QWebChannel，只留纯 HTML/CSS）

每个变体独立计时，20s 硬超时。结论写进 variant_result.json。
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "variant_result.json")

from PyQt5.QtCore import QUrl, QTimer, QEventLoop, Qt
from PyQt5.QtWidgets import QApplication

QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
app = QApplication(sys.argv)

from PyQt5.QtWebEngineWidgets import QWebEngineView

RESULTS = []

PLAIN = u"<!DOCTYPE html><html><body><h1>hello</h1></body></html>"
WITH_QRC = (u"<!DOCTYPE html><html><body><h1>hello</h1>"
            u"<script src=\"qrc:///qtwebchannel/qwebchannel.js\"></script>"
            u"<script>window.__hasQt = (typeof qt !== 'undefined');</script>"
            u"</body></html>")


def wait_load(view, how, arg, timeout_s=20):
    rec = {"variant": how, "target": arg if len(str(arg)) < 60 else "<inline>",
           "finished": False, "ok": None, "elapsed_ms": None, "progress_max": -1,
           "has_qt": None}
    t0 = time.perf_counter()
    loop = QEventLoop()

    def on_fin(ok):
        rec["finished"] = True
        rec["ok"] = bool(ok)
        loop.quit()

    def on_prog(p):
        if p > rec["progress_max"]:
            rec["progress_max"] = p

    view.loadFinished.connect(on_fin)
    view.loadProgress.connect(on_prog)
    QTimer.singleShot(int(timeout_s * 1000), loop.quit)

    if how == "setHtml":
        view.setHtml(arg, QUrl("about:blank"))
    else:
        view.load(QUrl.fromLocalFile(arg))

    loop.exec_()
    rec["elapsed_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    try:
        view.loadFinished.disconnect(on_fin)
        view.loadProgress.disconnect(on_prog)
    except Exception:
        pass

    # 问一下 JS 环境
    probe_done = []
    view.page().runJavaScript("(typeof qt !== 'undefined')",
                              lambda v: (rec.update({"has_qt": v}), probe_done.append(1)))
    q = QEventLoop()
    QTimer.singleShot(3000, q.quit)
    while not probe_done and q.isRunning():
        q.exec_()
    return rec


view = QWebEngineView()
view.resize(500, 600)
view.show()
QApplication.processEvents()

# V1
RESULTS.append(wait_load(view, "setHtml", PLAIN))
# V2
RESULTS.append(wait_load(view, "setHtml", WITH_QRC))
# V3
p3 = os.path.join(HERE, "card_page.html")
RESULTS.append(wait_load(view, "file", p3))
# V4
p4 = os.path.join(HERE, "card_page_nocore.html")
if os.path.exists(p4):
    RESULTS.append(wait_load(view, "file", p4))
else:
    RESULTS.append({"variant": "file", "target": "card_page_nocore.html",
                    "skipped": "file not found"})

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(RESULTS, f, ensure_ascii=False, indent=1)

for r in RESULTS:
    sys.stderr.write("VARIANT " + json.dumps(r, ensure_ascii=False) + "\n")
sys.stderr.flush()
print("DONE")
QTimer.singleShot(200, app.quit)
app.exec_()
