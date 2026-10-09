# -*- coding: utf-8 -*-
"""A 方案基准：qfluentwidgets 组合控件做「指令卡片」。

对应 NewCanWindow 里一张卡片要承载的东西：
    名字 / 通道标签(胶囊) / 间隔 / 开关 / 帧数预览

测三件事（都模拟 CAN 窗口的真实负载）：
    T1  创建 N 张卡片的耗时                 —— 开窗/导入配置的成本
    T2  N 张卡片文本刷新 ROUNDS 轮          —— 模拟遥测/计数刷新
    T3  N 个开关切换 ROUNDS 轮              —— 模拟批量启停

结果以 "RESULT_JSON {..}" 单行打印到 stdout，跑完自动退出（无人值守）。
"""
import json
import os
import sys
import time

os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.*=false")

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFrame,
)
from qfluentwidgets import (
    ElevatedCardWidget, BodyLabel, CaptionLabel,
    PillPushButton, SwitchButton, SmoothScrollArea, setTheme, Theme,
)

# ---------------- 可调参数 ----------------
N_CARDS = 200          # 卡片数量
ROUNDS_TEXT = 10       # 文本刷新轮数  -> N_CARDS * ROUNDS_TEXT 次 setText
ROUNDS_SWITCH = 5      # 开关轮数      -> N_CARDS * ROUNDS_SWITCH 次 setChecked
USE_DARK = False       # 是否深色主题


class CmdCard(ElevatedCardWidget):
    """一张指令卡片：纯组合控件，零自绘。"""

    def __init__(self, idx, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)

        left = QVBoxLayout()
        left.setSpacing(2)
        self.name = BodyLabel(u"指令 %03d" % idx)
        self.meta = CaptionLabel(u"500ms · 3 帧 · ID 0x1E180000")
        left.addWidget(self.name)
        left.addWidget(self.meta)
        row.addLayout(left, 1)

        self.chip = PillPushButton(u"A 通道")
        self.chip.setFixedWidth(76)
        row.addWidget(self.chip)

        self.sw = SwitchButton()
        self.sw.setOnText(u"")
        self.sw.setOffText(u"")
        row.addWidget(self.sw, 0, Qt.AlignVCenter)


class BenchWin(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(u"A 方案 · qfluentwidgets 组合控件")
        self.resize(560, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        self.title = BodyLabel(u"qfluentwidgets 组合控件基准")
        root.addWidget(self.title)

        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        holder = QWidget()
        self.vbox = QVBoxLayout(holder)
        self.vbox.setContentsMargins(2, 2, 12, 2)
        self.vbox.setSpacing(8)
        self.scroll.setWidget(holder)
        root.addWidget(self.scroll, 1)

        self.cards = []
        self.result = {}

    # ---------- T1 ----------
    def build_cards(self):
        t0 = time.perf_counter()
        for i in range(N_CARDS):
            c = CmdCard(i)
            self.vbox.addWidget(c)
            self.cards.append(c)
        QApplication.processEvents()          # 含布局+首次绘制
        return (time.perf_counter() - t0) * 1000.0

    # ---------- T2 ----------
    def burst_text(self):
        t0 = time.perf_counter()
        for r in range(ROUNDS_TEXT):
            for i, c in enumerate(self.cards):
                c.name.setText(u"指令 %03d · 第 %d 轮" % (i, r))
                c.meta.setText(u"500ms · %d 帧 · tick %d" % (3 + r, r))
        QApplication.processEvents()
        return (time.perf_counter() - t0) * 1000.0

    # ---------- T3 ----------
    def burst_switch(self):
        t0 = time.perf_counter()
        for r in range(ROUNDS_SWITCH):
            on = bool(r % 2)
            for c in self.cards:
                c.sw.setChecked(on)
        QApplication.processEvents()
        return (time.perf_counter() - t0) * 1000.0

    def run(self):
        setTheme(Theme.DARK if USE_DARK else Theme.LIGHT)
        self.show()
        QApplication.processEvents()

        t1 = self.build_cards()
        t2 = self.burst_text()
        t3 = self.burst_switch()

        n_text = N_CARDS * ROUNDS_TEXT
        n_sw = N_CARDS * ROUNDS_SWITCH
        self.result = {
            "scheme": "A_fluentwidgets",
            "fluent_version": _fw_version(),
            "cards": N_CARDS,
            "T1_build_ms": round(t1, 2),
            "T1_per_card_ms": round(t1 / N_CARDS, 4),
            "T2_text_total_ms": round(t2, 2),
            "T2_text_ops": n_text,
            "T2_text_us_per_op": round(t2 * 1000.0 / n_text, 2),
            "T3_switch_total_ms": round(t3, 2),
            "T3_switch_ops": n_sw,
            "T3_switch_us_per_op": round(t3 * 1000.0 / n_sw, 2),
            "rss_mb": _rss_mb(),
            "startup_ms": None,   # 由外层脚本用 wall clock 量
        }
        print("RESULT_JSON " + json.dumps(self.result, ensure_ascii=False))
        sys.stdout.flush()


def _fw_version():
    try:
        import qfluentwidgets
        return getattr(qfluentwidgets, "__version__", "unknown")
    except Exception:
        return "unknown"


def _rss_mb():
    try:
        import ctypes, ctypes.wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.wintypes.DWORD),
                        ("PageFaultCount", ctypes.wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        pmc = PMC()
        pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return round(pmc.WorkingSetSize / 1024.0 / 1024.0, 1)
    except Exception:
        return None


def main():
    app = QApplication(sys.argv)
    win = BenchWin()
    win.run()
    QTimer.singleShot(300, app.quit)      # 自动退出，不用人工关窗
    rc = app.exec_()
    sys.exit(rc)


if __name__ == "__main__":
    main()
