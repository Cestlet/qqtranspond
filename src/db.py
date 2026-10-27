"""
本地持久化存储模块
使用 SQLite 记录已处理的说说的 tid，避免重复转发
"""
import os
import sqlite3
import logging
from typing import Set
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("qqtranspond.db")


class ForwardDB:
    """已转发记录数据库"""

    def __init__(self, db_path: str):
        """
        :param db_path: SQLite 数据库文件路径
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_db()

    def _init_db(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS forwarded (
                    tid TEXT PRIMARY KEY,
                    uin TEXT NOT NULL,
                    content_short TEXT DEFAULT '',
                    forwarded_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_forwarded_uin
                ON forwarded(uin)
            """)
            conn.commit()

    def is_forwarded(self, tid: str) -> bool:
        """检查 tid 是否已经转发过"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT 1 FROM forwarded WHERE tid = ?", (tid,))
            return cur.fetchone() is not None

    def mark_forwarded(self, tid: str, uin: str, content_short: str = ""):
        """标记一条说说已转发"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO forwarded (tid, uin, content_short, forwarded_at) "
                "VALUES (?, ?, ?, ?)",
                (tid, uin, content_short[:200], now),
            )
            conn.commit()

    def get_forwarded_count(self) -> int:
        """获取已转发总数"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("SELECT COUNT(*) FROM forwarded")
            return cur.fetchone()[0]

    def get_recent(self, limit: int = 20) -> list:
        """获取最近转发的记录"""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "SELECT tid, uin, content_short, forwarded_at "
                "FROM forwarded ORDER BY forwarded_at DESC LIMIT ?",
                (limit,),
            )
            return [
                {"tid": r[0], "uin": r[1], "content_short": r[2], "forwarded_at": r[3]}
                for r in cur.fetchall()
            ]

    def clean_old(self, days: int = 30):
        """清理超过指定天数的记录"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM forwarded WHERE forwarded_at < datetime('now', ?)",
                (f"-{days} days",),
            )
            conn.commit()