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
        self.sheet_fields = {}
        self.wbsheet_names = None


    def execl_open(self):
        localFilePath = os.path.join(os.getcwd(), '.\\Can_Frame_Deal\\Can.xlsx')
        print(localFilePath)
        self.wb = load_workbook(localFilePath)
        self.wbsheet_names = self.wb.sheetnames



        log_print(self.wbsheet_names)
        #输出 wbsheet_names个数
        log_print(len(self.wbsheet_names))
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
        localfields = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            #print("excel_deal row is",row)
            try:
                field ={
                    "name": str(row[0]),
                    "bits": int(row[1]),
                    "start_bits" : current_bit,
                    "shell" :str(row[2])
                }
                localfields.append(field)
                current_bit += field["bits"]
            except Exception as e:
                log_print("send_file:", e)

        #保存localfields到sheet_fields中
        self.sheet_fields[sheet_name] = localfields

        return localfields ,row_len ,col_len



    def parse_can_data(self, data_str,name):

        #根据 Excel 中的字段信息解析 CAN 数据
        #:param hex_data: 十六进制字符串形式的 CAN 数据
        #:return: 解析结果列表
        flag = 0
        slot = 0
        sheet_slot = 0
        sheet_slot_name = None
        try:
            log_print("parse_can_data : parse_can_datas",type(data_str),data_str)
            data_hex = list(bytes.fromhex(data_str))  # 返回的是bytes对象，用list()转为列表
            log_print("parse_can_data :data_hex:", type(data_hex), data_hex)
            if(name == "woshishabi"):
                #for i in range(len(data_hex)):
                #    log_print("data_hex[i] is",i,"--",data_hex[i])
                log_print("woshishabi")
                log_print("ID is",data_hex[78] << 8 | data_hex[79])
                log_print("slot is" , data_hex[82])
                slot = data_hex[82] # 自动获取slot值
                if slot > 9:
                    sheet_slot = slot
                else:
                    sheet_slot = slot + 2
                sheet_slot_name = self.wbsheet_names[sheet_slot]
                log_print("sheet_slot is ",sheet_slot)
                flag = 1  # 自动激活二次解析
                log_print("self.wbsheet_names[slot]",self.wbsheet_names[sheet_slot])

            # 第一阶段：主解析表
            binary_data = bin(int(data_str.replace(" ", ""), 16))[2:].zfill(len(data_str.replace(" ", "")) * 4)
            parsed_data = []
            total_bits = len(binary_data)
            parsed_bits = 0
            parsed_bits_back = 0
            for field in self.sheet_fields[name]:
                start = field["start_bits"]
                end = start + field["bits"]
                value = int(binary_data[start:end], 2)
                parsed_data.append({
                    "name": field["name"],
                    "value": value,
                })
                log_print(f"主表 解析字段 {field['name']}，值：{value}","start bit - end bit ",start,end)
                parsed_bits = end  # 记录解析进度
            log_print("最终主表parsed_bits:", parsed_bits)
            log_print("最终主表解析数据:", parsed_data)
                # 第二阶段：条件解析
            if flag == 1 and sheet_slot_name and sheet_slot_name in self.sheet_fields:
                parsed_data_back = []
                remaining_bits = total_bits - parsed_bits
                parsed_bits_back = parsed_bits
                log_print(f"开始二次解析，剩余位数：{remaining_bits}，使用表：{sheet_slot_name}")
                for field in self.sheet_fields[sheet_slot_name]:
                    start2 = parsed_bits + field["start_bits"]
                    end2 = start2 + field["bits"]

                    if end2 > total_bits:
                        log_print(f"字段 {field['name']} 超出数据范围，终止解析","total_bits is ",total_bits)
                        break

                    value = int(binary_data[start2:end2], 2)
                    parsed_data_back.append({
                        "name": f"{sheet_slot_name}.{field['name']}",  # 添加命名空间
                        "value": value,
                    })
                    log_print(f"副表 解析字段 {field['name']}，值：{value}","start bit - end bit -bits ",start2,end2 ,field["bits"])
                    parsed_bits_back = end2
                log_print("最终副表parsed_bits:", parsed_bits_back)
                log_print("最终副表解析bit:", parsed_bits_back - parsed_bits)
                log_print("最终副表解析数据:", parsed_data_back)
                return parsed_data ,parsed_data_back,sheet_slot

            log_print("最终解析数据:", parsed_data)
            return parsed_data , None ,0

        except Exception as e:
            log_print(f"解析错误: {str(e)}")
            return []




"""
            binary_data = bin(int(data_str.replace(" ", ""), 16))[2:].zfill(len(data_str.replace(" ", "")) * 4)
            parsed_data = []
            for field in self.sheet_fields[name]:
                start = field["start_bits"]
                end = start + field["bits"]
                value = int(binary_data[start:end], 2)
                #print("start is",start , "end is",end, "value is",value,"hex value is",hex(value))
                parsed_data.append({
                    "name": field["name"],
                    "value": value,
                })
            log_print("parsed_data is",parsed_data)
            return parsed_data
        except Exception as e:
            log_print(f"parse_can_data 显示数据出错: {str(e)}")
"""








