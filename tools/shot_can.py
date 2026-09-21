# -*- coding: utf-8 -*-
r"""CAN 指令台出图：模拟模式（A/B 双通道 + 定时发送 + 帧明细展开），浅/深。

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\shot_can.py
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase

from uicmp.guicore.can_session import CanSession, Mode, CHAN_A, CHAN_B
from uicmp.apps.can_app import CanApp

OUT = os.path.join(_ROOT, 'docs', 'gui_ng')
os.makedirs(OUT, exist_ok=True)


def spin(app, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        time.sleep(0.005)


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')

    ses = CanSession(mode=Mode.SIM)
    w = CanApp(session=ses)
    w.resize(1000, 780)
    w.show()
    spin(app, 0.6)

    ses.open_channel(CHAN_A)
    ses.open_channel(CHAN_B)
    spin(app, 0.2)

    # 启用三条：快遥 / 星敏感器（多帧，展开）/ 时间同步
    cmds_a = ses.commands(CHAN_A)
    for c in cmds_a:
        if c.name in ('快遥 FAST', '星敏感器 STAR', '时间同步 TIME'):
            c.enabled = True
            if 'STAR' in c.name:
                w._expanded.add(id(c))
    w._refresh_table()
    spin(app, 0.2)

    # 跑一段定时发送，制造 TX/RX 日志
    w._toggle_run()
    spin(app, 0.45)
    w.grab().save(os.path.join(OUT, 'can_light.png'))

    w.toggle_theme()
    spin(app, 0.5)
    w.grab().save(os.path.join(OUT, 'can_dark.png'))
    print('saved can_light.png / can_dark.png')


if __name__ == '__main__':
    main()
