# -*- coding: utf-8 -*-
"""console_app · BMU debug console 页面（SerialLink/ConsoleSession 第一个真消费者）。

布局（自上而下）：
  连接条：串口选择 · 波特率 · 打开/关闭 · 状态徽章 · 主题切换
  输出区：只读 QTextEdit（环形截断 2000 行，防长跑内存膨胀）
  输入行：QLineEdit（↑↓ 历史）+ 发送
  工具行：清屏 · hex 显示开关

设计约定：
- 页面只碰文本，不碰字节——CR 结尾、utf-8 解码都在 ConsoleSession
- 会话对象可注入（测试用假链路回环，不打真串口）
"""
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
                             QLineEdit, QSizePolicy)

from qfluentwidgets import (PushButton, PrimaryPushButton,
                            CheckBox, FluentIcon as FIF,
                            TransparentToolButton)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from uicmp.guicore.console_session import ConsoleSession
from uicmp.guiwidgets import theme
from uicmp.guiwidgets.common import ConnectionBar

OUT_MAX_BLOCKS = 2000     # 输出区最大块数，超过截掉前 1/4
OUT_TRIM_TO = 1500


class ConsoleApp(QDialog):
    """BMU debug console 页面。link 可注入（测试），默认自建。"""

    def __init__(self, parent=None, session=None):
        super(ConsoleApp, self).__init__(parent)
        self.session = session if session is not None else ConsoleSession()
        self._dark = False
        self.setObjectName('ConsoleApp')
        self.setWindowTitle('BMU 控制台 · gui-ng')
        self.resize(720, 520)
        self._build()
        self.apply_theme(False)

    # ------------------------------------------------------------ UI 构建
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(theme.GAP)

        # ---- 连接条（共用组件）+ 主题按钮
        conn = QHBoxLayout()
        conn.setSpacing(theme.GAP_SM)
        self.conn = ConnectionBar(self.session.link, dark=self._dark)
        conn.addWidget(self.conn, 1)
        self.btn_theme = TransparentToolButton(FIF.CONSTRACT)
        self.btn_theme.setToolTip('浅/深主题')
        conn.addWidget(self.btn_theme, 0)
        v.addLayout(conn)

        # ---- 输出区
        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.out, 1)

        # ---- 输入行
        inp = QHBoxLayout()
        inp.setSpacing(theme.GAP_SM)
        self.input = _HistoryLineEdit()
        self.input.setPlaceholderText('输入命令，回车发送（↑↓ 翻历史）')
        self.btn_send = PrimaryPushButton(FIF.SEND, '发送')
        inp.addWidget(self.input, 1)
        inp.addWidget(self.btn_send, 0)
        v.addLayout(inp)

        # ---- 工具行
        tools = QHBoxLayout()
        tools.setSpacing(theme.GAP_SM)
        self.chk_hex = CheckBox('hex 显示')
        self.btn_clear = PushButton(FIF.DELETE, '清屏')
        tools.addWidget(self.chk_hex, 0)
        tools.addWidget(self.btn_clear, 0)
        tools.addStretch(1)
        v.addLayout(tools)

        # ---- 信号
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_send.clicked.connect(self._send_current)
        self.btn_clear.clicked.connect(self.out.clear)
        self.input.returnPressed.connect(self._send_current)
        self.session.received.connect(self._append_bytes)
        self.session.opened.connect(
            lambda: self._append_text('[√] 已连接 %s\n' % self.conn.current_port()))
        self.session.closed.connect(
            lambda: self._append_text('[×] 已断开\n'))
        self.session.error.connect(
            lambda m: self._append_text('[!] %s\n' % m))

    # ------------------------------------------------------------ 收 / 发
    def _send_current(self):
        cmd = self.input.text().strip()
        if not cmd:
            return
        if self.session.send_command(cmd):
            self.input.clear()

    def _append_bytes(self, data):
        """串口原始字节上屏：hex 模式显字节码，否则 utf-8(replace) 文本。"""
        if self.chk_hex.isChecked():
            text = ' '.join('%02X' % b for b in data) + '\n'
        else:
            text = data.decode('utf-8', 'replace')
        self.out.moveCursor(self.out.textCursor().End)
        self.out.insertPlainText(text)

    def _append_text(self, text):
        """UI 本地提示（连接/错误等），始终文本显示，不参与 hex 化。"""
        self.out.moveCursor(self.out.textCursor().End)
        self.out.insertPlainText(text)
        # 环形截断：超过上限砍前 1/4，避免长跑内存膨胀
        doc = self.out.document()
        if doc.blockCount() > OUT_MAX_BLOCKS:
            cursor = self.out.textCursor()
            cursor.movePosition(cursor.Start)
            cursor.movePosition(cursor.Down, cursor.KeepAnchor, OUT_MAX_BLOCKS - OUT_TRIM_TO)
            cursor.removeSelectedText()

    # ------------------------------------------------------------ 主题
    def toggle_theme(self):
        self._dark = not self._dark
        self.apply_theme(self._dark)

    def apply_theme(self, dark):
        """⚠️ 约定：任何控件重建之后都要重调本函数。"""
        self._dark = dark
        theme.apply_theme(self, dark)
        self.conn.set_dark(dark)
        self.out.setStyleSheet(
            'QTextEdit{background:%s; color:%s; border:1px solid %s;'
            'border-radius:%dpx; font-family:"%s","Consolas"; font-size:13px;}'
            % (theme.C_CARD_D if dark else theme.C_CARD,
               theme.C_TEXT_D if dark else theme.C_TEXT,
               theme.C_GRAY_BG_D if dark else theme.C_GRAY_BG,
               theme.R_CARD, theme.FONT_FAMILY))
        theme.fix_fonts(self)

    # ------------------------------------------------------------ 生命周期
    def closeEvent(self, e):
        self.session.close()
        super(ConsoleApp, self).closeEvent(e)


class _HistoryLineEdit(QLineEdit):
    """带历史浏览的输入行（↑↓ 走 ConsoleSession 的历史栈）。"""

    def set_session(self, session):
        self._session = session
        self._buf = ''

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key_Up:
            prev = self._session.history_prev() if self._session else None
            if prev is not None:
                if self._buf == '':
                    self._buf = self.text()
                self.setText(prev)
            return
        if key == Qt.Key_Down:
            nxt = self._session.history_next() if self._session else None
            if nxt is not None:
                self.setText(nxt)
                if nxt == '':
                    self._buf = ''
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self._buf = ''
        super(_HistoryLineEdit, self).keyPressEvent(e)
