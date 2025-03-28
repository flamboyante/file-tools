from PyQt5.QtWidgets import QTableView,QMenu, QFileDialog
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve , Qt# 移动到此位置

from siui.core import SiGlobal, SiColor
from siui.gui.color_group import SiColorGroup

from openpyxl import Workbook
from openpyxl.styles import Alignment
import os



class HkjTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 初始化主题系统
        self.color_group = SiColorGroup(reference=SiGlobal.siui.colors)
        #self.font_group = SiGlobal.siui.fonts

        # 配置动画参数
        self.animation_duration = 300  # 毫秒
        self.setup_ui_style()

        # 初始化右键菜单功能
        self._init_context_menu()
        # 监听主题变化
        #SiGlobal.siui.themeChanged.connect(self.reload_style_sheet)

    def setup_ui_style(self):
        """初始化样式和滚动条"""
        self.setStyleSheet("HkjTableView { border: none; }")
        self.verticalScrollBar().setStyleSheet("""
            QScrollBar:vertical { 
                width: 8px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: %s;
                border-radius: 4px;
            }
        """ % self.color_group.fromToken(SiColor.INTERFACE_BG_D))


    def setModel(self, model):
        """重写模型绑定，添加行高亮动画"""
        super().setModel(model)
        model.rowsInserted.connect(self._on_row_inserted)
        model.rowsRemoved.connect(self._on_row_removed)

    def _on_row_inserted(self, parent, first, last):
        """行插入动画（渐入效果）"""
        for row in range(first, last + 1):
            index = self.model().index(row, 0)
            self._animate_row(index, start_opacity=0.0, end_opacity=1.0)

    def _on_row_removed(self, parent, first, last):
        """行删除动画（渐出效果）"""
        for row in range(first, last + 1):
            index = self.model().index(row, 0)
            self._animate_row(index, start_opacity=1.0, end_opacity=0.0)

    def _animate_row(self, index, start_opacity, end_opacity):
        """行动画逻辑"""
        animation = QPropertyAnimation(self.viewport(), b"opacity")
        animation.setDuration(self.animation_duration)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(start_opacity)
        animation.setEndValue(end_opacity)
        animation.start(QPropertyAnimation.DeleteWhenStopped)

    def reload_style_sheet(self):
        """动态更新样式表以响应主题变化"""
        # 表头样式
        self.horizontalHeader().setStyleSheet("""
               QHeaderView::section {
                   background-color: %s;
                   color: %s;
                   padding: 8px;
                   border-radius: 6px;
               }
           """ % (
            self.color_group.fromToken(SiColor.INTERFACE_BG_D),
            self.color_group.fromToken(SiColor.TEXT_A)
        ))

        # 单元格样式
        self.setStyleSheet("""
               HkjTableView {
                   background-color: %s;
                   alternate-background-color: %s;
                   border-radius: 8px;
               }
               QTableView::item {
                   padding: 8px;
                   border-bottom: 1px solid %s;
               }
           """ % (
            self.color_group.fromToken(SiColor.INTERFACE_BG_B),
            self.color_group.fromToken(SiColor.INTERFACE_BG_C),
            self.color_group.fromToken(SiColor.SIDE_MSG_FLASH)
        ))

    def _init_context_menu(self):
        """初始化右键菜单功能"""
        print("""初始化右键菜单功能""")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)


    def _show_context_menu(self, pos):


        menu = QMenu()
        export_action = menu.addAction("导出为Excel")
        export_action.triggered.connect(self._export_to_excel)
        menu.exec_(self.viewport().mapToGlobal(pos))
    def _export_to_excel(self):
        """使用openpyxl直接导出数据"""
        try:
            model = self.model()
            if not model or model.rowCount() == 0:
                return

            # 创建Workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "Sheet1"

            # 写入表头（带样式）
            headers = []
            for col in range(model.columnCount()):
                header = model.headerData(col, Qt.Horizontal, Qt.DisplayRole) or f"Column {col + 1}"
                headers.append(header)
                cell = ws.cell(row=1, column=col + 1, value=header)
                cell.alignment = Alignment(horizontal='center', vertical='center')

            # 写入数据
            for row in range(model.rowCount()):
                for col in range(model.columnCount()):
                    item = model.item(row, col)
                    value = item.text() if item else ""
                    cell = ws.cell(row=row + 2, column=col + 1, value=value)
                    cell.alignment = Alignment(horizontal='center', vertical='center')

            # 自动调整列宽
            for col in ws.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2) * 1.2
                ws.column_dimensions[column].width = adjusted_width

            # 获取保存路径
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存文件",
                os.path.expanduser("~/Documents/table_export.xlsx"),
                "Excel文件 (*.xlsx)"
            )

            if not file_path:
                return

            # 确保文件后缀
            if not file_path.endswith('.xlsx'):
                file_path += '.xlsx'

            wb.save(file_path)
            print(f"成功导出到：{file_path}")

        except Exception as e:
            print(f"导出失败：{str(e)}")