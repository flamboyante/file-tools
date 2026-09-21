# -*- coding: utf-8 -*-
"""common · 跨页面复用的控件（通道配置条 / 日志面板等）。"""
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtSerialPort import QSerialPortInfo
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel

from qfluentwidgets import (ComboBox, EditableComboBox, PrimaryPushButton,
                            PushButton, TransparentToolButton, FluentIcon as FIF)

from uicmp.guiwidgets import theme
from uicmp.guiwidgets.theme import badge

BAUDS = ['115200', '9600', '921600', '4000000', '2000000']

# 常用档位（可输入的候选，不只限于这些——现场常需要敲奇数值）
BAUD_CHOICES = ['9600', '19200', '38400', '57600', '115200', '230400',
                '460800', '921600', '1000000', '2000000', '4000000']

# 通道预设：按 bmu_testkit/AGENT_INTERFACE.md §3 实测参数固化。
# 价值 = 防接错：选预设自动套波特率+校验，不用记 8O1 这种事。
# 数据位/停止位三个通道都是 8/1，不做 UI（底层 API 已支持透传）。
PRESETS = [
    ('BMU debug', 115200, 'N'),   # debug UART：字符交互
    ('self 422',  921600, 'O'),   # 自主管理 422
    ('SC 422',    921600, 'O'),   # SC 天线 422（当前跑文件传输）
]
CUSTOM_PRESET = '自定义'

PARITY_ITEMS = [('无校验 (N)', 'N'), ('奇校验 (O)', 'O'), ('偶校验 (E)', 'E')]


class ConnectionBar(QWidget):
    """通道配置条：预设 · 端口 · 波特率(可输入) · 校验 · 打开 · 状态徽章。

    ⚠️ 校验位是必须暴露的（P0）：SC/self 422 是 921600 **8O1**，
    只给波特率入口的话真机上按 8N1 打开必然通信失败（2026-09-21 审计发现）。

    参数按 settings_key（页面名）持久化——console/transfer/sc422 各记各的。
    """

    def __init__(self, link, dark=False, settings_key='common',
                 default_preset='BMU debug', parent=None):
        super(ConnectionBar, self).__init__(parent)
        self._link = link
        self._dark = dark
        self._key = 'connbar/%s' % settings_key
        self._default_preset = default_preset
        self._qs = QSettings('JiangCan', 'gui-ng')
        self._loading = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.GAP_SM)

        self.combo_preset = ComboBox()
        self.combo_preset.setFixedWidth(132)   # "BMU debug" 实测需 >=127px
        self.combo_preset.addItems([p[0] for p in PRESETS] + [CUSTOM_PRESET])
        self.combo_port = ComboBox()
        self.combo_port.setMinimumWidth(160)
        self.btn_refresh = TransparentToolButton(FIF.SYNC)
        self.btn_refresh.setToolTip('刷新串口列表')
        self.combo_baud = EditableComboBox()
        self.combo_baud.addItems(BAUD_CHOICES)
        self.combo_baud.setFixedWidth(134)   # 112 仍会裁 115200（内部 clear 按钮占位）
        self.combo_parity = ComboBox()
        self.combo_parity.addItems([p[0] for p in PARITY_ITEMS])
        self.combo_parity.setFixedWidth(110)
        self.btn_open = PrimaryPushButton('打开')
        self.btn_open.setFixedSize(88, 32)
        self.badge = badge('未连接', 'gray', dark)

        lay.addWidget(self.combo_preset, 0)
        lay.addWidget(self.combo_port, 0)
        lay.addWidget(self.btn_refresh, 0)
        lay.addWidget(self.combo_baud, 0)
        lay.addWidget(self.combo_parity, 0)
        lay.addWidget(self.btn_open, 0)
        lay.addWidget(self.badge, 0)
        lay.addStretch(1)

        self.btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_open.clicked.connect(self._toggle)
        self.combo_preset.currentTextChanged.connect(self._on_preset)
        self.combo_baud.currentTextChanged.connect(self._on_param_changed)
        self.combo_parity.currentTextChanged.connect(self._on_param_changed)
        self._link.opened.connect(self._on_opened)
        self._link.closed.connect(self._on_closed)
        self._link.error.connect(self._on_error)
        self.refresh_ports()
        self._load_settings()

    # ------------------------------------------------------------ 参数
    def parity_code(self):
        txt = self.combo_parity.currentText()
        for label, code in PARITY_ITEMS:
            if label == txt:
                return code
        return 'N'

    def _set_parity_code(self, code):
        for label, c in PARITY_ITEMS:
            if c == code:
                self.combo_parity.setCurrentText(label)
                return

    def _on_preset(self, name):
        """选预设 → 套参数；手动改参数 → 预设回落「自定义」。"""
        if self._loading:
            return
        for label, baud, parity in PRESETS:
            if label == name:
                self._loading = True
                self.combo_baud.setText(str(baud))   # setText：非列表值也生效
                self._set_parity_code(parity)
                self._loading = False
                self._save_settings()
                return
        self._save_settings()

    def _on_param_changed(self, _text):
        """参数被手动改动：预设切到「自定义」并持久化。"""
        if self._loading:
            return
        for label, baud, parity in PRESETS:
            if (self.combo_baud.currentText() == str(baud)
                    and self.parity_code() == parity):
                if self.combo_preset.currentText() != label:
                    self._loading = True
                    self.combo_preset.setCurrentText(label)
                    self._loading = False
                break
        else:
            if self.combo_preset.currentText() != CUSTOM_PRESET:
                self._loading = True
                self.combo_preset.setCurrentText(CUSTOM_PRESET)
                self._loading = False
        self._save_settings()

    # ------------------------------------------------------------ 持久化
    def _save_settings(self):
        self._qs.setValue(self._key + '/preset', self.combo_preset.currentText())
        self._qs.setValue(self._key + '/baud', self.combo_baud.currentText())
        self._qs.setValue(self._key + '/parity', self.parity_code())
        self._qs.setValue(self._key + '/port', self.current_port())

    def _load_settings(self):
        self._loading = True
        baud = self._qs.value(self._key + '/baud', '', type=str)
        parity = self._qs.value(self._key + '/parity', '', type=str)
        preset = self._qs.value(self._key + '/preset', '', type=str)
        if not preset:      # 首次运行：套本页默认预设（如 transfer → SC 422）
            preset = self._default_preset
            for label, b, p in PRESETS:
                if label == preset:
                    baud, parity = str(b), p
                    break
        if baud:
            self.combo_baud.setText(baud)      # setText：非列表值也能恢复
        if parity:
            self._set_parity_code(parity)
        if preset:
            self.combo_preset.setCurrentText(preset)
        port = self._qs.value(self._key + '/port', '', type=str)
        if port:
            for i in range(self.combo_port.count()):
                if self.combo_port.itemText(i).split('  ')[0].strip() == port:
                    self.combo_port.setCurrentIndex(i)
                    break
        self._loading = False

    # ------------------------------------------------------------ 端口
    def refresh_ports(self):
        self.combo_port.clear()
        for info in QSerialPortInfo.availablePorts():
            name = info.portName()
            desc = info.description() or ''
            self.combo_port.addItem('%s  %s' % (name, desc) if desc else name)
        if self.combo_port.count():
            self.combo_port.setCurrentIndex(0)
        # 刷新后尝试恢复上次端口
        port = self._qs.value(self._key + '/port', '', type=str)
        if port:
            for i in range(self.combo_port.count()):
                if self.combo_port.itemText(i).split('  ')[0].strip() == port:
                    self.combo_port.setCurrentIndex(i)
                    break

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
            self._save_settings()
            self._link.open(self.current_port(), baud=self.current_baud(),
                            data_bits=8, stop_bits=1, parity=self.parity_code())

    def _on_opened(self):
        # 「断开」是撤销型动作：主色家族但降一档（浅蓝 tint），
        # 把深蓝实心主按钮的名额让给页面当前该做的主操作
        self.btn_open.setText('断开')
        self.btn_open.setStyleSheet(theme.primary_tint_qss(self._dark))
        self._set_badge('已连接', 'ok')

    def _on_closed(self):
        self.btn_open.setText('打开')
        self.btn_open.setStyleSheet('')      # 恢复 PrimaryPushButton 原生深蓝
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
        if self._link.is_open:      # 断开态样式要随主题重算
            self.btn_open.setStyleSheet(theme.primary_tint_qss(dark))
