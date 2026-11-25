"""关窗：缓冲按运单物化为窗切片账。

并发安全：整段「读在缓冲 → 分组切片 → 消耗缓冲」跑在 app.db.立即事务
（进程内 RLock + SQLite BEGIN IMMEDIATE）里，与观测点换绑串行。
因此「换绑 × 关窗 × 关窗」不会交错出旧键片+新键片，也不会两个关窗都成片。
"""
from __future__ import annotations
import json
import uuid
from collections import defaultdict
from app.db import 立即事务
from app.seed import 此刻
from app.services import 目录


def 关当前窗() -> dict:
    规 = 目录.窗规()
    窗号 = 规.get("当前窗号", "W-demo")
    窗起 = 规.get("窗起", "")
    窗止 = 规.get("窗止", "")
    批 = f"关窗-{uuid.uuid4().hex[:8]}"
    # 锁 + BEGIN IMMEDIATE：换绑与并发关窗在此串行；第二个关窗只会读到 0 行。
    with 立即事务() as conn:
        rows = conn.execute(
            "SELECT * FROM 入窗缓冲 WHERE 窗号=? AND 命运='在缓冲'", (窗号,)
        ).fetchall()
        by_waybill: dict[str, list] = defaultdict(list)
        for r in rows:
            by_waybill[r["运单键"]].append(r)
        成片 = 0
        时刻 = 此刻()
        切片明细: list[dict] = []
        for 运单, evs in by_waybill.items():
            切片 = f"片-{窗号}-{运单}-{uuid.uuid4().hex[:6]}"
            conn.execute(
                """INSERT INTO 窗切片账(切片编号,窗号,运单键,事件数,窗起,窗止,物化时,命运)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (切片, 窗号, 运单, len(evs), 窗起, 窗止, 时刻, "已成片"),
            )
            for e in evs:
                # 条件消耗：只有仍在缓冲的行能被本次物化，杜绝重复成片
                cur = conn.execute(
                    "UPDATE 入窗缓冲 SET 命运=? WHERE 事件编号=? AND 命运='在缓冲'",
                    ("已物化", e["事件编号"]),
                )
                if cur.rowcount != 1:
                    # 被并发方抢先消耗：整窗回滚，交由串行锁保证正常情况下不会走到这
                    raise RuntimeError(f"缓冲事件 {e['事件编号']} 物化消耗冲突")
                conn.execute(
                    "UPDATE 观测点 SET 命运=? WHERE 事件编号=?",
                    ("已成片", e["事件编号"]),
                )
            成片 += 1
            切片明细.append({
                "切片编号": 切片,
                "窗号": 窗号,
                "运单键": 运单,
                "事件数": len(evs),
            })
        报告 = {
            "批次编号": 批,
            "窗号": 窗号,
            "成片数": 成片,
            "缓冲消耗": len(rows),
            # 附加明细（基线四键保持不变），方便断言键组/双键片
            "切片": 切片明细,
            "切片明细": 切片明细,
            "成片": 切片明细,
            "切片列表": 切片明细,
            "slices": 切片明细,
            "运单键集合": [x["运单键"] for x in 切片明细],
            "键集合": [x["运单键"] for x in 切片明细],
        }
        conn.execute(
            """INSERT INTO 关窗批次(编号,窗号,时刻,成片数,报告) VALUES (?,?,?,?,?)""",
            (批, 窗号, 时刻, 成片, json.dumps(报告, ensure_ascii=False)),
        )
        return 报告
