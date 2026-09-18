# -*- coding: utf-8 -*-
"""bmu_testkit — MCU 下位机上位机测试基础设施。

设计约束（务必遵守）：
  1. 本包**零 Qt 依赖**。GUI（V2）与 CLI 都构建在它之上，core 不许 import PyQt5。
  2. 两层结构：
       L1 transport —— 只管搬运任意 bytes，不认识任何协议
       L2 protocol  —— 422/CAN 组帧与应答解析，是「现在这套指令格式」的唯一实现
     换协议 = 换 L2，L1 不动。
  3. 超时默认 None（阻塞等待），但**每一次等待都记耗时**，用于问题定位与历史计时。
"""

__version__ = "0.1.0"
