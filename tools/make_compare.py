# -*- coding: utf-8 -*-
"""把 A/B 两方案 × 浅/深 共 4 张截图拼成一张对比图。

用 Qt 自己拼（不依赖 Pillow）。
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtGui import QImage, QPainter, QColor, QFont               # noqa: E402
from PyQt5.QtCore import Qt, QRectF, QPointF                          # noqa: E402
from PyQt5.QtWidgets import QApplication                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'docs', 'ui_three_way')

COL_W = 780
ASPECT = 900.0 / 1280.0
CELL_H = int(COL_W * ASPECT)          # 548
GAP = 20
LABEL_H = 30
TITLE_H = 56
PAD = 24

NAMES = [('a', 'A 方案 · qfluentwidgets 组合控件'),
         ('b', 'B 方案 · QWebEngine + HTML/CSS/JS')]

app = QApplication(sys.argv[:1])


def build():
    total_w = PAD * 2 + COL_W * 2 + GAP
    total_h = TITLE_H + (CELL_H + LABEL_H + GAP) * 2 + PAD
    canvas = QImage(total_w, total_h, QImage.Format_ARGB32)
    canvas.fill(QColor('#eef2f7'))

    p = QPainter(canvas)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    p.setFont(QFont('Microsoft YaHei UI', 14, QFont.Bold))
    p.setPen(QColor('#162033'))
    p.drawText(QRectF(PAD, 10, total_w - PAD * 2, 32),
               Qt.AlignLeft | Qt.AlignVCenter,
               'A / B 方案对比 · 同一测试用例 · 对照 docs/ui_mockup/ui_mockup_v3.html')
    p.setFont(QFont('Microsoft YaHei UI', 9))
    p.setPen(QColor('#7c8798'))
    p.drawText(QRectF(PAD, 31, total_w - PAD * 2, 20),
               Qt.AlignLeft | Qt.AlignVCenter,
               '数据与收发层完全同源（uicmp/core.py），差异只在渲染层　|　上排浅色，下排深色')

    for ci, (key, name) in enumerate(NAMES):
        for ri, theme in enumerate(('light', 'dark')):
            x = PAD + ci * (COL_W + GAP)
            y = TITLE_H + ri * (CELL_H + LABEL_H + GAP)

            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#ffffff'))
            p.drawRoundedRect(QRectF(x - 3, y - 3, COL_W + 6, CELL_H + LABEL_H + 6), 10, 10)

            p.setFont(QFont('Microsoft YaHei UI', 10, QFont.DemiBold))
            p.setPen(QColor('#162033'))
            p.drawText(QRectF(x + 6, y + 1, COL_W - 12, LABEL_H - 2),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       '%s　—　%s' % (name, '浅色' if ri == 0 else '深色'))

            src = os.path.join(OUT, 'shot_%s_%s.png' % (key, theme))
            if os.path.exists(src):
                img = QImage(src)
                if not img.isNull():
                    scaled = img.scaled(COL_W - 8, CELL_H - 4,
                                        Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    p.drawImage(QPointF(x, y + LABEL_H), scaled)
                else:
                    p.setPen(QColor('#e5484d'))
                    p.drawText(QRectF(x, y + LABEL_H, COL_W, 40), Qt.AlignCenter, '读图失败')
            else:
                p.setPen(QColor('#e5484d'))
                p.drawText(QRectF(x, y + LABEL_H, COL_W, 40), Qt.AlignCenter,
                           '缺文件 %s' % os.path.basename(src))
    p.end()

    out = os.path.join(OUT, 'compare_ab.png')
    canvas.save(out)
    print('  -> %s  (%d x %d)' % (out, canvas.width(), canvas.height()))
    return out


build()
print('done')
