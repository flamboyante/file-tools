import serial

from Media.Media import Media, MediaType


class SerialMedia(Media):

    def __init__(self, port: str, baud, data_bits, stop_bits, parity):
        super(SerialMedia, self).__init__(MediaType.SERIAL)
        try:
            self.serial = serial.Serial(port=port, baudrate=baud, parity=parity, stopbits=stop_bits, bytesize=data_bits)
        except Exception:
            raise
        finally:
            self.__is_open = False

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
            data = self.serial.read(length)
        except Exception:
            data = None
        finally:
            return data
