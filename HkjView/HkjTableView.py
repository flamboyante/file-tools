from PyQt5.QtWidgets import QTableView
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve  # 移动到此位置
from siui.core import SiGlobal, SiColor, Si
from siui.gui.color_group import SiColorGroup
from siui.gui import SiFont



class HkjTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)

        # 初始化主题系统
        self.color_group = SiColorGroup(reference=SiGlobal.siui.colors)
        #self.font_group = SiGlobal.siui.fonts

        # 配置动画参数
        self.animation_duration = 300  # 毫秒
        self.setup_ui_style()

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