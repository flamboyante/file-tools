from PyQt5.QtCore import Qt, QAbstractTableModel, pyqtSlot



class HexDataModel(QAbstractTableModel):
    def __init__(self, configs, parent=None):
        super().__init__(parent)
        self.configs = configs
        self.data_map = {}
        self._calc_table_size()

    def _calc_table_size(self):
        self.max_row = max(c.display_row for c in self.configs) + 1
        self.max_col = max(c.display_col for c in self.configs) + 1

    def rowCount(self, parent=None):
        return self.max_row

    def columnCount(self, parent=None):
        return self.max_col

    def data(self, index, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.data_map.get((index.row(), index.column()), "")
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                return f"Col {section + 1}"
            return f"Row {section + 1}"
        return None

    @pyqtSlot(bytes)
    def update_data(self, byte_data):
        self.beginResetModel()
        self.data_map.clear()

        for config in self.configs:
            try:
                if config.bit_offset >= 0:
                    value = self._parse_bit_field(byte_data, config)
                else:
                    byte_len = (config.bit_length + 7) // 8
                    value = int.from_bytes(
                        byte_data[config.start_byte:config.start_byte + byte_len],
                        'big'
                    )

                # 数据类型转换
                if config.dtype == 'bool':
                    value = '✔' if value else '✖'
                elif 'int' in config.dtype:
                    bits = int(config.dtype[3:])
                    if value & (1 << (bits - 1)):
                        value -= (1 << bits)

                self.data_map[(config.display_row, config.display_col)] = str(value)

            except IndexError:
                self.data_map[(config.display_row, config.display_col)] = "ERR"

        self.endResetModel()

