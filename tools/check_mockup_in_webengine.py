# -*- coding: utf-8 -*-
"""把 ui_mockup_v3.html 直接丢进 QWebEngine，看它自己能渲染成什么样。

目的：回答「B 方案能不能 100% 还原 v3」——
先看 v3 本身在当前 Chromium 内核下有多少 CSS 跑不动。
"""
import json
import os
import sys

os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = (
    '--disable-features=TSFImeSupport --disable-gpu --no-sandbox')

import PyQt5.QtWebEngineWidgets                                     # noqa: E402
from PyQt5.QtWidgets import QApplication                            # noqa: E402
from PyQt5.QtCore import QUrl, QTimer, QEventLoop                   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'docs', 'ui_three_way')
MOCK = r'C:\heike\md\pythonProjectV3.3.0_beta\docs\ui_mockup\ui_mockup_v3.html'

app = QApplication(sys.argv[:1])
w = PyQt5.QtWebEngineWidgets.QWebEngineView()
w.resize(1440, 980)
w.load(QUrl.fromLocalFile(MOCK))
w.show()

loop = QEventLoop()
scan_js = open(os.path.join(HERE, '_css_scan.js'), encoding='utf-8').read()


def phase1():
    """截图 + 注入扫描"""
    p = os.path.join(OUT, 'mockup_v3_in_qwebengine.png')
    ok = w.grab().save(p, 'PNG')
    print('  v3 在 QWebEngine 里的截图 -> %s  (%s)'
          % (os.path.basename(p), 'OK' if ok else 'FAIL'))
    w.page().runJavaScript(scan_js)
    QTimer.singleShot(900, phase2)


def phase2():
    t = w.title()
    try:
        d = json.loads(t)
        print()
        print('  检查了 %d 条 CSS 声明，其中 **%d 条当前内核不支持**' % (d['total'], d['unsupported']))
        if d.get('notes'):
            print('  备注:', d['notes'])
        if d['list']:
            print()
            print('  === 不支持的声明 ===')
            for line in d['list']:
                print('   ', line)
        else:
            print('  （无）')
    except Exception as e:
        print('  解析失败:', e)
        print('  原始 title:', t[:400])
    loop.quit()


QTimer.singleShot(3500, phase1)
QTimer.singleShot(30000, loop.quit)
loop.exec_()
