import sys

from PyQt5 import QtWidgets
from PyQt5.QtCore import Qt, QAbstractTableModel

from PyQt5.QtWidgets import QApplication, QTableView, QWidget, QVBoxLayout, QTableWidgetItem, QHeaderView

from PyQt5.QtGui import QStandardItemModel, QStandardItem

from PyQt5.QtWidgets import QMainWindow
from siui.components.widgets.table import SiTableView

from HkjView.HkjTableView import HkjTableView
from Pyqt5_UI.MainWindow_Frame_ui import Ui_MainWindow


from Can_Frame_Deal.Model_Excel import Model_Excel_Task

from  logging_config import log_print

class TableView_MainWindow(QMainWindow ,Ui_MainWindow):
    def __init__(self,parent=None):
        try:
            super(TableView_MainWindow, self).__init__(parent)
            self.setupUi(self)


            self.execler = Model_Excel_Task()
            self.sheetnames = self.execler.execl_open()
            log_print("sheetnams:" ,self.sheetnames)
            #List[Dict[str, str | int]]
            #self.local_field, self.row_len , self.col_len = self.execler.excel_deal(sheetname[0])

            self.local_radio_buttons = [
                self.radioButton_fast, self.radioButton_slow,
                self.radioButton_0, self.radioButton_1, self.radioButton_2,
                self.radioButton_3, self.radioButton_4, self.radioButton_5,
                self.radioButton_6, self.radioButton_7, self.radioButton_8,
                self.radioButton_9, self.radioButton_12, self.radioButton_13
            ]

            #############################################

            while self.stackedWidget.count() > 0:  # 循环移除所有预置页面
                widget = self.stackedWidget.widget(0)
                self.stackedWidget.removeWidget(widget)
                widget.deleteLater()
            # 初始化所有RadioButton文本
            self._init_radio_buttons()


            # 新增：存储所有Sheet模型的字典
            self.sheet_models = {}  # 格式: {sheet_index: QStandardItemModel}
            self._generate_sheet_models(self.sheetnames)

            # 动态生成TableView页面
            self._create_table_pages()

            # 绑定RadioButton信号
            self._connect_radio_buttons()

            # 默认选中第一个按钮
            self.radioButton_2.setChecked(True)
            #######################################################


            #self.model = None

            #self.set_model_init()

            #self.set_table_init()

            #self.init_siui_table()
        except Exception as e:
            log_print(f"TableView_MainWindow __init__: {str(e)}")

    """
    def set_model_init(self):
        try:
            log_print("set_model")

            self.model = QStandardItemModel(self.col_len   ,self.row_len,self)

            self.model.setHorizontalHeaderLabels(['遥测名称', '数值', 'start bit','16进制源码','参考公式'])

            ####3. 创建TableView并设置模型
            # 设置模型
            self.tableView.setModel(self.model)  # 参数：QAbstractItemModel        
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

"""

    def _generate_sheet_models(self, sheet_names):
        """为每个Excel Sheet生成独立数据模型"""
        for sheet_index, sheet_name in enumerate(sheet_names):
            # 处理当前Sheet数据
            local_field, row_len, col_len = self.execler.excel_deal(sheet_name)


            # 创建模型
            model = QStandardItemModel(col_len, row_len)
            model.setHorizontalHeaderLabels(['遥测名称', '数值', 'start bit', '16进制源码', '参考公式'])

            # 填充数据
            for row_idx, row_data in enumerate(local_field):
                name_item = QStandardItem(str(row_data.get("name", "")))
                bit_item = QStandardItem(str(row_data.get("start_bits", 0)))
                shell_item = QStandardItem(str(row_data.get("shell", "")))
                model.setItem(row_idx, 0, name_item)
                model.setItem(row_idx, 2, bit_item)
                model.setItem(row_idx, 4, shell_item)

            # 存储模型
            self.sheet_models[sheet_index] = model

    def get_sheet_model(self, sheet_index=0):
        """获取指定Sheet的模型（默认返回第一个）"""
        return self.sheet_models.get(sheet_index, None)

    def get_all_sheet_models(self):
        """获取全部Sheet模型字典"""
        return self.sheet_models
    def show_parsed_data(self, hex_data , name_index):
        try:
            # 解析数据
            parsed_data = None
            parsed_data_back =None
            parsed_data ,parsed_data_back ,back_sheet_slot= self.execler.parse_can_data(hex_data ,self.sheetnames[name_index])
            # 填充数据到第二列
            for row_idx, data in enumerate(parsed_data):
                value = str(data["value"])
                value_item = QStandardItem(value)
                value_item.setTextAlignment(Qt.AlignCenter)
                # 如果当前行存在则更新第二列数据，不存在则添加新行
                self.sheet_models.get(name_index).setItem(row_idx, 1, value_item)  # 第一列


                value_hex = str(hex(data["value"]))
                value_hex_item = QStandardItem(value_hex)
                value_hex_item.setTextAlignment(Qt.AlignCenter)
                # 如果当前行存在则更新第二列数据，不存在则添加新行
                self.sheet_models.get(name_index).setItem(row_idx, 3, value_hex_item)  # 第一列

            if  parsed_data_back is not None:#第二次
                for row_idx, data in enumerate(parsed_data_back):
                    value = str(data["value"])
                    value_item = QStandardItem(value)
                    value_item.setTextAlignment(Qt.AlignCenter)
                    # 如果当前行存在则更新第二列数据，不存在则添加新行
                    self.sheet_models.get(back_sheet_slot).setItem(row_idx, 1, value_item)  # 第一列

                    value_hex = str(hex(data["value"]))
                    value_hex_item = QStandardItem(value_hex)
                    value_hex_item.setTextAlignment(Qt.AlignCenter)
                    # 如果当前行存在则更新第二列数据，不存在则添加新行
                    self.sheet_models.get(back_sheet_slot).setItem(row_idx, 3, value_hex_item)  # 第一列


                    self.local_radio_buttons[back_sheet_slot].setChecked(True)  # 这会自动触发绑定的_switch_page方法


        except Exception as e:
            log_print(f"显示数据出错: {str(e)}")


    def _init_radio_buttons(self):
        radio_buttons = [
            self.radioButton_fast, self.radioButton_slow,
            self.radioButton_0, self.radioButton_1, self.radioButton_2,
            self.radioButton_3, self.radioButton_4, self.radioButton_5,
            self.radioButton_6, self.radioButton_7, self.radioButton_8,
            self.radioButton_9, self.radioButton_12, self.radioButton_13
        ]
        ##




    def _create_table_pages(self):
        radio_count = self.groupBox.layout().count()  # 获取RadioButton数量
        log_print("radio_count is",radio_count)
        for i in range(radio_count):  # 为每个RadioButton创建页面
            log_print("i",i)
            page = self._create_single_page(i,i)
            self.stackedWidget.addWidget(page)


    def _create_single_page(self,page_index,sheet_index):
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        # 添加标题标签（关键修改）
        title_label = QtWidgets.QLabel(f"当前视图：{self._get_radio_text(page_index)}")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                color: #2c3e50;
                margin-bottom: 10px;
            }
        """)
        layout.addWidget(title_label)

        # 获取当前Sheet的独立模型
        sheet_model = self.sheet_models.get(sheet_index)  # 从字典中提取
        log_print(f"创建TableView，当前Sheet索引：{sheet_index}")
        # 创建TableView并绑定模型
        tableView = HkjTableView()
        if sheet_model:  # 确保模型存在
            tableView.setModel(sheet_model)
        else:
            log_print(f"警告：Sheet索引 {sheet_index} 的模型未找到,shezhi 0 moxing")
            tableView.setModel(self.sheet_models.get(0))
        tableView.resizeColumnsToContents()
        tableView.verticalHeader().setDefaultSectionSize(40)
        tableView.horizontalHeader().setDefaultSectionSize(200)
        tableView.setAlternatingRowColors(True)
        tableView.setEditTriggers(QtWidgets.QTableView.NoEditTriggers)

        #### 设置列宽自适应策略
        tableView.verticalHeader().setSectionResizeMode(QHeaderView.Interactive)  # 允许手动调整
        tableView.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)  # 允许手动调整
        tableView.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        #self.tableView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)



        layout.addWidget(tableView)
        return page


    def _connect_radio_buttons(self):
        radio_buttons = [
            self.radioButton_fast, self.radioButton_slow,
            self.radioButton_0, self.radioButton_1, self.radioButton_2,
            self.radioButton_3, self.radioButton_4, self.radioButton_5,
            self.radioButton_6, self.radioButton_7, self.radioButton_8,
            self.radioButton_9, self.radioButton_12, self.radioButton_13
        ]
        for idx, btn in enumerate(radio_buttons):
            # 绑定信号时使用lambda确保正确传递索引
            btn.toggled.connect(lambda checked, x=idx: self._switch_page(x) if checked else None)


    def _switch_page(self, index):
        log_print(f"尝试切换到页面索引: {index}")
        if index < self.stackedWidget.count():
            self.stackedWidget.setCurrentIndex(index)
        else:
            log_print(f"无效的页面索引: {index} (总页数: {self.stackedWidget.count()})")

    def _get_radio_text(self, index):
        """根据索引获取RadioButton文本"""
        radio_buttons = [
            self.radioButton_fast, self.radioButton_slow,
            self.radioButton_0, self.radioButton_1, self.radioButton_2,
            self.radioButton_3, self.radioButton_4, self.radioButton_5,
            self.radioButton_6, self.radioButton_7, self.radioButton_8,
            self.radioButton_9, self.radioButton_12, self.radioButton_13
        ]
        return radio_buttons[index].text() if index < len(radio_buttons) else "未知视图"

    # 新增辅助方法
    def _update_sheet_model(self, sheet_index, data_list):
        """通用模型更新方法"""
        model = self.sheet_models.get(sheet_index)
        if not model:
            return

        for row_idx, data in enumerate(data_list):
            # 更新数值列
            value_item = QStandardItem(str(data["value"]))
            value_item.setTextAlignment(Qt.AlignCenter)
            model.setItem(row_idx, 1, value_item)

            # 更新16进制列
            hex_item = QStandardItem(hex(data["value"]))
            hex_item.setTextAlignment(Qt.AlignCenter)
            model.setItem(row_idx, 3, hex_item)