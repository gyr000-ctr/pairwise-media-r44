"""inventory 核心 API（初始未实现，仅标准库）。"""


class Inventory:
    def __init__(self, w, h, rotate=False):
        """构造"""
        raise NotImplementedError

    def place(self, item):
        """放置"""
        raise NotImplementedError

    def used(self):
        """已用格数"""
        raise NotImplementedError

    def grid(self):
        """占用图"""
        raise NotImplementedError
