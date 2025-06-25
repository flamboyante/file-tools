from scapy.layers.inet import IP, UDP
from scapy.layers.inet6 import IPv6
from scapy.layers.l2 import Dot1Q
from scapy.packet import Raw
from scapy.sendrecv import send, sniff

from Media.Media import Media, MediaType


# 以太接口子类，继承Media基类
class VlanMedia(Media):

    def __init__(self, ip: str, port: int, vlan_id: int):
        super().__init__(MediaType.VLAN)
        self.__vlan_id = vlan_id
        self.__ip = ip
        self.__sport = 0x9999
        self.__dport = port
        self.__udp: UDP = None
        self.__addr: IP = None
        self.__vlan: Dot1Q = None
        self.__is_open = False  # type: bool
        self.__data: bytes = None

    @property
    def is_open(self) -> bool:
        return self.__is_open

    def open(self):
        try:
            if self.__is_open is False:
                print(f'IP:  {self.__ip}')
                self.__udp = UDP(sport=self.__sport, dport=self.__dport)
                self.__vlan = Dot1Q(vlan=self.__vlan_id)
                self.__addr = IPv6(dst=self.__ip)
                self.__is_open = True
        except Exception:
            self.__is_open = False
            raise

    def close(self):
        try:
            if self.__is_open is True:
                self.__is_open = False
        except Exception:
            raise

    def send(self, data) -> int:
        try:
            packet = self.__vlan/self.__addr/self.__udp/Raw(load=data)
            send(packet)
            n = data.len
        except Exception:
            n = 0
            raise
        finally:
            return n

    def recv(self, length) -> bytes:
        try:
            sniff(filter=f"vlan {self.__vlan_id} and udp and port {self.__sport}", prn=self.packet_handler, count=1)
        except Exception:
            self.__data = None
            raise
        finally:
            return self.__data

    def packet_handler(self, pkt):
        if Dot1Q in pkt and pkt[Dot1Q].vlan == self.__vlan and UDP in pkt and pkt[UDP].dport == 0x9999:
            self.__data = pkt[Raw].load
