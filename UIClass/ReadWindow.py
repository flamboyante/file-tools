import threading

from PyQt5.QtWidgets import QDialog, QMessageBox

from ReadFile_ui import Ui_FlashRead
from WorkClass.ReadFileWork import ReadFileWork

from logging_config import log_print


class ReadWindow(QDialog, Ui_FlashRead):
    def __init__(self, parent=None):
        super(ReadWindow, self).__init__(parent)
        self.setupUi(self)

        log_print("ReadWindow thread id is ", threading.currentThread().ident)

        self.ReadWholeLength = 0x1e50000
        self.ReadUpdateLength = 1024
        self.value_flash_byte = bytes(0x00)
        self.value_mem_byte = bytes(0x00)
        self.work: ReadFileWork = None


        self.mem_value_mapping = {
            "主 PLP0 Flash0(默认)": 0x05,
            "主 PLP1 Flash2(默认)": 0x87,
            "主 BPPS OS Flash0(默认)": 0x12,
            "主 BPPS APP Flash0(默认)": 0x02,
            "主 BPPS CFG Flash0(默认)": 0x22,
            "主 BPPKA OS Flash0(默认)": 0x13,
            "主 BPPKA APP Flash0(默认)": 0x03,
            "主 BPPKA CFG Flash0(默认)": 0x23,
            "主 SCP OS Flash0(默认)": 0x10,
            "主 SCP APP Flash0(默认)": 0x00,
            "主 SCP CFG Flash0(默认)": 0x20,
        }
        self.flash_value_mapping = {
            "基带":      0xFF,
            "SC":       0xFA,
        }

        self.init_window()

    def init_window(self):
        self.pushButton_ReadBegin.setEnabled(True)
        self.pushButton_ReadInit.setEnabled(False)
        self.pushButton_ReadCancel.setEnabled(False)
        self.pushButton_ReadBegin.clicked.connect(self.begin)
        self.pushButton_ReadInit.clicked.connect(self.pause)
        self.pushButton_ReadCancel.clicked.connect(self.cancel)
        self.comboBox_Flash.addItems(self.flash_value_mapping.keys())
        self.comboBox_Flash_MEM.addItems(self.mem_value_mapping.keys())
        self.comboBox_Flash_MEM.setCurrentIndex(0)
        self.comboBox_Flash.setCurrentIndex(0)
        self.progressBar.setValue(0)  # 重置进度条

    def pause(self):
        log_print("Press read_pause")
        if self.pushButton_ReadInit.text() == '暂停读取':
            self.work.pause()
            self.pushButton_ReadInit.setText('继续读取')
        else:
            self.work.resume()
            self.pushButton_ReadInit.setText('暂停读取')

    def begin(self):
        log_print("Press ReadBegin")

        try:
            if self.read_init() is True:
                self.pushButton_ReadBegin.setEnabled(False)
                self.pushButton_ReadInit.setEnabled(True)
                self.pushButton_ReadCancel.setEnabled(True)
                self.textEdit.append("Read begin!")
                self.work = ReadFileWork(self.mainWindow.Serial_Worker.media, self.value_flash_byte, self.value_mem_byte, 0x4000000, "readflashnew.bin")
                self.work.Read_processe_signal.connect(self.update_progress_bar)
                self.work.read_bytes_signal.connect(self.update_test_view)
                self.work.Read_complete_signal.connect(self.complete)
                self.work.start()
        except Exception as e:
            log_print(str(e))
            QMessageBox.warning(self, 'Error', str(e))

    def cancel(self):
        log_print("Press ReadCancel")
        self.work.stop()
        self.comboBox_Flash.setEnabled(True)
        self.comboBox_Flash_MEM.setEnabled(True)
        self.pushButton_ReadBegin.setEnabled(True)
        self.pushButton_ReadCancel.setEnabled(False)

    def update_progress_bar(self, value):
        log_print("update_progress_bar is ", value)
        self.progressBar.setValue(value)

    def complete(self):
        self.pushButton_ReadBegin.setEnabled(True)
        self.pushButton_ReadInit.setEnabled(False)
        self.pushButton_ReadCancel.setEnabled(False)
        self.progressBar.setValue(100)
        QMessageBox.information(self, "读取完成", "读取成功")

    def update_test_view(self, byte_len: int):
        self.textEdit.append(f"Read {byte_len / 1024} KB")

    # 初始化读取参数
    def read_init(self) -> bool:
        log_print("read_init")

        flash_key = self.comboBox_Flash.currentText()
        flash_val = self.flash_value_mapping.get(flash_key)
        if flash_val is None:
            QMessageBox.warning(self, 'Error', 'Unknown Flash')
            return False
        self.value_flash_byte = flash_val.to_bytes(1, 'big')
        log_print("self.value_flash_byte", self.value_flash_byte)

        mem_key = self.comboBox_Flash_MEM.currentText()
        mem_val = self.mem_value_mapping.get(mem_key)
        if mem_val is None:
            QMessageBox.warning(self, 'Error', 'Unknown Mem')
            return False
        self.value_mem_byte = mem_val.to_bytes(1, 'big')
        log_print("self.value_mem_byte", self.value_mem_byte)

        if not self.mainWindow.Serial_Worker.status:
            QMessageBox.warning(self, "警告", "串口通信未初始化,请重新操作")
            return False

        self.textEdit.append("ReadInit ok ,please begin read")

        return True
