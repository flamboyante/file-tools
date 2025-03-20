import binascii
import os
import struct
import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QDialog, QMessageBox, QFileDialog

from FTP_downfile_ui import Ui_FTPForm


from Media.Media import Media

from logging_config import log_print


class FTPWindow(QDialog, Ui_FTPForm):
    def __init__(self,parent=None):
        super(FTPWindow, self).__init__(parent)
        self.setupUi(self)

        log_print("FTPWindow thread id is ", threading.currentThread().ident)

        self.PushButton_ChooseFTPFile.clicked.connect(self.open_file)
        self.PrimaryPushButton_FTPUpdate.clicked.connect(self.ftp_file_update_notify)
        self.PrimaryPushButton_FTPResult.clicked.connect(self.ftp_file_trans_result_inquire)
        self.PrimaryPushButton_SelfBegin.clicked.connect(self.ftp_self_write_start)
        self.PrimaryPushButton_SelfResult.clicked.connect(self.ftp_self_write_result_inquire)

        self.fileName = None
        self.fileSize = None

        self.serFTP: Media = None

        # self.resp_thread = FtpResponseThread()
        # self.resp_thread.start()

        self.FTPOp_value_mapping = {
            "Write": 0x11,
            "Read":  0x00
        }
        self.FTPflash_value_mapping = {
            "KA_PLP0":      [[0x80, 0], [0x80, 0]],
            "KA_PLP1":      [[0x81, 1], [0x81, 1]],
            "FNP":          [[0x82, 0], [0x82, 0]],
            "RESV":         [[0x83, 1], [0x83, 1]],
            "SC_PLP0":      [[0x84, 0], [0x84, 0]],
            "SC_PLP1":      [[0x85, 1], [0x85, 1]],
            "KA_BS0_CPUA":  [[0X8a, 0], [0X8a, 0]],
            "KA_BS1_CPUA":  [[0X8b, 0], [0X8b, 0]],
            "KA_BS2_CPUA":  [[0X8c, 0], [0X8c, 0]],
            "KA_BS3_CPUA":  [[0X8d, 0], [0X8d, 0]],
            "KA_BS0_CPUB":  [[0X8E, 0], [0X8E, 0]],
            "KA_BS1_CPUB":  [[0X8F, 0], [0X8F, 0]],
            "KA_BS2_CPUB":  [[0X90, 0], [0X90, 0]],
            "KA_BS3_CPUB":  [[0X91, 0], [0X91, 0]],
            "SC_BS0_CPUA":  [[0X92, 0], [0X92, 0]],
            "SC_BS1_CPUA":  [[0X93, 0], [0X93, 0]],
            "SC_BS0_CPUB":  [[0X96, 0], [0X96, 0]],
            "SC_BS1_CPUB":  [[0X97, 0], [0X97, 0]],
        }

        self.Init_FTPWindow()

    def Init_FTPWindow(self):
        self.ComboBox_FpgaCpu.addItems(self.FTPflash_value_mapping.keys())
        self.ComboBox_FpgaCpu.setCurrentIndex(0)

        self.ComboBox_OpCMD.addItems(self.FTPOp_value_mapping.keys())
        self.ComboBox_OpCMD.setCurrentIndex(0)

    def resp_slot(self, resp: str):
        if resp is not None:
            self.TextEdit_DownPrint.append(resp)

    def open_file(self):
        # 打开文件对话框并获取文件路径
        log_print("openFiler thread id is ", threading.currentThread().ident)
        self.fileName, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*);;Text Files (*.txt)")
        if self.fileName:
            self.fileSize = os.path.getsize(self.fileName)  # 获取文件大小
            log_print("fileSize:", self.fileSize)
            self.LineEdit_FliePath.setText(self.fileName)

    def log_file_transfer(self, text: str):
        try:
            self.TextEdit_DownPrint.append(text)
        except Exception as e:
            log_print(e)

    def exception_show(self, e: Exception, trace: str):
        QMessageBox.warning(self, f'异常: {str(e)}', trace)

    def Int_to_bytes_struct(self, int_num, len):
        if len == 1:
            byte_stream = struct.pack('>B', int_num)
            return byte_stream
        if len == 2:
            byte_stream = struct.pack('>H', (int_num))
            return byte_stream
        if len == 4:
            byte_stream = struct.pack('>I', int_num)
            return byte_stream

    def reverse_accumulate(self, byte_stream):
        """计算bytearray的和校验值"""
        checksum = 0
        for i in range(2, len(byte_stream)):  # 从索引2开始遍历
            checksum += byte_stream[i]
            #log_print("calculate_checksum_sum ", i, hex(byte_stream[i]), hex(checksum))
        # 将累加和转换为16位整数，并取反
        checksum = (~checksum) & 0xFFFF
        return checksum

    # FTP文件更新通知
    def ftp_file_update_notify(self):
        if self.serFTP is None:
            QMessageBox.warning(self, "警告", "没有初始化IPV6")
            return

        if self.serFTP.is_open is False:
            QMessageBox.warning(self, "警告", "未建立连接")
            return

        flash_key = self.ComboBox_FpgaCpu.currentText()
        if not flash_key:
            QMessageBox.warning(self, "警告", "未选取flash部件")
            return
        flash_value = self.FTPflash_value_mapping.get(flash_key)
        if flash_value is None:
            QMessageBox.warning(self, "警告", "未知flash部件")
            return
        FpgaCpu, fileson = flash_value[0]
        log_print(f"flash type: {hex(FpgaCpu), hex(fileson)}, key: {flash_key}")

        FTPOpCMD_TXT = self.ComboBox_OpCMD.currentText()
        if not FTPOpCMD_TXT:
            QMessageBox.warning(self, "警告", "未选取FTPOpCMD部件")
            return
        FTPOpCMD = self.FTPOp_value_mapping.get(FTPOpCMD_TXT)
        if FTPOpCMD is None:
            QMessageBox.warning(self, "警告", "未知FTPOpCMD_byte部件")
            return
        log_print(f"flash cmd: {hex(FTPOpCMD)}, key: {FTPOpCMD_TXT}")

        if self.fileName is None:
            QMessageBox.warning(self, "警告", "未选取文件")
            return

        file_name_array = self.fileName.encode(encoding='utf-8')
        if len(file_name_array) > 128:
            QMessageBox.warning(self, "error", f"文件路径{len(file_name_array)}超过128字节")
            return

        self.resp_thread = self.serFTP

        begin_array = bytearray(
            [0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x88, 0x01, 0xD1])

        # 文件类型
        FpgaCpuByte = self.Int_to_bytes_struct(FpgaCpu, 1)
        begin_array.extend(FpgaCpuByte)

        # 文件子类型
        fileson_Byte = self.Int_to_bytes_struct(fileson, 1)
        begin_array.extend(fileson_Byte)

        # 文件长度
        fileSize_Byte = self.Int_to_bytes_struct(self.fileSize, 4)
        begin_array.extend(fileSize_Byte)

        # 操作类型
        FTPOpCMD_Byte = self.Int_to_bytes_struct(FTPOpCMD, 1)
        begin_array.extend(FTPOpCMD_Byte)

        # 文件目录及名称
        begin_array.extend(file_name_array)
        padding_len = 128 - len(file_name_array)
        padding_array = bytes(padding_len)
        begin_array.extend(padding_array)

        # 校验
        accumulator = self.reverse_accumulate(begin_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        begin_array.extend(accumulator_byte)

        log_print(f"ftp_file_update_notify length: {len(begin_array)}, value: {begin_array.hex(' ')}")

        self.serFTP.send(begin_array)

    # FTP文件传输结果查询
    def ftp_file_trans_result_inquire(self):
        if self.serFTP is None:
            QMessageBox.warning(self, "警告", "没有初始化IPV6")
            return

        if self.serFTP.is_open is False:
            QMessageBox.warning(self, "警告", "未建立连接")
            return

        self.resp_thread = self.serFTP

        begin_array = bytearray(
            [0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x01, 0x01, 0xDA])
        accumulator = self.reverse_accumulate(begin_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        begin_array.extend(accumulator_byte)

        log_print(f"ftp_file_trans_result_inquire length: {len(begin_array)}, value: {begin_array.hex(' ')}")

        self.serFTP.send(begin_array)

    # 自主重构组件开始
    def ftp_self_write_start(self):
        if self.serFTP is None:
            QMessageBox.warning(self, "警告", "没有初始化IPV6")
            return

        if self.serFTP.is_open is False:
            QMessageBox.warning(self, "警告", "未建立连接")
            return

        self.resp_thread = self.serFTP

        flash_key = self.ComboBox_FpgaCpu.currentText()
        if not flash_key:
            QMessageBox.warning(self, "警告", "未选取flash部件")
            return
        flash_value = self.FTPflash_value_mapping.get(flash_key)
        if flash_value is None:
            QMessageBox.warning(self, "警告", "未知flash部件")
            return
        FpgaCpu, fileson = flash_value[0]
        log_print(f"flash type: {hex(FpgaCpu), hex(fileson)}, key: {flash_key}")

        begin_array = bytearray(
            [0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x29, 0x34, 0x0A])

        # 软件版本号
        begin_array.extend(bytes(32))

        # Vendor
        begin_array.extend(bytes(2))

        # app
        begin_array.extend(bytes(3))

        # 文件类型
        FpgaCpuByte = self.Int_to_bytes_struct(FpgaCpu, 1)
        begin_array.extend(FpgaCpuByte)

        # 文件子类型
        fileson_Byte = self.Int_to_bytes_struct(fileson, 1)
        begin_array.extend(fileson_Byte)

        # 预留
        begin_array.extend(bytes([0x00]))

        # 校验
        accumulator = self.reverse_accumulate(begin_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        begin_array.extend(accumulator_byte)

        log_print(f"ftp_self_write_start length: {len(begin_array)}, value: {begin_array.hex(' ')}")

        self.serFTP.send(begin_array)

    # 自主重构结果查询
    def ftp_self_write_result_inquire(self):
        if self.serFTP is None:
            QMessageBox.warning(self, "警告", "没有初始化IPV6")
            return

        if self.serFTP.is_open is False:
            QMessageBox.warning(self, "警告", "未建立连接")
            return

        self.resp_thread = self.serFTP

        flash_key = self.ComboBox_FpgaCpu.currentText()
        if not flash_key:
            QMessageBox.warning(self, "警告", "未选取flash部件")
            return
        flash_value = self.FTPflash_value_mapping.get(flash_key)
        if flash_value is None:
            QMessageBox.warning(self, "警告", "未知flash部件")
            return
        FpgaCpu, fileson = flash_value[0]
        log_print(f"flash type: {hex(FpgaCpu), hex(fileson)}, key: {flash_key}")

        send_byte = bytearray(
            [0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x09, 0x34, 0x0e])

        # Vendor
        send_byte.extend(bytes(2))

        # app
        send_byte.extend(bytes(3))

        # 文件类型
        FpgaCpuByte = self.Int_to_bytes_struct(FpgaCpu, 1)
        send_byte.extend(FpgaCpuByte)

        # 文件子类型
        fileson_Byte = self.Int_to_bytes_struct(fileson, 1)
        send_byte.extend(fileson_Byte)

        # 预留
        send_byte.extend(bytes(1))

        # 校验
        accumulator = self.reverse_accumulate(send_byte)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        send_byte.extend(accumulator_byte)

        log_print(f"ftp_self_write_result_inquire length: {len(send_byte)}, value: {send_byte.hex(' ')}")

        self.serFTP.send(send_byte)


class FtpResponseThread(QThread):

    resp_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super(FtpResponseThread, self).__init__(parent)  # 调用超类的构造函
        log_print("ReadFile_Work init  thread id is ", threading.currentThread().ident)

        self.ser = None

    def run(self):
        try:
            while True:
                if self.ser is None:
                    continue
                resp = self.ser.recv(512)
                if resp is None:
                    time.sleep(0.1)
                    continue
                resp_str = self.validate_response1(resp)
                self.resp_signal.emit(resp_str)
        except Exception:
            log_print(Exception)

    def validate_response1(self, resp: bytearray) -> str:
        try:
            type_code = int.from_bytes(resp[8:9], byteorder="big", signed=False)  # 假设错误代码在第12个字节
            if type_code == 0x01BF:
                return f"FTP文件通知应答: 状态 {resp[10]}"
            elif type_code == 0x01DB:
                return f"FTP文件传输结果查询应答: 文件传输结果 {resp[10]}"
            elif type_code == 0x340F:
                return f"自主重构结果查询应答: 重构结果 {resp[10]}"
            else:
                return f"未知响应: {resp.hex(' ')}"
        except Exception:
            raise
