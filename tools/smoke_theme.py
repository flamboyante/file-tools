# -*- coding: utf-8 -*-
"""theme 模块冒烟测试（offscreen 可跑，无需真屏幕）。

验证点：
1. apply_theme 浅/深来回切换不抛异常
2. 深色下 ElevatedCardWidget 底色确实变成 #161c26（坑②的验收）
3. fix_fonts 把 SimSun 拨正（坑③的验收，offscreen 需先手动载字体）
4. chip / badge / channel_badge 构造正常

跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\smoke_theme.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout
from PyQt5.QtGui import QColor, QFontDatabase
from qfluentwidgets import ElevatedCardWidget, BodyLabel

from uicmp.guiwidgets import theme

# offscreen 下字体表为空，不手动加载一个，family 判断会失真（出图同款坑）
# ⚠️ QFontDatabase 必须在 QApplication 之后用，之前用会直接段错误（实测）
app = QApplication([])
fid = QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
assert fid != -1, 'msyh.ttc 加载失败，字体断言会假失败'


class W(QDialog):
    def __init__(self):
        super(W, self).__init__()
        v = QVBoxLayout(self)
        self.card = ElevatedCardWidget(self)
        self.card.setFixedSize(200, 100)
        self.lb = BodyLabel('测试卡片', self.card)
        v.addWidget(self.card)
        v.addWidget(theme.chip('500K', 'blue', False))
        v.addWidget(theme.badge('运行中', 'run', False))
        v.addWidget(theme.channel_badge('A'))


def _card_bg(card):
    c = card.backgroundColor          # 1.11.3：属性，返回 QColor
    if callable(c):                   # 兼容未来版本改成方法
        c = c()
    return QColor(c).name()


def main():
    w = W()
    for dark in (False, True, False, True):
        theme.apply_theme(w, dark)
        bg = _card_bg(w.card)
        expect = '#161c26' if dark else '#ffffff'
        assert bg == expect, '卡片底色不符: dark=%s got=%s want=%s' % (dark, bg, expect)
        assert 'background' in w.styleSheet(), '窗口 QSS 缺背景'
        print('dark=%-5s card_bg=%s  label_font=%s' % (dark, bg, w.lb.font().family()))

    fam = w.lb.font().family()
    assert fam not in ('SimSun', 'NSimSun', '宋体', ''), '字体仍为 SimSun: %r' % fam

    f = theme.make_font(12, True)
    assert f.family() == theme.FONT_FAMILY and f.bold()

    print('SMOKE OK')


if __name__ == '__main__':
    main()
