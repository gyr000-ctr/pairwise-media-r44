"""damageover 核心 API（初始未实现，仅标准库）。"""


class Dot:
    def __init__(self, tick):
        """构造"""
        raise NotImplementedError

    def apply(self, name, dps, dur):
        """施加"""
        raise NotImplementedError

    def update(self, dt):
        """推进"""
        raise NotImplementedError

    def total(self, name):
        """累计伤害"""
        raise NotImplementedError
