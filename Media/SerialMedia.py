import serial

from Media.Media import Media, MediaType


class SerialMedia(Media):

    def __init__(self, port: str, baud, data_bits, stop_bits, parity,
                 timeout=None):
        """timeout: pyserial read 超时（秒）。None = 永久阻塞（旧行为）。

        新代码（线程读循环）必须传 timeout，否则 close 时 read 无法退出。
        """
        super(SerialMedia, self).__init__(MediaType.SERIAL)
        try:
            self.serial = serial.Serial(port=port, baudrate=baud, parity=parity,
                                        stopbits=stop_bits, bytesize=data_bits,
                                        timeout=timeout)
            # pyserial 构造即打开；is_open 如实反映（旧版 finally 硬置 False
            # 是 bug：构造成功也误报未打开）
            self.__is_open = self.serial.is_open
        except Exception:
            self.__is_open = False
            raise

    @property
    def is_open(self) -> bool:
        return self.__is_open

    def open(self):
        try:
            if not self.serial.is_open:
                self.serial.open()
            self.__is_open = True
        except Exception:
            self.__is_open = False
            raise

    def close(self):
        try:
            if self.serial.is_open:
                self.serial.close()
            self.__is_open = False
        except Exception:
            raise

    def send(self, data) -> int:
        try:
            n = self.serial.write(data)
        except Exception:
            n = 0
            raise
        finally:
            return n

    def recv(self, length) -> bytes:
        try:
            data = b''
            while True:
                tmp = self.serial.read(length - len(data))
                data += tmp
                if len(data) >= length:
                    break
        except Exception:
            data = None
        finally:
            return data
