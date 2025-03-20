import logging
import threading
from inspect import stack

# 配置日志记录器
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
    datefmt='%Y-%m-%d  %H:%M:%S',
    filename='debug_20240628.log',
    filemode='a'
)

# 创建一个包装器函数，用于替代print函数
def log_print(*args):
    # 获取当前调用帧的函数名
    current_frame = stack()[1]
    func_name = current_frame[3]
    # 将参数转换为字符串并打印输出
    print_message = " ".join(map(str, args))
    print(print_message)
    # 记录日志，包含函数名和消息
    logging.info("%s - %s", func_name, print_message)

