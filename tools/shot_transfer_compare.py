# -*- coding: utf-8 -*-
"""对比图：旧 BatchFlashDownWindow vs 新 TransferApp（offscreen 截图）。

为了公平：两边都塞 3 个任务。
输出：docs/gui_ng/compare_transfer.png
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtCore import QTimer, QEventLoop

OUT = os.path.join(_ROOT, 'docs', 'gui_ng')
os.makedirs(OUT, exist_ok=True)


def settle(ms=700):
    """等 qfluentwidgets 入场动画/布局稳定再 grab——
    否则连接条等控件会因渲染未完成从截图里消失（实测伪影）。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def mk_files(n=3):
    d = tempfile.mkdtemp()
    paths = []
    for i in range(n):
        p = os.path.join(d, 'firmware_%d.bin' % i)
        with open(p, 'wb') as f:
            f.write(bytes(2048))
        paths.append(p)
    return paths


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    files = mk_files(3)

    shots = {}

    # ---- 旧批量窗口
    try:
        from UIClass.BatchFlashDownWindow import BatchFlashDownWindow
        old = BatchFlashDownWindow()
        old.add_files(files)
        old.resize(1180, 660)
        old.show()
        settle()
        old.grab().save(os.path.join(OUT, 'old_batch.png'))
        shots['old'] = 'old_batch.png'
        old.close()
    except Exception as e:
        print('旧窗口截图失败:', type(e).__name__, e)

    # ---- 新 transfer_app：空态 → 有任务（浅）→ 深色
    from uicmp.apps.transfer_app import TransferApp
    new = TransferApp()
    new.resize(1180, 660)
    new.show()
    settle()
    new.grab().save(os.path.join(OUT, 'new_transfer_empty.png'))
    shots['new_empty'] = 'new_transfer_empty.png'

    new.add_files(files)
    settle()
    new.grab().save(os.path.join(OUT, 'new_transfer_light.png'))
    shots['new_light'] = 'new_transfer_light.png'

    new.toggle_theme()
    settle()
    new.grab().save(os.path.join(OUT, 'new_transfer_dark.png'))
    shots['new_dark'] = 'new_transfer_dark.png'
    new.close()

    print('saved:', shots)
    return shots


if __name__ == '__main__':
    main()
