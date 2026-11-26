"""pcmparse 核心 API（初始未实现，仅标准库）。"""


class PcmParse:
    def parse(self, data):
        """解析"""
        raise NotImplementedError

    def build(self, fmt):
        """构造头"""
        raise NotImplementedError
