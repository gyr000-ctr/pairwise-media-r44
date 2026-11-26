"""buffstack 核心 API（初始未实现，仅标准库）。"""


class BuffStack:
    def __init__(self):
        """构造"""
        raise NotImplementedError

    def apply(self, name, dur, stacks, mode):
        """施加"""
        raise NotImplementedError

    def tick(self, dt):
        """推进"""
        raise NotImplementedError

    def active(self):
        """生效列表"""
        raise NotImplementedError
