# -*- coding: utf-8 -*-
"""渲染 A / B 方案窗口并出图。

用法: python tools/shot.py    (默认 all)
      python tools/shot.py a   (A 方案)
      python tools/shot.py b   (B 方案)

出图条件的差别（踩过，写死在这里）：
  A：offscreen 平台即可，但 **必须手动加载字体文件** ——
     offscreen 下 QFontDatabase().families() == 0，不加载就一个字都没有。
  B：**必须真实平台** —— offscreen 下 Chromium 直接 Segmentation fault；
     且需要 QTimer 链式调度 + QEventLoop（processEvents 轮询不出图）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)                      # 关键：ECAN.open 用 os.getcwd() 找 DLL

os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS',
                      '--disable-features=TSFImeSupport --disable-gpu --no-sandbox')

_WANT = (sys.argv[1] if len(sys.argv) > 1 else 'all').lower()

if _WANT in ('b', 'all'):
    # WebEngine 在 offscreen 平台下会 Segmentation fault，必须用真实平台
    os.environ.pop('QT_QPA_PLATFORM', None)
else:
    # A 是纯 Qt 绘制，offscreen 下 grab() 就能出图（但要手动加载字体）
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication          # noqa: E402
from PyQt5.QtCore import QTimer                   # noqa: E402

OUT = os.path.join(ROOT, 'docs', 'ui_three_way')
os.makedirs(OUT, exist_ok=True)

W, H = 1280, 900


def _load_fonts():
    """offscreen 平台下 Qt 的字体库是空的（families() == 0），必须手动加载，
    否则**整张图一个字都画不出来**（框在、字没了）。真实桌面环境不需要。"""
    from PyQt5.QtGui import QFontDatabase
    n = 0
    for f in ('msyh.ttc', 'msyhbd.ttc', 'msyhl.ttc', 'consola.ttf',
              'simsun.ttc', 'segoeui.ttf', 'arial.ttf'):
        p = 'C:/Windows/Fonts/' + f
        if os.path.exists(p) and QFontDatabase.addApplicationFont(p) >= 0:
            n += 1
    print('  已加载字体文件 %d 个（offscreen 必需）' % n)


def _prime_a(w):
    """给 A 方案造统一状态：两个通道都开、各发一次、展开第一张卡的帧明细。"""
    w.resize(W, H)
    w.show()
    for _ in range(6):
        QApplication.processEvents()
    try:
        w._on_bus_toggle(core_chan('A'))
        w._on_bus_toggle(core_chan('B'))
        for _ in range(6):
            QApplication.processEvents()
        if w.cmds['A']:
            w._pick(0)
            w._send(0)
        if w._cards:
            w._cards[0].set_open(True)
        for _ in range(8):
            QApplication.processEvents()
    except Exception as e:
        print('  prime warn:', e)


def core_chan(ch):
    return ch


def shot_a(app):
    import time as _t
    from uicmp import core
    from uicmp.impl_a_fluent import AWindow
    w = AWindow(mode=core.Mode.SIM)
    _prime_a(w)
    for dark in (False, True):
        w._dark = dark
        w._apply_theme()          # 内部会「先重建再上色」，顺序已修正
        for _ in range(8):
            QApplication.processEvents()
        _t.sleep(0.30)
        for _ in range(8):
            QApplication.processEvents()
        if w._cards:              # 重建后展开状态会丢，重新展开
            w._cards[0].set_open(True)
        for _ in range(6):
            QApplication.processEvents()
        p = os.path.join(OUT, 'shot_a_%s.png' % ('dark' if dark else 'light'))
        ok = w.grab().save(p)
        print('  A %-5s -> %s  %s' % (dark, os.path.basename(p), 'OK' if ok else 'FAIL'))
    w._dark = False
    w._apply_theme()
    for _ in range(4):
        QApplication.processEvents()
    w.close()


def shot_b(app):
    """B 方案出图。

    WebEngine 不能用 processEvents() 轮询凑合 —— 它需要**真实事件循环**
    让 Chromium 合成器产出像素。这里用 QTimer 链式调度 + QEventLoop，
    并在 QTimer 回调里调 view.grab()。
    """
    from PyQt5.QtCore import QEventLoop
    from uicmp import core
    from uicmp.impl_b_web import BWindow

    w = BWindow(mode=core.Mode.SIM)
    w.resize(W, H)
    w.show()

    loop = QEventLoop()

    def step1():
        try:
            w.do_toggle_bus('A')
            w.do_toggle_bus('B')
            if w.cmds['A']:
                w.do_send('A', 0)
            if w.cmds['B']:
                w.do_send('B', 0)
            # 展开第一张卡，让帧明细露出来（和 v3 mockup 的默认状态一致）
            w._js("openSet['A-0']=true; renderTab();")
        except Exception as e:
            print('  prime warn:', e)
        QTimer.singleShot(1500, step2)

    def step2():
        p = os.path.join(OUT, 'shot_b_light.png')
        ok = w.view.grab().save(p, 'PNG')
        print('  B light -> %s  %s' % (os.path.basename(p), 'OK' if ok else 'FAIL'))
        w.do_toggle_theme()
        QTimer.singleShot(1500, step3)

    def step3():
        p = os.path.join(OUT, 'shot_b_dark.png')
        ok = w.view.grab().save(p, 'PNG')
        print('  B dark  -> %s  %s' % (os.path.basename(p), 'OK' if ok else 'FAIL'))
        loop.quit()

    QTimer.singleShot(3400, step1)
    QTimer.singleShot(45000, loop.quit)      # 兜底，防止永不退出
    loop.exec_()
    w.close()


def main():
    which = (sys.argv[1] if len(sys.argv) > 1 else 'all').lower()
    if which in ('b', 'all'):
        # ⚠️ QtWebEngineWidgets 必须在 QCoreApplication 创建**之前**导入，
        #    否则 Qt 直接抛 ImportError（不是警告，是硬失败）
        import PyQt5.QtWebEngineWidgets          # noqa: F401
    app = QApplication(sys.argv[:1])
    _load_fonts()
    if which in ('a', 'all'):
        shot_a(app)
    if which in ('b', 'all'):
        shot_b(app)
    print('done ->', OUT)


if __name__ == '__main__':
    main()
