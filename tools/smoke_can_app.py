# -*- coding: utf-8 -*-
r"""can_app 冒烟：表格渲染 / 展开帧明细 / 开关 / 单发 / 定时锁定 / 主题 / 清理。

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_can_app.py
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtGui import QFontDatabase

from fake_device import DeviceMedia
from uicmp.guicore.can_session import CanSession, Mode, CHAN_A
from uicmp.apps.can_app import CanApp, COL_SW, COL_SEND


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
    w.show()
    spin(app, 0.6)

    # ---- 1. 初始渲染：默认预设 A8 + B3
    assert w.table.rowCount() == 11, w.table.rowCount()
    print('1. 初始渲染 OK（A8 + B3 = 11 行）')

    # ---- 2. 打开双通道 → 卡片状态
    ses.open_channel(CHAN_A)
    ses.open_channel('B')
    spin(app, 0.2)
    assert w.bus[CHAN_A]._btn.text() == '关闭', w.bus[CHAN_A]._btn.text()
    assert w.bus[CHAN_A]._badge.text() == '已连接'
    print('2. 双通道打开 OK（按钮/徽章同步）')

    # ---- 3. 筛选
    w.combo_filter.setCurrentText('通道 A')
    assert w.table.rowCount() == 8, w.table.rowCount()
    w.combo_filter.setCurrentText('通道 B')
    assert w.table.rowCount() == 3, w.table.rowCount()
    w.combo_filter.setCurrentText('全部')
    assert w.table.rowCount() == 11
    print('3. 通道筛选 OK（A=8 / B=3 / 全部=11）')

    # ---- 4. 启用一条 → 状态列 + 计数
    c0 = ses.commands(CHAN_A)[0]
    w._on_switch(c0, True)
    spin(app, 0.1)
    # 找到它的行
    row0 = None
    for r in range(w.table.rowCount()):
        it = w.table.item(r, 1)
        if it and it.text() == c0.name:
            row0 = r
            break
    assert row0 is not None
    st = w.table.item(row0, 7)
    assert st.data(Qt.UserRole) == 'busy', st.data(Qt.UserRole)
    assert '启用 1 条' in w.lb_info.text(), w.lb_info.text()
    print('4. 启用指令 OK（状态 busy + 启用计数）')

    # ---- 5. 展开/折叠帧明细（含无残留检查）
    star = [c for c in ses.commands(CHAN_A) if 'STAR' in c.name][0]
    star_row = None
    for r in range(w.table.rowCount()):
        it = w.table.item(r, 1)
        if it and it.text() == star.name:
            star_row = r
            break
    w._on_dbl(star_row, 1)
    spin(app, 0.1)
    assert w.table.rowCount() == 12, '展开后应 +1 行: %d' % w.table.rowCount()
    # 残留检查：展开行的开关列与单发列必须无 widget（上一轮踩过）
    assert w.table.cellWidget(star_row + 1, COL_SW) is None, '展开行残留开关 widget'
    assert w.table.cellWidget(star_row + 1, COL_SEND) is None, '展开行残留单发 widget'
    frames_text = w.table.item(star_row + 1, 1).text()
    assert '帧5' in frames_text and '0x' in frames_text, frames_text[:80]
    w._on_dbl(star_row, 1)
    spin(app, 0.1)
    assert w.table.rowCount() == 11, '折叠后应恢复'
    print('5. 展开/折叠帧明细 OK（无 widget 残留）')

    # ---- 6. 单发 → 统计 + 监视
    st0 = ses.stats(CHAN_A)['tx']
    w._send_once(c0)
    spin(app, 0.15)
    assert ses.stats(CHAN_A)['tx'] == st0 + 1
    assert '单发' in w.mon.toPlainText()
    print('6. 单发 OK（统计 +1，监视有记录）')

    # ---- 7. 定时发送 + 运行锁
    w._on_switch(c0, True)
    ok, msg = ses.start_sending()
    assert ok, msg
    spin(app, 0.1)
    assert w.btn_run.text().find('发送中') >= 0, w.btn_run.text()
    assert not w.btn_add.isEnabled(), '运行中应锁定编辑'
    n0 = ses.stats(CHAN_A)['tx']
    spin(app, 0.9)      # 快遥间隔 500ms：0.4s 可能一次都等不到
    n1 = ses.stats(CHAN_A)['tx']
    assert n1 > n0, '定时未发送（%d → %d）' % (n0, n1)
    ses.stop_sending()
    spin(app, 0.15)
    assert ses.stats(CHAN_A)['tx'] == n1, '停止后仍在发'
    assert w.btn_add.isEnabled(), '停止后应解锁'
    print('7. 定时发送 + 运行锁 OK')

    # ---- 8. 复制 / 删除（删除的确认框打桩为 Yes）
    w._selected = c0
    w._copy()
    spin(app, 0.1)
    assert len(ses.commands(CHAN_A)) == 9, len(ses.commands(CHAN_A))
    copy_cmd = ses.commands(CHAN_A)[-1]
    assert copy_cmd.name.endswith('副本') and not copy_cmd.enabled
    orig_question = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    try:
        w._selected = copy_cmd
        w._delete()
    finally:
        QMessageBox.question = orig_question
    spin(app, 0.1)
    assert len(ses.commands(CHAN_A)) == 8
    print('8. 复制/删除 OK（副本禁用；删除带确认）')

    # ---- 9. 主题往返 + 关窗清理
    w.toggle_theme()
    w.toggle_theme()
    spin(app, 0.2)
    r, wr = link_threads = ses.link_threads if False else (None, None)
    ses.shutdown()
    assert not ses.any_open and not ses.is_running
    print('9. 主题往返 + 关停 OK')

    print('SMOKE OK')
    QTimer.singleShot(0, app.quit)
    app.exec_()


if __name__ == '__main__':
    main()
