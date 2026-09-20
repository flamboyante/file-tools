# -*- coding: utf-8 -*-
"""transfer_queue 冒烟测试（无硬件：假设备应答器）。

场景：
A. 3 任务队列（成功/失败/成功）+ SKIP 策略 → 全部跑完，汇总「完成2/失败1」
B. 同队列 + ABORT 策略 → 任务2失败后任务3标 SKIPPED，汇总「完成1/失败1/跳过1」
C. 队列中途取消 → 当前任务失败(已取消)，剩余 SKIPPED
D. 空队列 start → 直接 finished

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_transfer_queue.py
"""
import os
import sys
import time
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'tools'))

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication

from uicmp.guicore.serial_link import SerialLink
from uicmp.guicore.transfer_queue import (TransferQueue, TransferTask,
                                          T_DONE, T_FAILED, T_SKIPPED,
                                          POLICY_SKIP, POLICY_ABORT)
from fake_device import DeviceMedia

import uicmp.guicore.transfer_session as ts_mod
ts_mod.ACK_TIMEOUT = 1.0        # 缩短冒烟耗时


def spin_until(app, cond, timeout=30.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        app.processEvents()       # ⚠️ 必须在循环内：跨线程 queued 信号靠它送达
        time.sleep(0.01)
    return False


def make_queue():
    link = SerialLink()
    assert link.open('FAKE', media=DeviceMedia()) is True
    q = TransferQueue(link)
    return link, q


def statuses(q):
    return [t.status for t in q.tasks]


def main():
    app = QApplication(sys.argv)
    assert QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc') != -1

    tmp = tempfile.mkdtemp()
    ok_file = os.path.join(tmp, 'ok.bin')
    with open(ok_file, 'wb') as f:
        f.write(bytes(range(256)) * 8)          # 2048B → 2 帧
    # 「失败」任务用一个不存在的路径 → TransferSession.start 立即 failed
    # （比 force_status/mute 的时序控制更确定）
    bad_file = os.path.join(tmp, 'missing.bin')

    def mk_tasks():
        return [TransferTask(file_path=ok_file, flash_value=0xFB, mem_value=0x06),
                TransferTask(file_path=bad_file, flash_value=0xFB, mem_value=0x06),
                TransferTask(file_path=ok_file, flash_value=0xFB, mem_value=0x06)]

    def run_queue(policy, tasks):
        link, q = make_queue()
        box = {'summary': None}
        q.queue_finished.connect(lambda s: box.__setitem__('summary', s))
        assert q.start(tasks, policy=policy) is True
        assert spin_until(app, lambda: box['summary'] is not None), \
            '队列未结束: %r' % statuses(q)
        return box, q, link

    # ---- A. SKIP 策略：失败跳过，后续继续
    box, q, link = run_queue(POLICY_SKIP, mk_tasks())
    st = statuses(q)
    assert st == [T_DONE, T_FAILED, T_DONE], 'SKIP 状态机错误: %r' % st
    assert '完成 2' in box['summary'] and '失败 1' in box['summary'], box['summary']
    print('A. SKIP 策略 OK:', st, box['summary'])
    link.close()

    # ---- B. ABORT 策略：失败即停，剩余跳过
    link, q = make_queue()
    tasks = mk_tasks()
    box = {'summary': None}
    q.queue_finished.connect(lambda s: box.__setitem__('summary', s))
    assert q.start(tasks, policy=POLICY_ABORT) is True
    assert spin_until(app, lambda: box['summary'] is not None)
    st = statuses(q)
    assert st == [T_DONE, T_FAILED, T_SKIPPED], 'ABORT 状态机错误: %r' % st
    assert '跳过 1' in box['summary'], box['summary']
    print('B. ABORT 策略 OK:', st, box['summary'])
    link.close()

    # ---- C. 中途取消
    big = os.path.join(tmp, 'big.bin')
    with open(big, 'wb') as f:
        f.write(bytes(200 * 1024))
    link, q = make_queue()
    tasks = [TransferTask(file_path=big, flash_value=0xFB, mem_value=0x06),
             TransferTask(file_path=ok_file, flash_value=0xFB, mem_value=0x06)]
    box = {'summary': None}
    q.queue_finished.connect(lambda s: box.__setitem__('summary', s))
    q.start(tasks, policy=POLICY_SKIP)
    # 等第一个任务推进一点，然后取消
    assert spin_until(app, lambda: tasks[0].transferred > 0), '任务1未推进'
    q.cancel()
    assert spin_until(app, lambda: box['summary'] is not None), '取消后未收尾'
    st = statuses(q)
    assert st == [T_FAILED, T_SKIPPED], '取消状态机错误: %r' % st
    assert tasks[0].error == '已取消'
    print('C. 中途取消 OK:', st)
    link.close()

    # ---- D. 空队列
    link, q = make_queue()
    box = {'summary': None}
    q.queue_finished.connect(lambda s: box.__setitem__('summary', s))
    assert q.start([], policy=POLICY_SKIP) is True
    assert spin_until(app, lambda: box['summary'] is not None)
    assert '完成 0' in box['summary']
    print('D. 空队列 OK:', box['summary'])
    link.close()

    os.remove(ok_file)
    os.remove(big)
    print('SMOKE OK')
    QTimer.singleShot(0, app.quit)
    app.exec_()


if __name__ == '__main__':
    main()
