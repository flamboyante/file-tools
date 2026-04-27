import binascii
import threading
import os
import traceback
from sys import argv

from PyQt5.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition, QTimer
from Media.Media import Media, MediaType
from Media.SerialMedia import SerialMedia
from Media.EthernetMedia import EthernetMedia
from Media.VlanMedia import VlanMedia
from ycyk_422 import Ycyk_422_Work
from logging_config import  log_print
import serial
import time


begin_array_test = bytearray([0xEB ,0x90])
class Serial_Worker(QThread):
    Sign_Serial_init = pyqtSignal(MediaType, str, int, int, str, str)
    show_error_signal = pyqtSignal(str)
    serial_flag_signal = pyqtSignal(int)
   # send_data_signal = pyqtSignal(bytes)
    # 定义信号，用于通知主线程发送数据

    def __init__(self, parent=None):
        super(Serial_Worker, self).__init__(parent)
        log_print("Serial_Worker init thread id is ", threading.currentThread().ident)
        # self.Sign_Serial_init.connect(self.Slot_Serial_init)  # 连接信号和槽
        #self.send_data_signal.connect(self.send_data_slot)
        self.status = 0
        self.ser = None
        self.media = None
        self.serial_reader_thread = None

        # 创建定时器用于发送心跳检测帧
        self.heart_timer = QTimer()
        self.heart_timer.timeout.connect(self.check_heart)

        # self.mutex = QMutex()  # 创建互斥锁

    # 初始化通信介质
    def init_media(self, type, *args):
        log_print("在工作线程中接收到的数据：", type, *args)
        log_print("Slot_Serial_init thread id is ", threading.currentThread().ident)

        try:
            if type == MediaType.SERIAL:
                self.slot_serial_init(args[0], args[1], args[2], args[3], args[4])
            elif type == MediaType.ETHERNET:
                self.slot_ethernet_init('', args[0], args[1])
            else:
                self.slot_vlan_init('', args[0], args[1], args[2], args[3], args[4])

            self.media.open()
            if self.media.is_open:
                self.heart_timer.start(3000)
                log_print("接口已打开")
                self.serial_flag_signal.emit(1)
                self.status = 1
                # self.start_serial_reader_thread()
            else:
                log_print("接口未打开")
                self.serial_flag_signal.emit(0)
                self.status = 0
        except Exception as e:
            log_print(f"接口打开异常：{e}")
            self.show_error_signal.emit(str(e))
            self.status = 0

    # 以太网接口初始化
    def slot_ethernet_init(self, ver: str, ip: str, port: int):
        try:
            self.media = EthernetMedia(ip, port)
        except Exception:
            raise

    def slot_vlan_init(self, ver: str, ip: str, port: int, vlan_id: int, des_mac: str, iface: str):
        try:
            self.media = VlanMedia(ip, port, vlan_id, des_mac, "以太网")
        except Exception:
            raise

    # 串口初始化
    def slot_serial_init(self, com_port, baud_rate, data_bits, stop_bits, parity_check):
        log_print("在工作线程中接收到的数据：", com_port, baud_rate, data_bits, stop_bits, parity_check)

        serial_dict = {'NONE': serial.PARITY_NONE, 'EVEN': serial.PARITY_EVEN, 'ODD': serial.PARITY_ODD,
                       '1': serial.STOPBITS_ONE, '2': serial.STOPBITS_TWO, '1.5': serial.STOPBITS_ONE_POINT_FIVE}

        try:
            parity = serial_dict.get(parity_check)
            if parity is None:
                raise ValueError("Invalid parity check value")
            stop_bit = serial_dict.get(stop_bits)
            if stop_bit is None:
                raise ValueError("Invalid stop bits value")
            self.media = SerialMedia(com_port, baud_rate, data_bits, stop_bit, parity)
        except Exception:
            raise

        # # 在这里实现串行初始化的代码
        # try:
        #     # 根据校验位参数设置正确的校验模式
        #     if parity_check == 'NONE':
        #         parity = serial.PARITY_NONE
        #     elif parity_check == 'EVEN':
        #         parity = serial.PARITY_EVEN
        #     elif parity_check == 'ODD':
        #         parity = serial.PARITY_ODD
        #     else:
        #         raise ValueError("Invalid parity check value")
        #     print("parity_check", parity_check, parity)
        #     # 根据停止位参数设置正确的停止位
        #     if stop_bits == '1':
        #         stopbit = serial.STOPBITS_ONE
        #     elif stop_bits == '2':
        #         stopbit = serial.STOPBITS_TWO
        #     elif stop_bits =='1.5':
        #         stopbit =serial.STOPBITS_ONE_POINT_FIVE
        #     else:
        #         raise ValueError("Invalid stop bits value")
        #
        #     self.media = SerialMedia(com_port, baud_rate, data_bits, stopbit, parity)
        #
        #     log_print("串口已打开")
        # except serial.SerialException as e:
        #     raise
        # except ValueError as e:
        #     raise

    def close_serial(self):
        log_print("Close_serial  thread id is ", threading.currentThread().ident)
        try:
            if self.media.is_open:
                log_print("close ing ")
                self.media.close()
                self.heart_timer.stop()
                self.serial_flag_signal.emit(0)  # 发送串口已关闭的信号
                self.status = 0
                log_print("串口已关闭")
                if self.serial_reader_thread and self.serial_reader_thread.isRunning():
                    self.serial_reader_thread.stop()
            else:
                log_print("error")
        except Exception as e:
            log_print(f"接口关闭异常：{e}")

        # if self.ser and self.ser.is_open:
        # if self.ser.is_open:
        #     log_print("close ing ")
        #     self.serial_flag_signal.emit(0)  # 发送串口已关闭的信号
        #     self.status = 0
        #     log_print("串口已关闭")
        #     if self.serial_reader_thread and self.serial_reader_thread.isRunning():
        #         self.serial_reader_thread.stop()
        #     self.ser.close()
        #
        # else:
        #     log_print("error")

    def send_data_slot(self, data):
        log_print("send_data_slot  thread id is ", threading.currentThread().ident)
        log_print(data)
        # 发送数据到串行端口
        self.media.write(data)

    def receive_data_slot(self, data):
        log_print("receive_data_slot  thread id is ", threading.currentThread().ident)
        log_print(data)
        # 发送数据到串行端口
        self.receive_data_signal.emit(data)

    def check_heart(self):
        pass


class FileTransfer_Work(QThread):

    file_start_signal = pyqtSignal(str, int, int, bool,int, int)
    file_processe_signal = pyqtSignal(int)
    file_complete_signal = pyqtSignal()
    file_log_signal = pyqtSignal(str)
    file_exception_signal = pyqtSignal(Exception, str)   # 程序执行异常时的信号

    def __init__(self, serial_worker, parent=None):
        super(FileTransfer_Work, self).__init__(parent)  # 调用超类的构造函
        log_print("FileTransfer_Worker init  thread id is ", threading.currentThread().ident)
        self.serial_worker = serial_worker
        self.transferredSize = 0
        self.paused = False
        #传输相关设置
        self.LengthRecv = 13
        self.frame_resp = 0
        self.running = True
        self.Ycyk_422_Worker = Ycyk_422_Work(id=0xEB90)
        self.number = 0

    def file_start_slot(self, file_path, flash, mem, divide, frame_len, frame_num):
        log_print("transfer_file  thread id is ", threading.currentThread().ident)
        log_print(file_path)

        # 发送文件
        try:
            if divide is True:
                self.send_begin_frame(file_path, flash, mem, 0x03, frame_len, frame_num)  # 头帧a
            else:
                self.send_begin_frame(file_path, flash, mem, 0x00, frame_len, frame_num)  # 头帧a
            log_print("send_begin_frame Validation Pass, divide: " + str(divide) + ", length: " + str(frame_len) + ", number: " + str(frame_num))
        except ValueError as e:
            log_print("send_begin_frame ValueError occurred:", e)
            self.file_exception_signal.emit(e, traceback.format_exc())
            return

        try:
            self.send_file(file_path)   # 发送文件
            log_print("send_file Validation Pass !")
        except Exception as e:
            log_print("send_file:", e)
            self.file_exception_signal.emit(e, traceback.format_exc())

        try:
            self.send_finish_frame()    # 文件发送结束帧
            log_print("send_finish_frame Validation Pass !")
        except ValueError as e:
            log_print("ValueEroor occurred:", e)
            self.file_exception_signal.emit(e, traceback.format_exc())
        '''
        try:
            self.send_get_refactor_result_frame()
            log_print("send_get_refactor_result_frame Validation Pass !")
        except Exception as e:
            log_print(e)
        '''
        try:
            self.send_refactor_begin_frame(flash, mem)  # 发送开始重构帧
            log_print("send_refactor_begin_frame Validation Pass !")
        except Exception as e:
            log_print(e)
            self.file_exception_signal.emit(e, traceback.format_exc())

        log_print("FileTransfer_Work is success!!!!!!!")

    def validate_response1(self):
        # 定义期望读取的字节数
        expected_length = 13

        # 定义一个变量来存储接收到的数据
        response = b''
        try:
            response = self.serial_worker.media.recv(self.LengthRecv)
        except Exception as e:
            log_print("validate_response1 is ",e)
            raise
        self.Ycyk_422_Worker.binary_print_hex(response)
        response_hex = response.hex(' ')
        self.file_log_signal.emit(f'response: {response_hex}')
        log_print('response:', response_hex)

        type_code = response[9]  # 假设错误代码在第12个字节
        if type_code == 0x5A:
            log_print("文件传输开始应答:", response)
        elif type_code == 0xBB:
            log_print("文件传输结束应答", response)
            #self.Ycyk_422_Worker.binary_print_hex(response)
        elif type_code == 0x8A:
            log_print("文件传输应答", response)
        elif type_code == 0xCA:
            log_print("重构结果查询应答", response)
        else:
            log_print("指令错误", response)
        # 检查第11字节是否是0x00
        if response[10] == 0x00:
            log_print("校验通过,", response[10], "参数正常")
        elif response[10] == 0xFF:
            # 如果是0xFF，根据后续字节的不同，抛出不同类型的异常
            type_code = response[9]  # 假设错误代码在第10个字节
            if type_code == 0x5A:
                raise ValueError("文件传输开始 - 异常，不能开始文件重构.")
            elif type_code == 0xBB:
                raise ValueError("文件传输结束应答 - 重构异常.")
            elif type_code == 0x8A:
                raise ValueError("文件传输应答 - 接收异常")
            elif type_code == 0xCA:
                raise ValueError("重构结果查询应答 - 重构结果异常")
            else:
                raise ValueError("An unknown error with code 0xFF occurred.")
        elif response[10] == 0x11:
            raise ValueError("文件传输结束应答 - CRC重构异常.")
        else:
            # 如果第11个字节既不是0x00也不是0xFF，抛出一个通用的异常
            raise ValueError("Invalid response: The 11th byte is neither 0x00 nor 0xFF.")

    def send_get_refactor_result_frame(self):
        try:
            get_refactor_result_frame_bytes = self.Ycyk_422_Worker.get_refactor_result()
            self.serial_worker.media.send(get_refactor_result_frame_bytes)
            get_refactor_result_frame_hex = get_refactor_result_frame_bytes.hex(' ')
            self.file_log_signal.emit(f'send get refactor result frame: {get_refactor_result_frame_hex}')
            log_print(get_refactor_result_frame_hex)
            log_print("send_get_refactor_result_frame transfer completed.")
            time.sleep(0.1)
            self.validate_response1()
        except Exception as e:
            log_print('send_get_refactor_result_frame:', e)

    # 发送开始重构帧
    def send_refactor_begin_frame(self, flash, mem):
        try:
            refactor_begin_frame_byte = self.Ycyk_422_Worker.refactor_begin(0x18, flash, mem)
            refactor_begin_frame_hex = refactor_begin_frame_byte.hex(' ')
            self.file_log_signal.emit(f'send begin frame: {refactor_begin_frame_hex}')
            log_print(refactor_begin_frame_hex)
            self.serial_worker.media.send(refactor_begin_frame_byte)
            log_print("refactor_begin_frame_byte transfer completed.")
        except Exception as e:
            log_print('send_refactor_begin_frame:', e)
            raise

    # 发送开始帧
    def send_begin_frame(self, file_path, flash, mem, divide, frame_len, frame_num):
        try:
            send_begin_frame_byte = self.Ycyk_422_Worker.send_begin(0x18, file_path, flash, mem, divide, frame_len, frame_num)
            self.serial_worker.media.send(send_begin_frame_byte)
            send_begin_frame_hex = send_begin_frame_byte.hex(' ')
            self.file_log_signal.emit(f'send begin frame: {send_begin_frame_hex}')
            log_print(send_begin_frame_hex)
            log_print("send_begin_frame transfer completed.")
            self.validate_response1()
            time.sleep(1)
        except Exception as e:
            log_print('send_begin_frame:', e)
            raise

    # 发送文件
    def send_file(self, file_path):
        t_begin = time.time()
        self.transferredSize = 0
        with open(file_path, 'rb') as f:
            for i in range(self.Ycyk_422_Worker.segments):
                log_print("##################开始", i + 1," / ",self.Ycyk_422_Worker.segments ,"段发送###################")
                t1 = time.time()
                try:
                    self.send_file_segment(f, i)
                except Exception as e:
                    raise
                t2 = time.time()
                log_print("此段时间：", t2 - t1)
                log_print("##################完成", i + 1, " / ", self.Ycyk_422_Worker.segments, "段###################")
                self.file_log_signal.emit(f'section: [{i + 1}/{self.Ycyk_422_Worker.segments}], time: {round((t2 - t1), 2)}s')
                #time.sleep(100)
        t_end = time.time()
        log_print("-----------------------", (t_end - t_begin), "okkkkkkkkkkkkkkkkkkkkkkk---------------")
        self.file_log_signal.emit(f'file send finish, time: {round((t_end - t_begin), 2)}s')

    # 发送一段数据
    def send_file_segment(self, f, seg):
        for i in range(self.Ycyk_422_Worker.frames):

            # 阻塞线程
            while self.running is False:
                self.msleep(1)

            len = self.send_file_frame(f, seg, i)
            if len == 0:
                break

            try:
                self.validate_response1()
            except Exception as e:
                log_print('send_file error:', e)
                raise
            # self.Ycyk_422_Worker.file_count += 1
            self.transferredSize += len
            # time.sleep(0.1)
            self.file_processe_signal.emit(self.transferredSize)
            log_print("send_file_frame_byte transfer times is ", i, "/", self.Ycyk_422_Worker.frames - 1, f', len: {len}')
        # self.file_processe_signal.emit(self.transferredSize)

    # 发送一帧数据
    def send_file_frame(self, f, segment, frame):
        file_data = f.read(self.Ycyk_422_Worker.frame_size)
        if not file_data:
            log_print("file end")
            return 0

        if self.Ycyk_422_Worker.frames is 1:  # 每段只有一帧数据
            send_file_frame_byte = self.Ycyk_422_Worker.send_datas(0x18, segment, 3, file_data)
        else:
            if segment == self.Ycyk_422_Worker.segments - 1:
                frames = self.Ycyk_422_Worker.segments_end_frames
            else:
                frames = self.Ycyk_422_Worker.frames

            if frames == 1:
                send_file_frame_byte = self.Ycyk_422_Worker.send_datas(0x18, segment, 3, file_data)
            else:
                if frame is 0:  # 首帧
                    send_file_frame_byte = self.Ycyk_422_Worker.send_datas(0x18, segment, 1, file_data)

                elif frame == frames - 1:  # 最后一帧
                    send_file_frame_byte = self.Ycyk_422_Worker.send_datas(0x18, segment, 2, file_data)
                else:  # 中间帧
                    send_file_frame_byte = self.Ycyk_422_Worker.send_datas(0x18, segment, 0, file_data)
            first_20_bytes = send_file_frame_byte[:20]
            first_20_hex = first_20_bytes.hex(' ')
            log_print(first_20_hex)
            self.file_log_signal.emit(f'20 bytes of first frame: {first_20_hex}')

        return self.serial_worker.media.send(send_file_frame_byte)

    def send_finish_frame(self):
        try:
            send_finish_frame_byte = self.Ycyk_422_Worker.send_finish(0x18)
            self.serial_worker.media.send(send_finish_frame_byte)
            log_print("send_finish_frame transfer completed.")
            send_finish_frame_hex = send_finish_frame_byte.hex(' ')
            self.file_log_signal.emit(f'send begin frame: {send_finish_frame_hex}')
            log_print('send_finish_frame:', send_finish_frame_hex)

            self.validate_response1()

            # self.serial_worker.change_baud_rate(115200)
            log_print("transfer completed!!!!!!!!!!!!!!!!!!!!!!!!")

            self.file_complete_signal.emit()
        except Exception as e:
            log_print('send_finish_frame:', e)
            raise

    def send_pause(self):
        self.running = False

    def send_resume(self):
        self.running = True

"""type_code = response[9]  # 假设错误代码在第12个字节
        if type_code == 0x5A:
            log_print("文件传输开始应答:", response)
        elif type_code == 0xBB:
            log_print("文件传输结束应答", response)
        elif type_code == 0x8A:
            log_print("文件传输应答", response)
        else:
            log_print("错误", self.Ycyk_422_Worker.binary_print_hex(response))
        # 检查第11字节是否是0x00
        if response[10] == 0x00:
            log_print(response[10])
        elif response[10] == 0xFF:
            # 如果是0xFF，根据后续字节的不同，抛出不同类型的异常
            type_code = response[9]  # 假设错误代码在第10个字节
            if type_code == 0x5A:
                raise ValueError("文件传输开始 - 异常，不能开始文件重构.")
            elif type_code == 0xBB:
                raise ValueError("文件传输结束应答 - 重构异常.")
            elif type_code == 0x8A:
                raise ValueError("文件传输应答 - 接收异常")
            else:
                raise ValueError("An unknown error with code 0xFF occurred.")
        elif response[10] == 0x11:
            raise ValueError("文件传输结束应答 - CRC重构异常.")
        else:
            # 如果第11个字节既不是0x00也不是0xFF，抛出一个通用的异常
            raise ValueError("Invalid response: The 11th byte is neither 0x00 nor 0xFF.")"""
