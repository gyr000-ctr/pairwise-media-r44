"""aggro 核心 API（初始未实现，仅标准库）。"""


class Aggro:
    def __init__(self, decay):
        """构造"""
        raise NotImplementedError

    def add(self, target, amount, dist):
        """加仇恨"""
        raise NotImplementedError

    def tick(self, dt):
        """衰减"""
        raise NotImplementedError

    def target(self):
        """当前目标"""
        raise NotImplementedError
