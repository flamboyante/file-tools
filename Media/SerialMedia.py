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
        """写字节。异常正常抛出（2026-09-20 修复：原 finally:return
        把异常吞掉并返回 0，调用方误以为发送成功——bug 清单#1）。
        """
        return self.serial.write(data)

    def recv(self, length) -> bytes:
        """凑满 length 字节或抛异常。异常正常抛出（同 bug#1 修复）。

        timeout=None（遗留默认）时行为与旧版一致：凑满才返回，否则阻塞。
        timeout 有值时，读到空（超时到期且无数据）即返回已有部分，
        由调用方处理短读——绝不静默吞异常。
        """
        data = b''
        while len(data) < length:
            tmp = self.serial.read(length - len(data))
            if not tmp:
                break
            data += tmp
        return data
