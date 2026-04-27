
from ctypes import *
from enum import Enum


# from ctypes import cdll, c_ushort, c_byte, c_uint, c_ubyte

# from _ctypes import Structure

from logging_config import log_print

DevType = c_uint

'''
    Device Type
'''
USBCAN1 = DevType(3)
USBCAN2 = DevType(4)
USBCANFD = DevType(6)
'''
    Device Index
'''
DevIndex = c_uint(0)  # 设备索引
'''
    Channel
'''
Channel1 = c_uint(0)  # CAN1
Channel2 = c_uint(1)  # CAN2
'''
    ECAN Status
'''
STATUS_ERR = 0
STATUS_OK = 1

'''
    Device Information
'''


class BoardInfo(Structure):
    _fields_ = [("hw_Version",      c_ushort),  # 硬件版本号，用16进制表示
                ("fw_Version",      c_ushort),  # 固件版本号，用16进制表示
                ("dr_Version",      c_ushort),  # 驱动程序版本号，用16进制表示
                ("in_Version",      c_ushort),  # 接口库版本号，用16进制表示
                ("irq_Num",         c_ushort),  # 板卡所使用的中断号
                ("can_Num",         c_byte),  # 表示有几路CAN通道
                ("str_Serial_Num",  c_byte * 20),  # 此板卡的序列号，用ASC码表示
                ("str_hw_Type",     c_byte * 40),  # 硬件类型，用ASC码表示
                ("Reserved",        c_byte * 4)]  # 系统保留


class BaudRate(Enum):
    BAUD_1M = 1
    BAUD_800K = 2
    BAUD_666K = 3
    BAUD_500K = 4
    BAUD_400K = 5
    BAUD_250K = 6
    BAUD_200K = 7
    BAUD_125K = 8
    BAUD_100K = 9
    BAUD_80K = 10
    BAUD_50K = 11


class CAN_OBJ(Structure):
    _fields_ = [("ID", c_uint),  # 报文帧ID
                ("TimeStamp", c_uint),  # 接收到信息帧时的时间标识，从CAN控制器初始化开始计时，单位微秒
                ("TimeFlag", c_byte),  # 是否使用时间标识，为1时TimeStamp有效，TimeFlag和TimeStamp只在此帧为接收帧时有意义。
                ("SendType", c_byte),
                # 发送帧类型。=0时为正常发送，=1时为单次发送（不自动重发），=2时为自发自收（用于测试CAN卡是否损坏），=3时为单次自发自收（只发送一次，用于自测试），只在此帧为发送帧时有意义
                ("RemoteFlag", c_byte),  # 是否是远程帧。=0时为数据帧，=1时为远程帧
                ("ExternFlag", c_byte),  # 是否是扩展帧。=0时为标准帧（11位帧ID），=1时为扩展帧（29位帧ID）
                ("DataLen", c_byte),  # 数据长度DLC(<=8)，即Data的长度
                ("data", c_ubyte * 8),  # CAN报文的数据。空间受DataLen的约束
                ("Reserved", c_byte * 3)]  # 系统保留。


class INIT_CONFIG(Structure):
    _fields_ = [("acccode", c_uint32),  # 验收码。SJA1000的帧过滤验收码
                ("accmask", c_uint32),  # 屏蔽码。SJA1000的帧过滤屏蔽码。屏蔽码推荐设置为0xFFFF FFFF，即全部接收
                ("reserved", c_uint32),  # 保留
                ("filter", c_byte),  # 滤波使能。0=不使能，1=使能。使能时，请参照SJA1000验收滤波器设置验收码和屏蔽码
                ("timing0", c_byte),  # 波特率定时器0,详见动态库使用说明书7页
                ("timing1", c_byte),  # 波特率定时器1,详见动态库使用说明书7页
                ("mode", c_byte)]  # 模式。=0为正常模式，=1为只听模式，=2为自发自收模式。


class ERR_INFO(Structure):
    _fields_ = [
        ("ErrCode", c_uint),    # 错误码
        ("Passive_ErrData", c_byte * 3),
        ("ArLost_ErrData", c_byte)
    ]


class ECAN(object):
    is_open = False         # 设备是否打开
    type = 0                # 设备类型
    index = 0               # 设备索引
    dll_path = None         # DLL路径
    dll = None              # DLL

    def __init__(self, channel: c_uint):
        self.channel = channel                  # 设备通道
        self.err_code = 0
        self.tx_cnt = 0

    @classmethod
    def open(cls, dev_type: c_uint, dev_index: c_uint, dll_path: str):
        try:
            log_print("self.dll_path is ", dll_path)
            if not cls.is_open:
                cls.dll = cdll.LoadLibrary(dll_path)  # 加载DLL
                if cls.dll is None:
                    cls.is_open = False
                else:
                    ret = cls.dll.OpenDevice(dev_type, dev_index, 0)     # 打开设备
                    if ret != STATUS_OK:
                        cls.is_open = False
                    else:
                        cls.type = dev_type
                        cls.index = dev_index
                        cls.is_open = True
        except Exception as e:
            log_print(f"ECAN.open : {str(e)}")
            raise

    @classmethod
    def close(cls):
        try:
            if cls.is_open:
                ret = cls.dll.CloseDevice(cls.type, cls.index, 0)
                if ret != STATUS_OK:
                    cls.is_open = True
                else:
                    cls.is_open = False
        except Exception:
            print("Exception on CloseDevice!")
            raise

    @classmethod
    def info(cls):
        try:
            board_info = BoardInfo()
            ret = ECAN.dll.ReadBoardInfo(cls.type, cls.index, byref(board_info))
            return board_info, ret
        except Exception:
            print("Exception on ReadBoardInfo!")
            raise

    def config(self, baud: BaudRate) -> bool:
        try:
            if not ECAN.is_open:
                return False

            timing_map = {
                BaudRate.BAUD_1M: [0x00, 0x14],
                BaudRate.BAUD_800K: [0x00, 0x16],
                BaudRate.BAUD_666K: [0x80, 0xb6],
                BaudRate.BAUD_500K: [0x00, 0x1c],
                BaudRate.BAUD_400K: [0x80, 0xfa],
                BaudRate.BAUD_250K: [0x01, 0x1c],
                BaudRate.BAUD_200K: [0x81, 0xfa],
                BaudRate.BAUD_125K: [0x03, 0x1c],
                BaudRate.BAUD_100K: [0x04, 0x1c],
                BaudRate.BAUD_80K: [0x83, 0xff],
                BaudRate.BAUD_50K: [0x09, 0x1c]
            }
            config = INIT_CONFIG()
            config.acccode = 0  # 设置验收码
            config.accmask = 0xFFFFFFFF  # 设置屏蔽码
            config.filter = 0  # 设置滤波使能
            config.timing0, config.timing1 = timing_map.get(baud)
            log_print("config.timing0, config.timing1",config.timing0, hex(config.timing1))
            config.mode = 0
            ret = ECAN.dll.InitCAN(ECAN.type, ECAN.index, self.channel, byref(config))
            if ret != STATUS_OK:
                return False
            return True
        except Exception:
            print("Exception on InitCan!")
            raise

    def start(self) -> bool:
        try:
            if not ECAN.is_open:
                return False

            ret = ECAN.dll.StartCAN(ECAN.type, ECAN.index, self.channel)
            if ret != STATUS_OK:
                return False
            return True
        except Exception:
            print("Exception on StartCan!")
            raise

    def get_err_info(self) -> str:
        try:
            err_info = ERR_INFO()
            ret = ECAN.dll.ReadErrInfo(ECAN.type, ECAN.index, self.channel, byref(err_info))
            if ret != STATUS_OK:
                return ''
            # print(str(hex(err_info.Err_Code)))
            return str(f'{hex(err_info.ErrCode)}')
        except Exception:
            raise

    def transmit(self, can_obj):
        try:
            self.tx_cnt = self.tx_cnt + 1
            return ECAN.dll.Transmit(ECAN.type, ECAN.index, self.channel, byref(can_obj), c_uint16(1))
        except Exception:
            print("Exception on Transmit!")
            raise

    def receive(self, length):
        try:
            can_obj = (CAN_OBJ * length)()
            ret = ECAN.dll.Receive(ECAN.type, ECAN.index, self.channel, byref(can_obj), length, 0)
            return length, can_obj, ret
        except Exception:
            print("Exception on Receive!")
            raise
