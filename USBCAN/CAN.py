
class CAN_MSG(object):
    def __init__(self):
        self.id = 0
        self.remote_flag = 0
        self.extend_flag = 0
        self.dlc = 0
        self.data = bytearray(8)
