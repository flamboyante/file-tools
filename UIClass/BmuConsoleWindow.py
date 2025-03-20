from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QDialog

import new_bmu_debug_ui


# BMU控制台窗口
class BmuConsoleWindow(QDialog, new_bmu_debug_ui.Ui_Form):
    signal_input_enter = pyqtSignal(str)      # 字符输入信号, 以换行符结束

    def __init__(self, parent=None):
        super(BmuConsoleWindow, self).__init__(parent)
        self.setupUi(self)
        self.is_echo = True
        self.textEdit_Output.setTabChangesFocus(True)
        self.lineEdit_Input.returnPressed.connect(self.slot_return_pressed)
        self.setWindowFlags(Qt.WindowMinimizeButtonHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)

    # 在输出文本框中追加字符串
    def output(self, text):
        try:
            self.textEdit_Output.append(text)
        except Exception as e:
            print(str(e))
            raise

    # 从输入文本框中读取字符串
    def input(self) -> str:
        text = None
        try:
            text = self.lineEdit_Input.text()
            if self.is_echo is True:
                self.textEdit_Output.append(text)
            print(text)
        except Exception as e:
            print(str(e))
            raise
        finally:
            return text

    # 清除控制台文本框的内容
    def clear(self):
        try:
            self.textEdit_Output.clear()
            self.lineEdit_Input.clear()
        except Exception as e:
            print(str(e))
            raise

    def slot_return_pressed(self):
        try:
            text = self.lineEdit_Input.text()
            if self.is_echo is True:
                self.textEdit_Output.append(text)
            self.signal_input_enter.emit(text)
            print(text)
        except Exception as e:
            print(str(e))
            raise
