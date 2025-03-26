from PyQt5.QtCore import QThread, pyqtSignal

from logging_config import  log_print
import threading


# JCANThread 控制台线程
class JCANThread(QThread):
    signal_Can_Recv_Msg = pyqtSignal(str)
    def __init__(self, *args):
        super().__init__()
        log_print("ReadWindow thread id is ", threading.currentThread().ident)

        self.CanDev=  args[0]
        self.running = True
        self.recv_num = 0

    def start(self,priority =  ...):
        log_print("JCANThread start")
        super().start()
    def stop(self):
        log_print("JCANThread stop")
        super().terminate()

    def run(self):

        while (1):
            try:
                mstr = None
                len, rec, ret = self.CanDev.Receivce(self.CanDev.type,
                                                     self.CanDev.index,
                                                     self.CanDev.channel, 1)  #收1个can帧
                if (len > 0 and ret == 1):
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
                        for i in range(0, rec[0].DataLen):
                            mstr = mstr + hex(rec[0].data[i]).zfill(2) + " "
                    else:
                        mstr = mstr + " Type:Romte " + " Data: Remote Request"
                    log_print("nbbbbbbbbbbb is",mstr)
                    self.signal_Can_Recv_Msg.emit(mstr)
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
