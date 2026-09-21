# -*- coding: utf-8 -*-
"""sc422_app · SC 422 口 hex 收发台（自定义指令 + 定时发送）。

定位（小K 定）：**只做原始 hex 收发与定时**，不做协议指令面板。
布局：
  通道配置条 v2（预设 SC 422 / 921600 8O1，可改）+ 主题
  发送区：多行 hex 输入（即时校验）· 发送 · 定时(ms) · 清空 · 已发次数
  接收区：hex/ascii 视图 · 时间戳 · 自动滚动 · 清屏 · 收字节数
          日志按事件分行、TX 蓝 / RX 绿 / 错误红 —— 排"发了什么、回没回"是刚需

视图口径复用 sc422_session 的纯函数（ascii：0x20~0x7E 与 TAB 放行，其余 `.`）
"""
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette, QTextCharFormat
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
                             QPlainTextEdit, QPushButton, QSpinBox, QLabel,
                             QSizePolicy)

from qfluentwidgets import (PrimaryPushButton, CheckBox, FluentIcon as FIF,
                            TransparentToolButton)

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from uicmp.guicore.sc422_session import (Sc422Session, parse_hex, format_hex,
                                         format_ascii, now_stamp)
from uicmp.guiwidgets import theme
from uicmp.guiwidgets.common import ConnectionBar

OUT_MAX_BLOCKS = 2000
OUT_TRIM_TO = 1500

SAMPLE_HINT = 'EB 90 01 80 C0 00 00 01 00 1D FE A0'   # 心跳帧，做占位示例


class Sc422App(QDialog):
    """SC 422 hex 收发台。session 可注入（测试用假链路）。"""

    def __init__(self, parent=None, session=None):
        super(Sc422App, self).__init__(parent)
        from uicmp.guicore.serial_link import SerialLink
        if session is None:
            session = Sc422Session(SerialLink())
        self.session = session
        self._dark = False
        self.setObjectName('Sc422App')
        self.setWindowTitle('SC 422 收发台 · gui-ng')
        self.resize(860, 620)
        self._build()
        self.apply_theme(False)

    # ------------------------------------------------------------ UI
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(theme.GAP)

        # ---- 通道配置条 + 主题
        top = QHBoxLayout()
        top.setSpacing(theme.GAP_SM)
        self.conn = ConnectionBar(self.session.link, dark=self._dark,
                                  settings_key='sc422',
                                  default_preset='SC 422')
        top.addWidget(self.conn, 1)
        self.btn_theme = TransparentToolButton(FIF.CONSTRACT)
        self.btn_theme.setToolTip('浅/深主题')
        top.addWidget(self.btn_theme, 0)
        v.addLayout(top)

        # ---- 发送区
        v.addWidget(self._label('发送（hex）'))
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(SAMPLE_HINT)
        self.input.setFixedHeight(76)
        v.addWidget(self.input)

        self.hint = QLabel('')
        v.addWidget(self.hint)

        send_row = QHBoxLayout()
        send_row.setSpacing(theme.GAP_SM)
        self.btn_send = PrimaryPushButton(FIF.SEND, '发送')
        self.btn_timer = QPushButton('开始定时')
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(10, 60000)
        self.spin_interval.setValue(100)
        self.spin_interval.setFixedWidth(84)
        self.spin_interval.setSuffix(' ms')
        self.btn_clear_input = QPushButton('清空输入')
        send_row.addWidget(self.btn_send, 0)
        send_row.addSpacing(6)
        send_row.addWidget(QLabel('定时'))
        send_row.addWidget(self.spin_interval, 0)
        send_row.addWidget(self.btn_timer, 0)
        send_row.addWidget(self.btn_clear_input, 0)
        send_row.addStretch(1)
        self.lb_sent = QLabel('已发 0 次')
        send_row.addWidget(self.lb_sent, 0)
        v.addLayout(send_row)

        # ---- 接收区
        recv_row = QHBoxLayout()
        recv_row.setSpacing(theme.GAP_SM)
        recv_row.addWidget(self._label('接收'))
        self.chk_ts = CheckBox('时间戳')
        self.chk_ts.setChecked(True)
        self.chk_scroll = CheckBox('自动滚动')
        self.chk_scroll.setChecked(True)
        self.btn_view = QPushButton('hex 视图')
        self.btn_clear = QPushButton(FIF.DELETE.icon(), '清屏')
        recv_row.addWidget(self.chk_ts, 0)
        recv_row.addWidget(self.chk_scroll, 0)
        recv_row.addStretch(1)
        self.lb_recv = QLabel('收 0 字节')
        recv_row.addWidget(self.lb_recv, 0)
        recv_row.addWidget(self.btn_view, 0)
        recv_row.addWidget(self.btn_clear, 0)
        v.addLayout(recv_row)

        self.out = QTextEdit()
        self.out.setReadOnly(True)
        self.out.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.out, 1)

        # ---- 信号
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_send.clicked.connect(self._send)
        self.btn_timer.clicked.connect(self._toggle_timer)
        self.btn_clear_input.clicked.connect(self.input.clear)
        self.btn_clear.clicked.connect(self.out.clear)
        self.btn_view.clicked.connect(self._toggle_view)
        self.input.textChanged.connect(self._on_input_changed)
        self.session.sent.connect(self._on_sent)
        self.session.failed.connect(lambda m: self._append('!', m.encode()))
        self.session.timer_state.connect(self._on_timer_state)
        self.session.link.rx.connect(self._on_rx)
        self.session.link.opened.connect(
            lambda: self._append('!', ('已连接 %s  [%s]' % (
                self.conn.current_port(),
                self.conn.combo_preset.currentText())).encode()))
        self.session.link.closed.connect(
            lambda: self._append('!', '已断开'.encode()))

        self._append('!', ('提示：输入 hex（空格/0x/换行分隔均可），'
                           'SC 422 预设 921600 8O1').encode())
        self._on_input_changed()

    def _label(self, text):
        lb = QLabel(text)
        lb.setStyleSheet('font-weight: 500;')
        return lb

    # ------------------------------------------------------------ 发送
    def _send(self):
        self.session.send_hex(self.input.toPlainText())

    def _toggle_timer(self):
        if self.session.is_timing:
            self.session.stop_timer()
        else:
            self.session.start_timer(
                self.spin_interval.value(),
                lambda: self.input.toPlainText())

    def _on_input_changed(self):
        """即时校验：报字节数，或指出第一个问题（红字）。"""
        text = self.input.toPlainText()
        if not text.strip():
            self.hint.setText('')
            return
        try:
            payload = parse_hex(text)
            self.hint.setText('共 %d 字节' % len(payload))
            self.hint.setStyleSheet('color: %s;'
                                    % (theme.C_TEXT_SUB_D if self._dark else theme.C_TEXT_SUB))
        except ValueError as e:
            self.hint.setText('✗ %s' % e)
            self.hint.setStyleSheet('color: %s;'
                                    % (theme.C_RED_D if self._dark else theme.C_RED))

    def _on_sent(self, payload):
        self._append('TX', payload)
        self.lb_sent.setText('已发 %d 次' % self.session.sent_count)

    def _on_rx(self, data):
        self._append('RX', data)
        self._recv_bytes = getattr(self, '_recv_bytes', 0) + len(data)
        self.lb_recv.setText('收 %d 字节' % self._recv_bytes)

    def _on_timer_state(self, on):
        if on:
            self.btn_timer.setText('停止定时')
            self.btn_timer.setStyleSheet(theme.primary_active_qss(self._dark))
            self._append('!', ('定时发送已开始（间隔 %d ms）'
                               % self.session.interval_ms).encode())
        else:
            self.btn_timer.setText('开始定时')
            self.btn_timer.setStyleSheet(theme.outline_button_qss(self._dark))
            self._append('!', '定时发送已停止'.encode())

    # ------------------------------------------------------------ 视图
    def _toggle_view(self):
        self._hex_view = not getattr(self, '_hex_view', True)
        self.btn_view.setText('hex 视图' if self._hex_view else 'ascii 视图')
        self._append('!', ('切换为 %s 视图（仅影响后续）'
                           % ('hex' if self._hex_view else 'ascii')).encode())

    def _append(self, tag, payload):
        """按事件一行：时间戳 · 标签 · 数据（TX 蓝 / RX 绿 / 提示红·灰）。"""
        parts = []
        if self.chk_ts.isChecked():
            parts.append(now_stamp())
        parts.append('%-3s' % tag)
        if tag == 'RX' and not getattr(self, '_hex_view', True):
            body = format_ascii(payload)
        elif tag in ('TX', 'RX'):
            body = format_hex(payload)
        else:
            body = payload.decode('utf-8', 'replace')
        text = '%s  %s\n' % ('  '.join(parts), body)

        if tag == 'TX':
            color = theme.C_PRIMARY_D if self._dark else theme.C_PRIMARY
        elif tag == 'RX':
            color = theme.C_GREEN_D if self._dark else theme.C_GREEN
        elif tag == '!':
            color = theme.C_TEXT_SUB_D if self._dark else theme.C_TEXT_SUB
        else:
            color = theme.C_TEXT_D if self._dark else theme.C_TEXT

        cursor = self.out.textCursor()
        cursor.movePosition(cursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.setCharFormat(fmt)      # 每次显式设置，防格式残留（console 踩过）
        cursor.insertText(text)

        self._trim_output()
        if self.chk_scroll.isChecked():
            self.out.moveCursor(self.out.textCursor().End)

    def _trim_output(self):
        doc = self.out.document()
        if doc.blockCount() > OUT_MAX_BLOCKS:
            c = self.out.textCursor()
            c.movePosition(c.Start)
            c.movePosition(c.Down, c.KeepAnchor, OUT_MAX_BLOCKS - OUT_TRIM_TO)
            c.removeSelectedText()

    # ------------------------------------------------------------ 主题
    def _icon(self, fif):
        return fif.icon(color=theme.BTN_ICON_D if self._dark
                        else theme.BTN_ICON)

    def toggle_theme(self):
        self._dark = not self._dark
        self.apply_theme(self._dark)

    def apply_theme(self, dark):
        """⚠️ 约定：任何控件重建之后都要重调本函数。"""
        self._dark = dark
        theme.apply_theme(self, dark)
        self.conn.set_dark(dark)
        qss = theme.log_qss(dark, mono=True) + theme.scrollbar_qss(dark)
        self.input.setStyleSheet(qss)
        self.out.setStyleSheet(qss)
        for b in (self.btn_timer, self.btn_clear_input, self.btn_view,
                  self.btn_clear):
            b.setStyleSheet(theme.outline_button_qss(dark))
        self.btn_clear.setIcon(self._icon(FIF.DELETE))
        if self.session.is_timing:      # 定时中：主色激活态
            self.btn_timer.setStyleSheet(theme.primary_active_qss(dark))
        pal = self.input.palette()
        pal.setColor(QPalette.PlaceholderText,
                     QColor(theme.C_TEXT_SUB_D if dark else theme.C_TEXT_SUB))
        self.input.setPalette(pal)
        self.lb_sent.setStyleSheet('color: %s;' % (theme.C_TEXT_SUB_D if dark else theme.C_TEXT_SUB))
        self.lb_recv.setStyleSheet('color: %s;' % (theme.C_TEXT_SUB_D if dark else theme.C_TEXT_SUB))
        self._on_input_changed()
        theme.fix_fonts(self)

    # ------------------------------------------------------------ 生命周期
    def closeEvent(self, e):
        self.session.stop_timer()
        self.session.link.close()
        super(Sc422App, self).closeEvent(e)
