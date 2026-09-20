# -*- coding: utf-8 -*-
r"""dev_launcher · gui-ng 开发期统一入口（不依赖旧主窗口）。

四个按钮对应四个新页面，做完一个亮一个——这是「四个窗口先于主窗口」
策略的验收门面。最终主窗口迁移完成后，本入口退役。

跑法：
  cd C:\heike\uicmp
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe -m uicmp.dev_launcher
"""
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel)
from PyQt5.QtGui import QFontDatabase

from qfluentwidgets import (ElevatedCardWidget, PushButton, SubtitleLabel,
                            CaptionLabel, FluentIcon as FIF)

from uicmp.guiwidgets import theme


class DevLauncher(QDialog):
    def __init__(self):
        super(DevLauncher, self).__init__()
        self.setObjectName('DevLauncher')
        self.setWindowTitle('gui-ng · 开发入口')
        self.resize(460, 240)
        self._windows = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(theme.GAP)

        title = SubtitleLabel('gui-ng 四窗口')
        note = CaptionLabel('开发期验收入口：每完成一个亮一个；主窗口迁移后本窗口退役')
        note.setObjectName('devNote')
        v.addWidget(title)
        v.addWidget(note)

        grid = QHBoxLayout()
        grid.setSpacing(theme.GAP)
        self._btn_console = self._make_card(grid, '控制台', FIF.CONNECT, self._open_console)
        self._btn_transfer = self._make_card(grid, '文件传输', FIF.DOWNLOAD, None)
        self._btn_sc422 = self._make_card(grid, 'SC422', FIF.SEND, None)
        self._btn_debug = self._make_card(grid, 'CAN', FIF.ROBOT, None)
        v.addLayout(grid)
        v.addStretch(1)
        theme.apply_theme(self, False)

    def _make_card(self, layout, text, icon, cb):
        card = ElevatedCardWidget()
        card.setFixedSize(96, 96)
        cv = QVBoxLayout(card)
        cv.addStretch(1)
        btn = PushButton(icon, text)
        btn.setFixedWidth(80)
        if cb is None:
            btn.setEnabled(False)
            btn.setToolTip('未开工')
        else:
            btn.clicked.connect(cb)
        cv.addWidget(btn, 0, alignment=Qt.AlignCenter)
        cv.addStretch(1)
        layout.addWidget(card)
        return btn

    # ------------------------------------------------------------ 页面
    def _open_console(self):
        from uicmp.apps.console_app import ConsoleApp
        w = self._windows.get('console')
        if w is None or not w.isVisible():
            w = ConsoleApp()
            self._windows['console'] = w
        w.show()
        w.raise_()
        w.activateWindow()

    def closeEvent(self, e):
        for w in self._windows.values():
            w.close()
        super(DevLauncher, self).closeEvent(e)


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    w = DevLauncher()
    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
