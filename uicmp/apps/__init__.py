# -*- coding: utf-8 -*-
"""apps · 新 GUI 的功能页面（渲染层）。

每个页面 = 一个独立 QDialog，持有自己的 guicore 会话对象。
页面之间不互相引用——组合发生在 dev_launcher / 将来的主窗口。
"""
