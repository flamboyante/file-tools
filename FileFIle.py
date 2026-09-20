import sys

import serial
from PyQt5.QtSerialPort import QSerialPortInfo
import os

import Media.Media
from JiangCan_Tools.CanWindow import CanWindow

from PowerControl import PowerControl
from UIClass.BmuConsoleWindow import BmuConsoleWindow
from UIClass.FTPWindow import FTPWindow
from UIClass.ReadWindow import ReadWindow
from UIClass.SerialSendWindow import SerialSendWindow
from UIClass.BatchFlashDownWindow import BatchFlashDownWindow
from UIClass.NewCanWindow import NewCanWindow

# from UIClass.TableViewWindow import TableView_MainWindow

from WorkClass.BmuConsoleThread import BmuConsoleThread
from new_mainwindows_ui import  Ui_MainWindow
from new_downfile_ui import  Ui_Form
from logging_config import log_print
from ycyk_422 import  Ycyk_422_Work

from PyQt5 import QtWidgets
from PyQt5.QtWidgets import  QFileDialog
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QDialog
from PyQt5.QtCore import QThread, QTimer, Qt
from PyQt5.QtGui import  QIcon
import threading
import time

from Serial_thread import Serial_Worker, FileTransfer_Work

from qfluentwidgets import (FluentIcon,  Action,)


class FlashDownWindow(QDialog, Ui_Form):
    def __init__(self, parent=None):
        super(FlashDownWindow, self).__init__(parent)
        self.setupUi(self)
        self.setWindowIcon(QIcon('photo/ControlDesk.png'))
        self.setWindowTitle('FlamFIle')

        log_print("FlashDownWindow thread id is ", threading.currentThread().ident)

        self.PushButton_ChooseFile.clicked.connect(self.openFile)
        self.PushButton_BeginDown.clicked.connect(self.startFileTransfer)
        self.PrimaryPushButton_DownFlieInit.clicked.connect(self.InitFileTransfer)
        self.PushButton_CancelDown.clicked.connect(self.cancelTrans)
        self.ProgressBar.setValue(0)  # 重置进度条

        self.fileName = None
        self.fileSize = None
        self.InitFileTransfer_flag = 0
        self.FileTransfer_Qthread = None

        self.up_num = 0
        self.flag = False
        self.divide = True

        self.mem_value_mapping = {
            "PLP0 Flash0(默认)": 0x05,
            "PLP1 Flash0(默认)": 0x07,
            "BBPS OS Flash0(默认)": 0x12,
            "BBPS APP Flash0(默认)": 0x02,
            "BBPS CFG Flash0(默认)": 0x22,
            "BBPKA OS Flash0(默认)": 0x13,
            "BBPKA APP Flash0(默认)": 0x03,
            "BBPKA CFG Flash0(默认)": 0x23,
            "SCP OS Flash0(默认)": 0x10,
            "SCP APP Flash0(默认)": 0x00,
            "SCP CFG Flash0(默认)": 0x20,
            "BMU UPDATE": 0x06,
            "BMU DIR" : 0X36,
            "BMU GOLDEN": 0x26,
            "BMU IAP": 0x16,
            "PLP0 Flash1": 0x45,
            "PLP0 Flash2": 0x85,
            "PLP1 Flash1": 0x47,
            "PLP1 Flash2": 0x87,
            "BBPS OS Flash1": 0x52,
            "BBPS APP Flash1": 0x42,
            "BBPS CFG Flash1": 0x62,
            "BBPS OS Flash2": 0x92,
            "BBPS APP Flash2": 0x82,
            "BBPS CFG Flash2": 0xA2,
            "BBPKA OS Flash1": 0x53,
            "BBPKA APP Flash1": 0x43,
            "BBPKA CFG Flash1": 0x63,
            "BBPKA OS Flash2": 0x93,
            "BBPKA APP Flash2": 0x83,
            "BBPKA CFG Flash2": 0xA3,
            "SCP OS Flash1": 0x50,
            "SCP APP Flash1": 0x40,
            "SCP CFG Flash1": 0x60,
            "SCP OS Flash2": 0x90,
            "SCP APP Flash2": 0x80,
            "SCP CFG Flash2": 0xA0,
            "SCP EXC": 0x30,
            "SCP ATA2": 0x70,
            "BBPS EXC": 0x32,
            "BBPKA EXC": 0x33,
        }
        self.flash_value_mapping = {
            "基带":      0xFB,
            "基带2":     0x9B,
            "SC":       0xFA,
        }

        self.Init_FlashWindow()

    def Init_FlashWindow(self):
        self.ComboBox_Flash.addItems(self.flash_value_mapping.keys())
        self.ComboBox_Mem.addItems(self.mem_value_mapping.keys())
        self.ComboBox_Mem.setCurrentIndex(0)
        self.ComboBox_Flash.setCurrentIndex(0)

        if self.divide is True:
            self.checkBox_slice.setCheckState(Qt.Checked)
        else:
            self.LineEdit_frame_len.setEnabled(True)
            self.LineEdit_seg_num.setEnabled(True)
        self.checkBox_slice.stateChanged.connect(self.check_box_slice_changed)
        self.LineEdit_frame_len.setText("1000")
        self.LineEdit_seg_num.setText("1024")

        self.PushButton_CancelDown.setText('暂停下载')
        self.PushButton_CancelDown.setEnabled(False)

    def check_box_slice_changed(self, state):
        if state == Qt.Checked:
            self.divide = True
            self.LineEdit_frame_len.setEnabled(True)
            self.LineEdit_seg_num.setEnabled(True)
        else:
            self.divide = False
            self.LineEdit_frame_len.setEnabled(True)
            self.LineEdit_seg_num.setEnabled(False)

    def InitFileTransfer(self):
        if self.mainWindow.Serial_Worker.status and not self.FileTransfer_Qthread:
            self.FileTransfer_Worker = FileTransfer_Work(self.mainWindow.Serial_Worker)
            self.FileTransfer_Qthread = QThread()
            self.FileTransfer_Worker.moveToThread(self.FileTransfer_Qthread)  # 将 SerialFileTransfer 移动到新线程
            # 启动线程
            self.FileTransfer_Worker.file_start_signal.connect(self.FileTransfer_Worker.file_start_slot)
            self.FileTransfer_Worker.file_processe_signal.connect(self.updateProgressBar)
            self.FileTransfer_Worker.file_complete_signal.connect(self.CompleteFileTransfer)
            self.FileTransfer_Worker.file_log_signal.connect(self.log_file_transfer)
            self.FileTransfer_Worker.file_exception_signal.connect(self.exception_show)

            self.FileTransfer_Qthread.start()
            self.InitFileTransfer_flag = 1

            return
        elif not self.mainWindow.Serial_Worker.status:
            QMessageBox.warning(self, "警告", "串口通信未初始化,请重新操作")
            return
        else:
            QMessageBox.warning(self, "警告", "已初始化,请勿重新操作")
            return

    def openFile(self):
        # 打开文件对话框并获取文件路径
        log_print("openFiler thread id is ", threading.currentThread().ident)
        self.fileName, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*);;Text Files (*.txt)")
        if self.fileName:
            self.fileSize = os.path.getsize(self.fileName)  # 获取文件大小
            log_print("fileSize:", self.fileSize)
            self.LineEdit_FliePath.setText(self.fileName)

    def startFileTransfer(self):
        # 检查串口通信是否正常
        log_print("startFileTransfer thread id is ", threading.currentThread().ident)

        if self.InitFileTransfer_flag != 1:
            QMessageBox.warning(self, "警告", "文件传输未初始化，无法进行文件传输。")
            return

        if self.fileName is None:
            QMessageBox.warning(self, "警告", "未选取正确文件")
            return

        mem_key = self.ComboBox_Mem.currentText()
        if not mem_key:
            QMessageBox.warning(self, "警告", "未选取mem部件")
            return
        else:
            log_print(mem_key)
            mem_value = self.mem_value_mapping.get(mem_key)
            if mem_value is None:
                QMessageBox.warning(self, "警告", "未知mem部件")
                return
            log_print(hex(mem_value))

        flash_key = self.ComboBox_Flash.currentText()
        if not flash_key:
            QMessageBox.warning(self, "警告", "未选取flash部件")
            return
        else:
            log_print(flash_key)
            flash_value = self.flash_value_mapping.get(flash_key)
            if flash_value is None:
                QMessageBox.warning(self, "警告", "未知flash部件")
                return
            log_print(flash_value)
            log_print(flash_value, hex(flash_value))

        frame_len_str = self.LineEdit_frame_len.text()
        if not frame_len_str:
            frame_len = 1000
        else:
            frame_len = int(frame_len_str)
        frame_num_str = self.LineEdit_seg_num.text()
        if not frame_num_str:
            frame_num = 1024
        else:
            frame_num = int(frame_num_str)

        self.ProgressBar.setValue(0)  # 重置进度条
        self.TextEdit_DownPrint.append("erase flash ing ,please wait")
        self.FileTransfer_Worker.file_start_signal.emit(self.fileName, flash_value, mem_value, self.divide, frame_len, frame_num)
        self.PushButton_BeginDown.setEnabled(False)
        self.PushButton_CancelDown.setText('暂停下载')
        self.PushButton_CancelDown.setEnabled(True)
        self.flag = True

    def CompleteFileTransfer(self):
        self.ProgressBar.setValue(100)
        time.sleep(1)
        self.PushButton_CancelDown.setEnabled(False)
        #self.mainWindow.Serial_Worker.resume_serial_reader_signal.emit()
        QMessageBox.information(self, "打开普通串口", "文件下载成功,新版本开始运行")
        self.PushButton_BeginDown.setEnabled(True)


    def cancelTrans(self):
        if self.flag:
            self.FileTransfer_Worker.send_pause()
            self.PushButton_CancelDown.setText('继续下载')
            self.flag = False

        else:
            self.FileTransfer_Worker.send_resume()
            self.PushButton_CancelDown.setText('暂停下载')
            self.flag = True
        pass

    def updateProgressBar(self, transferredSize):
        #self.TextEdit_DownPrint.append('当前段:', transferredSize + 1)
        if self.fileSize > 0:  # 确保文件大小大于0
            self.ProgressBar.setValue(int(transferredSize / self.fileSize * 100))  # 计算并设置百分比
        else:
            self.ProgressBar.setValue(0)  # 如果文件大小为0，则重置进度条

    def log_file_transfer(self, text: str):
        try:
            self.TextEdit_DownPrint.append(text)
        except Exception as e:
            log_print(e)

    def exception_show(self, e: Exception, trace: str):
        QMessageBox.warning(self, f'异常: {str(e)}', trace)


# 主界面
class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.bmu_debug_window = None
        self.setupUi(self)
        self.setWindowIcon(QIcon('photo/computer.png'))
        self.setWindowTitle('FlamSerial')
        self.statusbar.hide()
        self.mainWindowsInit()

        log_print("new frame thread id is ", threading.currentThread().ident)

        self.Ycyk_Worker = Ycyk_422_Work(id=0xEB90)
        self.serial_bmu_flag = False

        # self.Ycyk_Worker.send_heart()

        # 多线程
        self.Serial_QThread = QThread()
        self.Serial_Worker = Serial_Worker()
        self.Serial_Worker.moveToThread(self.Serial_QThread)  # 修正了拼写错误

        self.Serial_Worker.show_error_signal.connect(self.show_error_dialog)
        self.Serial_Worker.serial_flag_signal.connect(self.show_serial_status)
        self.Serial_Worker.Sign_Serial_init.connect(self.Serial_Worker.init_media)  # 连接信号和槽

        self.Serial_QThread.start()

        self.bmu_debug_thread = None    # Type:BmuConsoleThread

        self.port_name = []
        self.time_scan = QTimer()
        self.time_scan.timeout.connect(self.Timer_Serial_Scan)
        self.time_scan.start(1000)

        # 添加您自己的代码来操作控件
        self.PrimaryPushButton_OpenSerial.clicked.connect(self.open_serial)
        self.primaryPushBtn_ethConnect.clicked.connect(self.connect_net)
        self.PrimaryPushButton_OpenSerialBmu.clicked.connect(self.open_serial_bmu)
        self.power_btn_list = self.tabWidget.currentWidget().findChildren(QtWidgets.QPushButton)

    def Timer_Serial_Scan(self):
        all_port = QSerialPortInfo.availablePorts()
        new_port = []
        for port in all_port:
            new_port.append(port.portName())
        if len(self.port_name) != len(new_port):
            log_print(self.port_name)
            self.port_name = new_port
            log_print(self.port_name)
            self.comboBox_SerialSel.clear()
            self.comboBox_SerialSel.addItems(self.port_name)
            self.comboBox_SerialSelBmu.clear()
            self.comboBox_SerialSelBmu.addItems(self.port_name)

    def open_serial(self):
        log_print("按下open serial按钮")

        com_port = self.comboBox_SerialSel.currentText()
        baud_rate = int(self.comboBox_byterate.currentText())
        data_bits = int(self.comboBox_data_bit.currentText())
        stop_bits = self.comboBox_stop_bit.currentText()
        parity_check = self.comboBox_checkbit.currentText()

        if self.Serial_Worker.status == 0:
            # 发出信号，传递数据到工作线程
            self.Enable_ComboBox_Controls(False)
            self.tab_eth.setDisabled(True)
            self.Serial_Worker.Sign_Serial_init.emit(Media.Media.MediaType.SERIAL, com_port, baud_rate, data_bits, stop_bits, parity_check)
            # self.heart_timer.start(3000)
        else:
            self.Enable_ComboBox_Controls(True)
            self.tab_eth.setEnabled(True)
            self.Serial_Worker.close_serial()

    def connect_net(self):
        log_print("按下建立连接按钮")
        try:
            ver = self.comboBox_ethIPVer.currentText()
            ip = self.comboBox_ethIpAddr.currentText()
            port = self.comboBox_ethPort.currentText()
            log_print("ver:", ver, 'ip:', ip, 'port:', port)
            log_print("port:", int(port))

            if self.Serial_Worker.status == 0:
                self.Enable_ComboBox_Controls(False)
                self.tab_serial.setDisabled(True)
                # port.encode('utf-8')
                if self.checkBox_Vlan.isChecked() is True:
                    vlan_id = self.lineEdit.text()
                    des_mac = self.lineEdit_DstMac.text()
                    iface = self.comboBox_iface.currentText()
                    self.Serial_Worker.Sign_Serial_init.emit(Media.Media.MediaType.VLAN, ip, int(port), int(vlan_id), des_mac, iface)
                else:
                    self.Serial_Worker.Sign_Serial_init.emit(Media.Media.MediaType.ETHERNET, ip, int(port), 0, '', '')
            else:
                self.Enable_ComboBox_Controls(True)
                self.tab_serial.setEnabled(True)
                self.Serial_Worker.close_serial()
        except Exception as e:
            print(e)

    def open_serial_bmu(self):
        log_print("按下open serial bmu按钮")

        try:
            if self.serial_bmu_flag is False:
                # 获取串口参数
                com_port = self.comboBox_SerialSelBmu.currentText()
                baud_rate = int(self.comboBox_baud_bmu.currentText())
                data_bits = int(self.comboBox_data_bit_bmu.currentText())
                stop_bits = self.comboBox_stop_bit_bmu.currentText()
                parity_check = self.comboBox_parity_bmu.currentText()

                serial_dict = {'NONE': serial.PARITY_NONE, 'EVEN': serial.PARITY_EVEN, 'ODD': serial.PARITY_ODD,
                               '1': serial.STOPBITS_ONE, '2': serial.STOPBITS_TWO,
                               '1.5': serial.STOPBITS_ONE_POINT_FIVE}

                parity = serial_dict.get(parity_check)
                if parity is None:
                    raise ValueError("Invalid parity check value")
                stop_bit = serial_dict.get(stop_bits)
                if stop_bit is None:
                    raise ValueError("Invalid stop bits value")

                # 创建串口接收线程
                self.bmu_debug_thread = BmuConsoleThread(com_port, baud_rate, data_bits, stop_bit, parity)
                self.bmu_debug_thread.signal_console_input.connect(self.set_bmu_console_info)
                self.bmu_debug_thread.signal_console_break.connect(self.bmu_console_break)
                self.bmu_debug_thread.start()
                self.serial_bmu_flag = True
                self.set_power_button_red(self.pushButton_BS0)
                self.set_power_button_red(self.pushButton_BS1)
                self.set_power_button_red(self.pushButton_BS2)
                self.set_power_button_red(self.pushButton_BS3)
                self.set_power_button_red(self.pushButton_COD0)
                self.set_power_button_red(self.pushButton_COD1)
                self.set_power_button_red(self.pushButton_SW0)
                self.set_power_button_red(self.pushButton_SC_BS4)
                self.set_power_button_red(self.pushButton_SC_BS5)
                self.set_power_button_red(self.pushButton_SC_COD0)
                self.set_power_button_red(self.pushButton_SC_COD1)
                self.set_power_button_red(self.pushButton_Gate)
                self.PrimaryPushButton_OpenSerialBmu.setText('关闭串口')
            else:
                self.bmu_debug_thread.stop()
                self.bmu_debug_thread = None
                self.serial_bmu_flag = False
                self.set_power_button_gray(self.pushButton_BS0)
                self.set_power_button_gray(self.pushButton_BS1)
                self.set_power_button_gray(self.pushButton_BS2)
                self.set_power_button_gray(self.pushButton_BS3)
                self.set_power_button_gray(self.pushButton_COD0)
                self.set_power_button_gray(self.pushButton_COD1)
                self.set_power_button_gray(self.pushButton_SW0)
                self.set_power_button_gray(self.pushButton_SC_BS4)
                self.set_power_button_gray(self.pushButton_SC_BS5)
                self.set_power_button_gray(self.pushButton_SC_COD0)
                self.set_power_button_gray(self.pushButton_SC_COD1)
                self.set_power_button_gray(self.pushButton_Gate)
                self.PrimaryPushButton_OpenSerialBmu.setText('打开串口')
        except Exception as e:
            if self.bmu_debug_thread:
                self.bmu_debug_thread = None
            QMessageBox.critical(self, '串口错误', f'{e}')
            log_print('open_serial_bmu:', e)

    def set_bmu_console_info(self, txt):
        if self.bmu_debug_window is not None:
            self.bmu_debug_window.output(txt)

    def bmu_console_break(self, emsg):
        QMessageBox.information(self, '串口中断', emsg)
        try:
            self.bmu_debug_thread.stop()
            self.bmu_debug_thread = None
            self.serial_bmu_flag = False
            self.set_power_button_gray(self.pushButton_BS0)
            self.set_power_button_gray(self.pushButton_BS1)
            self.set_power_button_gray(self.pushButton_BS2)
            self.set_power_button_gray(self.pushButton_BS3)
            self.set_power_button_gray(self.pushButton_COD0)
            self.set_power_button_gray(self.pushButton_COD1)
            self.set_power_button_gray(self.pushButton_SW0)
            self.set_power_button_gray(self.pushButton_SC_BS4)
            self.set_power_button_gray(self.pushButton_SC_BS5)
            self.set_power_button_gray(self.pushButton_SC_COD0)
            self.set_power_button_gray(self.pushButton_SC_COD1)
            self.set_power_button_gray(self.pushButton_Gate)
            self.PrimaryPushButton_OpenSerialBmu.setText('打开串口')
        except Exception as e:
            QMessageBox.critical(self, '串口错误', str(e))

    def send_bmu_cmd(self, cmd: str):
        log_print(cmd)
        if self.bmu_debug_thread is None:
            QMessageBox.information(self, '串口未打开', '')
            return
        self.bmu_debug_thread.send(cmd)

    def Enable_ComboBox_Controls(self, flag):
        if self.tabWidget_Media.currentIndex() is 0:
            if flag:
                self.comboBox_SerialSel.setEnabled(True)
                self.comboBox_byterate.setEnabled(True)
                self.comboBox_data_bit.setEnabled(True)
                self.comboBox_stop_bit.setEnabled(True)
                self.comboBox_checkbit.setEnabled(True)
            else:
                # 禁用控件
                self.comboBox_SerialSel.setEnabled(False)
                self.comboBox_byterate.setEnabled(False)
                self.comboBox_data_bit.setEnabled(False)
                self.comboBox_stop_bit.setEnabled(False)
                self.comboBox_checkbit.setEnabled(False)
        else:
            if flag:
                self.comboBox_ethIPVer.setEnabled(True)
                self.comboBox_ethIpAddr.setEnabled(True)
                self.comboBox_ethPort.setEnabled(True)
            else:
                self.comboBox_ethIPVer.setEnabled(False)
                self.comboBox_ethIpAddr.setEnabled(False)
                self.comboBox_ethPort.setEnabled(False)


    def show_error_dialog(self, error_message):
        # 这个槽函数会在主线程中调用，因此可以安全地操作 GUI
        QMessageBox.critical(self, '串口错误', error_message)

    def show_serial_status(self, flag):
        if self.tabWidget_Media.currentIndex() is 0:
            if flag == 1:
                self.PrimaryPushButton_OpenSerial.setText("关闭串口")
            elif flag == 0:
                self.PrimaryPushButton_OpenSerial.setText("打开串口")
        else:
            if flag == 1:
                self.primaryPushBtn_ethConnect.setText("断开连接")
            elif flag == 0:
                self.primaryPushBtn_ethConnect.setText("建立连接")

    def switch_power_btn(self, btn):
        if self.bmu_debug_thread is None:
            QMessageBox.information(self, '提示', '串口未打开')
            return
        key = btn.text()
        try:
            status = PowerControl.get_power_status(key)
            if status is not None:
                if status is True:
                    cmd = PowerControl.get_power_off_cmd(key)
                    self.bmu_debug_thread.send('8')
                    if self.bmu_debug_window is not None:
                        self.bmu_debug_window.output('8\r')
                    time.sleep(0.1)
                    self.bmu_debug_thread.send(cmd)
                    if self.bmu_debug_window is not None:
                        self.bmu_debug_window.output(cmd)
                    PowerControl.set_power_status(key, False)
                    self.set_power_button_red(btn)
                else:
                    cmd = PowerControl.get_power_on_cmd(key)
                    self.bmu_debug_thread.send('8')
                    if self.bmu_debug_window is not None:
                        self.bmu_debug_window.output('8\r')
                    time.sleep(0.1)
                    self.bmu_debug_thread.send(cmd)
                    if self.bmu_debug_window is not None:
                        self.bmu_debug_window.output(cmd)
                    PowerControl.set_power_status(key, True)
                    self.set_power_button_green(btn)
        except Exception as e:
            log_print(e)

    def power_on_off_bs0(self):
        self.switch_power_btn(self.pushButton_BS0)

    def power_on_off_bs1(self):
        self.switch_power_btn(self.pushButton_BS1)

    def power_on_off_bs2(self):
        self.switch_power_btn(self.pushButton_BS2)

    def power_on_off_bs3(self):
        self.switch_power_btn(self.pushButton_BS3)

    def power_on_off_cod0(self):
        self.switch_power_btn(self.pushButton_COD0)

    def power_on_off_cod1(self):
        self.switch_power_btn(self.pushButton_COD1)

    def power_on_off_sw0(self):
        self.switch_power_btn(self.pushButton_SW0)

    def power_on_off_sc_bs4(self):
        self.switch_power_btn(self.pushButton_SC_BS4)

    def power_on_off_sc_bs5(self):
        self.switch_power_btn(self.pushButton_SC_BS5)

    def power_on_off_sc_cod0(self):
        self.switch_power_btn(self.pushButton_SC_COD0)

    def power_on_off_sc_cod1(self):
        self.switch_power_btn(self.pushButton_SC_COD1)

    def power_on_off_gate(self):
        self.switch_power_btn(self.pushButton_Gate)

    def set_power_button_gray(self, btn: QtWidgets.QPushButton):
        btn.setStyleSheet('''QPushButton{background-color:rgb(128,128,128)}''')

    def set_power_button_red(self, btn: QtWidgets.QPushButton):
        btn.setStyleSheet('''QPushButton{background-color:rgb(255,0,0)}''')

    def set_power_button_green(self, btn: QtWidgets.QPushButton):
        btn.setStyleSheet('''QPushButton{background-color:rgb(0,255,0)}''')

    def mainWindowsInit(self):

        #comboBox_SerialSel
        self.comboBox_SerialSel.setPlaceholderText("选择串口")
        self.comboBox_byterate.setPlaceholderText("选择波特率")

        self.comboBox_data_bit.setPlaceholderText("选择数据位")
        self.comboBox_checkbit.setPlaceholderText("选择校验位")
        self.comboBox_stop_bit.setPlaceholderText("选择停止位")
        self.comboBox_byterate.addItems(['115200', '9600', '921600', '4000000', '2000000'])
        self.comboBox_data_bit.addItems(['6', '7', '8'])
        self.comboBox_stop_bit.addItems(['1', '1.5', '2'])
        self.comboBox_checkbit.addItems(['NONE', 'ODD', 'EVEN'])
        self.comboBox_data_bit.setCurrentIndex(2)
        self.comboBox_checkbit.setCurrentIndex(1)

        self.comboBox_baud_bmu.setPlaceholderText("选择波特率")
        self.comboBox_baud_bmu.addItems(['115200', '9600', '921600', '4000000', '2000000'])
        self.comboBox_baud_bmu.setCurrentIndex(2)

        self.comboBox_data_bit_bmu.setPlaceholderText("选择数据位")
        self.comboBox_data_bit_bmu.addItems(['6', '7', '8'])
        self.comboBox_data_bit_bmu.setCurrentIndex(2)

        self.comboBox_stop_bit_bmu.setPlaceholderText("选择停止位")
        self.comboBox_stop_bit_bmu.addItems(['1', '1.5', '2'])
        self.comboBox_stop_bit_bmu.setCurrentIndex(0)

        self.comboBox_parity_bmu.setPlaceholderText("选择校验位")
        self.comboBox_parity_bmu.addItems(['NONE', 'ODD', 'EVEN'])
        self.comboBox_parity_bmu.setCurrentIndex(1)

        self.CommandBar.addAction(Action(FluentIcon.ADD, '添加', triggered=lambda: log_print("添加")))

        # 添加分隔符
        self.CommandBar.addSeparator()

        # 批量添加动作
        self.CommandBar.addActions([
            Action(FluentIcon.CONNECT, '控制台', triggered=self.show_bmu_console_window),
            Action(FluentIcon.DOWNLOAD, '版本重构', triggered=self.show_FlashDownWindow),
            Action(FluentIcon.DOWNLOAD, '批量重构', triggered=self.show_BatchFlashDownWindow),
            Action(FluentIcon.ROBOT, '版本读取', triggered=self.show_FlashReadWindow),
            #Action(FluentIcon.POWER_BUTTON, '基带复位', triggered=self.IrRePOWER),
            Action(FluentIcon.SEARCH_MIRROR, '固件版本查询', triggered=self.IrVersionCheck),
            #Action(FluentIcon.MAIL, 'CAN收发', triggered=self.can_window_show),
            #Action(FluentIcon.MAIL, 'FTP',triggered = self.show_FTP_Window )
            Action(FluentIcon.MAIL, 'TableView',triggered = self.Table_Window_Show ),
            Action(FluentIcon.POWER_BUTTON, 'Can', triggered=self.Can_Window_Show),
            Action(FluentIcon.CONNECT, 'SerialSend', triggered=self.Serial_Send_Window_Show),
            Action(FluentIcon.SEND, 'Can 新版', triggered=self.Can_New_Window_Show),
            Action(FluentIcon.VIEW, 'UI 方案对比', triggered=self.Ui_Compare_Window_Show),
        ])

        # 添加始终隐藏的动作
        self.CommandBar.addHiddenAction(Action(FluentIcon.SCROLL, '排序', triggered=lambda: log_print('排序')))
        self.CommandBar.addHiddenAction(Action(FluentIcon.SETTING, '设置'))

        # 初始化Button为灰色
        self.set_power_button_gray(self.pushButton_BS0)
        self.set_power_button_gray(self.pushButton_BS1)
        self.set_power_button_gray(self.pushButton_BS2)
        self.set_power_button_gray(self.pushButton_BS3)
        self.set_power_button_gray(self.pushButton_COD0)
        self.set_power_button_gray(self.pushButton_COD1)
        self.set_power_button_gray(self.pushButton_SW0)
        self.set_power_button_gray(self.pushButton_SC_BS4)
        self.set_power_button_gray(self.pushButton_SC_BS5)
        self.set_power_button_gray(self.pushButton_SC_COD0)
        self.set_power_button_gray(self.pushButton_SC_COD1)
        self.set_power_button_gray(self.pushButton_Gate)

        self.pushButton_BS0.clicked.connect(self.power_on_off_bs0)
        self.pushButton_BS1.clicked.connect(self.power_on_off_bs1)
        self.pushButton_BS2.clicked.connect(self.power_on_off_bs2)
        self.pushButton_BS3.clicked.connect(self.power_on_off_bs3)
        self.pushButton_COD0.clicked.connect(self.power_on_off_cod0)
        self.pushButton_COD1.clicked.connect(self.power_on_off_cod1)
        self.pushButton_SW0.clicked.connect(self.power_on_off_sw0)
        self.pushButton_SC_BS4.clicked.connect(self.power_on_off_sc_bs4)
        self.pushButton_SC_BS5.clicked.connect(self.power_on_off_sc_bs5)
        self.pushButton_SC_COD0.clicked.connect(self.power_on_off_sc_cod0)
        self.pushButton_SC_COD1.clicked.connect(self.power_on_off_sc_cod1)
        self.pushButton_Gate.clicked.connect(self.power_on_off_gate)

    def IrRePOWER(self):
        if not self.Serial_Worker.status:
            QMessageBox.warning(self, "警告", "通信未初始化,请重新操作")
            return
        else:
            IR_reboot_byte = self.Ycyk_Worker.Send_Reboot()
            self.Serial_Worker.media.send(IR_reboot_byte)
            log_print("-------------复位遥控指令已经发送成功,-----------")

    def IrVersionCheck(self):
        if not self.Serial_Worker.status:
            QMessageBox.warning(self, "警告", "通信未初始化,请重新操作")
            return
        else:
            IR_VersionCheck_byte = self.Ycyk_Worker.Send_VersionCheck()
            self.Serial_Worker.media.send(IR_VersionCheck_byte)
            log_print("-------------固件版本查询遥控指令已经发送成功-----------")

    def Can_Window_Show(self):
        self.can_window = CanWindow()
        self.can_window.setWindowModality(Qt.NonModal)
        self.can_window.show()

    def Can_New_Window_Show(self):
        self.can_window_new = NewCanWindow()
        self.can_window_new.setWindowModality(Qt.NonModal)
        self.can_window_new.show()

    def Ui_Compare_Window_Show(self):
        """UI 三方案对比入口（C 现状 / A qfluentwidgets / B QWebEngine）。

        三个方案共用 uicmp.core 的数据与收发层，只换渲染层，
        所以比较出来的是「界面实现差异」而不是「通信实现差异」。
        """
        try:
            from uicmp.launcher import show as _show_uicmp
            self.uicmp_window = _show_uicmp(self)
        except Exception as e:
            log_print("UI 方案对比窗口初始化失败: %s" % e)
            QMessageBox.warning(self, "UI 方案对比", "初始化失败：%s" % e)

    def Serial_Send_Window_Show(self):
        self.serial_send_window = SerialSendWindow()
        self.serial_send_window.setWindowModality(Qt.NonModal)
        self.serial_send_window.show()


    def Table_Window_Show(self):
        try:
            self.table_window = TableView_MainWindow()
            self.table_window.setWindowModality(Qt.NonModal)
            self.table_window.show()
        except Exception as e:
            log_print(f"TableView_MainWindow初始化失败:{e}")

    def show_FlashDownWindow(self):
        # 在 MainWindow 类中，当创建 FlashDownWindow 时
        self.flashDownWindow = FlashDownWindow(self)
        self.flashDownWindow.mainWindow = self  # 设置 FlashDownWindow 的父窗口引用
        self.flashDownWindow.setWindowModality(Qt.NonModal)
        self.flashDownWindow.show()

    def show_BatchFlashDownWindow(self):
        self.batchFlashDownWindow = BatchFlashDownWindow(self)
        self.batchFlashDownWindow.mainWindow = self
        self.batchFlashDownWindow.setWindowModality(Qt.NonModal)
        self.batchFlashDownWindow.show()

    # 显示BMU控制台窗口
    def show_bmu_console_window(self):
        # if self.serial_bmu is None or self.serial_bmu.is_open is False:
        #     QMessageBox.information(self, '提示', '串口未打开')
        #     return
        self.bmu_debug_window = BmuConsoleWindow()
        self.bmu_debug_window.mainWindow = self
        self.bmu_debug_window.setWindowModality(Qt.NonModal)
        self.bmu_debug_window.signal_input_enter.connect(self.send_bmu_cmd)
        self.bmu_debug_window.show()

    def show_FlashReadWindow(self):
        # 在 MainWindow 类中，当创建 FlashDownWindow 时
        self.flashReadWindow = ReadWindow(self)
        self.flashReadWindow.mainWindow = self  # 设置 FlashDownWindow 的父窗口引用
        self.flashReadWindow.show()

    def show_FTP_Window(self):
        self.FTPWindow = FTPWindow(self)
        self.FTPWindow.serFTP = self.Serial_Worker.media  # 设置 FlashDownWindow 的父窗口引用
        self.FTPWindow.show()

    def hellp(self):
        log_print("hello")

# def sendcan1():
#     canobj = CAN_OBJ()
#     canobj.ID = 0x31801
#     canobj.DataLen = 3
#     canobj.data[0] = 0x00
#     canobj.data[1] = 0xaa
#     canobj.data[2] = 0xaa
#     canobj.data[3] = 0x00
#     canobj.data[4] = 0x00
#     canobj.data[5] = 0x00
#     canobj.data[6] = 0x00
#     canobj.data[7] = 0x00
#     canobj.RemoteFlag = 0
#     canobj.ExternFlag = 1
#     ecan.transmit(canobj)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    myWin = MainWindow()
    myWin.show()
    sys.exit(app.exec_())


'''
    def show_FlashDownWindow(self):
        # 在 MainWindow 类中，当创建 FlashDownWindow 时
        self.flashDownWindow = FlashDownWindow(self)
        self.flashDownWindow.mainWindow = self  # 设置 FlashDownWindow 的父窗口引用
        self.flashDownWindow.show()
'''
