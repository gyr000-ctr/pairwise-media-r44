from . import core as dot  # noqa: F401  支持 `damageover.dot.Dot` 与裸名 `dot.Dot`
from .core import *  # noqa: F401,F403
from .core import (  # noqa: F401
    Dot,
    DotError,
    InvalidTickError,
    InvalidDpsError,
    InvalidDurationError,
    InvalidDeltaError,
)
