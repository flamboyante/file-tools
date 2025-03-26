import openpyxl
from logging_config import log_print
from openpyxl import Workbook
from openpyxl import load_workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
import  os



class Model_Excel_Task():
    def __init__(self, parent=None):
        self.wb = None
        self.sheet_names = None
        self.fields = []


    def execl_open(self):
        localFilePath = os.path.join(os.getcwd(), '.\\Can_Frame_Deal\\Can.xlsx')
        print(localFilePath)
        self.wb = load_workbook(localFilePath)
        self.wbsheet_names = self.wb.sheetnames
        log_print(self.wbsheet_names)
        return  self.wbsheet_names

    def excel_deal(self,sheet_name):
        ws =None
        try:
            ws = self.wb[sheet_name]  # ws 类型：Worksheet
        except KeyError:
            print(f"Sheet '{sheet_name}' 不存在！")

        # 获取第1行数据
        row_num = 1
        row_cells = ws[row_num]  # 类型：tuple[Cell]
        row_values = [cell.value for cell in row_cells]  # 类型：list[Any]
        row_height = ws.row_dimensions[row_num].height  # 类型：float | None
        #获取第一行多少个元素
        row_len = len(row_values)
        print("row_len is",row_len)
        print(row_values)
        print(row_height)

        col_num = 1
        col_letter = get_column_letter(col_num)  # 类型：str
        col_cells = ws[col_letter]  # 类型：tuple[Cell]
        col_values = [cell.value for cell in col_cells]  # 类型：list[Any]
        col_width = ws.column_dimensions[col_letter].width  # 类型：float | None
        col_len = len(col_values)
        print("col_len is",col_letter)
        print("col_len is",col_len)
        print(col_values)
        print(col_width)

        current_bit = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            print(row)
            try:
                field ={
                    "name": str(row[0]),
                    "bits": int(row[1]),
                    "start_bits" : current_bit,
                }
                self.fields.append(field)
                current_bit += field["bits"]
            except Exception as e:
                log_print("send_file:", e)



        return self.fields ,row_len ,col_len



    def parse_can_data(self, hex_data):
        """
        根据 Excel 中的字段信息解析 CAN 数据
        :param hex_data: 十六进制字符串形式的 CAN 数据
        :return: 解析结果列表
        """
        try:
            log_print("parse_can_datais",hex_data)
            binary_data = bin(int(hex_data.replace(" ", ""), 16))[2:].zfill(len(hex_data.replace(" ", "")) * 4)
            parsed_data = []
            for field in self.fields:
                start = field["start_bits"]
                end = start + field["bits"]
                value = int(binary_data[start:end], 2)
                parsed_data.append({
                    "name": field["name"],
                    "value": value
                })
            log_print("parsed_data is",parsed_data)
            return parsed_data
        except Exception as e:
            log_print(f"parse_can_data 显示数据出错: {str(e)}")








