import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

数据目录 = Path(os.environ.get("数据目录", Path(__file__).resolve().parent.parent / "data"))
夹具目录 = Path(os.environ.get("夹具目录", Path(__file__).resolve().parent.parent.parent / "fixtures"))
库路径 = 数据目录 / "闸对.db"


def 连接(自动提交: bool = False) -> sqlite3.Connection:
    """打开库连接。

    自动提交=True 时关闭 sqlite3 的隐式事务，调用方须显式使用 写事务()。
    写闸（封印 / 版本追加）靠 BEGIN IMMEDIATE + 唯一索引串行化并发写。
    """
    数据目录.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(库路径, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 30000")
    if 自动提交:
        c.isolation_level = None
    return c


@contextmanager
def 写事务(conn: sqlite3.Connection):
    """显式 IMMEDIATE 写事务：并发写闸在此排队，避免封印与重放交错覆盖。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")
