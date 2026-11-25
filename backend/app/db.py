from pathlib import Path
import os
import sqlite3
import threading
from contextlib import contextmanager

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "潮切.db"

# 管道级串行锁：换绑（改缓冲+观测）与关窗物化互斥，杜绝并发双成功/双键片。
# 用 RLock：同一线程内允许重入，避免辅助函数意外嵌套时自锁。
管道锁 = threading.RLock()


def 连接() -> sqlite3.Connection:
    数据目录.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(库路径, timeout=8.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 8000")
    return c


@contextmanager
def 立即事务():
    """进程内加锁 + SQLite BEGIN IMMEDIATE。

    保证「读在缓冲 → 切片 → 消耗缓冲」与「换绑改键/旁路」整段串行且单事务同成败。
    """
    with 管道锁:
        conn = 连接()
        旧隔离 = conn.isolation_level
        conn.isolation_level = None  # 切到 autocommit，显式管事务
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.isolation_level = 旧隔离
            conn.close()
