import json
from app.seed import 此刻
from app.services import 时间


def 扫缺腿超时(conn, 最大行程秒: int, 水位事件时: str, 处理时: str) -> int:
    """水位推进后，把超最大行程秒仍在途的开腿打进旁路。"""
    n = 0
    rows = list(conn.execute("SELECT * FROM 开腿账 WHERE 状态='在途'"))
    for leg in rows:
        if 时间.差秒(leg["进站事件时"], 水位事件时) < 最大行程秒:
            continue
        conn.execute(
            "UPDATE 开腿账 SET 状态='已旁路', 旁路原因=?, 更新处理时=? WHERE 开腿键=?",
            ("缺腿超时", 处理时, leg["开腿键"]),
        )
        conn.execute(
            "UPDATE 刷卡点 SET 命运=? WHERE 事件编号=?",
            ("已旁路", leg["进站事件编号"]),
        )
        conn.execute(
            "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
            (
                "缺腿超时",
                leg["卡号"],
                leg["进站事件编号"],
                json.dumps(
                    {
                        "开腿键": leg["开腿键"],
                        "进站事件时": leg["进站事件时"],
                        "水位": 水位事件时,
                        "最大行程秒": 最大行程秒,
                    },
                    ensure_ascii=False,
                ),
                处理时,
            ),
        )
        n += 1
    return n


def 成对写出站(conn, 开腿, 出站事件编号: str, 出站站点键: str, 出站事件时: str, 处理时: str):
    """同票成对：开腿仍在途才写行程。若开腿已被换绑切断/重复进站旁路，返回 None，交调用方按孤儿处置。

    硬约束：行程卡号取开腿账卡号，绝不另取刷卡卡号——开腿行卡号不可被改写，
    因此行程卡号与开腿卡号天然一致，杜绝半截迁移式撕裂。
    """
    guard = conn.execute(
        "SELECT 状态, 卡号 FROM 开腿账 WHERE 开腿键=?", (开腿["开腿键"],)
    ).fetchone()
    if not guard or guard["状态"] != "在途":
        return None
    行程键 = f"行-{开腿['进站事件编号']}-{出站事件编号}"
    历时 = max(0, 时间.差秒(开腿["进站事件时"], 出站事件时))
    conn.execute(
        """INSERT INTO 行程账(行程键,卡号,进站事件编号,出站事件编号,进站站点键,出站站点键,
           进站事件时,出站事件时,历时秒,状态,版本,处理时)
           VALUES (?,?,?,?,?,?,?,?,?,'已成对',1,?)""",
        (
            行程键,
            开腿["卡号"],
            开腿["进站事件编号"],
            出站事件编号,
            开腿["进站站点键"],
            出站站点键,
            开腿["进站事件时"],
            出站事件时,
            历时,
            处理时,
        ),
    )
    cur = conn.execute(
        "UPDATE 开腿账 SET 状态='已成对', 更新处理时=? WHERE 开腿键=? AND 状态='在途'",
        (处理时, 开腿["开腿键"]),
    )
    if cur.rowcount == 0:
        raise RuntimeError(f"开腿{开腿['开腿键']}成对冲突：已被并发旁路")
    conn.execute(
        "UPDATE 刷卡点 SET 命运=?, 行程键=? WHERE 事件编号 IN (?,?)",
        ("已成对", 行程键, 开腿["进站事件编号"], 出站事件编号),
    )
    return 行程键
