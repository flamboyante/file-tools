# -*- coding: utf-8 -*-
"""三方案 UI 对比 —— 统一入口。

三个按钮各开一个**独立窗口**（不是同一窗口内切换）。
理由：切换式入口需要销毁重建窗口，你没法并排比较；
独立窗口可以同时摆在屏幕上，一眼看出差别。

用法（两种）：
    1. 主程序命令栏 → 「UI 方案对比」
    2. 命令行：python -m uicmp.launcher
"""
import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QWidget, QGridLayout)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from uicmp import core                                      # noqa: E402

CARDS = [
    ('A', 'qfluentwidgets 1.11.3 组合控件',
     'Qt 进程内自绘。用现成组件搭，投影 / 开关动画由控件库提供。\n'
     '细节样式（胶囊、徽章）仍要 QSS 描 —— 是「少 QSS」，不是「无 QSS」。'),
    ('B', 'QWebEngine + HTML/CSS/JS',
     'Chromium 跨进程合成（内核 83）。\n'
     '视觉上限最高，代价是多一层进程 + 桥接约束（见模块注释两条铁律）。'),
]


class Launcher(QDialog):
    """三方案入口。点哪个开哪个，可同时开三个并排看。"""

    def __init__(self, parent=None):
        super(Launcher, self).__init__(parent)
        self.setWindowTitle('UI 方案对比 · 统一测试用例')
        self.setMinimumSize(680, 380)
        self._wins = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(12)

        head = QLabel('同一份数据、同一套收发层，只换渲染层')
        head.setStyleSheet('font-size:15px; font-weight:700;')
        v.addWidget(head)

        sub = QLabel('测试用例：%s' % (core.case_source() or 'uicmp/case.json'))
        sub.setStyleSheet('color:#7c8798; font-size:12px;')
        v.addWidget(sub)

        note = QLabel('两个窗口可同时打开并排比较。请对同一张卡片做同样的操作。')
        note.setStyleSheet('color:#7c8798; font-size:12px;')
        v.addWidget(note)

        grid = QGridLayout()
        grid.setSpacing(12)
        for i, (key, title, desc) in enumerate(CARDS):
            grid.addWidget(self._make_card(key, title, desc), i // 3, i % 3)
        v.addLayout(grid, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        btn = QPushButton('全部打开')
        btn.clicked.connect(self.open_all)
        foot.addWidget(btn)
        v.addLayout(foot)

    def _make_card(self, key, title, desc):
        box = QWidget()
        box.setStyleSheet(
            'QWidget{background:#ffffff; border:1px solid #dfe7f1; border-radius:12px;}'
            'QLabel{border:none;}')
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(7)

        t = QLabel('%s 方案' % key)
        t.setStyleSheet('font-size:15px; font-weight:700;')
        v.addWidget(t)

        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet('color:#5b6675; font-size:12px;')
        v.addWidget(d, 1)

        b = QPushButton('打开')
        b.clicked.connect(lambda _=False, k=key: self.open_one(k))
        v.addWidget(b)
        return box

    # ------------------------------------------------------------ 开关
    def open_one(self, key):
        w = self._wins.get(key)
        if w is not None:
            try:
                if w.isVisible():
                    w.raise_()
                    w.activateWindow()
                    return w
            except RuntimeError:
                pass
        if key == 'A':
            from uicmp.impl_a_fluent import AWindow as W
        else:
            from uicmp.impl_b_web import BWindow as W
        w = W()
        w.setAttribute(Qt.WA_DeleteOnClose, False)
        self._wins[key] = w
        w.show()
        return w

    def open_all(self):
        for key, _t, _d in CARDS:
            self.open_one(key)

    def closeEvent(self, e):
        for w in list(self._wins.values()):
            try:
                w.close()
            except Exception:
                pass
        super(Launcher, self).closeEvent(e)


def show(parent=None):
    """给主程序调用的入口。"""
    dlg = Launcher(parent)
    dlg.setWindowModality(Qt.NonModal)
    dlg.show()
    return dlg


if __name__ == '__main__':
    app = QApplication(sys.argv)
    win = Launcher()
    win.show()
    sys.exit(app.exec_())
