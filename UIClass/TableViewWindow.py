import sys

from PyQt5.QtCore import Qt, QAbstractTableModel

from PyQt5.QtWidgets import QApplication, QTableView, QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView

from PyQt5.QtGui import QStandardItemModel, QStandardItem

from PyQt5.QtWidgets import QMainWindow
from siui.components.widgets.table import SiTableView

from Pyqt5_UI.MainWindow_Frame_ui import Ui_MainWindow


from Can_Frame_Deal.Model_Excel import Model_Excel_Task

from  logging_config import log_print

class TableView_MainWindow(QMainWindow ,Ui_MainWindow):
    def __init__(self,parent=None):
        try:
            super(TableView_MainWindow, self).__init__(parent)
            self.setupUi(self)

            self.execler = Model_Excel_Task()
            sheetname = self.execler.execl_open()
            #List[Dict[str, str | int]]
            self.local_field, self.row_len , self.col_len = self.execler.excel_deal(sheetname[0])

            print(self.local_field)

            self.model = None

            self.set_model_init()

            self.set_table_init()

            #self.init_siui_table()
        except Exception as e:
            log_print(f"TableView_MainWindow __init__: {str(e)}")


    def set_model_init(self):
        try:
            log_print("set_model")

            self.model = QStandardItemModel(self.col_len   ,self.row_len,self)

            self.model.setHorizontalHeaderLabels(['遥测名称', '数值', 'start bit','16进制源码','参考公式'])

            """3. 创建TableView并设置模型"""
            # 设置模型
            self.tableView.setModel(self.model)  # 参数：QAbstractItemModel        """4. 表格属性设置"""
            # 设置表格列宽自适应内容
            self.tableView.resizeColumnsToContents()  # 返回值：None

            # 设置行高
            self.tableView.verticalHeader().setDefaultSectionSize(40)  # 参数：int（像素）
            self.tableView.horizontalHeader().setDefaultSectionSize(200)
            #print(self.tableView.width() / 3)
            #self.tableView.horizontalHeader().setDefaultSectionSize(self.tableView.width() / 3)  # 按三列平分初始宽度

            # 在set_model_init()中添加
            self.tableView.setWordWrap(True)  # 启用自动换行
            self.tableView.setTextElideMode(Qt.ElideNone)  # 禁止文本缩略

            self.tableView.setAlternatingRowColors(True)  # 增加行间辨识度
            self.tableView.verticalHeader().setMinimumSectionSize(30)
            # 设置不可编辑（可选）
            self.tableView.setEditTriggers(QTableView.NoEditTriggers)

            # 设置列宽自适应策略
            self.tableView.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)  # 允许手动调整
            self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)  # 允许手动调整
            self.tableView.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            #self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        except Exception as e:
            log_print(f"set_model_init error: {str(e)}")

    def set_table_init(self):
        log_print("set_data")
        try:
            # 清空旧数据（可选，根据业务需求决定）
            #self.model.removeRows(0, self.model.rowCount())

            for row_idx, row_data in enumerate(self.local_field):  # 使用枚举获取行索引
                # 提取字典数据
                name = str(row_data.get("name", ""))  # 安全获取name字段
                # 创建第一列（遥测名称）
                name_item = QStandardItem(name)
                name_item.setTextAlignment(Qt.AlignCenter)

                # 创建第三列（bit）
                start_bits = str(row_data.get("start_bits", 0))  # 转换为字符串显示
                bit_item = QStandardItem(start_bits)
                bit_item.setTextAlignment(Qt.AlignCenter)

                shell = str(row_data.get("shell", ""))
                shell_item = QStandardItem(shell)
                shell_item.setTextAlignment(Qt.AlignCenter)
                #shell_item.setFlags(shell_item.flags() | Qt.TextWordWrap)
                #shell_item.setTextAlignment(Qt.AlignCenter | Qt.TextWordWrap)

                # 设置到对应列
                self.model.setItem(row_idx, 0, name_item)  # 第一列
                self.model.setItem(row_idx, 2, bit_item)  # 第三列
                self.model.setItem(row_idx, 4, shell_item)  # 第五列



                log_print(f"Inserted row {row_idx}: {name} | {start_bits} | {shell}")

        except Exception as e:
            log_print(f"set_data error: {str(e)}")


    def show_parsed_data(self, hex_data):
        try:
            # 解析数据
            parsed_data = self.execler.parse_can_data(hex_data)
            # 填充数据到第二列
            for row_idx, data in enumerate(parsed_data):
                value = str(data["value"])
                value_item = QStandardItem(value)
                value_item.setTextAlignment(Qt.AlignCenter)
                # 如果当前行存在则更新第二列数据，不存在则添加新行
                self.model.setItem(row_idx, 1, value_item)  # 第一列


                value_hex = str(hex(data["value"]))
                value_hex_item = QStandardItem(value_hex)
                value_hex_item.setTextAlignment(Qt.AlignCenter)
                # 如果当前行存在则更新第二列数据，不存在则添加新行
                self.model.setItem(row_idx, 3, value_hex_item)  # 第一列
        except Exception as e:
            log_print(f"显示数据出错: {str(e)}")


