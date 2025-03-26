from PyQt5.QtCore import QThread, pyqtSignal

import  serial
# BMU控制台线程
class BmuConsoleThread(QThread):
    signal_console_input = pyqtSignal(str)
    signal_console_break = pyqtSignal(str)

    def __init__(self, *args):
        super().__init__()
        try:
            self.serial = serial.Serial(port=args[0], baudrate=args[1], bytesize=args[2], parity=args[4], stopbits=args[3])
            if self.serial.is_open:
                self.serial.close()
            self.idle_time = 5  # 两帧数据间隔
            self.exit = True
            print(type(self.serial), self.serial)
        except Exception:
            self.exit = False
            raise

    def start(self, priority=...):
        super().start()
        try:
            self.serial.open()
        except Exception:
            raise

    def stop(self):
        super().terminate()
        try:
            if self.exit:
                self.serial.close()
        except Exception:
            raise

    def run(self):
        while self.isRunning():
            if self.exit and self.serial and self.serial.is_open:
                data = self.serial_read()
                if len(data):
                    txt = data.decode('utf-8', 'replace')
                    # txt = data.decode('utf-8')
                    print(f'BmuConsoleThread: {txt}')
                    self.signal_console_input.emit(txt)

    # 从串口中读取数据
    def serial_read(self) -> bytes:
        data = bytearray()
        try:
            while True:
                if self.serial.in_waiting:
                    data += self.serial.read_all()
                else:
                    break
                QThread.msleep(self.idle_time)
        except Exception as e:
            self.exit = False
            self.signal_console_break.emit(str(e))
            print(f'serial_read: {str(e)}')
        finally:
            return data

    def send(self, cmd: str):
        self.serial.write(f'{cmd}\r'.encode('utf-8'))
