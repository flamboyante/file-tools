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

            self.init_siui_table()
        except Exception as e:
            log_print(f"TableView_MainWindow __init__: {str(e)}")


    def set_model_init(self):
        try:
            log_print("set_model")

            self.model = QStandardItemModel(self.col_len   ,self.row_len,self)

            self.model.setHorizontalHeaderLabels(['遥测名称', '数值', 'bit'])

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


            # 设置不可编辑（可选）
            self.tableView.setEditTriggers(QTableView.NoEditTriggers)

            # 设置列宽自适应策略
            self.tableView.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)  # 允许手动调整
            self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)  # 允许手动调整
        except Exception as e:
            log_print(f"set_data error: {str(e)}")

    def set_table_init(self):
        log_print("set_data")
        try:
            # 清空旧数据（可选，根据业务需求决定）
            #self.model.removeRows(0, self.model.rowCount())

            for row_idx, row_data in enumerate(self.local_field):  # 使用枚举获取行索引
                # 提取字典数据
                name = str(row_data.get("name", ""))  # 安全获取name字段
                start_bits = str(row_data.get("start_bits", 0))  # 转换为字符串显示

                # 创建第一列（遥测名称）
                name_item = QStandardItem(name)
                name_item.setTextAlignment(Qt.AlignCenter)

                # 创建第三列（bit）
                bit_item = QStandardItem(start_bits)
                bit_item.setTextAlignment(Qt.AlignCenter)

                # 设置到对应列
                self.model.setItem(row_idx, 0, name_item)  # 第一列
                self.model.setItem(row_idx, 2, bit_item)  # 第三列



                log_print(f"Inserted row {row_idx}: {name} | {start_bits}")

        except Exception as e:
            log_print(f"set_data error: {str(e)}")




    def init_siui_table(self):
        ###############################

        self.demo_table_simple.resize(752, 360)

        self.demo_table_simple.addColumn("歌曲名", 190, 40, Qt.AlignLeft | Qt.AlignVCenter)
        self.demo_table_simple.addColumn("歌手", 160, 40, Qt.AlignLeft | Qt.AlignVCenter)
        self.demo_table_simple.addColumn("专辑", 240, 40, Qt.AlignLeft | Qt.AlignVCenter)
        self.demo_table_simple.addColumn("时长", 64, 40, Qt.AlignRight | Qt.AlignVCenter)

        self.demo_table_simple.addRow(data=["どうして", "高瀬統也", "どうして (feat. 野田愛実)", "03:01"])
        """
        self.demo_table_simple.addRow(data=["風色Letter", "水瀬いのり", "glow", "04:38"])
        self.demo_table_simple.addRow(data=["ステンドノクターン", "初音ミク", "ステンドノクターン", "03:39"])
        self.demo_table_simple.addRow(data=["鯖鯖", "山崎あおい", "鯖鯖", "05:06"])
        self.demo_table_simple.addRow(data=["優しい恋人", "しまも", "優しい恋人", "05:42"])
        self.demo_table_simple.addRow(data=["Summer Dream", "Kirara Magic", "Summer Dream (feat. Chevy)", "03:36"])
        self.demo_table_simple.addRow(data=["RPG", "Lefty Hand Cream", "Lefty Hand Covers Ⅱ", "04:16"])
        self.demo_table_simple.addRow(data=["The des Alizes", "Foxtail-Grass Studio", "Re*Collection", "03:40"])
        self.demo_table_simple.addRow(data=["他追着风", "霏泠Ice", "他追着风", "04:39"])
        self.demo_table_simple.addRow(data=["ちるちる", "REOL", "Σ", "03:17"])
        self.demo_table_simple.addRow(data=["展 / Re: Expansion", "RABPIT", "序章: 弥卢", "04:00"])
        self.demo_table_simple.addRow(
            data=["Never Gonna Give You Up", "Rick Astley", "Whenever You Need Somebody", "03:34"])
        """
        '''
        self.table_simple.body().setAdjustWidgetsSize(True)
        self.table_simple.body().addWidget(self.demo_table_simple)
        self.table_simple.body().addPlaceholder(12)
        self.table_simple.adjustSize()
        '''
    ##############################################################




