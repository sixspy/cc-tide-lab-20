from datetime import datetime, timezone
from app.db import 连接

建表 = """
CREATE TABLE IF NOT EXISTS 窗规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 网点源 (
  源键 TEXT PRIMARY KEY,
  名称 TEXT NOT NULL,
  区域 TEXT NOT NULL DEFAULT '',
  说明 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 观测点 (
  事件编号 TEXT PRIMARY KEY,
  运单键 TEXT NOT NULL,
  网点键 TEXT NOT NULL,
  事件时 TEXT NOT NULL,
  处理时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已装载',
  批次编号 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 入窗缓冲 (
  事件编号 TEXT PRIMARY KEY,
  运单键 TEXT NOT NULL,
  网点键 TEXT NOT NULL,
  事件时 TEXT NOT NULL,
  窗号 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '在缓冲',
  入缓冲时 TEXT NOT NULL,
  键态 TEXT NOT NULL DEFAULT '现行键',
  原键 TEXT NOT NULL DEFAULT '',
  归档键 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 窗切片账 (
  切片编号 TEXT PRIMARY KEY,
  窗号 TEXT NOT NULL,
  运单键 TEXT NOT NULL,
  事件数 INTEGER NOT NULL,
  窗起 TEXT NOT NULL,
  窗止 TEXT NOT NULL,
  物化时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已成片'
);
CREATE TABLE IF NOT EXISTS 迟到匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  事件编号 TEXT NOT NULL,
  运单键 TEXT NOT NULL,
  原因 TEXT NOT NULL,
  事件时 TEXT NOT NULL,
  入匣时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 窗贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  缓冲笔数 INTEGER NOT NULL,
  切片笔数 INTEGER NOT NULL,
  迟到笔数 INTEGER NOT NULL,
  是否对齐 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  时刻 TEXT NOT NULL,
  入流 INTEGER NOT NULL DEFAULT 0,
  入缓冲 INTEGER NOT NULL DEFAULT 0,
  迟到 INTEGER NOT NULL DEFAULT 0,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 关窗批次 (
  编号 TEXT PRIMARY KEY,
  窗号 TEXT NOT NULL,
  时刻 TEXT NOT NULL,
  成片数 INTEGER NOT NULL DEFAULT 0,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 换绑账 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  旧键 TEXT NOT NULL,
  新键 TEXT NOT NULL,
  形态 TEXT NOT NULL,
  拒因 TEXT NOT NULL DEFAULT '',
  归档键 TEXT NOT NULL DEFAULT '',
  拒因或归档键 TEXT NOT NULL DEFAULT '',
  指纹 TEXT NOT NULL DEFAULT '',
  valid INTEGER NOT NULL DEFAULT 1,
  改绑缓冲数 INTEGER NOT NULL DEFAULT 0,
  归档缓冲数 INTEGER NOT NULL DEFAULT 0,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 旧键拒载账 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  旧键 TEXT NOT NULL,
  新键 TEXT NOT NULL DEFAULT '',
  形态 TEXT NOT NULL DEFAULT '',
  指纹 TEXT NOT NULL,
  事件编号 TEXT NOT NULL DEFAULT '',
  拒因 TEXT NOT NULL,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 换绑归档轨 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  事件编号 TEXT NOT NULL,
  旧键 TEXT NOT NULL,
  新键 TEXT NOT NULL DEFAULT '',
  归档键 TEXT NOT NULL,
  网点键 TEXT NOT NULL DEFAULT '',
  事件时 TEXT NOT NULL DEFAULT '',
  窗号 TEXT NOT NULL DEFAULT '',
  指纹 TEXT NOT NULL DEFAULT '',
  时刻 TEXT NOT NULL
);
"""

# 旧库增量列：列名 → DDL 片段（新装库的 CREATE 已含这些列）
_缓冲增量列 = {
    "键态": "TEXT NOT NULL DEFAULT '现行键'",
    "原键": "TEXT NOT NULL DEFAULT ''",
    "归档键": "TEXT NOT NULL DEFAULT ''",
}


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    # 旧库补列（幂等）
    现有列 = {r["name"] for r in conn.execute("PRAGMA table_info(入窗缓冲)").fetchall()}
    for 列, ddl in _缓冲增量列.items():
        if 列 not in 现有列:
            conn.execute(f"ALTER TABLE 入窗缓冲 ADD COLUMN {列} {ddl}")
    if conn.execute("SELECT COUNT(*) AS c FROM 窗规").fetchone()["c"] == 0:
        for k, v in {
            "窗长秒": "3600",
            "允许迟到秒": "0",
            "关窗策略": "按事件时整点",
            "当前窗号": "W-demo",
            "窗起": "2026-11-24T00:00:00Z",
            "窗止": "2026-11-24T01:00:00Z",
            "换绑形态": "切流账册拒旧键",
        }.items():
            conn.execute("INSERT INTO 窗规(键,值) VALUES (?,?)", (k, v))
    # 老库也补一颗换绑策略默认子（不覆盖已选形态）
    conn.execute(
        "INSERT OR IGNORE INTO 窗规(键,值) VALUES ('换绑形态','切流账册拒旧键')"
    )
    if conn.execute("SELECT COUNT(*) AS c FROM 网点源").fetchone()["c"] == 0:
        for row in [
            ("网点-东站", "东站分拨", "华东", "示范网点"),
            ("网点-西港", "西港分拨", "华东", "示范网点"),
            ("网点-北仓", "北仓分拨", "华北", "示范网点"),
        ]:
            conn.execute(
                "INSERT INTO 网点源(源键,名称,区域,说明) VALUES (?,?,?,?)", row
            )
    conn.commit()
    conn.close()
