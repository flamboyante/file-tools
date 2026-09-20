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

from qfluentwidgets import (Theme, setTheme, setThemeColor,
                            CardWidget, ElevatedCardWidget)

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

# ------------------------------------------------------------ 状态语义色
# 分层设计（对比度约束不同）：
#   STRIPE = 图形元素（3:1 达标即可）→ 用亮色，色条清透
#   TEXT   = 文字（4.5:1 必须达标）→ 用深/浅亮色，保证可读
# 明度对齐到同族：蓝/绿/红/灰四色的视觉重量一致，色条并排不打架。
STATE_STRIPE = {           # (浅色, 深色)
    'running': ('#3b82f6', '#4c8dff'),
    'done':    ('#10b981', '#2fc48a'),
    'failed':  ('#ef4444', '#f2555a'),
    'pending': ('#94a3b8', '#64748b'),
    'skipped': ('#cbd5e1', '#4a5561'),
    'busy':    ('#60a5fa', '#7aa7ff'),
}
STATE_TEXT = {             # (浅色, 深色)——文字对比度 4.5:1+
    'running': ('#1d4ed8', '#7aa7ff'),
    'done':    ('#047857', '#34d399'),
    'failed':  ('#dc2626', '#fb7185'),
    'pending': ('#64748b', '#8d99a8'),
    'skipped': ('#94a3b8', '#5b6b7b'),
    'busy':    ('#1d4ed8', '#7aa7ff'),
}


def state_stripe(kind, dark):
    a, b = STATE_STRIPE.get(kind, STATE_STRIPE['pending'])
    return b if dark else a


def state_text(kind, dark):
    a, b = STATE_TEXT.get(kind, STATE_TEXT['pending'])
    return b if dark else a


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
    # 坑④（2026-09-20 补）：qfluentwidgets 出厂强调色是青绿 #009faa——
    # 不显式设置的话，PrimaryPushButton/CheckBox/Switch 全是那个绿调。
    # 必须每次随主题重设：→ 主蓝（浅 #2f6fed / 深 #4c8dff）
    setThemeColor(C_PRIMARY_D if dark else C_PRIMARY)

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


# ================================================================ 控件 QSS 工厂
# 目标：把「旧批量窗口验证过的那套清新配方」+ v3 卡片语言统一到这里，
# 一次定义、所有页面共用、浅深双套。细则见各函数 docstring。

def _c(dark, light_val, dark_val):
    return dark_val if dark else light_val


def table_qss(dark):
    """表格：白卡圆角 + 定制表头 + 行 hover。浅深双套。"""
    card = _c(dark, C_CARD, C_CARD_D)
    border = _c(dark, '#dfe5ee', '#232c39')
    grid = _c(dark, '#eef1f6', '#1f2937')
    head_bg = _c(dark, '#f5f7fa', '#1d2530')
    head_fg = _c(dark, C_TEXT_SUB, C_TEXT_SUB_D)
    text = _c(dark, C_TEXT, C_TEXT_D)
    hover = _c(dark, '#f3f7ff', '#1b2532')
    return '''
    QTableWidget {
        background: %(card)s;
        border: 1px solid %(border)s;
        border-radius: %(radius)dpx;
        gridline-color: %(grid)s;
        color: %(text)s;
        font-size: 12px;
    }
    QTableWidget::item { padding: 6px 10px; border: none; }
    QTableWidget::item:hover { background: %(hover)s; }
    QTableWidget QTableCornerButton::section { background: %(head_bg)s; border: none; }
    QHeaderView::section {
        background: %(head_bg)s;
        color: %(head_fg)s;
        border: none;
        border-bottom: 1px solid %(grid)s;
        padding: 8px 10px;
        font-weight: 600;
        font-size: 12px;
    }
    ''' % dict(card=card, border=border, grid=grid, head_bg=head_bg,
               head_fg=head_fg, text=text, hover=hover, radius=R_CARD)


def combo_qss(dark):
    """下拉框（表格单元格内 / 独立皆可用）。"""
    bg = _c(dark, C_CARD, '#1d2530')
    border = _c(dark, '#cfd7e3', '#2a3442')
    text = _c(dark, C_TEXT, C_TEXT_D)
    hover_border = _c(dark, '#8fb5ff', '#4c8dff')
    view_bg = _c(dark, C_CARD, '#1d2530')
    sel_bg = _c(dark, C_PRIMARY_BG, C_PRIMARY_BG_D)
    return '''
    QComboBox {
        background: %(bg)s;
        border: 1px solid %(border)s;
        border-radius: 6px;
        padding: 3px 8px;
        color: %(text)s;
    }
    QComboBox:hover { border-color: %(hb)s; }
    QComboBox:disabled { color: %(dis)s; background: %(disbg)s; }
    QComboBox::drop-down { border: none; width: 18px; }
    QComboBox QAbstractItemView {
        background: %(view)s;
        color: %(text)s;
        border: 1px solid %(border)s;
        selection-background-color: %(sel)s;
        outline: none;
    }
    ''' % dict(bg=bg, border=border, text=text, hb=hover_border, view=view_bg,
               sel=sel_bg, dis=_c(dark, C_GRAY, C_GRAY_D),
               disbg=_c(dark, '#e8edf3', '#20262f'))


def progress_qss(dark, height=8):
    """进度条：圆角轨道 + 主色填充。"""
    track = _c(dark, C_GRAY_BG, C_GRAY_BG_D)
    chunk = _c(dark, C_PRIMARY, C_PRIMARY_D)
    text = _c(dark, C_TEXT_SUB, C_TEXT_SUB_D)
    return '''
    QProgressBar {
        background: %(track)s;
        border: none;
        border-radius: %(h)dpx;
        min-height: %(h)dpx;
        max-height: %(h)dpx;
        text-align: center;
        font-size: 11px;
        color: %(text)s;
    }
    QProgressBar::chunk { background: %(chunk)s; border-radius: %(h)dpx; }
    ''' % dict(track=track, chunk=chunk, text=text, h=height)


def table_button_qss(dark):
    """表格行内小按钮（删除等）：无底色，hover 变红，pressed 加深。"""
    text = _c(dark, C_TEXT_SUB, C_TEXT_SUB_D)
    hover_bg = _c(dark, C_RED_BG, C_RED_BG_D)
    hover_fg = _c(dark, C_RED, C_RED_D)
    press_bg = _c(dark, '#fbd5d5', '#4a1d21')
    press_fg = _c(dark, '#b91c1c', '#ff8f93')
    return '''
    QPushButton {
        background: transparent;
        border: none;
        color: %(text)s;
        padding: 4px 8px;
        border-radius: 6px;
    }
    QPushButton:hover { background: %(hb)s; color: %(hf)s; }
    QPushButton:pressed { background: %(pb)s; color: %(pf)s; }
    QPushButton:disabled { color: %(dis)s; }
    ''' % dict(text=text, hb=hover_bg, hf=hover_fg, pb=press_bg, pf=press_fg,
               dis=_c(dark, '#b8c2ce', '#4a5561'))


def outline_button_qss(dark):
    """工具条按钮（白底描边 + hover 淡蓝 + **pressed 下沉**）。"""
    bg = _c(dark, C_CARD, '#1d2530')
    border = _c(dark, '#cfd7e3', '#2a3442')
    text = _c(dark, C_TEXT, C_TEXT_D)
    hover_bg = _c(dark, '#eef4ff', '#1b2a47')
    hover_border = _c(dark, '#8fb5ff', '#4c8dff')
    press_bg = _c(dark, '#dbeafe', '#24365c')
    press_border = _c(dark, '#6a9bf0', '#3b6fd4')
    return '''
    QPushButton {
        background: %(bg)s;
        border: 1px solid %(border)s;
        border-radius: 7px;
        padding: 6px 13px;
        color: %(text)s;
    }
    QPushButton:hover { background: %(hb)s; border-color: %(hb2)s; }
    QPushButton:pressed { background: %(pb)s; border-color: %(pb2)s; }
    QPushButton:disabled { color: %(dis)s; border-color: %(disbg)s; background: %(disbg)s; }
    ''' % dict(bg=bg, border=border, text=text, hb=hover_bg, hb2=hover_border,
               pb=press_bg, pb2=press_border,
               dis=_c(dark, '#9aa6b5', '#5b6b7b'),
               disbg=_c(dark, '#eef2f9', '#141a22'))


def drop_area_qss(dark):
    """空态拖拽区：虚线边框 + 引导文案。"""
    bg = _c(dark, '#fbfdff', '#12181f')
    dash = _c(dark, '#9bb7dc', '#31415a')
    title = _c(dark, '#1e40af', '#7aa7ff')
    hint = _c(dark, '#64748b', '#8d99a8')
    return '''
    QFrame#dropArea {
        background: %(bg)s;
        border: 2px dashed %(dash)s;
        border-radius: %(r)dpx;
    }
    QLabel#dropTitle { color: %(title)s; font-size: 17px; font-weight: 700; }
    QLabel#dropHint { color: %(hint)s; font-size: 12px; }
    ''' % dict(bg=bg, dash=dash, title=title, hint=hint, r=R_CARD)


def log_qss(dark):
    """日志区：卡片底 + 细边 + 等宽字体。"""
    bg = _c(dark, C_CARD, C_CARD_D)
    border = _c(dark, '#dfe5ee', '#232c39')
    text = _c(dark, C_TEXT, C_TEXT_D)
    return '''
    QTextEdit {
        background: %(bg)s;
        color: %(text)s;
        border: 1px solid %(border)s;
        border-radius: %(r)dpx;
        padding: 6px;
        font-family: "%(font)s", "Consolas";
        font-size: 12px;
    }
    ''' % dict(bg=bg, border=border, text=text, font=FONT_FAMILY, r=R_CARD)


def primary_active_qss(dark):
    """按钮「激活/选中」态：主色底白字（锁定、开关类按钮用）。"""
    bg = _c(dark, C_PRIMARY, C_PRIMARY_D)
    press = _c(dark, '#1d4ed8', '#3b6fd4')
    return '''
    QPushButton {
        background: %(bg)s;
        color: #ffffff;
        border: 1px solid %(bg)s;
        border-radius: 7px;
        padding: 6px 13px;
        font-weight: 600;
    }
    QPushButton:hover { border-color: #ffffff; }
    QPushButton:pressed { background: %(p)s; }
    ''' % dict(bg=bg, p=press)


def scrollbar_qss(dark):
    """细圆角滚动条（质感件）。"""
    handle = _c(dark, '#c4cdd9', '#37414f')
    hover = _c(dark, '#9aa6b5', '#4a5561')
    return '''
    QScrollBar:vertical {
        background: transparent; width: 10px; margin: 2px;
    }
    QScrollBar::handle:vertical {
        background: %(handle)s; border-radius: 4px; min-height: 30px;
    }
    QScrollBar::handle:vertical:hover { background: %(hover)s; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
    QScrollBar:horizontal {
        background: transparent; height: 10px; margin: 2px;
    }
    QScrollBar::handle:horizontal {
        background: %(handle)s; border-radius: 4px; min-width: 30px;
    }
    QScrollBar::handle:horizontal:hover { background: %(hover)s; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
    ''' % dict(handle=handle, hover=hover)
