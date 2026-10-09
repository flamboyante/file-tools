# -*- coding: utf-8 -*-
"""A 方案视觉渲染：用 qfluentwidgets 复刻 mockup 里「气泡指令条」的卡片。

目标不是 100% 还原，而是**用组合控件尽力复刻**，然后截图出来跟 mockup 对比。
凡是 qfluentwidgets 做不到的（hover 位移、渐变按钮、color-mix），代码里用注释标出。

产出：out_fluent_light.png / out_fluent_dark.png
"""
import os
import sys

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from qfluentwidgets import (
    ElevatedCardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PillPushButton, SwitchButton, SmoothScrollArea,
    setTheme, Theme, setThemeColor,
)

HERE = os.path.dirname(os.path.abspath(__file__))

# mockup 的设计令牌（摘自 ui_mockup_final_bubbles.html :root / .dark）
TOK = {
    "light": dict(bg="#eef2f9", panel="#ffffff", line="#e2e8f2",
                  text="#1d2633", muted="#7c8798", accent="#2f6fed",
                  blue="#2f6fed", purple="#8b5cf6", green="#0e9f6e",
                  gray_soft="#eef1f6", blue_soft="#e9f0ff", purple_soft="#f0eafd",
                  green_soft="#e5f6ef", orange_soft="#fdf2dd", orange="#f29400",
                  red="#e5484d", red_soft="#fdeaea"),
    "dark": dict(bg="#0d1117", panel="#161c26", line="#263141",
                 text="#e8edf5", muted="#8d99a8", accent="#4c8dff",
                 blue="#4c8dff", purple="#a78bfa", green="#2fc48a",
                 gray_soft="#222b38", blue_soft="#1b2a47", purple_soft="#2b2044",
                 green_soft="#0f2e22", orange_soft="#32260d", orange="#f6b64a",
                 red="#f2555a", red_soft="#3a1a1d"),
}

CARDS = [
    ("A", "快遥 FAST", "ch=A · 无限次 · 500ms", ["间隔 500ms", "1 帧", "IRCode 00 5A"], "运行中", True, True),
    ("A", "慢遥 SLOW1", "ch=A · 无限次 · 500ms", ["间隔 500ms", "1 帧", "IRCode 00 AA"], "已停止", False, False),
    ("A", "星敏感器 STAR", "ch=A · 无限次 · 100ms", ["间隔 100ms", "5 帧", "ID 0x1E160000"], "待发送", False, False),
    ("B", "BUS 总线帧", "ch=B · 无限次 · 500ms", ["间隔 500ms", "1 帧", "IRCode 00 25 25"], "已停止", False, False),
    ("B", "姿态 ATTITUDE", "ch=B · 无限次 · 500ms", ["间隔 500ms", "6 帧", "ID 0x1E2E0000"], "失败", False, False),
]

BADGE = {  # 状态 -> (前景, 背景)  对应 mockup 的 .badge.run/gray/pend/err
    "运行中": ("accent", "blue_soft"),
    "已停止": ("muted", "gray_soft"),
    "待发送": ("orange", "orange_soft"),
    "失败": ("red", "red_soft"),
}


class CmdBar(ElevatedCardWidget):
    """一张指令卡片。用组合控件拼，不自绘。"""

    def __init__(self, ch, name, sub, chips, status, on, running, t):
        super(CmdBar, self).__init__()
        self.setFixedHeight(60)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(12)

        # ① 通道方块：QSS qlineargradient 能做渐变（能复刻 mockup 的 .cmd-ch）
        sq = QLabel(ch)
        sq.setFixedSize(34, 34)
        sq.setAlignment(Qt.AlignCenter)
        c1, c2 = ("#4c8dff", "#2f6fed") if ch == "A" else ("#a78bfa", "#8b5cf6")
        sq.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 %s,stop:1 %s);border-radius:10px;color:#fff;"
            "font-weight:800;font-size:14px;}" % (c1, c2))
        row.addWidget(sq)

        # ② 名称 + 副标题
        col = QVBoxLayout()
        col.setSpacing(1)
        nm = BodyLabel(name)
        nm.setStyleSheet("font-weight:700;font-size:13.5px;color:%s;" % t["text"])
        sb = CaptionLabel(sub)
        sb.setStyleSheet("font-size:10.5px;color:%s;" % t["muted"])
        col.addWidget(nm)
        col.addWidget(sb)
        row.addLayout(col, 1)

        # ③ chips：PillPushButton 默认是蓝色实心，这里用 QSS 压成 mockup 的浅底 chip
        for txt in chips:
            c = PillPushButton(txt)
            c.setFixedHeight(22)
            c.setCursor(Qt.ArrowCursor)
            c.setStyleSheet(
                "PillPushButton{background:%s;color:%s;border:none;"
                "border-radius:99px;padding:0 11px;font-size:11px;font-weight:400;}"
                % (t["gray_soft"], t["muted"]))
            row.addWidget(c)

        # ④ 状态 badge
        fg, bgk = BADGE.get(status, ("muted", "gray_soft"))
        bd = QLabel(status)
        bd.setFixedHeight(20)
        bd.setAlignment(Qt.AlignCenter)
        bd.setStyleSheet(
            "QLabel{background:%s;color:%s;border-radius:99px;"
            "padding:0 10px;font-size:10.5px;font-weight:600;}" % (t[bgk], t[fg]))
        row.addWidget(bd)

        # ⑤ 开关
        sw = SwitchButton()
        try:
            sw.setOnText("")
            sw.setOffText("")
        except Exception:
            pass
        sw.setChecked(on)
        sw.setFixedWidth(44)
        row.addWidget(sw)


class Win(QWidget):
    def __init__(self, mode):
        super(Win, self).__init__()
        self.mode = mode
        t = TOK[mode]
        self.setWindowTitle("A 方案 · qfluentwidgets")
        self.resize(660, 430)
        self.setStyleSheet("QWidget{background:%s;}" % t["bg"])

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        head = QLabel("qfluentwidgets 组合控件复刻")
        head.setStyleSheet("font-size:17px;font-weight:700;color:%s;" % t["text"])
        root.addWidget(head)

        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("SmoothScrollArea{background:transparent;border:none;}"
                                  "QWidget{background:transparent;}")
        holder = QWidget()
        v = QVBoxLayout(holder)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(8)
        for ch, name, sub, chips, status, on, running in CARDS:
            v.addWidget(CmdBar(ch, name, sub, chips, status, on, running, t))
        v.addStretch(1)
        self.scroll.setWidget(holder)
        root.addWidget(self.scroll, 1)

    def shot(self):
        self.show()
        QApplication.processEvents()
        QTimer.singleShot(900, self._grab)

    def _grab(self):
        p = os.path.join(HERE, "out_fluent_%s.png" % self.mode)
        pm = self.grab()
        pm.save(p, "PNG")
        sys.stderr.write("SAVED %s  %dx%d\n" % (p, pm.width(), pm.height()))
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    mode = sys.argv[1] if len(sys.argv) > 1 else "light"
    setThemeColor("#2f6fed")
    setTheme(Theme.DARK if mode == "dark" else Theme.LIGHT)
    w = Win(mode)
    w.shot()
    app.exec_()
    print("DONE %s" % mode)


if __name__ == "__main__":
    main()
