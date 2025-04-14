
import binascii
import os
import struct
import math
from  logging_config import log_print


class Ycyk_422_Work():

    def __init__(self, parent=None):
        # 初始化文件计数器
        self.file_count = 0
        # 初始化命令计数器
        self.cmd_count = 0
        # 定义帧的大小，单位可能是字节
        self.frame_size = 1000
        # 定义帧的数量
        self.frames = 10
        # 计算总的段大小，等于帧的数量乘以帧大小
        self.segment_size = self.frames * self.frame_size
        # 初始化段计数器
        self.segments = 0
        # 初始化段结束长度
        self.segments_end = 0
        self.segments_end_frames = 0
        self.if_file_divide = 0
        self.file_seg_length = 0
        self.apid = 0
        self.flash = 0

    def check_apid(self, array):
        if self.flash is 0xFA:
            self.apid = 0x1D
        elif self.flash is 0xFF:
            self.apid =0x18
        array[2] = (array[2] & 0b11111000) | ((self.apid >>4) & 0b00001111)
        array[3] = (array[3] & 0b00001111) | (self.apid & 0b00001111) << 4

    def binary_print_hex(self, byte_array):
        hex_array = binascii.hexlify(byte_array)
        for i in range(0, len(hex_array), 2):
            pass
            #print("0x"+hex_array[i:i+2].decode('utf8')+" ")
            #if (i%16)==14:
                #print("\n\r")
        #print('')

    def calculate_crc16_ccitt_false_with_binary(self, file_path):
        """计算文件的CRC16-CCITT-FALSE校验和"""
        crc_value = 0xFFFF
        with open(file_path, 'rb') as file:
            chunk = file.read(1024)  # 分块读取，这里使用1KB的块大小
            while chunk:
                crc_value = binascii.crc_hqx(chunk, crc_value)
                chunk = file.read(1024)
        return crc_value

    def reverse_accumulate(self, byte_stream):
        """计算bytearray的和校验值"""
        checksum = 0
        for i in range(2, len(byte_stream)):  # 从索引2开始遍历
            checksum += byte_stream[i]
            #log_print("calculate_checksum_sum ", i, hex(byte_stream[i]), hex(checksum))
        # 将累加和转换为16位整数，并取反
        checksum = (~checksum) & 0xFFFF
        return checksum

    def reverse_accumulate_error(self, byte_stream):
        accumulator = 0
        for i in range(2, len(byte_stream)):
            accumulator ^= byte_stream[i]
            #log_print("reverse_accumulate ",i,hex(byte_stream[i]),hex(accumulator))
        accumulator = (~accumulator) & 0xFFFF
        return accumulator

    def Int_to_bytes_struct(self, int_num, len):
        #log_print(int_num,len)
        if len == 1:
            byte_stream = struct.pack('>B',int_num)
            return byte_stream
        if len == 2:
            byte_stream = struct.pack('>H',(int_num))
            return byte_stream
        if len == 4:
            byte_stream = struct.pack('>I',int_num)
            return byte_stream

    def refactor_begin(self, flash, mem):
        self.flash = flash
        begin_array = bytearray(
            [0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x03, 0x01, 0xAF])
        if self.cmd_count > 0x3fff:
            self.cmd_count = 0
        begin_array[4] &= ~0x3f
        begin_array[4] |= (self.cmd_count >> 8 & 0x3f)
        begin_array[5] &= ~0xff
        begin_array[5] |= (self.cmd_count & 0xff)

        self.check_apid(begin_array)


        self.cmd_count += 1
        flash_byte = self.Int_to_bytes_struct(flash, 1)
        begin_array.extend(flash_byte)
        log_print(flash_byte)
        mem_type = self.Int_to_bytes_struct(mem, 1)
        begin_array.extend(mem_type)
        accumulator = self.reverse_accumulate(begin_array)
        log_print("reverse_accumulate，accumulator :", hex(accumulator))

        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        begin_array.extend(accumulator_byte)
        self.binary_print_hex(begin_array)
        return begin_array

    def get_frame_segment(self, file_length_all):
        self.segments = int(file_length_all / self.segment_size)
        self.segments_end = file_length_all % self.segment_size

        if self.segments_end != 0:
            self.segments += 1
            self.segments_end_frames = int(self.segments_end / self.frame_size)
            if (self.segments_end % self.frame_size) != 0:
                self.segments_end_frames += 1
        else:
            self.segments_end_frames = self.frames

        if self.segments is 1:
            log_print("一次发送")
            self.if_file_divide = 0
            self.file_seg_length = file_length_all
        elif self.segments is 0:
            log_print("file error")
        else:
            log_print("多次发送")
            self.if_file_divide = 0b11
            self.file_seg_length = self.segment_size

    def Send_begin(self, file_path, flash, mem):
        self.flash = flash
        file_length_all = os.path.getsize(file_path)
        self.get_frame_segment(file_length_all)
        begin_array = bytearray([0xEB, 0x90, 0x01, 0x80, 0xC0, 0x01, 0x00, 0x10, 0x01, 0x55, 0x18])
        if self.cmd_count > 0x3fff:
            self.cmd_count = 0
        begin_array[4] &= ~0x3f
        begin_array[4] |= (self.cmd_count >> 8 & 0x3f)
        begin_array[5] &= ~0xff
        begin_array[5] |= (self.cmd_count & 0xff)
        self.check_apid(begin_array)


        self.cmd_count += 1



        flash_byte = self.Int_to_bytes_struct(flash, 1)
        begin_array.extend(flash_byte)

        mem_type = self.Int_to_bytes_struct(mem, 1)
        begin_array.extend(mem_type)


        log_print("segments_end: ",self.segments_end, "hex:", hex(self.segments_end))

        combine_file_devide = self.if_file_divide << 14 | self.segments
        combine_file_devide_byte = self.Int_to_bytes_struct(combine_file_devide, 2)
        # log_print("file_seg  ",is_segment ,"hex:" ,hex(is_segment))
        # log_print("combine_file_devide  ",combine_file_devide,"hex:" , hex(combine_file_devide))
        # self.binary_print_hex(combine_file_devide_byte)
        begin_array.extend(combine_file_devide_byte)

        file_seg_length_byte = self.Int_to_bytes_struct(self.file_seg_length, 4)
        segments_end_byte = self.Int_to_bytes_struct(self.segments_end, 4)

        begin_array.extend(file_seg_length_byte)
        begin_array.extend(segments_end_byte)

        # Bytes_RCRK_FILE_BEGIN
        crc_return = self.calculate_crc16_ccitt_false_with_binary(file_path)
        #log_print("hex crc16: ", hex(crc_return))
        crc_byte = self.Int_to_bytes_struct(crc_return, 2)
        begin_array.extend(crc_byte)

        # binary_print_hex(begin_array)
        accumulator = self.reverse_accumulate(begin_array)
        log_print("reverse_accumulate，accumulator :", hex(accumulator))

        accumulator_byte =self. Int_to_bytes_struct(accumulator, 2)
        begin_array.extend(accumulator_byte)

        log_print("begin array :", begin_array)
        self.binary_print_hex(begin_array)
        return begin_array

    def SerialFile_Once(self,filename):
        # 读取文件并转换为字节流
        with open(filename, 'rb') as f:
            file_data = f.read()
            log_print(filename, "file data :", file_data)
            return file_data

    def Send_datas(self, seg, group_flag, file_data):
        if self.file_count > 0x3fff:
            self.file_count = 0
        file_len = len(file_data)
        packet_len = 2 + file_len - 1
        packet_len_byte = self.Int_to_bytes_struct(packet_len, 2)
        rcrk_data = seg
        rcrk_data_byte = self.Int_to_bytes_struct(rcrk_data, 2)
        data_array = bytearray([0xEB, 0x90, 0x01, 0x8f, 0xC0, 0x00])
        data_array[4] &= ~0xC0
        data_array[4] |= group_flag << 6
        data_array[4] &= ~0x3f
        data_array[4] |= (self.file_count >> 8 & 0x3f)
        data_array[5] &= ~0xff
        data_array[5] |= (self.file_count & 0xff)
        self.check_apid(data_array)

        data_array.extend(packet_len_byte)
        data_array.extend(rcrk_data_byte)
        data_array.extend(file_data)

        accumulator = self.reverse_accumulate(data_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        data_array.extend(accumulator_byte)

        #log_print("times :", times, "data_send :", data_array)
        #binary_print_hex(data_array)
        #ser.write(data_array)
        return data_array

    def send_heart(self):
        begin_array = bytearray([0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x01, 0x00, 0x1d])
        accumulator = self.reverse_accumulate(begin_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        begin_array.extend(accumulator_byte)
        self.binary_print_hex(begin_array)
        return begin_array

    def get_refactor_result(self):
        begin_array = bytearray([0xEB, 0x90, 0x01, 0x80, 0xC0, 0x00, 0x00, 0x01, 0x01, 0xC5])
        if self.cmd_count > 0x3fff:
            self.cmd_count = 0
        begin_array[4] &= ~0x3f
        begin_array[4] |= (self.cmd_count >> 8 & 0x3f)
        begin_array[5] &= ~0xff
        begin_array[5] |= (self.cmd_count & 0xff)
        self.check_apid(begin_array)

        self.cmd_count += 1

        accumulator = self.reverse_accumulate(begin_array)
        log_print("reverse_accumulate，accumulator :", hex(accumulator))

        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        begin_array.extend(accumulator_byte)
        self.binary_print_hex(begin_array)
        return begin_array

    def Send_Finish(self):
        # 基带
        # data_array = bytearray([0xEB, 0x90, 0x01, 0x85, 0xC0, 0x00])
        # KA tx
        #finish_array = bytearray([0xEB, 0x90, 0x02, 0x10, 0xC0, 0x02])
        # KA tx
        finish_array = bytearray([0xEB, 0x90, 0x01, 0x80, 0xC0, 0x01])
        if self.cmd_count > 0x3fff:
            self.cmd_count = 0
        finish_array[4] &= ~0x3f
        finish_array[4] |= (self.cmd_count >> 8 & 0x3f)
        finish_array[5] &= ~0xff
        finish_array[5] |= (self.cmd_count & 0xff)
        self.check_apid(finish_array)

        self.cmd_count += 1
        rcrk_finish = 0x01AA
        rcrk_finish_byte = self.Int_to_bytes_struct(rcrk_finish, 2)
        packet_len = 0x01
        packet_len_byte = self.Int_to_bytes_struct(packet_len, 2)
        finish_array.extend(packet_len_byte)
        finish_array.extend(rcrk_finish_byte)

        accumulator = self.reverse_accumulate(finish_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        finish_array.extend(accumulator_byte)

        log_print("send finish :", finish_array)
        self.binary_print_hex(finish_array)

        return finish_array

    def Send_Reboot(self):
        reboot_array = bytearray([0xEB, 0x90, 0x01, 0x80, 0XC0, 0x00])
        if self.cmd_count > 0x3fff:
            self.cmd_count = 0
        reboot_array[4] &= ~0x3f
        reboot_array[4] |= (self.cmd_count >> 8 & 0x3f)
        reboot_array[5] &= ~0xff
        reboot_array[5] |= (self.cmd_count & 0xff)
        self.check_apid(reboot_array)

        self.cmd_count += 1
        rcrk_finish = 0x001A
        rcrk_finish_byte = self.Int_to_bytes_struct(rcrk_finish, 2)
        packet_len = 0x01
        packet_len_byte = self.Int_to_bytes_struct(packet_len, 2)
        reboot_array.extend(packet_len_byte)
        reboot_array.extend(rcrk_finish_byte)

        accumulator = self.reverse_accumulate(reboot_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        reboot_array.extend(accumulator_byte)

        log_print("reboot array 1 :", reboot_array)
        self.binary_print_hex(reboot_array)
        return reboot_array

    def Send_VersionCheck(self):
        Version_array = bytearray([0xEB, 0x90, 0x01, 0x80, 0XC0, 0x00])
        if self.cmd_count > 0x3fff:
            self.cmd_count = 0
        Version_array[4] &= ~0x3f
        Version_array[4] |= (self.cmd_count >> 8 & 0x3f)
        Version_array[5] &= ~0xff
        Version_array[5] |= (self.cmd_count & 0xff)
        self.check_apid(Version_array)

        self.cmd_count += 1
        IRcode = 0x0101
        IRcode_byte = self.Int_to_bytes_struct(IRcode, 2)
        packet_len = 0x01
        packet_len_byte = self.Int_to_bytes_struct(packet_len, 2)
        Version_array.extend(packet_len_byte)
        Version_array.extend(IRcode_byte)

        accumulator = self.reverse_accumulate(Version_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        Version_array.extend(accumulator_byte)

        log_print("reboot array 1 :", Version_array)
        self.binary_print_hex(Version_array)
        return Version_array

    def send_ftp_start(self):
        reboot_array = bytearray([0xEB, 0x90, 0x01, 0x80, 0XC0, 0x00])
        if self.cmd_count > 0x3fff:
            self.cmd_count = 0
        reboot_array[4] &= ~0x3f
        reboot_array[4] |= (self.cmd_count >> 8 & 0x3f)
        reboot_array[5] &= ~0xff
        reboot_array[5] |= (self.cmd_count & 0xff)
        self.check_apid(reboot_array)

        self.cmd_count += 1
        rcrk_finish = 0x001A
        rcrk_finish_byte = self.Int_to_bytes_struct(rcrk_finish, 2)
        packet_len = 0x01
        packet_len_byte = self.Int_to_bytes_struct(packet_len, 2)
        reboot_array.extend(packet_len_byte)
        reboot_array.extend(rcrk_finish_byte)

        accumulator = self.reverse_accumulate(reboot_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        reboot_array.extend(accumulator_byte)

        log_print("reboot array 1 :", reboot_array)
        self.binary_print_hex(reboot_array)
        return reboot_array

    def Send_stars_info(self):

        stars_array1 = bytearray([0xEB, 0x90, 0x01, 0x85, 0x01, 0xC0, 0x00,0x3B,
                                0x00, 0x01, 0x12, 0x34, 0x56, 0x78, 0x00, 0x00, 0x00,0x11,0x55,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x11, 0x11, 0x11, 0x11,
                                0x12, 0x13, 0x14, 0x15])
        stars_array2 = bytearray([0xEB, 0x90, 0x02, 0x10, 0xC0,0x01, 0x00, 0x3B,
                                  0x00, 0x01, 0x12, 0x34, 0x56, 0x78, 0x00, 0x00, 0x00, 0x11, 0x55,
                                  0x00, 0x01, 0x11, 0x11,
                                  0x00, 0x02, 0x11, 0x11,
                                  0x00, 0x03, 0x11, 0x11,
                                  0x00, 0x04, 0x11, 0x11,
                                  0x00, 0x05, 0x11, 0x11,
                                  0x00, 0x06, 0x11, 0x11,
                                  0x00, 0x00, 0x07, 0x11,0x11,
                                  0x00, 0x08, 0x11,
                                  0x00, 0x09, 0x11, 0x11,
                                  0x00, 0x10, 0x11, 0x11,
                                  0x00, 0x11, 0x11, 0x11,
                                  0x00, 0x12, 0x11, 0x11])
        stars_array = bytearray([0xEB, 0x90, 0x02, 0x60, 0xC0, 0x01, 0x00, 0x3B,
                                  0x00, 0x01, 0x12, 0x34, 0x56, 0x78, 0x00, 0x00, 0x00, 0x11, 0x55,
                                  0x00, 0x01, 0x11, 0x11,
                                  0x00, 0x02, 0x11, 0x11,
                                  0x00, 0x03, 0x11, 0x11,
                                  0x00, 0x04, 0x11, 0x11,
                                  0x00, 0x05, 0x11, 0x11,
                                  0x00, 0x06, 0x11, 0x11,
                                  0x00, 0x00, 0x07, 0x11, 0x11,
                                  0x00, 0x08, 0x11,
                                  0x00, 0x09, 0x11, 0x11,
                                  0x00, 0x10, 0x11, 0x11,
                                  0x00, 0x11, 0x11, 0x11,
                                  0x00, 0x12, 0x11, 0x11])
        accumulator = self.reverse_accumulate(stars_array)
        accumulator_byte = self.Int_to_bytes_struct(accumulator, 2)
        stars_array.extend(accumulator_byte)

        log_print("send array 1 :", stars_array)
        self.binary_print_hex(stars_array)
        return stars_array









