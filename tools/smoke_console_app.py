# -*- coding: utf-8 -*-
"""console_app + console_session 冒烟测试（无硬件，假链路回环）。

验证点：
1. ConsoleSession.send_command 自动补 CR（b'hello\\r'）
2. 回环 → text_received → 输出区出现文本
3. ↑↓ 历史浏览（两条命令来回翻，翻到头清空）
4. hex 显示开关
5. 未打开链路时发送被拒
6. 主题切换两次不抛异常；关窗后链路关闭、线程退出

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_console_app.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import QApplication

from uicmp.guicore.serial_link import SerialLink
from uicmp.guicore.console_session import ConsoleSession

# 复用冒烟假串口（回环 + 加锁 + 阻塞读语义）
_smoke_dir = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(_smoke_dir, 'smoke_serial_link.py'), encoding='utf-8').read()
_ns = {'__file__': os.path.join(_smoke_dir, 'smoke_serial_link.py')}
exec(src.split('def main()')[0], _ns)
FakeMedia = _ns['FakeMedia']


def main():
    app = QApplication(sys.argv)
    assert QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc') != -1

    from uicmp.apps.console_app import ConsoleApp

    link = SerialLink()
    session = ConsoleSession(link=link)
    win = ConsoleApp(session=session)
    win.input.set_session(session)
    win.show()

    fake = FakeMedia()
    assert session.open('FAKE', baud=115200, media=fake) is True
    assert session.is_open

    # ---- 1/2. 发送 → CR 结尾 → 回环 → 输出区
    sent = []
    link._writer.put = sent.append          # 拦截队列，直接查帧内容
    session.send_command('version')
    assert sent == [b'version\r'], 'CR 结尾缺失或内容错: %r' % sent
    assert win.input.text() == '', '发送后输入行未清空'

    # 模拟设备回显（不等回环：直接喂 received 信号）
    session._on_rx(b'version=V3.3.0\r\n')
    assert 'version=V3.3.0' in win.out.toPlainText(), '输出区未收到文本'
    print('1/2. 发送 CR 结尾 + 回显上屏 OK')

    # ---- 3. 历史浏览
    session.send_command('help')
    # 历史: [version, help]，当前输入行空
    assert session.history_prev() == 'help'
    assert session.history_prev() == 'version'
    assert session.history_prev() == 'version', '翻到头应停住'
    assert session.history_next() == 'help'
    assert session.history_next() == '', '翻出新尽头应返回空串'
    assert session.history_next() is None, '空串之后再翻应返回 None'
    print('3. 历史浏览 OK')

    # ---- 4. hex 显示（必须拿到真字节，不能是替换字符）
    win.chk_hex.setChecked(True)
    session._on_rx(b'\x1a\xcf')
    assert '1A CF' in win.out.toPlainText(), 'hex 显示未生效（原始字节丢了？）'
    win.chk_hex.setChecked(False)
    session._on_rx(b'\x1a\xcf')
    assert '\ufffd' in win.out.toPlainText(), '文本模式应为 replace 解码'
    print('4. hex/文本双模式 OK')

    # ---- 5. 未打开链路拒发
    session2 = ConsoleSession(link=SerialLink())
    assert session2.send_command('x') is False
    print('5. 未打开拒发 OK')

    # ---- 6. 主题切换 + 关窗清理
    win.toggle_theme()
    win.toggle_theme()
    r, w = link._reader, link._writer
    win.close()
    assert not session.is_open
    assert not r.isRunning() and not w.isRunning(), '关窗后线程未退出'
    print('6. 主题切换 + 关窗清理 OK')

    print('SMOKE OK')
    QTimer.singleShot(0, app.quit)
    app.exec_()


if __name__ == '__main__':
    main()
