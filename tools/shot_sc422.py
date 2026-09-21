# -*- coding: utf-8 -*-
r"""sc422 页出图：模拟一轮心跳问答（TX/RX 双色 + 时间戳），浅/深。

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\shot_sc422.py
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
from uicmp.guicore.serial_link import SerialLink
from uicmp.guicore.sc422_session import Sc422Session
from uicmp.apps.sc422_app import Sc422App

OUT = os.path.join(_ROOT, 'docs', 'gui_ng')
os.makedirs(OUT, exist_ok=True)

HEARTBEAT = 'EB 90 01 80 C0 00 00 01 00 1D FE A0'
HB_ACK = bytes.fromhex('1ACF0187C0000001001FFE97')
VERSION_REQ = 'EB 90 01 80 C0 00 00 01 01 01 FF B9'


def settle(ms=700):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')

    link = SerialLink()
    link.open('FAKE', media=DeviceMedia())
    win = Sc422App(session=Sc422Session(link))
    win.resize(900, 640)
    win.show()

    # 一轮心跳问答 + 一次版本查询
    win.input.setPlainText(HEARTBEAT)
    for _ in range(2):
        win._send()
        win._on_rx(HB_ACK)
    win.input.setPlainText(VERSION_REQ)
    win._send()
    win._on_rx(bytes.fromhex('1ACF0187C0000002015A00FE53'))
    settle()
    win.grab().save(os.path.join(OUT, 'sc422_light.png'))

    win.toggle_theme()
    settle()
    win.grab().save(os.path.join(OUT, 'sc422_dark.png'))
    print('saved sc422_light.png / sc422_dark.png')


if __name__ == '__main__':
    main()
