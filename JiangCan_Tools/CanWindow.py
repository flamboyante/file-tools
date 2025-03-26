import os

from PyQt5.QtWidgets import QDialog

from JiangCan_Tools import can_ui
from JiangCan_Tools.JiangCan import JCan_MSG
from JiangCan_Tools.ECAN import ECAN, STATUS_OK, BaudRate
from logging_config import  log_print


class CanWindow(QDialog, can_ui.Ui_CanForm):
    def __init__(self, parent=None):
        super(CanWindow, self).__init__(parent)
        self.setupUi(self)
        self.can_dev: ECAN = None

        self.type_map = {
            "USBCAN-I":  3,
            "USBCAN-II": 4,
            "USBCAN-FD": 6
        }

        self.ycyk_map = {
            '快遥': 0,
            '慢遥': 1
        }

        self.comboBox_Type.addItems(self.type_map.keys())
        self.comboBox_Type.setCurrentIndex(0)
        self.comboBox_Ycyk.addItems(self.ycyk_map.keys())
        self.comboBox_Ycyk.setCurrentIndex(0)

        self.pushButton_Open.clicked.connect(self.open_dev)
        self.pushButton_Send.clicked.connect(self.send_cmd)

    def open_dev(self):
        try:
            pwd = os.getcwd()
            print(pwd)
            dev_key = self.comboBox_Type.currentText()
            dev_val = self.type_map.get(dev_key)
            log_print("dev_key is",dev_key , "dev_val is" ,dev_val)
            localFilePath = os.path.join(os.getcwd(), '.\\JiangCan_Tools\\ECanVci64.dll')
            self.can_dev = ECAN(dev_val, 0, 1, localFilePath)
            self.can_dev.open()
            if self.can_dev.is_open:
                self.textEdit_Info.append("CAN open OK")
                info, ret = self.can_dev.info()
                if ret == STATUS_OK:
                    self.textEdit_Info.append(f"hw_Version: {str(hex(info.hw_Version))}")
                    self.textEdit_Info.append(f"fw_Version: {str(hex(info.fw_Version))}")
                    self.textEdit_Info.append(f"dr_Version: {str(hex(info.dr_Version))}")
                    self.textEdit_Info.append(f"in_Version: {str(hex(info.in_Version))}")
                    self.textEdit_Info.append(f"irq_Num: {str(hex(info.irq_Num))}")
                    self.textEdit_Info.append(f"can_Num: {str(hex(info.can_Num))}")
                    str_info = ''
                    for i in range(0, 10):
                        str_info = str_info + chr(info.str_Serial_Num[i])  # 结构体中str_Serial_Num内部存放存放SN号的ASC码
                    self.textEdit_Info.append("SN:" + str_info)
                    str_info = ''
                    for i in range(0, 40):
                        str_info = str_info + chr(info.str_hw_Type[i])  # 结构体中str_Serial_Num内部存放存放SN号的ASC码
                    self.textEdit_Info.append("str_hw_Type:" + str_info)
                    if self.can_dev.config(BaudRate.BAUD_500K):
                        self.textEdit_Info.append("CAN config OK")
                        if self.can_dev.start():
                            self.textEdit_Info.append("CAN start OK")
                        else:
                            self.textEdit_Info.append("CAN start FAIL")
                    else:
                        self.textEdit_Info.append("CAN config FAIL")
            else:
                self.textEdit_Info.append(f"CAN open FAIL {self.can_dev.get_err_info()}")

        except Exception as e:
            log_print(f"CanWindow Opendev : {str(e)}")


    def send_cmd(self):
        msg = JCan_MSG()
        msg.id = 0x31801
        msg.remote_flag = 0
        msg.extend_flag = 1
        msg.dlc = 3
        msg.data[0] = 0x00
        msg.data[1] = 0x1A
        msg.data[2] = 0x1A
        if self.can_dev.transmit(msg):
            self.textEdit_Recv.append(f'SEND OK')
        else:
            self.textEdit_Recv.append(f'SEND ERROR: {self.can_dev.get_err_info()}')
