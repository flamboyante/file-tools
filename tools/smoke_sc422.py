# -*- coding: utf-8 -*-
r"""sc422 冒烟：hex 解析容错 / ascii 口径 / 定时发送 / TX-RX 日志 / 主题。

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_sc422.py
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, 'tools')):
    if p not in sys.path:
        sys.path.insert(0, p)

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase

from fake_device import DeviceMedia
from uicmp.guicore.sc422_session import (Sc422Session, parse_hex, format_hex,
                                         format_ascii)
from uicmp.guicore.serial_link import SerialLink
from uicmp.apps.sc422_app import Sc422App


def spin(app, seconds):
    t0 = time.time()
    while time.time() - t0 < seconds:
        app.processEvents()
        time.sleep(0.005)


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')

    # ---- 1. parse_hex 容错
    for text in ('EB 90', 'eb90', '0xEB 0x90', 'EB\n90', '  eb\t90  '):
        assert parse_hex(text) == b'\xeb\x90', '解析失败: %r' % text
    print('1. parse_hex 容错 OK（空格/0x/换行/大小写/制表符）')

    # ---- 2. parse_hex 报错（人话原因）
    for text, kw in (('', '空'), ('EB 9', '偶数'), ('EB GG', '非法字符'),
                     ('ZZ', '非法字符')):
        try:
            parse_hex(text)
            raise AssertionError('应当报错: %r' % text)
        except ValueError as e:
            assert kw in str(e), '错误信息不含 %s: %s' % (kw, e)
    print('2. parse_hex 报错 OK（空/奇数位/非法字符）')

    # ---- 3. 视图口径
    assert format_hex(b'\xeb\x90\x01') == 'EB 90 01'
    assert format_ascii(b'AB\r\n\x00\xffC') == 'AB....C', format_ascii(b'AB\r\n\x00\xffC')
    assert format_ascii(b'\t A') == '\t A', 'TAB 应放行'
    print('3. 视图口径 OK（hex 大写空格分隔 / ascii 只放行 0x20-0x7E 与 TAB）')

    # ---- 4. 未打开链路拒发
    link0 = SerialLink()
    s0 = Sc422Session(link0)
    errs = []
    s0.failed.connect(errs.append)
    assert s0.send_hex('EB 90') is False
    assert errs, '未打开应报错'
    print('4. 未打开拒发 OK（%s）' % errs[-1])

    # ---- 5. 打开后发送 + 计数
    link = SerialLink()
    assert link.open('FAKE', media=DeviceMedia()) is True
    session = Sc422Session(link)
    sent, errs2 = [], []
    session.sent.connect(sent.append)
    session.failed.connect(errs2.append)
    assert session.send_hex('EB 90 01 80') is True
    assert sent and sent[0] == b'\xeb\x90\x01\x80', sent
    assert session.sent_count == 1
    print('5. 发送 + 计数 OK（已发 %d 次）' % session.sent_count)

    # ---- 6. 定时发送
    session.start_timer(30, lambda: 'AA BB')
    assert session.is_timing and session.interval_ms == 30
    spin(app, 0.25)
    n = session.sent_count
    assert n >= 3, '定时未生效，计数=%d' % n
    session.stop_timer()
    assert not session.is_timing
    spin(app, 0.1)
    assert session.sent_count == n, '停止后仍在发送'
    print('6. 定时发送 OK（30ms × %d 次，停止即止）' % (n - 1))

    # ---- 7. 定时下限保护 + 空内容不中断
    assert session.start_timer(0, lambda: 'AA') is True
    assert session.interval_ms == Sc422Session.MIN_INTERVAL_MS, session.interval_ms
    session.stop_timer()
    session.start_timer(20, lambda: '')       # 空内容：不发送也不停
    spin(app, 0.1)
    assert session.is_timing, '空内容不应中断定时'
    session.stop_timer()
    print('7. 定时保护 OK（下限 %dms / 空内容不中断）' % Sc422Session.MIN_INTERVAL_MS)

    # ---- 8. UI：输入校验提示 + TX/RX 日志 + 主题
    # 注入已打开的链路（默认自建的是未打开状态，发送会被拒）
    link2 = SerialLink()
    assert link2.open('FAKE', media=DeviceMedia()) is True
    win = Sc422App(session=Sc422Session(link2))
    win.show()
    win.input.setPlainText('EB 90')                 # 合法
    app.processEvents()
    assert '共 2 字节' in win.hint.text(), win.hint.text()
    win.input.setPlainText('EB GG')                 # 非法
    app.processEvents()
    assert '非法字符' in win.hint.text(), win.hint.text()
    win.input.setPlainText('EB 90 01 80 C0 00 00 01 00 1D FE A0')
    app.processEvents()
    win._send()
    app.processEvents()
    assert '已发 1 次' in win.lb_sent.text(), win.lb_sent.text()
    text = win.out.toPlainText()
    assert 'TX' in text and 'EB 90 01 80' in text, text[:200]
    # ascii 视图切换 + 收到数据
    win._toggle_view()
    assert 'ascii' in win.btn_view.text()
    win._on_rx(b'AB\r\n')
    app.processEvents()
    assert 'AB..' in win.out.toPlainText(), win.out.toPlainText()[-120:]
    win.btn_clear.click()
    assert win.out.toPlainText() == '', '清屏失败'
    win.toggle_theme()
    win.toggle_theme()
    print('8. UI OK（校验提示 / TX 行 / ascii 视图 / 清屏 / 主题往返）')

    # ---- 9. 关窗清理
    r, w = link2._reader, link2._writer
    win.close()
    assert not link2.is_open
    assert not r.isRunning() and not w.isRunning(), '关窗后线程未退出'
    print('9. 关窗清理 OK')

    print('SMOKE OK')
    QTimer.singleShot(0, app.quit)
    app.exec_()


if __name__ == '__main__':
    main()
