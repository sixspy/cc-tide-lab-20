"""测试引导：把 backend/ 目录放上 sys.path，保证任意 cwd / 调用方式都能 import app。

pytest 在导入本目录的测试模块之前会先导入本 conftest，因此这里的路径注入
对 ``pytest backend/tests``、绝对路径以及 IDE 收集均生效。
"""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
