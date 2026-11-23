from datetime import datetime, timezone

from app.db import 连接

建表 = """
CREATE TABLE IF NOT EXISTS 站规 (
  键 TEXT PRIMARY KEY,
  值 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 线路 (
  线路键 TEXT PRIMARY KEY,
  名称 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 站点 (
  站点键 TEXT PRIMARY KEY,
  线路键 TEXT NOT NULL REFERENCES 线路(线路键),
  站名 TEXT NOT NULL,
  站序 INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS 刷卡点 (
  事件编号 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  站点键 TEXT NOT NULL,
  方向 TEXT NOT NULL,
  事件时 TEXT NOT NULL,
  处理时 TEXT NOT NULL,
  命运 TEXT NOT NULL DEFAULT '已入流',
  行程键 TEXT NOT NULL DEFAULT '',
  批次编号 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 装载批次 (
  编号 TEXT PRIMARY KEY,
  时刻 TEXT NOT NULL,
  报告 TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS 开腿账 (
  开腿键 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  进站事件编号 TEXT NOT NULL,
  进站站点键 TEXT NOT NULL,
  进站事件时 TEXT NOT NULL,
  状态 TEXT NOT NULL DEFAULT '在途',
  旁路原因 TEXT NOT NULL DEFAULT '',
  更新处理时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 卡号换绑 (
  换绑键 TEXT PRIMARY KEY,
  旧卡 TEXT NOT NULL,
  新卡 TEXT NOT NULL,
  事件时 TEXT NOT NULL,
  处理时 TEXT NOT NULL,
  处置列表 TEXT NOT NULL DEFAULT '[]',
  审计 TEXT NOT NULL DEFAULT '{}',
  valid INTEGER NOT NULL DEFAULT 0,
  来源 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS 行程账 (
  行程键 TEXT PRIMARY KEY,
  卡号 TEXT NOT NULL,
  进站事件编号 TEXT NOT NULL,
  出站事件编号 TEXT NOT NULL,
  进站站点键 TEXT NOT NULL,
  出站站点键 TEXT NOT NULL,
  进站事件时 TEXT NOT NULL,
  出站事件时 TEXT NOT NULL,
  历时秒 INTEGER NOT NULL DEFAULT 0,
  状态 TEXT NOT NULL DEFAULT '已成对',
  版本 INTEGER NOT NULL DEFAULT 1,
  处理时 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 旁路匣 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  原因 TEXT NOT NULL,
  卡号 TEXT NOT NULL DEFAULT '',
  事件编号 TEXT NOT NULL DEFAULT '',
  载荷 TEXT NOT NULL,
  时刻 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS 行程贯验 (
  编号 INTEGER PRIMARY KEY AUTOINCREMENT,
  时刻 TEXT NOT NULL,
  刷卡数 INTEGER NOT NULL,
  行程数 INTEGER NOT NULL,
  开腿数 INTEGER NOT NULL,
  旁路数 INTEGER NOT NULL,
  是否通过 INTEGER NOT NULL,
  说明 TEXT NOT NULL
);
"""


def 此刻() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _迁移(conn) -> None:
    """老库补列/补站规，幂等。"""
    列 = {r["name"] for r in conn.execute("PRAGMA table_info(开腿账)")}
    if "旁路原因" not in 列:
        conn.execute("ALTER TABLE 开腿账 ADD COLUMN 旁路原因 TEXT NOT NULL DEFAULT ''")
        conn.execute(
            "UPDATE 开腿账 SET 旁路原因='重复进站' WHERE 状态='已旁路' AND 旁路原因=''"
        )
    for k, v in {
        "卡号换绑口径": "切断旧开腿旁路",
        "换绑在途开腿处置": "换绑事务内旧卡全部在途开腿旁路(换绑切断)，新卡从空开腿开始，禁止改开腿行卡号",
    }.items():
        conn.execute(
            "INSERT INTO 站规(键, 值) VALUES (?, ?) "
            "ON CONFLICT(键) DO UPDATE SET 值=excluded.值",
            (k, v),
        )


def 初始化库() -> None:
    conn = 连接()
    conn.executescript(建表)
    _迁移(conn)
    if conn.execute("SELECT COUNT(*) AS c FROM 站规").fetchone()["c"] == 0:
        for k, v in {
            "站名": "闸对",
            "最大行程秒": "7200",
            "同站进出": "允许",
            "重复进站策略": "旧腿旁路并开新腿",
            "配对策略": "同卡先进后出",
            "卡号换绑口径": "切断旧开腿旁路",
            "换绑在途开腿处置": "换绑事务内旧卡全部在途开腿旁路(换绑切断)，新卡从空开腿开始，禁止改开腿行卡号",
            "骨架": "刷卡点装载→同卡进站出站成对物化→缺腿异向超时旁路→行程账与刷卡点互证",
        }.items():
            conn.execute("INSERT INTO 站规(键, 值) VALUES (?, ?)", (k, v))
    if conn.execute("SELECT COUNT(*) AS c FROM 线路").fetchone()["c"] == 0:
        conn.execute("INSERT INTO 线路(线路键, 名称) VALUES (?, ?)", ("线1", "一号线"))
        for i, (k, n) in enumerate(
            [("站A", "城东站"), ("站B", "中心站"), ("站C", "河西站")], start=1
        ):
            conn.execute(
                "INSERT INTO 站点(站点键, 线路键, 站名, 站序) VALUES (?,?,?,?)",
                (k, "线1", n, i),
            )
    conn.commit()
    conn.close()
