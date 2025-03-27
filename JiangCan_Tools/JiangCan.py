from PyQt5.QtCore import QThread, pyqtSignal

from logging_config import  log_print
import threading
import time
from Can_Frame_Deal.Model_Data import HexDataDeal
# JCANThread 控制台线程
class JCANThread(QThread):
    signal_Can_Recv_Msg = pyqtSignal(str)
    signal_Can_All_Data     = pyqtSignal(str)
    def __init__(self, *args):
        super().__init__()
        log_print("JCANThread thread id is ", threading.currentThread().ident)

        self.CanDev=  args[0]
        self.running = True
        self.recv_num = 0


        self.all_data_buffer = ""  # 用于存储所有接收到的数据
        self.last_recv_time = time.time()  # 记录上一次接收到 CAN 帧的时间
        self.idle_time_threshold = 0.05  # 空闲时间阈值，单位：秒

    def start(self,priority =  ...):
        log_print("JCANThread start")
        super().start()
    def stop(self):
        log_print("JCANThread stop")
        super().terminate()

    def run(self):
        try:
            while self.running:
                len, rec, ret = self.CanDev.Receivce(self.CanDev.type,
                                                     self.CanDev.index,
                                                     self.CanDev.channel, 1)  # 收1个can帧
                if len > 0 and ret == 1:
                    self.last_recv_time = time.time()  # 更新上一次接收到 CAN 帧的时间
                    mstr = "Rec: " + str(self.recv_num)
                    self.recv_num = self.recv_num + 1

                    if rec[0].TimeFlag == 0:
                        mstr = mstr + " Time: "
                    else:
                        mstr = mstr + " Time:" + hex(rec[0].TimeStamp).zfill(8)
                    if rec[0].ExternFlag == 0:
                        mstr = mstr + " ID:" + hex(rec[0].ID).zfill(3) + " Format:Stand "
                    else:
                        mstr = mstr + " ID:" + hex(rec[0].ID).zfill(8) + " Format:Exten "
                    if rec[0].RemoteFlag == 0:
                        mstr = mstr + " Type:Data " + " Data: "
                        data_str = ""
                        for i in range(0, rec[0].DataLen):
                            final_hex = '0x' + (hex(rec[0].data[i])[2:]).zfill(2)
                            data_str = data_str + final_hex + " "
                        self.all_data_buffer += data_str  # 将当前帧的数据添加到缓冲区
                        mstr = mstr + data_str
                        self.signal_Can_Recv_Msg.emit(mstr)
                    else:
                        mstr = mstr + " Type:Romte " + " Data: Remote Request"
                    log_print("nbbbbbbbbbbb is", mstr)
                else:
                    # 检查是否达到空闲时间阈值
                    if time.time() - self.last_recv_time > self.idle_time_threshold:
                        if self.all_data_buffer:
                            self.signal_Can_All_Data.emit(self.all_data_buffer)  # 发送所有数据
                            self.all_data_buffer = ""  # 清空缓冲区
                        self.last_recv_time = time.time()  # 更新上一次接收到 CAN 帧的时间
                self.usleep(100)
        except Exception as e:
            log_print(f"JCANThread RECV ERROR: {str(e)}")
            raise






'''
    try:
        
    except Exception as e:
        log_print(f"TableView_MainWindow __init__: {str(e)}")
        raise
'''
