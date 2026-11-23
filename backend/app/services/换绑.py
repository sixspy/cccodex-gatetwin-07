"""卡号换绑（全局唯一口径：切断旧开腿旁路，禁止开腿行卡号改写）。

口径甲（本系统贯彻的唯一架构，区别于「开腿随新卡迁移」口径乙）：
- 换绑写闸与开腿处置在同一事务内提交，禁止半截迁移；
- 旧卡全部在途开腿在事务内旁路（旁路原因=换绑切断），其进站刷卡点命运同步置已旁路并入旁路匣；
- 新卡从空开腿开始；开腿账.卡号永不更新，因此行程账卡号与开腿账卡号恒等，无撕裂面；
- 换绑后旧卡再出站：查无在途开腿 → 出站孤儿旁路，配不到任何已切断腿；
- 换绑后新卡出站：只能配换绑之后新开的腿。

换绑闸（valid=0 不处置任何开腿，审计留痕）：
1. 旧卡=新卡；2. 旧卡已有生效换绑；3. 新卡自身仍有在途开腿（未先出站/换绑）。
"""
import json

from app.seed import 此刻

口径名 = "切断旧开腿旁路"
旁路原因 = "换绑切断"


def _生换绑键(旧卡: str, 新卡: str, 事件时: str) -> str:
    return f"换-{旧卡}-{新卡}-{事件时}".replace(":", "").replace("-", "")


def 做换绑(conn, 体: dict, 来源: str = "写闸") -> dict:
    """在调用方事务/连接内执行换绑；返回处置报告（含 valid、处置列表、审计）。"""
    旧卡 = (体.get("旧卡") or "").strip()
    新卡 = (体.get("新卡") or "").strip()
    事件时 = 体.get("事件时") or 此刻()
    处理时 = 此刻()
    换绑键 = (体.get("换绑键") or "").strip() or _生换绑键(旧卡, 新卡, 事件时)

    幂等 = conn.execute(
        "SELECT * FROM 卡号换绑 WHERE 换绑键=?", (换绑键,)
    ).fetchone()
    if 幂等:
        return {
            "换绑键": 换绑键,
            "valid": bool(幂等["valid"]),
            "旧卡": 幂等["旧卡"],
            "新卡": 幂等["新卡"],
            "处置列表": json.loads(幂等["处置列表"]),
            "审计": json.loads(幂等["审计"]),
            "幂等跳过": True,
        }

    审计 = {"口径": 口径名, "闸门": []}
    处置列表 = []
    valid = True

    if not 旧卡 or not 新卡:
        valid = False
        审计["闸门"].append("旧卡/新卡不得为空")
    if 旧卡 == 新卡 and 旧卡:
        valid = False
        审计["闸门"].append("旧卡与新卡相同，拒绝换绑")
    if 旧卡:
        旧换 = conn.execute(
            "SELECT 换绑键, 新卡 FROM 卡号换绑 WHERE 旧卡=? AND valid=1", (旧卡,)
        ).fetchone()
        if 旧换:
            valid = False
            审计["闸门"].append(f"旧卡已生效换绑至{旧换['新卡']}（换绑键{旧换['换绑键']}）")
    if 新卡:
        新在途 = conn.execute(
            "SELECT 开腿键 FROM 开腿账 WHERE 卡号=? AND 状态='在途'", (新卡,)
        ).fetchall()
        if 新在途:
            valid = False
            审计["闸门"].append(
                "新卡存在在途开腿，须先出站或先换绑：" + ",".join(r["开腿键"] for r in 新在途)
            )

    if valid:
        # 口径甲核心：事务内切断旧卡全部在途开腿；只改状态，绝不动卡号列。
        在途 = conn.execute(
            "SELECT * FROM 开腿账 WHERE 卡号=? AND 状态='在途' ORDER BY 进站事件时 ASC",
            (旧卡,),
        ).fetchall()
        for leg in 在途:
            conn.execute(
                "UPDATE 开腿账 SET 状态='已旁路', 旁路原因=?, 更新处理时=? WHERE 开腿键=?",
                (旁路原因, 处理时, leg["开腿键"]),
            )
            conn.execute(
                "UPDATE 刷卡点 SET 命运='已旁路' WHERE 事件编号=?",
                (leg["进站事件编号"],),
            )
            载荷 = {
                "开腿键": leg["开腿键"],
                "旧卡": 旧卡,
                "新卡": 新卡,
                "换绑键": 换绑键,
                "口径": 口径名,
                "进站事件编号": leg["进站事件编号"],
                "进站事件时": leg["进站事件时"],
            }
            conn.execute(
                "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
                (旁路原因, 旧卡, leg["进站事件编号"], json.dumps(载荷, ensure_ascii=False), 处理时),
            )
            处置列表.append(
                {
                    "开腿键": leg["开腿键"],
                    "进站事件编号": leg["进站事件编号"],
                    "处置": "旁路",
                    "旁路原因": 旁路原因,
                }
            )
        审计["在途开腿数"] = len(在途)
        审计["说明"] = "旧卡在途开腿已全部换绑切断，新卡自空开腿起算；开腿行卡号未改写"
    else:
        审计["说明"] = "换绑闸门未过，未处置任何开腿"

    conn.execute(
        """INSERT INTO 卡号换绑(换绑键,旧卡,新卡,事件时,处理时,处置列表,审计,valid,来源)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            换绑键,
            旧卡,
            新卡,
            事件时,
            处理时,
            json.dumps(处置列表, ensure_ascii=False),
            json.dumps(审计, ensure_ascii=False),
            1 if valid else 0,
            来源,
        ),
    )
    return {
        "换绑键": 换绑键,
        "valid": valid,
        "旧卡": 旧卡,
        "新卡": 新卡,
        "事件时": 事件时,
        "处理时": 处理时,
        "处置列表": 处置列表,
        "审计": 审计,
    }


def 查换绑(旧卡: str = "", 新卡: str = "") -> list:
    """只读接口：旧卡、新卡、开腿处置列表、审计、valid。"""
    from app.db import 连接

    sql = "SELECT * FROM 卡号换绑 WHERE 1=1"
    参数 = []
    if 旧卡:
        sql += " AND 旧卡=?"
        参数.append(旧卡)
    if 新卡:
        sql += " AND 新卡=?"
        参数.append(新卡)
    sql += " ORDER BY 处理时 DESC, 换绑键 DESC"
    conn = 连接()
    try:
        out = []
        for r in conn.execute(sql, 参数):
            d = dict(r)
            d["valid"] = bool(d["valid"])
            d["处置列表"] = json.loads(d["处置列表"] or "[]")
            d["审计"] = json.loads(d["审计"] or "{}")
            out.append(d)
        return out
    finally:
        conn.close()
