# -*- coding: utf-8 -*-
r"""ConnectionBar 冒烟：通道预设 / 可输入波特率 / 校验位透传 / 持久化。

重点回归 P0 缺口：校验位必须真的传到 link.open（SC/self 422 是 8O1）。
跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_connection_bar.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase

from uicmp.guiwidgets.common import ConnectionBar, PRESETS


class FakeLink(object):
    """替身 link：只记录 open 参数与开关状态。"""

    class _Sig(object):
        def __init__(self):
            self._slots = []

        def connect(self, fn):
            self._slots.append(fn)

        def emit(self, *a):
            for fn in self._slots:
                fn(*a)

    def __init__(self):
        self.opened = self._Sig()
        self.closed = self._Sig()
        self.error = self._Sig()
        self.is_open = False
        self.open_args = None

    def open(self, port, **kw):
        self.open_args = dict(kw, port=port)
        self.is_open = True
        self.opened.emit()
        return True

    def close(self):
        self.is_open = False
        self.closed.emit()


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')

    KEY_BASE = 'connbar/_smoke'
    qs = QSettings('JiangCan', 'gui-ng')
    for k in ('preset', 'baud', 'parity', 'port'):
        qs.remove(KEY_BASE + '/' + k)

    link = FakeLink()
    bar = ConnectionBar(link, settings_key='_smoke', default_preset='SC 422')
    bar.show()

    # ---- 1. 首次运行套默认预设（SC 422 → 921600 + Odd）
    assert bar.combo_baud.currentText() == '921600', bar.combo_baud.currentText()
    assert bar.parity_code() == 'O', bar.parity_code()
    assert bar.combo_preset.currentText() == 'SC 422'
    print('1. 默认预设套用 OK（SC 422 → 921600 8O1）')

    # ---- 2. 切换预设联动
    bar.combo_preset.setCurrentText('BMU debug')
    assert bar.combo_baud.currentText() == '115200' and bar.parity_code() == 'N'
    bar.combo_preset.setCurrentText('self 422')
    assert bar.combo_baud.currentText() == '921600' and bar.parity_code() == 'O'
    print('2. 预设联动 OK（debug/self 切换参数正确）')

    # ---- 3. 手动改参数 → 预设回落「自定义」
    bar.combo_baud.setText('250000')             # 模拟手敲（setText 才能设非列表值）
    assert bar.combo_preset.currentText() == '自定义', bar.combo_preset.currentText()
    print('3. 可输入波特率 + 预设回落自定义 OK')

    # ---- 4. P0：校验位必须真的传到 link.open
    bar.combo_preset.setCurrentText('SC 422')
    bar.combo_port.clear()
    bar.combo_port.addItem('COM_TEST')
    bar._toggle()                                # 打开
    assert link.open_args is not None, '未触发 open'
    assert link.open_args.get('parity') == 'O', '校验位未透传: %r' % link.open_args
    assert link.open_args.get('baud') == 921600, link.open_args
    assert link.open_args.get('data_bits') == 8 and link.open_args.get('stop_bits') == 1
    print('4. P0 校验位透传 OK（open 收到 parity=O / 921600 8O1）')

    # ---- 5. 持久化：新建实例应读回上一组参数
    bar._toggle()                                # 关闭（顺带保存）
    bar2 = ConnectionBar(FakeLink(), settings_key='_smoke')
    assert bar2.combo_baud.currentText() == '921600', bar2.combo_baud.currentText()
    assert bar2.parity_code() == 'O', bar2.parity_code()
    assert bar2.combo_preset.currentText() == 'SC 422'
    print('5. 持久化 OK（新实例读回 921600 8O1 / SC 422）')

    # ---- 6. 非列表波特率也要能持久化恢复
    # （坑：EditableComboBox.setCurrentText 对列表外的值静默忽略——
    #   用 setText 才能设/恢复任意值，2026-09-21 实测）
    bar2.combo_baud.setText('250000')
    bar3 = ConnectionBar(FakeLink(), settings_key='_smoke')
    assert bar3.combo_baud.currentText() == '250000', \
        '非列表波特率未恢复: %r' % bar3.combo_baud.currentText()
    assert bar3.combo_preset.currentText() == '自定义'
    print('6. 非列表波特率持久化恢复 OK（250000 / 自定义）')

    # ---- 7. 收尾：清理测试留下的配置
    for k in ('preset', 'baud', 'parity', 'port'):
        qs.remove(KEY_BASE + '/' + k)
    print('7. 测试配置已清理 OK')
    print('SMOKE OK')


if __name__ == '__main__':
    main()
