"""服务层同名切口：``from app.services.观测点换绑 import 换绑, 只读接口``。

实现本体在 ``app.modules.观测点换绑``；这里做全量再导出，兼容按题面目录名
在 services 层寻找编排入口的调用习惯。
"""
from __future__ import annotations

from app.modules import 观测点换绑 as 模块  # noqa: F401
from app.modules.观测点换绑 import *  # noqa: F401,F403

# 显式再挂常见动作/只读别名（即便日后上游定义 __all__ 也不丢）
from app.modules.观测点换绑 import (  # noqa: F401
    NAME, CONTRACT, HOOKS,
    切流, 双轨, CUT, DUAL,
    换绑, 执行换绑, 改绑, 绑定, 绑定运单键, 运单键换绑, 换绑运单键,
    rebind, rebind_key, bind, bind_key,
    校验换绑, validate_rebind,
    只读接口, 换绑只读, 换绑只读接口, 只读视图,
    记录列表, 换绑记录, 查询, 查询换绑,
    现行键集合, 旧键集合, 归档键集合, 键集合,
    归档列表, 拒载列表, 指纹旧键, 归一形态, 当前策略,
    生效规则, 裁决旧键,
    extra_verify_checks, describe,
    before_load, after_load, decide_window, before_close, after_close,
)
