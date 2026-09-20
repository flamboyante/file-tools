# -*- coding: utf-8 -*-
"""最原始的真机通路测试 —— 不走任何封装，直接调 ECAN。

目的：把「设备打不开」和「总线不通」这两件事分开。
  1. transmit 的返回码说明驱动层认不认这次发送
  2. receive 能不能拿到帧说明硬件层通不通
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from JiangCan_Tools.ECAN import (ECAN, BaudRate, CAN_OBJ,          # noqa: E402
                                 Channel1, Channel2)

DLL = os.path.join(ROOT, 'JiangCan_Tools', 'ECanVci64.dll')
print('DLL:', DLL, os.path.exists(DLL))
print()

print('--- open ---')
ECAN.open(0, 0, DLL)
print('ECAN.is_open =', ECAN.is_open)

print()
print('--- 通道 A (Channel1) ---')
a = ECAN(Channel1)
print('  config:', a.config(BaudRate.BAUD_500K))
print('  start :', a.start())

print()
print('--- 通道 B (Channel2) ---')
b = ECAN(Channel2)
print('  config:', b.config(BaudRate.BAUD_500K))
print('  start :', b.start())

print()
print('--- A 发一帧 0x31801 [00 5A 5A] ---')
obj = CAN_OBJ()
obj.ID = 0x31801
obj.DataLen = 3
obj.data[0] = 0x00
obj.data[1] = 0x5A
obj.data[2] = 0x5A
obj.RemoteFlag = 0
obj.ExternFlag = 1
obj.SendType = 0
t0 = time.time()
ret = a.transmit(obj)
print('  transmit 返回 =', ret, ' (耗时 %.3fs)' % (time.time() - t0))
print('  返回码含义: 1=OK, 0=失败（无 ACK / 总线错误）')
print('  注意：CAN 发送需要总线上有其它节点 ACK；两通道没接到同一总线时，')
print('        这个发送会在重试后失败或超时。')

print()
print('--- 等 B 收（2 秒）---')
found = 0
t0 = time.time()
while time.time() - t0 < 2.0:
    length, arr, ret2 = b.receive(1)
    if length > 0 and ret2 == 1 and arr:
        f = arr[0]
        data = [f.data[i] for i in range(f.DataLen)]
        print('  ✓ 收到: ID=0x%X  DataLen=%d  data=%s  RemoteFlag=%d  ExternFlag=%d'
              % (f.ID, f.DataLen, ' '.join('%02X' % x for x in data),
                 f.RemoteFlag, f.ExternFlag))
        found += 1
    time.sleep(0.01)
if not found:
    print('  ✗ 2 秒内一帧都没收到')
print('  共收到 %d 帧' % found)

print()
print('--- 反向：B 发 A 收 ---')
obj2 = CAN_OBJ()
obj2.ID = 0x8031801
obj2.DataLen = 3
obj2.data[0] = 0x00
obj2.data[1] = 0x25
obj2.data[2] = 0x25
obj2.RemoteFlag = 0
obj2.ExternFlag = 1
obj2.SendType = 0
print('  transmit 返回 =', b.transmit(obj2))
found2 = 0
t0 = time.time()
while time.time() - t0 < 1.5:
    length, arr, ret3 = a.receive(1)
    if length > 0 and ret3 == 1 and arr:
        f = arr[0]
        print('  ✓ 收到: ID=0x%X  data=%s' % (f.ID, ' '.join('%02X' % x for x in f.data[:f.DataLen])))
        found2 += 1
    time.sleep(0.01)
if not found2:
    print('  ✗ 1.5 秒内一帧都没收到')

print()
print('--- cleanup ---')
try:
    ECAN.close()
    print('  ECAN.close() OK')
except Exception as e:
    print('  close 失败:', e)

print()
print('判读：')
print('  transmit=1 且 receive 有帧  -> 真机通路成立')
print('  transmit=1 但 receive 无帧  -> 两通道不在同一总线（线没接/无终端电阻）')
print('  transmit=0                  -> 总线无 ACK，同样是接线问题')
