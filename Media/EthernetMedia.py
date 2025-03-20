import socket
from Media.Media import Media, MediaType


# 以太接口子类，继承Media基类
class EthernetMedia(Media):

    def __init__(self, ip: str, port: int):
        super().__init__(MediaType.ETHERNET)
        self.__sock = None
        self.__addr = (ip, port)
        self.__is_open = False  # type: False

    @property
    def is_open(self) -> bool:
        return self.__is_open

    def open(self):
        try:
            if self.__is_open is False:
                self.__sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
                server_address = ('::', 0x9999)
                self.__sock.bind(server_address)
            self.__is_open = True
        except Exception:
            self.__is_open = False
            raise

    def close(self):
        try:
            if self.__is_open is True:
                self.__sock.close()
            self.__is_open = False
        except Exception:
            raise

    def send(self, data) -> int:
        try:
            n = self.__sock.sendto(data, self.__addr)
        except Exception:
            n = 0
            raise
        finally:
            return n

    def recv(self, length) -> bytes:
        try:
            data, addr = self.__sock.recvfrom(length)
            print(f'real: [addr: {addr}, data: {data}], expect: [{self.__addr}]')
        except Exception:
            data = None
            raise
        finally:
            return data
