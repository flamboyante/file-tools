# -*- coding: utf-8 -*-
r"""console 页出图：已连接 + 命令回显 + 提示着色（浅/深）。

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\shot_console.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt5.QtCore import QTimer, QEventLoop
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase

from fake_device import DeviceMedia
from uicmp.apps.console_app import ConsoleApp

OUT = os.path.join(_ROOT, 'docs', 'gui_ng')
os.makedirs(OUT, exist_ok=True)

DEMO = [
    ('[√] 已连接 COM3\n', 'done'),
    ('version\n', None),
    ('BMU_FW v3.3.0-rc2  2026-09-20 14:22\n', None),
    ('build: M2S / ycyk422 / refactor-ready\n', None),
    ('help\n', None),
    ('commands: version | reg <addr> | flash <slot> | reset | trace on\n', None),
    ('reg 0x1A\n', None),
    ('reg[0x1A] = 0x00 0x8F 0x5C 0x21\n', None),
    ('[!] trace 通道未使能，已忽略\n', 'failed'),
    ('flash BMU_UPDATE\n', None),
    ('ready, waiting for refactor begin...\n', None),
]


def settle(ms=700):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')

    w = ConsoleApp()
    w.resize(760, 560)
    w.show()
    w.session.open('FAKE', media=DeviceMedia())
    for text, kind in DEMO:
        w._append_text(text, kind)
    settle()
    w.grab().save(os.path.join(OUT, 'console_light.png'))

    w.toggle_theme()
    settle()
    w.grab().save(os.path.join(OUT, 'console_dark.png'))
    print('saved console_light.png / console_dark.png')


if __name__ == '__main__':
    main()
