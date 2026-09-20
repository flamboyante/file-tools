# -*- coding: utf-8 -*-
"""guiwidgets · 新 GUI 的公共零件（控件层）。

theme  : 色板 token + 主题切换（浅/深双主题，v3 mockup 色系）
common : 状态徽章 / 进度卡 / 日志面板等跨页面复用件（后续）

与 guicore 的边界：本包是「渲染层零件」，允许 import PyQt5 / qfluentwidgets；
guicore 不允许。判据同 core.py：guicore 里出现 QWidget / QPainter 就是边界划错。
"""
