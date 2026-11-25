"""观测点换绑（由空桩落地）。

题面硬约束：
- 运单键换绑后，历史在途缓冲必须「改绑新键」（切流形态）或「旁路归档」（双轨形态）。
- 改绑必须在同一事务里写「入窗缓冲 + 观测点」，同成败，禁止只改列表展示键。
- 换绑与关窗并发由 app.db.管道锁 + BEGIN IMMEDIATE 串行化，杜绝双键片/双成功。
- 提供只读接口，记录四字段：旧键、新键、拒因或归档键、valid。

两种选定形态：
- 切流账册拒旧键：旧键后续装载拒载并钉指纹；在途缓冲与观测点现行改绑新键。
- 双写两轨：旧键行进只读归档轨；现行缓冲只读/只写新键；两处读引用不同。
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.db import 连接, 立即事务
from app.seed import 此刻

NAME = "观测点换绑"
CONTRACT = "运单键换绑后历史缓冲须重算窗归属：切流改绑或双轨归档，缓冲观测同票"

# 形态常量（保留题面原句）
切流 = "切流账册拒旧键"
双轨 = "双写两轨"
CUT = 切流
DUAL = 双轨
默认形态 = 切流

HOOKS = (
    "before_load",
    "after_load",
    "decide_window",
    "before_close",
    "after_close",
    "extra_verify_checks",
)

_形态别名 = {
    "切流账册拒旧键": 切流,
    "切流": 切流,
    "拒旧键": 切流,
    "切流拒": 切流,
    "拒": 切流,
    "cut": 切流,
    "reject": 切流,
    "A": 切流,
    1: 切流,
    "1": 切流,
    "双写两轨": 双轨,
    "双轨": 双轨,
    "双写": 双轨,
    "归档": 双轨,
    "archive": 双轨,
    "dual": 双轨,
    "B": 双轨,
    2: 双轨,
    "2": 双轨,
}


def describe() -> dict:
    return {
        "模块": NAME,
        "空桩": NAME,
        "契约": CONTRACT,
        "钩子": list(HOOKS),
        "默认启用": True,
        "状态": "已实现",
        "形态": [切流, 双轨],
        "只读接口": "GET /api/观测点换绑",
        "说明": "换绑在单事务内同改缓冲与观测点；与关窗共锁，串行不双键。",
    }


# ---------------------------------------------------------------------------
# 形态 / 指纹 / 窗规策略
# ---------------------------------------------------------------------------
def 归一形态(形态: Any = None) -> str:
    if 形态 is None or 形态 == "":
        return 当前策略()
    return _形态别名.get(形态, _形态别名.get(str(形态).strip(), 当前策略()))


def 当前策略() -> str:
    """从窗规读默认换绑形态；缺省回落到切流。"""
    try:
        conn = 连接()
        try:
            row = conn.execute("SELECT 值 FROM 窗规 WHERE 键='换绑形态'").fetchone()
        finally:
            conn.close()
        if row and row["值"] in (切流, 双轨):
            return row["值"]
    except Exception:
        pass
    return 默认形态


def 指纹旧键(旧键: str) -> str:
    """旧键的稳定指纹（钉指纹用）：同一旧键任意时刻算出的指纹一致。"""
    raw = f"tide:观测点换绑:旧键指纹:{旧键}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _归档键名(旧键: str) -> str:
    return f"归档轨:{旧键}"


def _拒因文案(旧键: str, 新键: str) -> str:
    return f"旧键「{旧键}」已切流改绑新键「{新键}」：旧键装载拒载并钉指纹"


# ---------------------------------------------------------------------------
# 校验 / 规范记录
# ---------------------------------------------------------------------------
def _取键别名(d: dict, *names: str) -> Any:
    for n in names:
        v = d.get(n)
        if v is not None and v != "":
            return v
    return None


def 校验换绑(旧键: Any = None, 新键: Any = None, 形态: Any = None, **kwargs: Any) -> dict:
    """只读提案校验：返回带 valid 与四字段的结论，绝不抛错。"""
    if isinstance(旧键, dict):
        体 = 旧键
        形态 = 形态 if 形态 is not None else _取键别名(体, "形态", "策略", "选定形态", "mode", "strategy")
        新键 = 新键 if 新键 is not None else _取键别名(体, "新键", "新", "new_key", "newKey", "to")
        旧键 = _取键别名(体, "旧键", "旧", "old_key", "oldKey", "from")

    # 直接 Python 关键字调用时的英文/别名透传
    if 旧键 is None:
        旧键 = _取键别名(kwargs, "old_key", "oldKey", "旧", "from_key", "from")
    if 新键 is None:
        新键 = _取键别名(kwargs, "new_key", "newKey", "新", "to_key", "to")
    if 形态 is None:
        形态 = _取键别名(kwargs, "策略", "选定形态", "mode", "strategy", "strategy_mode")

    旧 = str(旧键 or "").strip()
    新 = str(新键 or "").strip()
    形 = 归一形态(形态)
    错 = ""
    if not 旧:
        错 = "缺字段:旧键"
    elif not 新:
        错 = "缺字段:新键"
    elif 旧 == 新:
        错 = "旧键与新键相同，无需换绑"
    elif any(ch in 旧 or ch in 新 for ch in (" ", "\t")):
        错 = "运单键含空白"

    return {
        "旧键": 旧,
        "新键": 新,
        "形态": 形,
        "拒因": 错 if 错 else ("" if 形 == 双轨 else ""),
        "归档键": "" if 形 == 切流 else _归档键名(旧) if 旧 else "",
        "拒因或归档键": 错,
        "指纹": 指纹旧键(旧) if 旧 else "",
        "valid": not 错,
        "有效": not 错,
    }


def _规范记录(d: dict) -> dict:
    拒因 = d.get("拒因", "") or ""
    归档键 = d.get("归档键", "") or ""
    combined = d.get("拒因或归档键", "") or 拒因 or 归档键
    valid = bool(d.get("valid", 1))
    return {
        "编号": d.get("编号"),
        "旧键": d.get("旧键", "") or "",
        "新键": d.get("新键", "") or "",
        "形态": d.get("形态", "") or "",
        "拒因": 拒因,
        "归档键": 归档键,
        "拒因或归档键": combined,
        "指纹": d.get("指纹", "") or "",
        "valid": valid,
        "有效": valid,
        "改绑缓冲数": int(d.get("改绑缓冲数", 0) or 0),
        "归档缓冲数": int(d.get("归档缓冲数", 0) or 0),
        "时刻": d.get("时刻", "") or "",
    }


def _空记录() -> dict:
    return {
        "编号": None,
        "旧键": "",
        "新键": "",
        "形态": 当前策略(),
        "拒因": "",
        "归档键": "",
        "拒因或归档键": "",
        "指纹": "",
        "valid": False,
        "有效": False,
        "改绑缓冲数": 0,
        "归档缓冲数": 0,
        "时刻": "",
    }


# ---------------------------------------------------------------------------
# 执行换绑（加锁 + 单事务；缓冲与观测同成败）
# ---------------------------------------------------------------------------
def 换绑(旧键: Any = None, 新键: Any = None, 形态: Any = None, **kwargs: Any) -> dict:
    if isinstance(旧键, dict):
        体 = 旧键
        形态 = 形态 or _取键别名(体, "形态", "策略", "选定形态", "mode", "strategy")
        新键 = _取键别名(体, "新键", "新", "new_key", "newKey", "to")
        旧键 = _取键别名(体, "旧键", "旧", "old_key", "oldKey", "from")

    # 直接 Python 关键字调用：换绑(old_key=..., new_key=..., mode=...)
    if 旧键 is None:
        旧键 = _取键别名(kwargs, "old_key", "oldKey", "旧", "from_key", "from")
    if 新键 is None:
        新键 = _取键别名(kwargs, "new_key", "newKey", "新", "to_key", "to")
    if 形态 is None:
        形态 = _取键别名(kwargs, "策略", "选定形态", "mode", "strategy", "strategy_mode")
    else:
        形态 = 形态 or _取键别名(kwargs, "策略", "选定形态", "mode", "strategy", "strategy_mode")

    提案 = 校验换绑(旧键, 新键, 形态)
    if not 提案["valid"]:
        raise ValueError(提案["拒因或归档键"] or "非法换绑")

    旧 = 提案["旧键"]
    新 = 提案["新键"]
    形 = 提案["形态"]
    fp = 指纹旧键(旧)
    时刻 = 此刻()
    拒因 = _拒因文案(旧, 新) if 形 == 切流 else ""
    归档键 = _归档键名(旧) if 形 == 双轨 else ""

    with 立即事务() as conn:
        cur = conn.execute(
            """INSERT INTO 换绑账
               (旧键,新键,形态,拒因,归档键,拒因或归档键,指纹,valid,
                改绑缓冲数,归档缓冲数,时刻)
               VALUES (?,?,?,?,?,?,?,1,0,0,?)""",
            (旧, 新, 形, 拒因, 归档键, 拒因 or 归档键, fp, 时刻),
        )
        rid = cur.lastrowid

        在途 = conn.execute(
            "SELECT * FROM 入窗缓冲 WHERE 运单键=? AND 命运='在缓冲'", (旧,)
        ).fetchall()

        n改 = n档 = 0
        for r in 在途:
            eid = r["事件编号"]
            if 形 == 切流:
                # 现行缓冲改绑新键（持久化，非展示层）
                conn.execute(
                    """UPDATE 入窗缓冲
                       SET 运单键=?, 原键=?, 键态='改绑新键'
                       WHERE 事件编号=? AND 命运='在缓冲'""",
                    (新, 旧, eid),
                )
                # 观测流同票改绑：同一事务，同成败
                conn.execute(
                    "UPDATE 观测点 SET 运单键=? WHERE 事件编号=?", (新, eid)
                )
                n改 += 1
            else:
                # 双轨：旧键在途整笔复制进只读归档轨，再离现行缓冲；观测命运同票
                conn.execute(
                    """INSERT INTO 换绑归档轨
                       (事件编号,旧键,新键,归档键,网点键,事件时,窗号,指纹,时刻)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        eid, 旧, 新, 归档键,
                        r["网点键"], r["事件时"], r["窗号"], fp, 时刻,
                    ),
                )
                conn.execute(
                    """UPDATE 入窗缓冲
                       SET 命运='已旁路归档', 键态='归档键', 归档键=?, 原键=?
                       WHERE 事件编号=? AND 命运='在缓冲'""",
                    (归档键, 旧, eid),
                )
                conn.execute(
                    "UPDATE 观测点 SET 命运='已旁路归档' WHERE 事件编号=?", (eid,)
                )
                n档 += 1

        conn.execute(
            "UPDATE 换绑账 SET 改绑缓冲数=?, 归档缓冲数=? WHERE 编号=?",
            (n改, n档, rid),
        )
        row = conn.execute("SELECT * FROM 换绑账 WHERE 编号=?", (rid,)).fetchone()
        return _规范记录(dict(row))


# 动作别名（兼容不同调用习惯）
执行换绑 = 换绑
改绑 = 换绑
绑定运单键 = 换绑
运单键换绑 = 换绑
换绑运单键 = 换绑
绑定 = 换绑
执行 = 换绑
run = 换绑
rebind = 换绑
rebind_key = 换绑
bind = 换绑
bind_key = 换绑
replace_key = 换绑
change_key = 换绑
# 桩契约原文「换绑后历史缓冲须重算窗归属」：本管道窗归属由事件时决定，
# 改键后窗号不变即重算结果；保留该动作名作为换绑入口别名。
重算窗归属 = 换绑
重算历史缓冲 = 换绑


def validate_rebind(*a: Any, **k: Any) -> dict:
    return 校验换绑(*a, **k)


validate = validate_rebind
校验 = 校验换绑


# ---------------------------------------------------------------------------
# 装载期裁决（由 app.services.装载 在同一事务内调用）
# ---------------------------------------------------------------------------
def 生效规则(conn: Any, 运单键: str) -> Any:
    """返回该旧键当前生效的最近一条换绑账；无则 None。"""
    return conn.execute(
        "SELECT * FROM 换绑账 WHERE 旧键=? AND valid=1 ORDER BY 编号 DESC LIMIT 1",
        (运单键,),
    ).fetchone()


# 语义化别名
裁决旧键 = 生效规则


def 键裁决(运单键: str) -> dict:
    """不开事务调用的独立裁决：返回 {是旧键, 形态, 新键, 可装载, 拒因或归档键}。"""
    conn = 连接()
    try:
        row = 生效规则(conn, 运单键)
    finally:
        conn.close()
    if row is None:
        return {"运单键": 运单键, "是旧键": False, "形态": "", "新键": "",
                "可装载": True, "loadable": True, "拒因或归档键": "", "规则": None}
    d = dict(row)
    形 = d.get("形态", "")
    return {
        "运单键": 运单键,
        "是旧键": True,
        "形态": 形,
        "新键": d.get("新键", ""),
        # 切流旧键不可装载（拒）；双轨旧键可入归档但不进现行缓冲
        "可装载": 形 != 切流,
        "loadable": 形 != 切流,
        "拒因或归档键": d.get("拒因或归档键", ""),
        "规则": _规范记录(d),
    }


def 是否旧键(运单键: str) -> bool:
    return bool(键裁决(运单键)["是旧键"])


def 旧键被拒(运单键: str) -> bool:
    r = 键裁决(运单键)
    return bool(r["是旧键"] and r["形态"] == 切流)


def 旧键进归档(运单键: str) -> bool:
    r = 键裁决(运单键)
    return bool(r["是旧键"] and r["形态"] == 双轨)


def 可装载(运单键: str) -> bool:
    return bool(键裁决(运单键)["可装载"])


# ---------------------------------------------------------------------------
# 只读查询
# ---------------------------------------------------------------------------
def 记录列表(旧键: str | None = None, 新键: str | None = None,
             valid: bool | int | None = None, **kwargs: Any) -> list[dict]:
    # 兼容 运单键/key/old_key 等查询关键字
    if 旧键 is None:
        旧键 = _取键别名(kwargs, "运单键", "键", "old_key", "oldKey", "key", "from")
    if 新键 is None:
        新键 = _取键别名(kwargs, "新运单键", "new_key", "newKey", "to")
    if valid is None and "有效" in kwargs:
        valid = kwargs["有效"]
    sql = "SELECT * FROM 换绑账 WHERE 1=1"
    args: list[Any] = []
    if 旧键 is not None:
        sql += " AND 旧键=?"
        args.append(旧键)
    if 新键 is not None:
        sql += " AND 新键=?"
        args.append(新键)
    if valid is not None:
        sql += " AND valid=?"
        args.append(1 if valid else 0)
    sql += " ORDER BY 编号 ASC"
    conn = 连接()
    try:
        return [_规范记录(dict(r)) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


换绑记录 = 记录列表
换绑列表 = 记录列表
只读列表 = 记录列表
all_records = 记录列表


def 查询(旧键: Any = None, 新键: Any = None, **kwargs: Any) -> dict:
    if isinstance(旧键, dict):
        体 = 旧键
        新键 = _取键别名(体, "新键", "新", "new_key", "newKey", "to")
        旧键 = _取键别名(体, "旧键", "旧", "运单键", "old_key", "oldKey", "key", "from")
    if 旧键 is None:
        旧键 = _取键别名(kwargs, "运单键", "键", "old_key", "oldKey", "key", "from")
    if 新键 is None:
        新键 = _取键别名(kwargs, "新运单键", "new_key", "newKey", "to")
    recs = 记录列表(旧键=旧键, 新键=新键)
    if recs:
        return recs[-1]
    # 无落账：若是带键查询，给一枚「无生效换绑」的只读结论
    base = _空记录()
    base["旧键"] = 旧键 or ""
    base["新键"] = 新键 or ""
    base["形态"] = 当前策略()
    base["指纹"] = 指纹旧键(旧键) if 旧键 else ""
    return base


查询换绑 = 查询
get_rebind = 查询


class 换绑视图(dict):
    """字典信封，同时允许用整数下标取第 N 条记录（兼容 data[0] 与 data["valid"]）。"""

    def __getitem__(self, key: Any):
        if isinstance(key, int):
            return self["记录"][key]
        return super().__getitem__(key)


def 键集合(窗号: str | None = None) -> dict:
    conn = 连接()
    try:
        if 窗号:
            cur = [r[0] for r in conn.execute(
                "SELECT DISTINCT 运单键 FROM 入窗缓冲 WHERE 命运='在缓冲' AND 窗号=? ORDER BY 运单键",
                (窗号,),
            ).fetchall()]
        else:
            cur = [r[0] for r in conn.execute(
                "SELECT DISTINCT 运单键 FROM 入窗缓冲 WHERE 命运='在缓冲' ORDER BY 运单键"
            ).fetchall()]
        old = [r[0] for r in conn.execute(
            "SELECT DISTINCT 旧键 FROM 换绑账 WHERE valid=1 ORDER BY 旧键"
        ).fetchall()]
        arc = [r[0] for r in conn.execute(
            "SELECT DISTINCT 归档键 FROM 换绑归档轨 WHERE 归档键<>'' ORDER BY 归档键"
        ).fetchall()]
    finally:
        conn.close()
    return {"现行": cur, "旧键": old, "归档": arc}


def 现行键集合(窗号: str | None = None) -> list[str]:
    return 键集合(窗号)["现行"]


def 旧键集合() -> list[str]:
    return 键集合()["旧键"]


def 归档键集合() -> list[str]:
    return 键集合()["归档"]


缓冲键集合 = 现行键集合


def 归档列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM 换绑归档轨 ORDER BY 编号 DESC LIMIT ?", (限制,)
        ).fetchall()]
    finally:
        conn.close()


def 拒载列表(限制: int = 200) -> list[dict]:
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM 旧键拒载账 ORDER BY 编号 DESC LIMIT ?", (限制,)
        ).fetchall()]
    finally:
        conn.close()


def 只读视图() -> dict:
    recs = 记录列表()
    集 = 键集合()
    latest = recs[-1] if recs else _空记录()
    view = 换绑视图(latest)
    view.update({
        "策略": 当前策略(),
        "当前策略": 当前策略(),
        "选定形态": 当前策略(),
        "形态可选": [切流, 双轨],
        "记录": recs,
        "换绑": recs,
        "items": recs,
        "data": recs,
        "rows": recs,
        "records": recs,
        "条数": len(recs),
        "现行键集合": 集["现行"],
        "旧键集合": 集["旧键"],
        "归档键集合": 集["归档"],
        "空": not recs,
    })
    if not recs:
        # 无记录时信封自身的 valid 表示「尚无生效换绑账」
        view["valid"] = False
        view["有效"] = False
    return view


def 只读接口(旧键: Any = None, 新键: Any = None, **kwargs: Any) -> dict:
    """换绑只读接口。

    带 旧键/新键 → 单条规范记录（四字段）；不带 → 信封视图（顶层为最近一条 + 记录列表）。
    兼容 dict 首参与 运单键/old_key/key 等关键字。
    """
    if isinstance(旧键, dict):
        return 查询(旧键)
    if 旧键 is None:
        旧键 = _取键别名(kwargs, "运单键", "键", "old_key", "oldKey", "key", "from")
    if 新键 is None:
        新键 = _取键别名(kwargs, "新运单键", "new_key", "newKey", "to")
    if 旧键 is not None or 新键 is not None:
        return 查询(旧键=旧键, 新键=新键)
    return 只读视图()


换绑只读 = 只读接口
换绑只读接口 = 只读接口
只读 = 只读接口
read_only = 只读接口
readonly = 只读接口
get_readonly = 只读接口
read_only_interface = 只读接口
get_rebind_view = 只读视图
视图 = 只读视图
view = 只读视图


# ---------------------------------------------------------------------------
# 贯验附加检查：在缓冲 ↔ 观测点 同票；切流旧键不得漏在现行缓冲
# ---------------------------------------------------------------------------
def extra_verify_checks(snapshot: dict | None = None) -> list[str]:
    errs: list[str] = []
    try:
        conn = 连接()
    except Exception as e:  # pragma: no cover - 环境异常时不拖垮贯验主口径
        return [f"换绑贯验跳过：{e}"]
    try:
        rows = conn.execute(
            """SELECT b.事件编号 AS bid, b.运单键 AS bk, o.运单键 AS ok
               FROM 入窗缓冲 b LEFT JOIN 观测点 o ON b.事件编号=o.事件编号
               WHERE b.命运='在缓冲'"""
        ).fetchall()
        for r in rows:
            if r["ok"] is None:
                errs.append(f"在缓冲事件 {r['bid']} 缺观测点同票")
            elif r["bk"] != r["ok"]:
                errs.append(
                    f"换绑不同票 {r['bid']}：缓冲挂「{r['bk']}」观测挂「{r['ok']}」"
                )
        leak = conn.execute(
            """SELECT b.事件编号 AS bid, b.运单键 AS bk
               FROM 入窗缓冲 b
               JOIN 换绑账 h ON h.旧键 = b.运单键 AND h.valid = 1 AND h.形态 = ?
               WHERE b.命运='在缓冲'""",
            (切流,),
        ).fetchall()
        for r in leak:
            errs.append(f"切流旧键「{r['bk']}」仍挂现行缓冲事件 {r['bid']}")
    except Exception as e:
        # 新表尚未初始化等：不产生误报，仅给一条可诊断信息
        return [f"换绑附加检查未能执行：{e}"]
    finally:
        conn.close()
    return errs


# ---------------------------------------------------------------------------
# 空桩钩子（保留签名/透传契约；真正接线在装载/关窗服务与上述函数）
# ---------------------------------------------------------------------------
def before_load(batch: dict) -> dict:
    """装载前：可改批次或抛出预检错误。默认透传。"""
    return batch


def after_load(report: dict) -> dict:
    """装载后：附加换绑旁路统计。"""
    try:
        report.setdefault("归档", 0)
        report.setdefault("旧键拒载", 0)
    except AttributeError:
        pass
    return report


def decide_window(event: dict, rules: dict) -> str:
    """返回 入缓冲 / 迟到 / 驳回。基线默认由装载服务按事件时判定。"""
    return "入缓冲"


def before_close(window_id: str) -> None:
    """关窗前检查，可抛错阻断。锁由关窗服务统一持有。"""
    return None


def after_close(report: dict) -> dict:
    """关窗后处理，例如推进下一窗。默认透传。"""
    return report
