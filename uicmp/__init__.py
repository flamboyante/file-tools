# -*- coding: utf-8 -*-
"""三方案 UI 对比包（C / A / B）。

    core.py           共享层：数据 + 设备 + 收发（三份共用，不含渲染）
    impl_c_qss.py     C 方案：原生 PyQt5 + 手写 QSS + QPainter 全自绘（现状风格）
    impl_a_fluent.py  A 方案：qfluentwidgets 组合控件
    impl_b_web.py     B 方案：QWebEngine + HTML/JS
    launcher.py       统一入口

统一测试用例见 case.json，三份实现共读。
"""
