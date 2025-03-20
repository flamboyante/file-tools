import sys

from PyQt5.QtCore import Qt, QAbstractTableModel

from PyQt5.QtWidgets import QApplication, QTableView, QWidget, QVBoxLayout,QTableWidgetItem

from PyQt5.QtWidgets import QMainWindow

from Pyqt5_UI.MainWindow_Frame_ui import Ui_MainWindow


class TableView_MainWindow(QMainWindow ,Ui_MainWindow):
    def __init__(self,parent=None):
        super(TableView_MainWindow, self).__init__(parent)
        self.setupUi(self)

