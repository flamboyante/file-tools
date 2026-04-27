import os,time

from PyQt5.QtWidgets import QDialog, QMessageBox
from PyQt5.QtCore import QTimer, QThread, Qt
from JiangCan_Tools import can_ui

from JiangCan_Tools.ECAN import ECAN, STATUS_OK, BaudRate, CAN_OBJ, Channel1, Channel2
from WorkClass.CanSendThread import CANSendThread
from logging_config import  log_print

from JiangCan_Tools.JiangCan import JCANThread
from ycyk_422 import ycyk_can_frame


# from UIClass.TableViewWindow import TableView_MainWindow

class CanWindow(QDialog, can_ui.Ui_CanForm):
    def __init__(self, parent=None):
        super(CanWindow, self).__init__(parent)
        try:
            self.setupUi(self)
            self.can_dev: ECAN = None
            self.can_send = None
            self.can_dev_b: ECAN = None
            self.can_send_b = None
            self.is_opened = False
            self.tx_cnt = 0

            self.type_map = {
                "USBCAN-I":  3,
                "USBCAN-II": 4,
                "USBCAN-FD": 6
            }

            self.pushButton_Open.clicked.connect(self.toggle_can_device)
            self.pushButton_TableView.clicked.connect(self.open_table_view)

            self.can_recv_thread = None
            self.can_tableview = None

            self.timer_fast = QTimer()
            self.timer_fast.timeout.connect(self.timer_fast_callback)
            self.timer_fast.setSingleShot(False)

            self.timer_slow1 = QTimer()
            self.timer_slow1.timeout.connect(self.timer_slow1_callback)
            self.timer_slow1.setSingleShot(False)

            self.timer_slow2 = QTimer()
            self.timer_slow2.timeout.connect(self.timer_slow2_callback)
            self.timer_slow2.setSingleShot(False)

            self.timer_slow3 = QTimer()
            self.timer_slow3.timeout.connect(self.timer_slow3_callback)
            self.timer_slow3.setSingleShot(False)

            self.timer_time = QTimer()
            self.timer_time.timeout.connect(self.timer_time_callback)
            self.timer_time.setSingleShot(False)

            self.timer_attitude = QTimer()
            self.timer_attitude.timeout.connect(self.timer_attitude_callback)
            self.timer_attitude.setSingleShot(False)

            self.timer_star = QTimer()
            self.timer_star.timeout.connect(self.timer_star_callback)
            self.timer_star.setSingleShot(False)

            self.timer_star_wgs84 = QTimer()
            self.timer_star_wgs84.timeout.connect(self.timer_star_wgs84_callback)
            self.timer_star_wgs84.setSingleShot(False)

            self.timer_bus = QTimer()
            self.timer_bus.timeout.connect(self.timer_bus_callback)
            self.timer_bus.setSingleShot(False)

            self.checkBox_fast.stateChanged.connect(self.checkbox_fast_callback)
            self.checkBox_slow1.stateChanged.connect(self.checkbox_slow1_callback)
            self.checkBox_slow2.stateChanged.connect(self.checkbox_slow2_callback)
            self.checkBox_slow3.stateChanged.connect(self.checkbox_slow3_callback)
            self.checkBox_time.stateChanged.connect(self.checkbox_time_callback)
            self.checkBox_attitude.stateChanged.connect(self.checkbox_attitude_callback)
            self.checkBox_star.stateChanged.connect(self.checkbox_star_callback)
            self.checkBox_star_wgs84.stateChanged.connect(self.checkbox_star_wgs84_callback)
            self.checkBox_bus_state.stateChanged.connect(self.checkbox_bus_callback)

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
        self.tx_cnt = self.tx_cnt + self.can_dev.tx_cnt
        self.textEdit_Info.append("CAN TX Counter, Total: " + str(self.tx_cnt) + ", Once: " + str(self.can_dev.tx_cnt)
                                  + ", Single: " + str(self.can_send.can_tx_single)
                                  + ", Start: " + str(self.can_send.can_tx_start)
                                  + ", Middle: " + str(self.can_send.can_tx_middle)
                                  + ", Stop: " + str(self.can_send.can_tx_stop))

    def checkbox_fast_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_fast.text()
            val = int(text)
            self.timer_fast.start(val)
        else:
            self.timer_fast.stop()

    def checkbox_slow1_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_slow1.text()
            val = int(text)
            self.timer_slow1.start(val)
        else:
            self.timer_slow1.stop()

    def checkbox_slow2_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_slow2.text()
            val = int(text)
            self.timer_slow2.start(val)
        else:
            self.timer_slow2.stop()

    def checkbox_slow3_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_slow3.text()
            val = int(text)
            self.timer_slow3.start(val)
        else:
            self.timer_slow3.stop()

    def checkbox_time_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_time.text()
            val = int(text)
            self.timer_time.start(val)
        else:
            self.timer_time.stop()

    def checkbox_attitude_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_attitude.text()
            val = int(text)
            self.timer_attitude.start(val)
        else:
            self.timer_attitude.stop()

    def checkbox_star_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_star.text()
            val = int(text)
            self.timer_star.start(val)
        else:
            self.timer_star.stop()

    def checkbox_star_wgs84_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_star_wgs84.text()
            val = int(text)
            self.timer_star_wgs84.start(val)
        else:
            self.timer_star_wgs84.stop()

    def checkbox_bus_callback(self, state):
        if state == Qt.Checked:
            text = self.lineEdit_bus_state.text()
            val = int(text)
            self.timer_bus.start(val)
        else:
            self.timer_bus.stop()

    def timer_fast_callback(self):
        if self.is_opened:
            self.send_msg_for_fast_test()
        else:
            print("can not open")

    def timer_slow1_callback(self):
        if self.is_opened:
            self.send_msg_for_slow_test()
        else:
            print("can not open")

    def timer_slow2_callback(self):
        if self.is_opened:
            self.send_msg_for_slow2_test()
        else:
            print("can not open")

    def timer_slow3_callback(self):
        if self.is_opened:
            self.send_msg_for_slow3_test()
        else:
            print("can not open")

    def timer_time_callback(self):
        if self.is_opened:
            self.send_msg_for_time_test()
        else:
            print("can not open")

    def timer_attitude_callback(self):
        if self.is_opened:
            self.send_msg_for_attitude_test()
        else:
            print("can not open")

    def timer_star_callback(self):
        if self.is_opened:
            self.send_msg_for_star_test()
        else:
            print("can not open")

    def timer_star_wgs84_callback(self):
        if self.is_opened:
            self.send_msg_for_star_wgs84_test()
        else:
            print("can not open")

    def timer_bus_callback(self):
        if self.is_opened:
            self.send_msg_for_bus_test()
        else:
            print("can not open")

    def open_dev(self):
        try:
            pwd = os.getcwd()
            print(pwd)
            dev_key = self.comboBox_Type.currentText()
            dev_val = self.type_map.get(dev_key)
            log_print("dev_key is",dev_key , "dev_val is" ,dev_val)
            #localFilePath = os.path.join(os.getcwd(), '.\\JiangCan_Tools\\ECanVci64.dll')
            ECAN.open(0, 0, '.\\dist\\Can_Frame_Deal\\ECanVci64.dll')
            if ECAN.is_open is True:
                self.textEdit_Info.append("CAN open OK")
                self.is_opened = True

                # 读取CAN盒信息
                info, ret = ECAN.info()
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

                self.can_dev = ECAN(Channel1)
                if self.can_dev.config(BaudRate.BAUD_500K):
                    self.textEdit_Info.append("CAN Channel1 config OK")
                    if self.can_dev.start():
                        self.textEdit_Info.append("CAN Channel1 start OK")
                        self.is_opened = True
                        self.disable_tab()
                        self.can_send = CANSendThread(self.can_dev)
                        self.can_send.start()
                        self.Start_CAN_THREAD()
                        # self.Start_CAN_THREAD()
                    else:
                        self.textEdit_Info.append("CAN Channel1 start FAIL")
                else:
                    self.textEdit_Info.append("CAN Channel1 config FAIL")

                self.can_dev_b = ECAN(Channel2)
                if self.can_dev_b.config(BaudRate.BAUD_500K):
                    self.textEdit_Info.append("CAN Channel2 config OK")
                    if self.can_dev_b.start():
                        self.textEdit_Info.append("CAN Channel2 start OK")
                        self.can_send_b = CANSendThread(self.can_dev_b)
                        self.can_send_b.start()
                    else:
                        self.textEdit_Info.append("CAN Channel2 start FAIL")
                else:
                    self.textEdit_Info.append("CAN Channel2 config FAIL")
            else:
                self.textEdit_Info.append(f"CAN open FAIL {self.can_dev.get_err_info()}")
                self.is_opened = False

        except Exception as e:
            log_print(f"CanWindow Opendev : {str(e)}")
            raise

    def close_dev(self):
        try:
            if ECAN.is_open:
                # 停止接收线程
                if self.can_recv_thread:
                    self.can_recv_thread.isRunning = False
                    self.can_recv_thread.stop()
                    self.can_recv_thread.quit()

                ECAN.close()
                self.is_opened = False
                self.enable_tab()
                self.textEdit_Info.append("CAN设备已关闭")
        except Exception as e:
            log_print(f"Close device error: {str(e)}")
            QMessageBox.critical(self, 'Error', f'关闭设备失败: {str(e)}')

    def send_msg_for_fast_test(self):
        frame = ycyk_can_frame()
        frame.name = "FAST"
        frame.prio = 0x0
        frame.src = 0x0
        frame.grp = 0x0
        frame.dst = 0x18
        frame.func = 0x1
        frame.data = [0x00, 0x5a, 0x5a]
        self.can_send.send(frame)
        # self.can_b_send.send(frame)

    def send_msg_for_slow_test(self):
        frame = ycyk_can_frame()
        frame.name = "SLOW1"
        frame.prio = 0x0
        frame.src = 0x0
        frame.grp = 0x0
        frame.dst = 0x18
        frame.func = 0x1
        frame.data = [0x00, 0xaa, 0x51, 0xFB]
        self.can_send.send(frame)
        # self.can_b_send.send(frame)

    def send_msg_for_slow2_test(self):
        frame = ycyk_can_frame()
        frame.name = "SLOW2"
        frame.prio = 0x0
        frame.src = 0x0
        frame.grp = 0x0
        frame.dst = 0x18
        frame.func = 0x1
        frame.data = [0x00, 0xaa, 0x52, 0xFC]
        self.can_send.send(frame)
        # self.can_b_send.send(frame)

    def send_msg_for_slow3_test(self):
        frame = ycyk_can_frame()
        frame.name = "SLOW3"
        frame.prio = 0x0
        frame.src = 0x0
        frame.grp = 0x0
        frame.dst = 0x18
        frame.func = 0x1
        frame.data = [0x00, 0xaa, 0x53, 0xfd]
        self.can_send.send(frame)
        # self.can_b_send.send(frame)

    def send_msg_for_time_test(self):
        frame = ycyk_can_frame()
        frame.name = "TIME"
        frame.prio = 0x1
        frame.src = 0x0
        frame.grp = 0x3
        frame.dst = 0x3F
        frame.func = 0x1
        frame.data = [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        self.can_send.send(frame)
        self.can_send_b.send(frame)

    def send_msg_for_attitude_test(self):
        data = [0x00, 0x25, 0x00, 0x02, 0x00, 0x01, 0x02, 0x03,
                0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b,
                0x0c, 0x0d, 0x0e, 0x0f, 0x10, 0x11, 0x12, 0x13,
                0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1a, 0x1b,
                0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x21, 0x22, 0x55]

        frame = ycyk_can_frame()
        frame.name = "ATTITUDE"
        frame.prio = 0x1
        frame.src = 0x0
        frame.grp = 0x01
        frame.dst = 0x3F
        frame.func = 0x1
        frame.data = data
        self.can_send.send(frame)
        self.can_send_b.send(frame)

    def send_msg_for_star_test(self):
        data = [0x00, 0x23, 0x00, 0x01, 0x20, 0x1f, 0x1e, 0x1d,
                0x1c, 0x1b, 0x1a, 0x19, 0x18, 0x17, 0x16, 0x15,
                0x14, 0x13, 0x12, 0x11, 0x10, 0x0f, 0x0e, 0x0d,
                0x0c, 0x0b, 0x0a, 0x09, 0x08, 0x07, 0x06, 0x05,
                0x04, 0x03, 0x02, 0x01, 0x00, 0x11]

        frame = ycyk_can_frame()
        frame.name = "STAR"
        frame.prio = 0x1
        frame.src = 0x0
        frame.grp = 0x01
        frame.dst = 0x15
        frame.func = 0x1
        frame.data = data
        self.can_send.send(frame)
        self.can_send_b.send(frame)

    def send_msg_for_star_wgs84_test(self):
        data = [0x00, 0x23, 0x00, 0x04, 0x20, 0x1f, 0x1e, 0x1d,
                0x1c, 0x1b, 0x1a, 0x19, 0x18, 0x17, 0x16, 0x15,
                0x14, 0x13, 0x12, 0x11, 0x10, 0x0f, 0x0e, 0x0d,
                0x0c, 0x0b, 0x0a, 0x09, 0x08, 0x07, 0x06, 0x05,
                0x04, 0x03, 0x02, 0x01, 0x00, 0x11]

        frame = ycyk_can_frame()
        frame.name = "STAR_WGS84"
        frame.prio = 0x1
        frame.src = 0x0
        frame.grp = 0x01
        frame.dst = 0x15
        frame.func = 0x1
        frame.data = data
        self.can_send.send(frame)
        self.can_send_b.send(frame)

    def send_msg_for_bus_test(self):
        frame = ycyk_can_frame()
        frame.name = "BUS"
        frame.prio = 0x1
        frame.src = 0x0
        frame.grp = 0x0
        frame.dst = 0x18
        frame.func = 0x1
        frame.data = [0x00, 0x25, 0x25]
        self.can_send.send(frame)
        self.can_send_b.send(frame)

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
                # self.can_dev.send_msg_for_fast_test()
                self.send_msg_for_fast_test()
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
            # log_print("Received all CAN data:", type(all_data_str),all_data_str)

            self.Can_Recv_Print_Blue(all_data_str)

            all_data_str = self.trim_hex(all_data_str)

            #hex_str = ' '.join([x.replace('0x', '') for x in all_data_str])
            all_data_hex = list(bytes.fromhex(all_data_str))  # 返回的是bytes对象，用list()转为列表
            # log_print("Received all CAN data  hex:", type(all_data_hex), all_data_hex)

            if all_data_hex[3] == 0xa5:
                # log_print("收到快遥")
                name_index = 0
            elif all_data_hex[3] == 0x55:
                name_index =1
                # log_print("收到慢遥")
            else:
                # log_print("收到其他", all_data_hex[3])
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
        # log_print(hex_str)
        return hex_str

    def disable_tab(self):
        self.pushButton_Open.setText("关闭设备")  # 修改按钮文字
        self.comboBox_Type.setDisabled(True)

    def enable_tab(self):
        self.pushButton_Open.setText("打开设备")  # 修改按钮文字
        self.comboBox_Type.setEnabled(True)
