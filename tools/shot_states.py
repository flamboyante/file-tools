# -*- coding: utf-8 -*-
r"""状态预览图：五状态任务 + 已连接态 + 进度条状态色（浅/深）。

用途：色板与交互的验收图。改色板/按钮态后跑一遍，输出到 docs/gui_ng/。
跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\shot_states.py
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt5.QtCore import QTimer, QEventLoop
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase

from fake_device import DeviceMedia
from uicmp.apps.transfer_app import TransferApp
from uicmp.guicore.transfer_queue import (TransferTask, T_PENDING, T_RUNNING,
                                          T_DONE, T_FAILED, T_SKIPPED)

OUT = os.path.join(_ROOT, 'docs', 'gui_ng')
os.makedirs(OUT, exist_ok=True)


def settle(ms=700):
    """等 qfluentwidgets 入场动画稳定（不等会截出假缺失，实测坑）。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')

    d = tempfile.mkdtemp()
    files = []
    for i in range(5):
        p = os.path.join(d, 'part_%d.bin' % i)
        with open(p, 'wb') as f:
            f.write(bytes(4096))
        files.append(p)

    w = TransferApp()
    w.resize(1180, 640)
    w.show()

    # 五个状态各一行（进度条颜色应分别为 灰/蓝/绿/红/浅灰）
    for i, st in enumerate((T_PENDING, T_RUNNING, T_DONE, T_FAILED, T_SKIPPED)):
        t = TransferTask(file_path=files[i], total=4096,
                         flash_value=0xFB, mem_value=0x06)
        t.status = st
        if st == T_RUNNING:
            t.transferred = 2048
        if st == T_DONE:
            t.transferred = 4096
        if st == T_FAILED:
            t.transferred = 1536
            t.error = '示例：等待 data 应答超时（1.5s）'
        w.queue.tasks.append(t)
    w._refresh_table()

    # 注入假链路并打开 → 「断开」浅蓝按钮 + 已连接徽章 + 主按钮让位给「开始」
    w.link.open('FAKE', media=DeviceMedia())
    w._set_running_ui(True)          # 运行中按钮态（暂停/停止可用）
    settle()
    w.grab().save(os.path.join(OUT, 'state_palette_light.png'))

    w.toggle_theme()
    settle()
    w.grab().save(os.path.join(OUT, 'state_palette_dark.png'))
    print('saved state_palette_light.png / state_palette_dark.png')


if __name__ == '__main__':
    main()
