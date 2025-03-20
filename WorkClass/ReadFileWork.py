import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal, QWaitCondition, QMutex

from Media import Media
from logging_config import log_print


# 文件传输类，不设置超时
class ReadFileWork(QThread):
    Read_processe_signal = pyqtSignal(int)
    Read_complete_signal = pyqtSignal()
    read_bytes_signal = pyqtSignal(int)

    def __init__(self, media: Media, flash: bytes, mem: bytes, size: int, file: str, parent=None):
        super(ReadFileWork, self).__init__(parent)  # 调用超类的构造函
        log_print("ReadFile_Work init  thread id is ", threading.currentThread().ident)

        self.is_pause = False
        self.is_stop = False
        self.cond = QWaitCondition()
        self.mutex = QMutex()

        self.ser = media                # 通信接口
        self.flash = flash              # 器件
        self.mem = mem                  # 起始地址
        self.bytes_to_read = size       # 大小
        self.file_name = file           # 保存的文件名字
        self.FileLengthOnce = 1024      # 每帧的大小

    def pause(self):
        self.is_pause = True

    def resume(self):
        self.is_pause = False
        self.cond.wakeAll()

    def stop(self):
        self.is_stop = True
        if self.is_pause is True:
            self.is_pause = False
            self.cond.wakeAll()

    def run(self):
        try:
            log_print("Read work thread id is ", threading.currentThread().ident)

            if ord(self.flash) > 0x0b:
                self.FileLengthOnce = 256

            log_print("self.FileLengthOnce  is ", self.FileLengthOnce)

            self.ser.send(self.flash)
            self.ser.send(self.mem)

            bytes_read = 0  # 已读取的字节数
            times = 0

            log_print("Read_start_slot into: ", self.file_name)
            with open(self.file_name, 'wb') as file:  # 使用'wb'模式以二进制形式写入文件
                log_print("open file ok")
                t1 = time.time()
                while bytes_read < self.bytes_to_read:
                    self.mutex.lock()
                    if self.is_pause is True:
                        self.cond.wait(self.mutex)

                    if self.is_stop is True:
                        self.ser.send(b'END')
                        self.mutex.unlock()
                        log_print(f"停止读取: read bytes {bytes_read}")
                        break

                    # 读取串口数据
                    data = self.validate_response_ack(self.FileLengthOnce)
                    if data:
                        file.write(data)
                        bytes_read += len(data)
                        self.ser.send(b'ACK')

                        self.Read_processe_signal.emit(bytes_read * 100 / self.bytes_to_read)
                        self.read_bytes_signal.emit(bytes_read)

                        if (times % 1024) == 0:
                            t2 = time.time()
                            log_print("times", times,"t2-t1", t2-t1)
                            log_print("bytes_read:", bytes_read)
                        times = times + 1

                    # bytes_read += 0x10000
                    # self.read_bytes_signal.emit(bytes_read)
                    # self.Read_processe_signal.emit(bytes_read * 100 / self.bytes_to_read)
                    # self.sleep(1)
                    self.mutex.unlock()
                log_print("读取完毕。")
                self.Read_complete_signal.emit()
        except Exception:
            raise

    def validate_response_ack(self, length) -> bytes:
        response = b''
        try:
            response = self.ser.recv(length)
        except Exception:
            raise 
        finally:
            return response
        