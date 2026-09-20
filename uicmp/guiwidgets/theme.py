# -*- coding: utf-8 -*-
"""theme · 新 GUI 统一色板与主题切换（浅/深）。

════════════════════════════════════════════════════════════════
这个模块存在的理由
════════════════════════════════════════════════════════════════
色板只是它的一半价值；另一半是把 qfluentwidgets 1.11.3 主题切换的
全部已知坑收敛成「调一个函数」，让任何新页面不再各自踩坑：

① `setTheme()` 不管顶层 QDialog 背景（白字白底）→ QPalette 补
② `ElevatedCardWidget` 底色不跟随 `setTheme()` → `setBackgroundColor()`
   显式指定；⚠️ 顺序：先重建卡片、再上色，反了会被重建覆盖
③ qfluentwidgets 的 label 构造时 QFont 只设 pixelSize、不设 family，
   中文 Windows 上落到 SimSun（宋体）→ `fix_fonts()` 逐个拨正，
   **每次重建控件后都要再拨一次**

以上三条全部是 2026-09-20 在 exp/ui-three-way 分支实测过的（见
docs/ui_three_way/README.md 第四节），不是理论推断。

色值来源：docs/ui_mockup/ui_mockup_v3.html（A 方案已验证还原 90%）。
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPalette, QFont
from PyQt5.QtWidgets import QWidget, QLabel, QSizePolicy

from qfluentwidgets import (Theme, setTheme, CardWidget, ElevatedCardWidget)

# ---------------------------------------------------------------- 色板 token
# 命名约定：不带后缀 = 浅色用；*_D = 深色用。页面代码禁止散写色值，
# 一律从这里取 —— 「清新配色」跨页面成立的前提就是色板单点维护。

C_PRIMARY      = '#2f6fed'   # 主色（蓝）——按钮 / 强调 / 运行态
C_PRIMARY_D    = '#4c8dff'
C_PRIMARY_BG   = '#e9f0ff'   # 主色的浅底（胶囊/徽章背景用）
C_PRIMARY_BG_D = '#1b2a47'

C_PURPLE       = '#8b5cf6'   # 通道 B / 次强调
C_PURPLE_D     = '#a78bfa'
C_PURPLE_BG    = '#f0eafd'
C_PURPLE_BG_D  = '#2b2044'

C_GREEN        = '#0e9f6e'   # 成功 / 已连接 / RX
C_GREEN_D      = '#2fc48a'
C_GREEN_BG     = '#e5f6ef'
C_GREEN_BG_D   = '#0f2e22'

C_RED          = '#e5484d'   # 错误 / 断开
C_RED_D        = '#f2555a'
C_RED_BG       = '#fdeaea'
C_RED_BG_D     = '#3a1a1d'

C_GRAY         = '#7c8798'   # 中性 / 停止 / 占位
C_GRAY_D       = '#8d99a8'
C_GRAY_BG      = '#e8edf3'
C_GRAY_BG_D    = '#252e3a'

C_BUSY         = '#5b6b7b'   # 进行中（蓝灰，区别于主色蓝）
C_BUSY_D       = '#9fb0bf'

# 面板与文字
C_WINDOW       = '#eef2f9'   # 顶层窗口底
C_WINDOW_D     = '#0d1117'
C_CARD         = '#ffffff'   # 卡片底
C_CARD_D       = '#161c26'
C_TEXT         = '#1f2733'   # 主文字
C_TEXT_D       = '#e6edf3'
C_TEXT_SUB     = '#5b6b7b'   # 次级文字
C_TEXT_SUB_D   = '#8d99a8'

# ---------------------------------------------------------------- 尺寸 token
R_CARD   = 10    # 卡片圆角
R_CHIP   = 11    # 胶囊/徽章圆角
GAP      = 10    # 通用间距（卡片间、区块间）
GAP_SM   = 6     # 小间距（胶囊内、行内）

FONT_FAMILY = 'Microsoft YaHei UI'
FONT_SIZE_BODY   = 12    # 正文（qfluentwidgets Caption 侧）
FONT_SIZE_SUB    = 10.5  # 徽章/说明
FONT_SIZE_TITLE  = 14    # 卡片标题（StrongBodyLabel 级）


# ---------------------------------------------------------------- QSS 工厂
def chip_style(kind, dark):
    """胶囊样式。kind ∈ {blue, purple, green, red, gray}。"""
    pal = {
        'blue':   (C_PRIMARY, C_PRIMARY_D, C_PRIMARY_BG, C_PRIMARY_BG_D),
        'purple': (C_PURPLE,  C_PURPLE_D,  C_PURPLE_BG,  C_PURPLE_BG_D),
        'green':  (C_GREEN,   C_GREEN_D,   C_GREEN_BG,   C_GREEN_BG_D),
        'red':    (C_RED,     C_RED_D,     C_RED_BG,     C_RED_BG_D),
        'gray':   (C_GRAY,    C_GRAY_D,    C_GRAY_BG,    C_GRAY_BG_D),
    }[kind]
    fg = pal[1] if dark else pal[0]
    bg = pal[3] if dark else pal[2]
    return ('QLabel{background:%s; color:%s; border-radius:%dpx;'
            'padding:3px 11px; font-size:%gpx;}' % (bg, fg, R_CHIP, FONT_SIZE_BODY - 1))


def badge_style(kind, dark):
    """状态徽章样式。kind ∈ {ok, run, busy, err, gray}。"""
    pal = {
        'ok':   (C_GREEN, C_GREEN_D, C_GREEN_BG, C_GREEN_BG_D),
        'run':  (C_PRIMARY, C_PRIMARY_D, C_PRIMARY_BG, C_PRIMARY_BG_D),
        'busy': (C_BUSY,  C_BUSY_D,  C_GRAY_BG,   C_GRAY_BG_D),
        'err':  (C_RED,   C_RED_D,   C_RED_BG,    C_RED_BG_D),
        'gray': (C_GRAY,  C_GRAY_D,  C_GRAY_BG,   C_GRAY_BG_D),
    }[kind]
    fg = pal[1] if dark else pal[0]
    bg = pal[3] if dark else pal[2]
    return ('QLabel{background:%s; color:%s; border-radius:%dpx;'
            'padding:2px 10px; font-size:%gpx; font-weight:600;}'
            % (bg, fg, R_CHIP, FONT_SIZE_SUB))


def chip(text, kind, dark):
    """胶囊 QLabel（⚠️ WA_StyledBackground 必须开，否则 background 不绘制）。"""
    lb = QLabel(text)
    lb.setAttribute(Qt.WA_StyledBackground, True)
    lb.setStyleSheet(chip_style(kind, dark))
    lb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lb


def badge(text, kind, dark):
    """状态徽章 QLabel。"""
    lb = QLabel(text)
    lb.setAttribute(Qt.WA_StyledBackground, True)
    lb.setStyleSheet(badge_style(kind, dark))
    lb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return lb


def channel_badge(ch, dark=False, size=34):
    """通道方块徽章（渐变底 + 白字）。A=蓝 / B=紫。"""
    lb = QLabel(str(ch))
    lb.setFixedSize(size, size)
    lb.setAlignment(Qt.AlignCenter)
    a, b = ((C_PRIMARY_D, C_PRIMARY) if str(ch).upper() == 'A'
            else (C_PURPLE_D, C_PURPLE))
    lb.setStyleSheet(
        'QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,'
        'stop:0 %s,stop:1 %s); color:#ffffff; border-radius:%dpx;'
        'font-size:%dpx; font-weight:800;}' % (a, b, R_CARD, int(size * 0.42)))
    return lb


# ---------------------------------------------------------------- 字体修正
_BAD_FAMILIES = ('SimSun', 'NSimSun', '宋体', '')


def fix_fonts(widget):
    """把落到 SimSun 的控件字体族拨正（坑③）。

    qfluentwidgets 的 label 构造时 QFont() 只设 pixelSize 不设 family，
    family 取 QApplication.font() —— 中文 Windows 上是 SimSun。
    `setFontFamilies()` / 窗口级 `setFont()` 实测都改不动（label 是
    显式 setFont 的，不走继承），只能建好后逐个拨。
    **每次重建控件后都要再调一次。**
    """
    for w in widget.findChildren(QWidget):
        try:
            fam = w.font().family()
        except Exception:
            continue
        if fam in _BAD_FAMILIES:
            f = w.font()
            f.setFamily(FONT_FAMILY)
            w.setFont(f)


def make_font(point_size=FONT_SIZE_BODY, bold=False):
    """统一字体构造入口（新代码用它，别裸 QFont）。"""
    f = QFont(FONT_FAMILY)
    f.setPointSize(point_size)
    f.setBold(bold)
    return f


# ---------------------------------------------------------------- 主题切换
def apply_theme(win, dark):
    """对一个顶层窗口应用浅/深主题（坑①②③一次收敛）。

    ⚠️ 调用约定：窗口若重建了卡片类控件，**先重建、后调本函数**——
    `setBackgroundColor` 的上色会被随后的重建覆盖（坑②的顺序）。

    win 需要在自己的 QSS / 控件刷新逻辑里响应 dark 布尔值；
    本函数负责的是三件通用的事：qfluentwidgets 全局主题、
    顶层背景（QPalette + 窗口 QSS）、已建卡片底色、字体。
    """
    setTheme(Theme.DARK if dark else Theme.LIGHT)

    # 坑①：setTheme 不管顶层背景 → QPalette + QSS 双保险
    pal = win.palette()
    pal.setColor(QPalette.Window, QColor(C_WINDOW_D if dark else C_WINDOW))
    win.setPalette(pal)
    win.setAutoFillBackground(True)
    cls_name = win.metaObject().className()
    win.setStyleSheet('%s{background:%s;}' % (
        cls_name, C_WINDOW_D if dark else C_WINDOW))

    # 坑②：卡片底色不跟随主题 → 显式指定（先停动画再上色，立即生效）
    bg = QColor(C_CARD_D if dark else C_CARD)
    for cls in (CardWidget, ElevatedCardWidget):
        for w in win.findChildren(cls):
            try:
                w.backgroundColorAni.stop()
            except Exception:
                pass
            try:
                w.setBackgroundColor(bg)
            except Exception:
                pass

    # 坑③：SimSun 拨正
    fix_fonts(win)
