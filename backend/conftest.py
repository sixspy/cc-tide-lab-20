"""保证无论从仓库根还是 backend/ 目录运行 pytest，都能 ``import app``。"""
import os
import sys

_BACKEND = os.path.dirname(os.path.abspath(__file__))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
