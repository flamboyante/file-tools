import datetime
import time
from queue import Queue

from PyQt5.QtCore import QThread

from JiangCan_Tools.ECAN import CAN_OBJ, USBCAN2, DevIndex, Channel1
from ycyk_422 import ycyk_can_frame
import pprint


class CANSendThread(QThread):

    def __init__(self, *args):
        super().__init__()
        try:
            self.can_dev = args[0]
            self.q = Queue(maxsize=100)
            self.can_tx_start = 0
            self.can_tx_middle = 0
            self.can_tx_stop = 0
            self.can_tx_single = 0
            print("CAN SEND")
        except Exception:
            raise

    def start(self, priority=...):
        super().start()

    def stop(self):
        super().terminate()

    def run(self):
        while True:
            try:
                can_obj = self.q.get()
                self.can_send(can_obj)
                # print("CAN TX: " + str(self.can_dev.tx_cnt))
                # self.can_dev.Tramsmit(USBCAN2, DevIndex, Channel1, can_obj)
            except Exception:
                raise

    def send(self, can_obj):
        self.q.put(can_obj)

    def can_send(self, frame: ycyk_can_frame):

        if frame.data is not None:
            print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f") + " " + frame.name)
            length = len(frame.data)
            frames = int(length / 8)
            end = int(length % 8)
            if end != 0:
                frames = frames + 1
            else:
                end = 8
            # print("length: " + str(length) + " frame: " + str(frames) + " end: " + str(end))
            if frames == 1:
                self.can_tx_single = self.can_tx_single + 1
                can_obj = CAN_OBJ()
                can_obj.ID = int(((frame.prio & 0x3) << 27) | ((frame.src & 0x3F) << 21) | ((frame.grp & 0x3) << 19)
                                 | ((frame.dst & 0x3F) << 13) | (0X3 << 11) | (0X0 << 5) | (frame.func & 0x1F))
                can_obj.DataLen = int(end)
                for i in range(end):
                    can_obj.data[i] = int(frame.data[i])
                can_obj.RemoteFlag = int(0)
                can_obj.ExternFlag = int(1)
                # print("CAN ID: " + hex(can_obj.ID) + " length: " + str(can_obj.DataLen) + " data: " + hex(can_obj.data[0]) + " " + hex(can_obj.data[1]) + " " + hex(can_obj.data[2]) + " " + hex(can_obj.data[3]) + " " + hex(can_obj.data[4]) + " " + hex(can_obj.data[5]) + " " + hex(can_obj.data[6]) + " " + hex(can_obj.data[7]))
                self.can_dev.transmit(can_obj)
            else:
                # 起始帧
                self.can_tx_start = self.can_tx_start + 1
                can_obj = CAN_OBJ()
                can_obj.ID = int(((frame.prio & 0x3) << 27) | ((frame.src & 0x3F) << 21) | ((frame.grp & 0x3) << 19)
                                 | ((frame.dst & 0x3F) << 13) | (0x1 << 11) | (0x0 << 5) | (frame.func & 0x1F))
                can_obj.DataLen = int(8)
                for i in range(8):
                    can_obj.data[i] = int(frame.data[i])
                can_obj.RemoteFlag = int(0)
                can_obj.ExternFlag = int(1)
                print("CAN ID: " + hex(can_obj.ID) + "length: " + str(can_obj.DataLen) + " data: " + hex(can_obj.data[0]) + " " + hex(can_obj.data[1]) + " " + hex(can_obj.data[2]) + " " + hex(can_obj.data[3]) + " " + hex(can_obj.data[4]) + " " + hex(can_obj.data[5]) + " " + hex(can_obj.data[6]) + " " + hex(can_obj.data[7]))
                self.can_dev.transmit(can_obj)

                # 中间帧
                for j in range(1, frames - 1):
                    self.can_tx_middle = self.can_tx_middle + 1
                    can_obj = CAN_OBJ()
                    can_obj.ID = int(((frame.prio & 0x3) << 27) | ((frame.src & 0x3F) << 21) | ((frame.grp & 0x3) << 19)
                                     | ((frame.dst & 0x3F) << 13) | (0x0 << 11) | ((int(j) & 0x3F) << 5) | (frame.func & 0x1F))
                    can_obj.DataLen = int(8)
                    for i in range(8):
                        can_obj.data[i] = int(frame.data[j*8+i])
                    can_obj.RemoteFlag = int(0)
                    can_obj.ExternFlag = int(1)
                    # print("CAN ID: " + hex(can_obj.ID) + "length: " + str(can_obj.DataLen) + " data: " + hex(can_obj.data[0]) + " " + hex(can_obj.data[1]) + " " + hex(can_obj.data[2]) + " " + hex(can_obj.data[3]) + " " + hex(can_obj.data[4]) + " " + hex(can_obj.data[5]) + " " + hex(can_obj.data[6]) + " " + hex(can_obj.data[7]))
                    self.can_dev.transmit(can_obj)

                self.can_tx_stop = self.can_tx_stop + 1
                k = frames - 1
                # 结束帧
                can_obj = CAN_OBJ()
                can_obj.ID = int(((frame.prio & 0x3) << 27) | ((frame.src & 0x3F) << 21) | ((frame.grp & 0x3) << 19)
                                 | ((frame.dst & 0x3F) << 13) | (0x2 << 11) | ((int(k) & 0x3F) << 5) | (frame.func & 0x1F))
                can_obj.DataLen = int(end)
                for i in range(int(end)):
                    can_obj.data[i] = int(frame.data[k * 8 + i])
                can_obj.RemoteFlag = int(0)
                can_obj.ExternFlag = int(1)
                # print("CAN ID: " + hex(can_obj.ID) + "length: " + str(can_obj.DataLen) + " data: " + hex(can_obj.data[0]) + " " + hex(can_obj.data[1]) + " " + hex(can_obj.data[2]) + " " + hex(can_obj.data[3]) + " " + hex(can_obj.data[4]) + " " + hex(can_obj.data[5]) + " " + hex(can_obj.data[6]) + " " + hex(can_obj.data[7]))
                self.can_dev.transmit(can_obj)

            # time.sleep(0.001)
