from abc import abstractmethod, ABC
from enum import Enum


# 通信接口定义
class MediaType(Enum):
    SERIAL = 1  # 串口接口
    ETHERNET = 2  # 以太接口


# 通信接口基类
class Media(ABC):

    def __init__(self, type: MediaType):
        self.__type = type
        self._is_open: bool = False

    @property
    def type(self) -> MediaType:
        return self.__type

    @property
    @abstractmethod
    def is_open(self) -> bool:
        pass

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def send(self, data) -> int:
        pass

    @abstractmethod
    def recv(self, length) -> bytes:
        pass