# -*- coding: utf-8 -*-
r"""按钮配色选型图：5 个候选 × 浅/深两组（工具条按钮实际尺寸与形态）。

用途：配色拍板用。选定后把对应的值写进 theme.outline_button_qss。
跑法：
  C:\hkj\anaconda3\envs\pyqt_side_all_0328\python.exe tools\shot_button_colors.py
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QFrame, QLabel, QPushButton)
from PyQt5.QtGui import QFontDatabase

OUT = os.path.join(_ROOT, 'docs', 'gui_ng')
os.makedirs(OUT, exist_ok=True)


def cand_qss(bg, border, fg, hover, press):
    return ('''
    QPushButton {
        background: %s; border: 1px solid %s; border-radius: 7px;
        padding: 6px 13px; color: %s; font-size: 12px;
    }
    QPushButton:hover { background: %s; }
    QPushButton:pressed { background: %s; }
    ''' % (bg, border, fg, hover, press))


# (名称, 说明, 浅色参数, 深色参数)
#   浅色: (底, 边框, 字, hover, press)  深色: 同
CANDS = [
    ('A 冷蓝灰', '带蓝的灰，中性但有色相',
     ('#f4f7fc', '#c3cede', '#2c3a52', '#e6eefa', '#dbe6f6'),
     ('#2a3145', '#3f4a63', '#dce4f2', '#33405c', '#27303f')),
    ('B 深蓝实', '蓝底实心，和主色同族',
     ('#e8f1ff', '#b8d4ff', '#1d4ed8', '#d7e8ff', '#c7ddff'),
     ('#1e3a5f', '#33608f', '#cfe2ff', '#254a75', '#18304f')),
    ('C 蓝描边', '暗底 + 主色描边，轻但清楚',
     ('#ffffff', '#6a9bf0', '#1d4ed8', '#eef4ff', '#dbeafe'),
     ('#141c26', '#4c8dff', '#8ab4ff', '#1b2a47', '#16243c')),
    ('D 暖米', '暖色对照（与蓝主色易冲突）',
     ('#fdf6e3', '#ecd9a8', '#8a6d1f', '#f8eecd', '#f2e2b5'),
     ('#33301f', '#4f4931', '#ffe0a3', '#3f3a25', '#2a281a')),
    ('E 现状', '当前值（中性抬亮灰）',
     ('#ffffff', '#cfd7e3', '#1f2733', '#eef4ff', '#dbeafe'),
     ('#2a3441', '#3d4a5c', '#e6edf3', '#26385e', '#2e4573')),
]

BTN_TEXTS = ['添加', '暂停', '停止', '锁定']


class Preview(QDialog):
    def __init__(self):
        super(Preview, self).__init__()
        self.setObjectName('Preview')
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        root.addWidget(self._section('深色模式（页底 #0d1117）', '#0d1117', dark=True))
        root.addWidget(self._section('浅色模式（页底 #eef2f9）', '#eef2f9', dark=False))

    def _section(self, title, page_bg, dark):
        frame = QFrame()
        frame.setStyleSheet('QFrame{background:%s; border-radius:10px;}' % page_bg)
        v = QVBoxLayout(frame)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(6)
        lb = QLabel(title)
        lb.setStyleSheet('color:%s; font-size:12px; font-weight:600;'
                         % ('#8d99a8' if dark else '#5b6b7b'))
        v.addWidget(lb)
        for name, desc, light, darkp in CANDS:
            row = QHBoxLayout()
            row.setSpacing(8)
            tag = QLabel('%s · %s' % (name, desc))
            tag.setFixedWidth(300)
            tag.setStyleSheet('color:%s; font-size:12px;'
                              % ('#9fb0bf' if dark else '#64748b'))
            row.addWidget(tag)
            params = darkp if dark else light
            qss = cand_qss(*params)
            for t in BTN_TEXTS:
                b = QPushButton(t)
                b.setStyleSheet(qss)
                b.setFixedWidth(74)
                row.addWidget(b)
            row.addStretch(1)
            v.addLayout(row)
        return frame


def main():
    app = QApplication(sys.argv)
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    w = Preview()
    w.setStyleSheet('Preview{background:#f0f2f6;}')
    w.show()
    for _ in range(5):
        app.processEvents()
    w.adjustSize()
    app.processEvents()
    p = os.path.join(OUT, 'button_color_candidates.png')
    w.grab().save(p)
    print('saved', p)


if __name__ == '__main__':
    main()
