# -*- coding: utf-8 -*-
r"""can 冒烟：命令模型 / 预设 / 调度器 / 会话（模拟模式）+ 统计。

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_can.py
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtWidgets import QApplication

from uicmp.guicore import can_commands as cc
from uicmp.guicore.can_session import (CanSession, Mode, CHAN_A, CHAN_B)


def spin(app, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        time.sleep(0.005)


def main():
    app = QApplication(sys.argv)

    # ---- 1. 帧与指令模型
    f = cc.CanFrame(0x123, [1, 2, 3])
    assert f.to_dict() == {'id': 0x123, 'data': '01 02 03'}
    assert cc.CanFrame.from_dict(f.to_dict()).data == [1, 2, 3]
    try:
        cc.CanFrame(1, list(range(9)))
        raise AssertionError('应拒绝 >8 字节')
    except ValueError:
        pass
    cmd = cc.CanCommand('T', 'A', 200, 5, True, [f])
    c2 = cmd.copy()
    c2.frames[0].data[0] = 0xFF
    assert cmd.frames[0].data[0] == 1, 'copy 必须深拷贝（否则改一条影响另一条）'
    d = cc.CanCommand.from_dict(cmd.to_dict())
    assert (d.name, d.channel, d.interval_ms, d.count, d.enabled) == ('T', 'A', 200, 5, True)
    assert cc.CanCommand('x', 'Z', 1).channel == 'A', '非法通道应回落 A'
    assert cc.CanCommand('x', 'A', 1).interval_ms == cc.MIN_INTERVAL_MS, '间隔下限保护'
    print('1. 帧/指令模型 OK（8B 限制 / 深拷贝 / 序列化 / 通道与间隔回落）')

    # ---- 2. hex 解析（沿用旧口径）
    assert cc.parse_hex_bytes('00 23 aa') == [0x00, 0x23, 0xAA]
    assert cc.parse_hex_bytes('0023aa') == [0x00, 0x23, 0xAA]
    assert cc.parse_hex_bytes('0x00,0x23') == [0x00, 0x23]
    assert cc.parse_hex_bytes('zz') is None
    assert cc.parse_hex_bytes('') == []
    print('2. hex 解析 OK（空格/连写/0x/逗号；非法返回 None）')

    # ---- 3. 预置指令
    pa, pb = cc.default_commands('A'), cc.default_commands('B')
    assert len(pa) == 8 and len(pb) == 3
    star = [c for c in pa if 'STAR' in c.name][0]
    assert len(star.frames) == 5, '星敏感器 38 字节应切 5 帧: %d' % len(star.frames)
    assert len(star.frames[0].data) == 8
    attitude = [c for c in pa if 'ATTITUDE' in c.name][0]
    assert len(attitude.frames) == 5
    # 预设两通道互不共享对象
    pa2 = cc.default_commands('A')
    pa2[0].frames[0].data[0] = 0xEE
    assert cc.default_commands('A')[0].frames[0].data[0] != 0xEE, '预设应每次深拷贝'
    print('3. 预置指令 OK（A %d 条 / B %d 条，多帧切分正确，深拷贝隔离）' % (len(pa), len(pb)))

    # ---- 4. 调度器：到期发送 / 次数用尽自动停
    sent = []
    sched = cc.CANCommandScheduler()
    sched.set_callback(lambda c: sent.append(c.name))
    # 打桩时间，手控 tick（不打桩的话要真实等待，慢且不稳）
    fake_t = [100.0]
    orig = cc.time_monotonic
    cc.time_monotonic = lambda: fake_t[0]
    try:
        c_inf = cc.CanCommand('INF', 'A', 100, cc.INFINITE, True)
        c_lim = cc.CanCommand('LIM', 'A', 100, 2, True)
        sched.set_commands([c_inf, c_lim])
        sched.tick()
        assert sent == ['INF', 'LIM'], sent
        fake_t[0] += 0.2   # 步长留余量：0.1 会踩浮点边界(100.1-100.0<0.1)
        sched.tick()
        assert sent == ['INF', 'LIM', 'INF', 'LIM'], sent
        assert c_lim.enabled is False, '次数用尽应自动停'
        fin = sched.take_just_finished()
        assert [c.name for c in fin] == ['LIM'], fin
        assert sched.remaining_of(c_lim) == 0
        fake_t[0] += 0.2   # 步长留余量：0.1 会踩浮点边界(100.1-100.0<0.1)
        sched.tick()
        assert sent.count('LIM') == 2, '停后不应再发'
        assert sent.count('INF') == 3, '无限指令应继续'
        assert sched.count_active() == 1
        sched.finish_silently()
        assert sched.count_active() == 0
        fake_t[0] += 1
        sched.tick()
        assert sent.count('INF') == 3, 'finish_silently 后不该再发'
    finally:
        cc.time_monotonic = orig
    print('4. 调度器 OK（到期发送 / 次数用尽自动停 + 通知 / 无限继续 / 静默停止）')

    # ---- 5. 会话：模拟模式收发 + 统计 + 调度
    ses = CanSession(mode=Mode.SIM)
    tx, rx, states, finished = [], [], [], []
    ses.txResult.connect(lambda *a: tx.append(a))
    ses.rxFrame.connect(lambda *a: rx.append(a))
    ses.busState.connect(lambda *a: states.append(a))
    ses.commandFinished.connect(finished.append)

    assert ses.open_channel(CHAN_A) and ses.simulating
    assert '模拟' in states[-1][2], states[-1]
    assert ses.open_channel(CHAN_B) and ses.simulating
    # 单发 → A 发帧，B 应收到（模拟同一总线）
    cmd_a = cc.CanCommand('T1', CHAN_A, 100, cc.INFINITE, False,
                          [cc.CanFrame(0x100, [1, 2])])
    assert ses.send_once(cmd_a) is True
    assert tx and rx, '模拟回环未生效 tx=%d rx=%d' % (len(tx), len(rx))
    assert rx[0][0] == CHAN_B and rx[0][1] == 0x100, rx[0]
    assert ses.stats(CHAN_A)['tx'] == 1 and ses.stats(CHAN_B)['rx'] == 1, ses.stats(CHAN_A)
    print('5. 会话模拟收发 OK（A 发 B 收，双方统计都记）')

    # ---- 6. 定时发送（真实节拍）
    ses.replace(CHAN_A, [cc.CanCommand('F', CHAN_A, 50, cc.INFINITE, True,
                                       [cc.CanFrame(0x200, [9])])])
    ok, msg = ses.start_sending()
    assert ok, msg
    spin(app, 0.35)
    n = ses.stats(CHAN_A)['tx']
    assert n >= 3, '定时未发够: %d' % n
    ses.stop_sending()
    spin(app, 0.15)
    assert ses.stats(CHAN_A)['tx'] == n, '停止后仍在发'
    print('6. 定时发送 OK（50ms 真实节拍 × %d 次，停止即止）' % n)

    # ---- 7. 边界：未开通道 / 无启用指令
    ses2 = CanSession(mode=Mode.SIM)
    ok, msg = ses2.start_sending()
    assert not ok and '通道' in msg, msg
    ses2.open_channel(CHAN_A)
    ok, msg = ses2.start_sending()
    assert not ok and '启用' in msg, msg
    assert ses2.send_once(cc.CanCommand('x', CHAN_B, 100, 1, False, [])) is False
    print('7. 边界提示 OK（未开通道 / 无启用指令 / 单发到未开通道）')

    # ---- 8. 命令表操作 + 序列化往返 + 恢复预设
    ses3 = CanSession(mode=Mode.SIM)
    n0 = len(ses3.commands(CHAN_A))
    c = ses3.add_command(CHAN_A)
    assert len(ses3.commands(CHAN_A)) == n0 + 1
    ses3.move_command(CHAN_A, c, -1)
    ses3.remove_command(CHAN_A, c)
    assert len(ses3.commands(CHAN_A)) == n0
    dumped = ses3.serialize()
    ses3.load_presets()
    ses3.deserialize(dumped)
    assert len(ses3.commands(CHAN_A)) == n0 and len(ses3.commands(CHAN_B)) == 3
    print('8. 命令表 OK（增删移 + 序列化往返 + 恢复预设）')

    # ---- 9. 关停
    ses.shutdown()
    assert not ses.any_open and not ses.is_running
    ses2.shutdown()
    print('9. 关停 OK')

    print('SMOKE OK')


if __name__ == '__main__':
    main()
