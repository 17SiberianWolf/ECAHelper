"""ECAHelper 后端包。

为保证包内模块能以 ``import config`` 方式引用同级的 config.py（无论运行的
工作目录如何），在包初始化时将 ``src/``（本包的父目录）加入 sys.path。

冻结（PyInstaller）态下 ``config`` 与 ``eca_helper`` 已被打包为顶层模块，
导入路径由引导器管理，**禁止**手工注入 sys.path，故此处加 frozen 守卫。
"""

import os
import sys

if not getattr(sys, "frozen", False):
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # = <root>/src
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
else:
    _ROOT = None

__all__ = ["_ROOT"]
