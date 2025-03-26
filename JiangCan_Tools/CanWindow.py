import os,time

from PyQt5.QtWidgets import QDialog

from JiangCan_Tools import can_ui

from JiangCan_Tools.ECAN import ECAN, STATUS_OK, BaudRate
from logging_config import  log_print

from JiangCan_Tools.JiangCan import JCANThread
from Can_Frame_Deal.Model_Data import HexDataDeal

from UIClass.TableViewWindow import TableView_MainWindow
class CanWindow(QDialog, can_ui.Ui_CanForm):
    def __init__(self, parent=None):
        super(CanWindow, self).__init__(parent)
        try:
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
            self.pushButton_Send.clicked.connect(self.send_test)
            self.pushButton_TableView.clicked.connect(self.open_table_view)

            self.can_recv_thread = None
            self.can_tableview = None
        except Exception as e:
            log_print(f"CanWindow __init__ : {str(e)}")
            raise

    def open_dev(self):
        try:
            pwd = os.getcwd()
            print(pwd)
            dev_key = self.comboBox_Type.currentText()
            dev_val = self.type_map.get(dev_key)
            log_print("dev_key is",dev_key , "dev_val is" ,dev_val)
            localFilePath = os.path.join(os.getcwd(), '.\\JiangCan_Tools\\ECanVci64.dll')
            self.can_dev = ECAN(dev_val, 0, 0, localFilePath)
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
                            self.Start_CAN_THREAD()
                        else:
                            self.textEdit_Info.append("CAN start FAIL")
                    else:
                        self.textEdit_Info.append("CAN config FAIL")
            else:
                self.textEdit_Info.append(f"CAN open FAIL {self.can_dev.get_err_info()}")

        except Exception as e:
            log_print(f"CanWindow Opendev : {str(e)}")
            raise



    def send_test(self):

        ret = self.get_checkBox_sendFlag()
        if ret is False:
            sendtimes = 1
            sendtimelag = 0
        else:
            sendtimes = self.get_combox_times()
            sendtimelag = self.get_combox_lag()

        while(sendtimes):
            try:
                if self.comboBox_Ycyk.currentText() == '快遥':
                    log_print("comboBox_Ycyk快遥",sendtimes)
                    self.can_dev.send_msg_for_fast_test()
                else:
                    log_print("comboBox_Ycyk慢遥",sendtimes)
                    self.can_dev.send_msg_for_slow_test()
            except Exception as e:
                log_print(f"CanWindow send_test : {str(e)}")
                raise
            #延时sendtimelag ms
            time.sleep(sendtimelag / 1000 )
            sendtimes -= 1





    def get_combox_times(self):
        try:
            times = self.comboBox_sendTimes.currentText()
            log_print("times is",times, type(times))
            #转为int
            return int(times)
        except Exception as e:
            log_print(f"get_combox_timer : {str(e)}")
            raise

    def get_combox_lag(self):
        try:
            lag = self.comboBox_sendTime_lag.currentText()
            log_print("lag is",lag, type(lag))
            #转为int
            return int(lag)
        except Exception as e:
            log_print(f"get_combox_timer : {str(e)}")
            raise

    def get_checkBox_sendFlag(self):
        try:
            flag = self.checkBox_sendFlag.isChecked()
            log_print("flag is",flag, type(flag))
            #转为int
            return flag
        except Exception as e:
            log_print(f"get_checkBox_sendFlag : {str(e)}")
            raise


    def Start_CAN_THREAD(self):
        try:
            self.can_recv_thread = JCANThread(self.can_dev)
            self.can_recv_thread.signal_Can_Recv_Msg.connect(self.Can_Recv_Print)
            self.can_recv_thread.signal_Can_All_Data.connect(self.handle_all_can_data)
            self.can_recv_thread.isRunning = True
            self.can_recv_thread.start()
        except Exception as e:
            log_print(f"Start_CAN_THREAD : {str(e)}")
            raise
        print("Start_CAN_THREAD OK!!!!!!!!!!")

    def open_table_view(self):
        self.can_tableview = TableView_MainWindow()
        self.can_tableview.show()



    def Can_Recv_Print(self, recv_msg):
        self.textEdit_Recv.append(recv_msg)

    def handle_all_can_data(self, all_data_str):
        log_print("Received all CAN data:", all_data_str)
        all_data_str = self.trim_hex(all_data_str)
        if self.can_tableview is not None:
            trimmer = all_data_str[30:-9]
            result = self.can_tableview.show_parsed_data(trimmer)
            log_print("Processed data:", result)


    def trim_hex(self,hex_str):
        hex_str = hex_str.replace("0x", "")
        log_print(hex_str)
        return hex_str

