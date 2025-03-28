# 新增发送线程类
from PyQt5.QtCore import QThread,pyqtSignal
from logging_config import  log_print
import threading

class HSendThread(QThread):
    def __init__(self, parent=None, send_flag=False, times=1, interval=1000, dev=None, ycyk_type='快遥'):
        super().__init__(parent)
        super().__init__()
        log_print("HSendThread thread id is ", threading.currentThread().ident)


        self.send_flag = send_flag
        self.times = times if send_flag else 1
        self.interval = interval if send_flag else 0
        self.dev = dev
        self.ycyk_type = ycyk_type

    def run(self):
        try:
            count = self.times
            while count > 0:
                if self.ycyk_type == '快遥':
                    self.dev.send_msg_for_fast_test()
                else:
                    self.dev.send_msg_for_slow_test()

                if self.interval > 0:
                    self.msleep(self.interval)  # 使用QThread的休眠方法

                count -= 1
        except Exception as e:
            log_print(f"SendThread error: {str(e)}")