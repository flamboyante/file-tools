from queue import Queue

from PyQt5.QtCore import QThread
from scapy.arch import get_if_hwaddr
from scapy.layers.inet import IP, UDP
from scapy.layers.inet6 import IPv6
from scapy.layers.l2 import Dot1Q, Ether
from scapy.packet import Raw
from scapy.sendrecv import send, sniff, sendp

from Media.Media import Media, MediaType


class VlanMediaThread(QThread):

    def __init__(self, iface: str, src_ip: str, dsp_port: int):
        super().__init__()
        self.__iface = iface
        self.__src_ip = src_ip
        self.__dst_port = dsp_port
        self.__data = None
        self.__queue = Queue(1000)
        self.__stop_flag = False

    def get_data(self):
        return self.__queue.get()

    def packet_handler(self, pkt):
        # print(f'get pkt')
        # for p in pkt:
        #     p.show()
        self.__queue.put(pkt[Raw].load)

    def stop_condition(self):
        return self.__stop_flag

    def run(self):
        # while True:
        sniff(iface=self.__iface, count=0, filter=f"ip6 and udp and dst port {self.__dst_port}",
              prn=self.packet_handler)
        # sniff(iface=self.__iface, count=0, filter=f"ip6 and udp and dst port {self.__dst_port}")
        #
        # sniff()

    def stop(self):
        self.__stop_flag = True


# 以太接口子类，继承Media基类
class VlanMedia(Media):

    def __init__(self, ip: str, port: int, vlan_id: int, des_mac: str, iface: str):
        super().__init__(MediaType.VLAN)
        self.__iface = iface
        self.__src_mac = '00:00:00:00:00:00'
        self.__des_mac = des_mac
        self.__vlan_id = vlan_id
        self.__dst_ip = ip
        self.__src_port = 0x9999
        self.__dst_port = port
        self.__udp: UDP = None
        self.__addr: IP = None
        self.__vlan: Dot1Q = None
        self.__is_open = False  # type: bool
        self.__data: bytes = None
        self.__thread = VlanMediaThread(self.__iface, '', self.__src_port)

    @property
    def is_open(self) -> bool:
        return self.__is_open

    def open(self):
        try:
            if self.__is_open is False:
                self.__src_mac = get_if_hwaddr(self.__iface)
                self.__udp = UDP(sport=self.__src_port, dport=self.__dst_port)
                self.__vlan = Dot1Q(vlan=self.__vlan_id)
                # self.__addr = IPv6(src='0206:0004:0041:0000:0000:0000:0000:0100', dst=self.__dst_ip)
                self.__addr = IPv6(dst=self.__dst_ip)
                print(f'IP:  {self.__dst_ip}, MAC: {self.__src_mac}')
                self.__thread.start()
                self.__is_open = True
        except Exception:
            self.__is_open = False
            raise

    def close(self):
        try:
            if self.__is_open is True:
                self.__thread.stop()
                self.__is_open = False
        except Exception:
            raise

    def send(self, data) -> int:
        try:
            packet = Ether(src=self.__src_mac, dst=self.__des_mac) / self.__vlan / self.__addr / self.__udp / Raw(
                load=data)
            # packet = Ether(src=self.__src_mac) / self.__vlan / self.__addr / self.__udp / Raw(
            #     load=data)
            sendp(packet, iface=self.__iface)
            # send(packet)
            return len(data)
        except Exception:
            raise

    def recv(self, length) -> bytes:
        try:
            return self.__thread.get_data()
        except Exception:
            raise
