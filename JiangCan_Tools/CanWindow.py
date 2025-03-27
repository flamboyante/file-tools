import os,time

from PyQt5.QtWidgets import QDialog, QMessageBox
from PyQt5.QtCore import QTimer
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
            self.is_opened = False

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

            self.comboBox_sendTime_lag.addItem("1000")
            self.comboBox_sendTimes.addItem("1")

            self.pushButton_Open.clicked.connect(self.toggle_can_device)
            self.pushButton_Send.clicked.connect(self.send_test)
            self.pushButton_TableView.clicked.connect(self.open_table_view)

            self.can_recv_thread = None
            self.can_tableview = None
        except Exception as e:
            log_print(f"CanWindow __init__ : {str(e)}")
            raise

    def toggle_can_device(self):
        """切换设备状态"""
        log_print("toggle_can_device")
        if self.is_opened:
            self.close_dev()
        else:
            self.open_dev()
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
                            self.is_opened = True
                            self.disable_tab()
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


    def close_dev(self):
        try:
            if self.can_dev and self.can_dev.is_open:
                # 停止接收线程
                if self.can_recv_thread:
                    self.can_recv_thread.isRunning = False
                    self.can_recv_thread.stop()
                    self.can_recv_thread.quit()

                self.can_dev.close()
                self.is_opened = False
                self.enable_tab()
                self.textEdit_Info.append("CAN设备已关闭")
        except Exception as e:
            log_print(f"Close device error: {str(e)}")
            QMessageBox.critical(self, 'Error', f'关闭设备失败: {str(e)}')

    def _do_send(self):
        if self.remaining_times <= 0:
            self.pushButton_Send.setEnabled(True)  # 发送完成后恢复按钮
            return

        if self.get_checkBox_sendFlag() is False and self.remaining_times is not 1:
            log_print("强制关闭连续发送")
            self.remaining_times = 0
            self.pushButton_Send.setEnabled(True)
            QMessageBox.critical(self, 'Info', '强制关闭连续发送')
            return

        try:
            # 执行单次发送
            if self.current_ycyk == '快遥':
                self.can_dev.send_msg_for_fast_test()
            else:
                self.can_dev.send_msg_for_slow_test()

            self.remaining_times -= 1

            # 使用QTimer实现非阻塞延时
            if self.send_interval > 0:
                QTimer.singleShot(self.send_interval, self._do_send)
            else:
                self._do_send()  # 无间隔连续发送

        except Exception as e:
            log_print(f"发送失败: {str(e)}")
            self.pushButton_Send.setEnabled(True)
    def send_test(self):
        if not self.is_opened:
            QMessageBox.warning(self, 'Error', 'CAN INIT ERROR')
            return

        # 初始化发送参数
        self.remaining_times = self.get_combox_times() if self.get_checkBox_sendFlag() else 1
        self.send_interval = self.get_combox_lag() if self.get_checkBox_sendFlag() else 0
        self.current_ycyk = self.comboBox_Ycyk.currentText()

        # 禁用发送按钮防止重复点击
        self.pushButton_Send.setEnabled(False)

        # 开始发送流程
        self._do_send()




    def get_combox_times(self):
        try:
            times = self.comboBox_sendTimes.currentText()
            if times is None:
                times = 1
            log_print("times is",times, type(times))
            #转为int
            return int(times)
        except Exception as e:
            log_print(f"get_combox_timer : {str(e)}")
            raise

    def get_combox_lag(self):
        try:
            lag = self.comboBox_sendTime_lag.currentText()
            if lag is None:
                lag = 1000
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

    def Can_Recv_Print_Blue(self, recv_msg):
        try:
            # 分割并格式化消息
            self.textEdit_Recv.append("\n")
            numbers = recv_msg.split()
            grouped = [numbers[i:i + 8] for i in range(0, len(numbers), 8)]
            # 使用HTML换行标签<br>代替\n
            formatted_msg = '<br>'.join([' '.join(group) for group in grouped])
            # 插入带样式的HTML内容
            self.textEdit_Recv.insertHtml(f'<font color="blue">{formatted_msg}</font><br>')
        except Exception as e:
            log_print(f"Can_Recv_Print_Blue : {str(e)}")

    def handle_all_can_data(self, all_data_str):
        name_index = 0
        try:
            log_print("Received all CAN data:", type(all_data_str),all_data_str)

            self.Can_Recv_Print_Blue(all_data_str)

            all_data_str = self.trim_hex(all_data_str)

            #hex_str = ' '.join([x.replace('0x', '') for x in all_data_str])
            all_data_hex = list(bytes.fromhex(all_data_str))  # 返回的是bytes对象，用list()转为列表
            log_print("Received all CAN data  hex:", type(all_data_hex), all_data_hex)

            if all_data_hex[3] == 0xa5:
                log_print("收到快遥")
                name_index = 0
            elif all_data_hex[3] == 0x55:
                name_index =1
                log_print("收到慢遥")
            else:
                log_print("收到其他", all_data_hex[3])
                return


            if self.can_tableview is not None:
                trimmer = all_data_str[30:-9]
                result = self.can_tableview.show_parsed_data(trimmer,name_index)
                log_print("Processed data:", result)
        except Exception as e:
            log_print(f"handle_all_can_data : {str(e)}")
            raise

    def trim_hex(self,hex_str):
        hex_str = hex_str.replace("0x", "")
        log_print(hex_str)
        return hex_str

    def disable_tab(self):
        self.pushButton_Open.setText("关闭设备")  # 修改按钮文字
        self.comboBox_Type.setDisabled(True)

    def enable_tab(self):
        self.pushButton_Open.setText("打开设备")  # 修改按钮文字
        self.comboBox_Type.setEnabled(True)