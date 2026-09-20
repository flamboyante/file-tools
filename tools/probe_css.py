# -*- coding: utf-8 -*-
"""探测 Qt 5.15 QWebEngine 内嵌 Chromium 的版本与 CSS 能力。

用 document.title 回传，避开 runJavaScript 的多层转义。
"""
import json
import os
import sys

os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = (
    '--disable-features=TSFImeSupport --disable-gpu --no-sandbox')

import PyQt5.QtWebEngineWidgets                                   # noqa: E402
from PyQt5.QtWidgets import QApplication                          # noqa: E402
from PyQt5.QtCore import QUrl, QTimer, QEventLoop                 # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

app = QApplication(sys.argv[:1])
w = PyQt5.QtWebEngineWidgets.QWebEngineView()
w.resize(760, 240)
w.load(QUrl.fromLocalFile(os.path.join(HERE, '_probe_page.html')))
w.show()

loop = QEventLoop()


def ask():
    t = w.title()
    try:
        d = json.loads(t)
        print('Chromium 内核版本: %s' % d.get('chromium'))
        print()
        for k in sorted(d):
            if k == 'chromium':
                continue
            print('  %-16s %s' % (k, d[k]))
    except Exception as e:
        print('title 解析失败:', e, '| 原始:', t[:200])
    loop.quit()


QTimer.singleShot(3000, ask)
QTimer.singleShot(20000, loop.quit)
loop.exec_()
