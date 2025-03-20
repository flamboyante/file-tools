import ctypes
import tkinter
from ctypes import *
from enum import Enum

from USBCAN.CAN import CAN_MSG
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
    BAUD_1M = 1  # 串口接口
    BAUD_800K = 2  # 以太接口
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
    def __init__(self, dev_type: c_uint, index: c_uint, channel: c_uint, dll_path: str):
        self.type = dev_type                    # 设备类型
        self.index = index                      # 设备索引
        self.channel = channel                  # 设备通道
        self.dll_path = dll_path                # DLL路径
        self.dll = None                         # DLL
        self.is_open = False
        self.err_code = 0
        self.dll = cdll.LoadLibrary(self.dll_path)  # 加载DLL
        if self.dll is None:
            self.is_open = False
            log_print(f"DLL Couldn't be loaded, path: {self.dll_path}")

    def open(self):
        try:
            if not self.is_open:
                if self.dll is None:
                    self.is_open = False
                else:
                    ret = self.dll.OpenDevice(self.type, self.index, 0)     # 打开设备
                    if ret != STATUS_OK:
                        self.is_open = False
                    else:
                        self.is_open = True
        except Exception:
            print("Exception on OpenDevice!")
            raise

    def close(self):
        try:
            if self.is_open:
                ret = self.dll.CloseDevice(self.type, self.index, 0)
                if ret != STATUS_OK:
                    self.is_open = True
                else:
                    self.is_open = False
        except Exception:
            print("Exception on CloseDevice!")
            raise

    def config(self, baud: BaudRate) -> bool:
        try:
            if not self.is_open:
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
            config.mode = 2
            ret = self.dll.InitCAN(self.type, self.index, self.channel, byref(config))
            if ret != STATUS_OK:
                return False
            return True
        except Exception:
            print("Exception on InitCan!")
            raise

    def start(self) -> bool:
        try:
            if not self.is_open:
                return False

            ret = self.dll.StartCAN(self.type, self.index, self.channel)
            if ret != STATUS_OK:
                return False
            return True
        except Exception:
            print("Exception on StartCan!")
            raise

    def info(self):
        try:
            board_info = BoardInfo()
            ret = self.dll.ReadBoardInfo(self.type, self.index, byref(board_info))
            return board_info, ret
        except Exception:
            print("Exception on ReadBoardInfo!")
            raise

    def receive(self) -> CAN_MSG:
        try:
            obj = CAN_OBJ()
            ret = self.dll.Receive(self.type, self.index, self.channel, byref(obj), c_uint16(1), 0)
            if ret != STATUS_OK:
                return None
            msg = CAN_MSG()
            msg.id = obj.ID
            msg.remote_flag = obj.RemoteFlag
            msg.extend_flag = obj.ExternFlag
            msg.dlc = obj.DataLen
            msg.data = obj.data
            return msg
        except Exception:
            print("Exception on Receive!")
            raise

    def transmit(self, msg: CAN_MSG) -> bool:
        try:
            obj = CAN_OBJ()
            obj.SendType = c_byte(2)
            obj.ID = c_uint(msg.id)
            obj.RemoteFlag = c_byte(msg.remote_flag)
            obj.ExternFlag = c_byte(msg.extend_flag)
            obj.DataLen = c_byte(msg.dlc)
            for i in range(0, msg.dlc):
                obj.data[i] = c_ubyte(msg.data[i])
            for i in range(msg.dlc, 8):
                obj.data[i] = c_ubyte(0)
            print(obj.data[0], obj.data[1], obj.data[2], obj.data[3])
            print(self.type, self.index, self.channel)
            ret = self.dll.Transmit(self.type, self.index, self.channel, byref(obj), c_uint16(1))
            print(f'ret: {ret}')
            if ret != 1:
                return False
            return True
        except Exception:
            print("Exception on Transmit!")
            raise

    def get_err_info(self) -> str:
        try:
            err_info = ERR_INFO()
            ret = self.dll.ReadErrInfo(self.type, self.index, self.channel, byref(err_info))
            if ret != STATUS_OK:
                return ''
            # print(str(hex(err_info.Err_Code)))
            return str(f'{hex(err_info.Err_Code)}')
        except Exception:
            raise
