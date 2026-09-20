# -*- coding: utf-8 -*-
"""common · 跨页面复用的控件（连接条 / 日志面板等）。"""
from PyQt5.QtCore import Qt
from PyQt5.QtSerialPort import QSerialPortInfo
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel

from qfluentwidgets import (ComboBox, PrimaryPushButton, PushButton,
                            TransparentToolButton, FluentIcon as FIF)

from uicmp.guiwidgets import theme
from uicmp.guiwidgets.theme import badge

BAUDS = ['115200', '9600', '921600', '4000000', '2000000']


class ConnectionBar(QWidget):
    """串口连接条：端口选择 · 刷新 · 波特率 · 打开/关闭 · 状态徽章。

    直接绑定一个 SerialLink，页面不再各自维护连接 UI。
    用法：
        bar = ConnectionBar(link)
        bar.opened/closed/error 信号按需订阅（已转发自 link）
    """

    def __init__(self, link, dark=False, bauds=BAUDS, parent=None):
        super(ConnectionBar, self).__init__(parent)
        self._link = link
        self._dark = dark

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.GAP_SM)

        self.combo_port = ComboBox()
        self.combo_port.setMinimumWidth(180)
        self.btn_refresh = TransparentToolButton(FIF.SYNC)
        self.btn_refresh.setToolTip('刷新串口列表')
        self.combo_baud = ComboBox()
        self.combo_baud.addItems(bauds)
        self.btn_open = PrimaryPushButton('打开')
        self.btn_open.setFixedWidth(88)
        self.badge = badge('未连接', 'gray', dark)

        lay.addWidget(self.combo_port, 0)
        lay.addWidget(self.btn_refresh, 0)
        lay.addWidget(QLabel('@'), 0)
        lay.addWidget(self.combo_baud, 0)
        lay.addWidget(self.btn_open, 0)
        lay.addWidget(self.badge, 0)
        lay.addStretch(1)

        self.btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_open.clicked.connect(self._toggle)
        self._link.opened.connect(self._on_opened)
        self._link.closed.connect(self._on_closed)
        self._link.error.connect(self._on_error)
        self.refresh_ports()

    # ------------------------------------------------------------ 端口
    def refresh_ports(self):
        self.combo_port.clear()
        for info in QSerialPortInfo.availablePorts():
            name = info.portName()
            desc = info.description() or ''
            self.combo_port.addItem('%s  %s' % (name, desc) if desc else name)
        if self.combo_port.count():
            self.combo_port.setCurrentIndex(0)

    def current_port(self):
        txt = self.combo_port.currentText()
        return txt.split('  ')[0].strip() if txt else ''

    def current_baud(self):
        try:
            return int(self.combo_baud.currentText())
        except ValueError:
            return 115200

    # ------------------------------------------------------------ 开关
    def _toggle(self):
        if self._link.is_open:
            self._link.close()
        elif self.current_port():
            self._link.open(self.current_port(), baud=self.current_baud())

    def _on_opened(self):
        self.btn_open.setText('关闭')
        self._set_badge('已连接', 'ok')

    def _on_closed(self):
        self.btn_open.setText('打开')
        self._set_badge('未连接', 'gray')

    def _on_error(self, msg):
        if '失败' in msg or '异常' in msg:
            self._set_badge('故障', 'err')

    def _set_badge(self, text, kind):
        new = badge(text, kind, self._dark)
        self.layout().replaceWidget(self.badge, new)
        self.badge.deleteLater()
        self.badge = new

    # ------------------------------------------------------------ 主题
    def set_dark(self, dark):
        self._dark = dark
        kind = 'ok' if self._link.is_open else 'gray'
        self._set_badge(self.badge.text(), kind)
