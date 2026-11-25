"""观测点换绑：三条夹具 + 只读接口契约。

夹具一：换绑后只灌旧键——切流账册拒（钉指纹）或双写两轨进归档。
夹具二：灌新键可成片；且换绑把在途缓冲与观测点同票改绑（不是只改展示键）。
夹具三：换绑与关窗并发，不得产生双键/双成功的现行片。

另含只读接口四字段（旧键、新键、拒因或归档键、valid）与 HTTP 接线检查。
"""
from __future__ import annotations

import os
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

_tmp = tempfile.mkdtemp(prefix="tide-huanbang-")
os.environ["数据目录"] = _tmp
os.environ.setdefault(
    "夹具目录",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "fixtures"),
)

import pytest  # noqa: E402

from app import seed  # noqa: E402
from app.db import 连接  # noqa: E402
from app.services import 装载, 关窗, 贯验, 目录  # noqa: E402
from app.modules import 观测点换绑 as RB  # noqa: E402


@pytest.fixture()
def 库(tmp_path, monkeypatch):
    """每条用例独立 sqlite 文件，避免与主链套件共库串扰。"""
    import app.db as db

    monkeypatch.setattr(db, "数据目录", tmp_path)
    monkeypatch.setattr(db, "库路径", tmp_path / "换绑.db")
    seed.初始化库()
    yield db


def _事件(编号: str, 键: str, 时: str, 网点: str = "网点-东站") -> dict:
    return {"事件编号": 编号, "运单键": 键, "网点键": 网点, "事件时": 时}


def _缓冲运单键集合(窗号: str | None = None) -> set[str]:
    sql = "SELECT DISTINCT 运单键 FROM 入窗缓冲 WHERE 命运='在缓冲'"
    args: tuple = ()
    if 窗号:
        sql += " AND 窗号=?"
        args = (窗号,)
    with 连接() as c:
        return {r[0] for r in c.execute(sql, args).fetchall()}


# ---------------------------------------------------------------------------
# 夹具一：换绑后只灌旧键——切流拒（钉指纹）或进归档
# ---------------------------------------------------------------------------
def test_夹具一_只灌旧键_切流拒并钉指纹_双轨进归档(库):
    # 形态 A：切流账册拒旧键 -------------------------------------------------
    old_a, new_a = "运单-夹具1A-旧", "运单-夹具1A-新"
    rec_a = RB.换绑(old_a, new_a, 形态=RB.切流)
    assert rec_a["valid"] is True
    assert rec_a["旧键"] == old_a and rec_a["新键"] == new_a
    # 四字段契约
    for k in ("旧键", "新键", "拒因或归档键", "valid"):
        assert k in rec_a
    assert rec_a["拒因"] and "拒" in rec_a["拒因或归档键"]
    assert rec_a["指纹"], "切流拒旧键须钉指纹"

    rep_a = 装载.装一批({
        "批次编号": "夹具1A",
        "事件": [_事件("fix1a-e1", old_a, "2026-11-24T00:11:00Z")],
    })
    assert rep_a["驳回"] == 1
    assert rep_a["入缓冲"] == 0
    assert _缓冲运单键集合() == set()

    # 指纹落账：同一旧键两次拒载指纹一致（钉得住）
    装载.装一批({
        "批次编号": "夹具1A-2",
        "事件": [_事件("fix1a-e2", old_a, "2026-11-24T00:12:00Z")],
    })
    with 连接() as c:
        pins = [r[0] for r in c.execute(
            "SELECT 指纹 FROM 旧键拒载账 WHERE 旧键=? ORDER BY 编号", (old_a,)
        ).fetchall()]
    assert len(pins) == 2 and pins[0] == pins[1] == rec_a["指纹"]

    # 只读接口：按旧键查到的记录带齐四字段
    dto_a = RB.只读接口(旧键=old_a)
    assert dto_a["新键"] == new_a and dto_a["valid"] is True
    assert "拒" in dto_a["拒因或归档键"]

    # 形态 B：双写两轨，旧键进只读归档 --------------------------------------
    old_b, new_b = "运单-夹具1B-旧", "运单-夹具1B-新"
    rec_b = RB.换绑(old_b, new_b, 形态=RB.双轨)
    assert rec_b["valid"] is True and rec_b["归档键"]
    assert rec_b["拒因或归档键"] == rec_b["归档键"]

    rep_b = 装载.装一批({
        "批次编号": "夹具1B",
        "事件": [_事件("fix1b-e1", old_b, "2026-11-24T00:21:00Z")],
    })
    assert rep_b.get("归档", 0) == 1
    assert rep_b["入缓冲"] == 0 and rep_b["驳回"] == 0

    arch = RB.归档列表()
    assert any(r["旧键"] == old_b and r["归档键"] == rec_b["归档键"] for r in arch)
    dto_b = RB.只读接口(旧键=old_b)
    assert dto_b["归档键"] and dto_b["拒因或归档键"] == dto_b["归档键"]

    # 换绑后现行缓冲键集合可区分：旧键都不在现行集合
    cur = RB.现行键集合()
    assert old_a not in cur and old_b not in cur


# ---------------------------------------------------------------------------
# 夹具二：灌新键可成片；在途历史同票改绑新键（缓冲 + 观测点持久化）
# ---------------------------------------------------------------------------
def test_夹具二_在途改绑同票_灌新键可成片(库):
    old, new = "运单-夹具2-旧", "运单-夹具2-新"
    装载.装一批({
        "批次编号": "夹具2-前",
        "事件": [
            _事件("fix2-e1", old, "2026-11-24T00:10:00Z", "网点-东站"),
            _事件("fix2-e2", old, "2026-11-24T00:40:00Z", "网点-西港"),
        ],
    })
    assert len(目录.缓冲列表()) == 2

    RB.换绑(old, new, 形态=RB.切流)

    # 不是只改展示键：缓冲与观测点底表运单键都已持久化改绑，且同票
    with 连接() as c:
        bkeys = [r[0] for r in c.execute(
            "SELECT 运单键 FROM 入窗缓冲 WHERE 事件编号 IN ('fix2-e1','fix2-e2')"
        ).fetchall()]
        okeys = [r[0] for r in c.execute(
            "SELECT 运单键 FROM 观测点 WHERE 事件编号 IN ('fix2-e1','fix2-e2')"
        ).fetchall()]
    assert bkeys == [new, new] and okeys == [new, new]
    assert all(r["运单键"] == new for r in 目录.缓冲列表())
    assert RB.现行键集合() == [new]

    # 换绑后再灌新键一笔，关窗 → 三张事件聚成一张新键片
    rep = 装载.装一批({
        "批次编号": "夹具2-新",
        "事件": [_事件("fix2-e3", new, "2026-11-24T00:20:00Z", "网点-北仓")],
    })
    assert rep["入缓冲"] == 1

    关 = 关窗.关当前窗()
    assert 关["成片数"] == 1 and 关["缓冲消耗"] == 3
    with 连接() as c:
        slices = c.execute(
            "SELECT 运单键, 事件数 FROM 窗切片账 WHERE 窗号=? ORDER BY 切片编号",
            ("W-demo",),
        ).fetchall()
    assert len(slices) == 1
    assert slices[0]["运单键"] == new and slices[0]["事件数"] == 3
    assert 贯验.跑一次()["是否对齐"] is True


def test_双轨形态_在途旧键旁路归档_不进现行片(库):
    old, new = "运单-夹具2B-旧", "运单-夹具2B-新"
    装载.装一批({"事件": [_事件("fix2b-e1", old, "2026-11-24T00:15:00Z")]})
    RB.换绑(old, new, 形态=RB.双轨)

    # 在途旧键已旁路：离现行缓冲、进归档轨，观测命运同票
    assert _缓冲运单键集合() == set()
    arch = RB.归档列表()
    assert any(r["事件编号"] == "fix2b-e1" for r in arch)
    with 连接() as c:
        fate_b = c.execute(
            "SELECT 命运 FROM 入窗缓冲 WHERE 事件编号='fix2b-e1'"
        ).fetchone()[0]
        fate_o = c.execute(
            "SELECT 命运 FROM 观测点 WHERE 事件编号='fix2b-e1'"
        ).fetchone()[0]
    assert fate_b == "已旁路归档" and fate_o == "已旁路归档"

    # 灌新键可独立成片
    装载.装一批({"事件": [_事件("fix2b-n1", new, "2026-11-24T00:16:00Z")]})
    关 = 关窗.关当前窗()
    assert 关["成片数"] == 1
    with 连接() as c:
        row = c.execute("SELECT 运单键,事件数 FROM 窗切片账").fetchone()
    assert row[0] == new and row[1] == 1
    assert 贯验.跑一次()["是否对齐"] is True


# ---------------------------------------------------------------------------
# 夹具三：换绑 × 双关窗 并发，不得双键片 / 双成功
# ---------------------------------------------------------------------------
def test_夹具三_换绑与关窗并发_不得双键现行片(库):
    轮数, 每轮 = 8, 4
    成片回报总和 = 0
    for i in range(轮数):
        w = f"W-race-{i}"
        目录.改窗规({
            "当前窗号": w,
            "窗起": "2026-11-24T00:00:00Z",
            "窗止": "2026-11-24T01:00:00Z",
        })
        old, new = f"运单-race{i}-旧", f"运单-race{i}-新"
        evs = [
            _事件(f"race-{i}-{j}", old, f"2026-11-24T00:{10 + j:02d}:00Z")
            for j in range(每轮)
        ]
        assert 装载.装一批({"事件": evs})["入缓冲"] == 每轮

        闸 = threading.Barrier(3)
        回报: dict = {}
        错误: list[BaseException] = []

        def _收(fn, 槽):
            try:
                闸.wait()
                回报[槽] = fn()
            except BaseException as e:  # noqa: BLE001
                错误.append(e)

        ts = [
            threading.Thread(target=_收, args=(lambda: RB.换绑(old, new), "rb")),
            threading.Thread(target=_收, args=(关窗.关当前窗, "c1")),
            threading.Thread(target=_收, args=(关窗.关当前窗, "c2")),
        ]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=20)
            assert not t.is_alive(), "并发用例线程死锁/超时"

        assert not 错误, f"并发体抛错: {错误!r}"
        # 不加锁时两个关窗可能都回报成片（双成功）；加锁后整轮只成片一次
        成片回报总和 += int(回报["c1"]["成片数"]) + int(回报["c2"]["成片数"])

        with 连接() as c:
            groups = c.execute(
                """SELECT 运单键, COUNT(*) AS 片数, COALESCE(SUM(事件数),0) AS 事件数
                   FROM 窗切片账 WHERE 窗号=? GROUP BY 运单键""",
                (w,),
            ).fetchall()
            活 = c.execute(
                "SELECT COUNT(*) FROM 入窗缓冲 WHERE 窗号=? AND 命运='在缓冲'", (w,)
            ).fetchone()[0]

        # 每窗只有一个运单键、一张片、事件数齐；绝不同时挂旧键片与新键片
        assert len(groups) == 1, f"出现双键/多张现行片: {[dict(g) for g in groups]}"
        g = groups[0]
        assert g["运单键"] in (old, new)
        assert g["片数"] == 1 and g["事件数"] == 每轮
        assert 活 == 0

    assert 成片回报总和 == 轮数, "存在并发双成功（两个关窗都成片）"
    assert 贯验.跑一次()["是否对齐"] is True


# ---------------------------------------------------------------------------
# 只读接口 / HTTP 接线
# ---------------------------------------------------------------------------
def test_只读接口_提案校验与HTTP(库):
    # 非法提案：空键 / 同键 → valid False 且带拒因
    bad = RB.校验换绑("", "运单-x")
    assert bad["valid"] is False and bad["拒因或归档键"]
    same = RB.校验换绑("运单-k", "运单-k")
    assert same["valid"] is False

    old, new = "运单-http-旧", "运单-http-新"
    RB.换绑(old, new, 形态=RB.切流)

    from starlette.testclient import TestClient
    from app.main import app

    cli = TestClient(app)

    r = cli.get("/api/观测点换绑")
    assert r.status_code == 200
    body = r.json()
    # 信封顶层即最新一条契约记录
    assert body["valid"] is True
    assert body["旧键"] == old and body["新键"] == new
    assert body["拒因或归档键"]
    assert isinstance(body["记录"], list) and body["记录"]

    rq = cli.get("/api/观测点换绑", params={"旧键": old})
    assert rq.status_code == 200
    one = rq.json()
    assert one["旧键"] == old and one["新键"] == new and one["valid"] is True

    rl = cli.get("/api/换绑记录")
    assert rl.status_code == 200 and isinstance(rl.json(), list)

    # HTTP 执行换绑（别名路径 + 宽松字段名）
    rp = cli.post("/api/换绑", json={"旧键": "运单-p-旧", "新键": "运单-p-新", "形态": "双轨"})
    assert rp.status_code == 200, rp.text
    rec = rp.json()
    assert rec["valid"] is True and rec["归档键"]

    # 窗规策略可读写选定形态
    rg = cli.post("/api/窗规", json={"换绑形态": RB.双轨})
    assert rg.status_code == 200 and rg.json()["换绑形态"] == RB.双轨
