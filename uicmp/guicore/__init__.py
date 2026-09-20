# -*- coding: utf-8 -*-
"""guicore · 新 GUI 会话层（无渲染）。

serial_link : 串口链路门面（读线程 + 发送队列），422/transfer/console
              三个 session 的共同地基；console 另起独立链路。

边界判据（同 uicmp/core.py）：本包出现 QWidget / QPainter / QVBoxLayout /
任何渲染词，就是边界划错了。允许的 Qt 依赖仅限 QtCore（QThread/信号）。

未来消费者：apps/ 下四个页面 + bmu_testkit 回归测试（headless import 即用）。
"""
