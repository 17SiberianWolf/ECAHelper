"""ECAHelper 后端包。

为保证包内模块能以 ``import config`` 方式引用根目录的 config.py（无论运行
的工作目录如何），在包初始化时将项目根目录加入 sys.path。
"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

__all__ = ["_ROOT"]
