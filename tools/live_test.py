# -*- coding: utf-8 -*-
"""真机验证：USBCAN-II 双通道，A 发 B 收。

前提（需要你这边保证）：
  1. USBCAN-II 已插好、驱动正常
  2. A/B 两通道接到**同一条 CAN 总线**（或有 120Ω 终端电阻的回路）
  3. 总线上没有别的设备在跑高负载

判据：
  - 打开两个通道返回「真机」而不是「模拟」
  - A 发一条指令 → B 侧收到相同 ID/数据的帧
  - 反向再来一次（B 发 A 收）

用 Mode.REAL 强制真机 —— 打不开就直接报错，不会偷偷回退模拟。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)                      # ECAN.open 用 os.getcwd() 找 DLL

os.environ.pop('QT_QPA_PLATFORM', None)

from PyQt5.QtCore import QTimer, QEventLoop                        # noqa: E402
from PyQt5.QtWidgets import QApplication                           # noqa: E402

from uicmp import core                                             # noqa: E402


def main():
    app = QApplication(sys.argv[:1])
    bus = core.CanBus(core.Mode.REAL)

    log = []
    got = {core.CHAN_A: [], core.CHAN_B: []}

    bus.busState.connect(lambda ch, ok, m: log.append('[bus] %s open=%s %s' % (ch, ok, m)))
    bus.txResult.connect(lambda ch, ok, tag, i, t:
                         log.append('[tx ] %s ok=%s %s %d/%d' % (ch, ok, tag, i + 1, t)))
    bus.rxFrame.connect(lambda ch, fid, d:
                        (got[ch].append((fid, tuple(d))),
                         log.append('[rx ] %s 0x%X %s' % (ch, fid, ' '.join('%02X' % b for b in d)))))

    a, b = core.load_case()
    print('用例：A=%d 条  B=%d 条' % (len(a), len(b)))
    print()

    loop = QEventLoop()
    steps = []

    def step_open():
        print('--- 打开 A / B 通道（Mode.REAL）---')
        bus.open_channel(core.CHAN_A)
        bus.open_channel(core.CHAN_B)
        print('  A 打开:', bus.is_open(core.CHAN_A), ' 模拟模式:', bus.simulating)
        print('  B 打开:', bus.is_open(core.CHAN_B), ' 模拟模式:', bus.simulating)
        if bus.simulating:
            print()
            print('  ✗ 回退到模拟了 —— 说明真机打不开。')
            print('    检查：USBCAN 是否插好 / 是否被别的程序占着（旧 CAN 窗口）/ DLL 是否在。')
            loop.quit()
            return
        print()
        print('--- A 发第 1 条，等 B 收 ---')
        sent = a[0]
        print('  发送:', sent.name, [core.fmt_frame(f) for f in sent.frames])
        bus.send_once(sent)
        QTimer.singleShot(800, step_check_a)

    def step_check_a():
        n = len(got[core.CHAN_B])
        print('  B 侧收到 %d 帧' % n)
        if n:
            print('  ✓ A→B 通路成立')
        else:
            print('  ✗ A→B 没收到（检查两通道是否接在同一总线 / 终端电阻）')
        print()
        print('--- B 发第 1 条，等 A 收 ---')
        sent = b[0]
        print('  发送:', sent.name, [core.fmt_frame(f) for f in sent.frames])
        bus.send_once(sent)
        QTimer.singleShot(800, step_check_b)

    def step_check_b():
        n = len(got[core.CHAN_A])
        print('  A 侧收到 %d 帧' % n)
        print('  %s B→A 通路%s' % ('✓' if n else '✗', '成立' if n else '没收到'))
        print()
        print('--- 多帧指令（5 帧）测试 ---')
        multi = None
        for c in a:
            if len(c.frames) > 1:
                multi = c
                break
        if multi is None:
            print('  用例里没有多帧指令，跳过')
            loop.quit()
            return
        before = len(got[core.CHAN_B])
        print('  发送:', multi.name, '共 %d 帧' % len(multi.frames))
        bus.send_once(multi)
        QTimer.singleShot(1200, lambda: step_check_multi(before, multi))

    def step_check_multi(before, multi):
        got_n = len(got[core.CHAN_B]) - before
        print('  B 侧收到 %d 帧（期望 %d）' % (got_n, len(multi.frames)))
        print('  %s' % ('✓ 多帧完整送达' if got_n == len(multi.frames)
                        else '⚠ 帧数不符，检查总线负载或接收缓冲'))
        print()
        print('=== 完整日志 ===')
        for line in log:
            print(' ', line)
        bus.shutdown()
        loop.quit()

    QTimer.singleShot(400, step_open)
    QTimer.singleShot(30000, loop.quit)
    loop.exec_()
    bus.shutdown()


if __name__ == '__main__':
    main()
