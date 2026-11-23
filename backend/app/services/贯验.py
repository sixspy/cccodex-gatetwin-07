import json

from app.db import 连接
from app.seed import 此刻


def 跑贯验() -> dict:
    """行程账与刷卡点互证：每笔已成对行程对应两笔已成对刷卡；旁路/开腿命运自洽。"""
    conn = 连接()
    try:
        问题 = []
        刷卡数 = conn.execute("SELECT COUNT(*) FROM 刷卡点").fetchone()[0]
        行程 = conn.execute("SELECT * FROM 行程账 WHERE 状态='已成对'").fetchall()
        开腿数 = conn.execute("SELECT COUNT(*) FROM 开腿账 WHERE 状态='在途'").fetchone()[0]
        旁路数 = conn.execute("SELECT COUNT(*) FROM 旁路匣").fetchone()[0]

        for t in 行程:
            进 = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 事件编号=?", (t["进站事件编号"],)
            ).fetchone()
            出 = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 事件编号=?", (t["出站事件编号"],)
            ).fetchone()
            if not 进 or not 出:
                问题.append(f"行程{t['行程键']}缺刷卡点")
                continue
            if 进["命运"] != "已成对" or 出["命运"] != "已成对":
                问题.append(f"行程{t['行程键']}刷卡命运非已成对")
            if 进["行程键"] != t["行程键"] or 出["行程键"] != t["行程键"]:
                问题.append(f"行程{t['行程键']}刷卡行程键不一致")
            if 进["卡号"] != t["卡号"] or 出["卡号"] != t["卡号"]:
                问题.append(f"行程{t['行程键']}卡号不一致")
            if 进["方向"] != "进站" or 出["方向"] != "出站":
                问题.append(f"行程{t['行程键']}方向不配对")
            # 撕裂防线：行程卡号必须与其所配开腿账卡号恒等（切断口径下开腿行卡号永不改写）
            腿 = conn.execute(
                "SELECT 卡号, 状态 FROM 开腿账 WHERE 进站事件编号=?",
                (t["进站事件编号"],),
            ).fetchone()
            if not 腿:
                问题.append(f"行程{t['行程键']}缺开腿账")
            elif 腿["卡号"] != t["卡号"]:
                问题.append(
                    f"行程{t['行程键']}卡号{t['卡号']}与开腿卡号{腿['卡号']}撕裂"
                )
            elif 腿["状态"] != "已成对":
                问题.append(f"行程{t['行程键']}开腿状态非已成对")

        # 换绑切断口径互证
        换绑行 = conn.execute("SELECT * FROM 卡号换绑").fetchall()
        for rb in 换绑行:
            处置 = json.loads(rb["处置列表"] or "[]")
            if rb["valid"]:
                旧在途 = conn.execute(
                    "SELECT COUNT(*) AS c FROM 开腿账 WHERE 卡号=? AND 状态='在途'",
                    (rb["旧卡"],),
                ).fetchone()["c"]
                if 旧在途 != 0:
                    问题.append(f"换绑{rb['换绑键']}生效后旧卡{rb['旧卡']}仍有{旧在途}条在途开腿")
                for d in 处置:
                    腿 = conn.execute(
                        "SELECT 卡号, 状态, 旁路原因 FROM 开腿账 WHERE 开腿键=?",
                        (d["开腿键"],),
                    ).fetchone()
                    if not 腿:
                        问题.append(f"换绑{rb['换绑键']}处置开腿{d['开腿键']}不存在")
                        continue
                    if 腿["卡号"] != rb["旧卡"]:
                        问题.append(
                            f"换绑{rb['换绑键']}开腿{d['开腿键']}卡号被改写为{腿['卡号']}（禁止迁移）"
                        )
                    if 腿["状态"] != "已旁路" or 腿["旁路原因"] != "换绑切断":
                        问题.append(
                            f"换绑{rb['换绑键']}开腿{d['开腿键']}未按换绑切断旁路"
                        )
            elif 处置:
                问题.append(f"换绑{rb['换绑键']}valid=0 却产生了开腿处置（半截迁移）")
        # 有效换绑唯一：一张旧卡至多一条 valid=1
        重复 = conn.execute(
            "SELECT 旧卡, COUNT(*) AS c FROM 卡号换绑 WHERE valid=1 GROUP BY 旧卡 HAVING c > 1"
        ).fetchall()
        for r in 重复:
            问题.append(f"旧卡{r['旧卡']}存在{r['c']}条生效换绑，违反唯一换绑闸")

        # 已旁路开腿必须带旁路原因，且在途/成对腿不得带原因
        for leg in conn.execute("SELECT * FROM 开腿账").fetchall():
            if leg["状态"] == "已旁路" and not leg["旁路原因"]:
                问题.append(f"开腿{leg['开腿键']}已旁路但旁路原因为空")
            if leg["状态"] in ("在途", "已成对") and leg["旁路原因"]:
                问题.append(f"开腿{leg['开腿键']}状态{leg['状态']}却带旁路原因")

        成对刷 = conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已成对'"
        ).fetchone()[0]
        if 成对刷 != len(行程) * 2:
            问题.append(f"已成对刷卡{成对刷} ≠ 行程{len(行程)}×2")

        开腿刷 = conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已开腿'"
        ).fetchone()[0]
        if 开腿刷 != 开腿数:
            问题.append(f"已开腿刷卡{开腿刷} ≠ 在途开腿{开腿数}")

        通过 = 1 if not 问题 else 0
        说明 = "行程账与刷卡点互证通过" if 通过 else "；".join(问题)[:800]
        conn.execute(
            """INSERT INTO 行程贯验(时刻,刷卡数,行程数,开腿数,旁路数,是否通过,说明)
               VALUES (?,?,?,?,?,?,?)""",
            (此刻(), 刷卡数, len(行程), 开腿数, 旁路数, 通过, 说明),
        )
        conn.commit()
        return {
            "是否通过": bool(通过),
            "刷卡数": 刷卡数,
            "行程数": len(行程),
            "开腿数": 开腿数,
            "旁路数": 旁路数,
            "说明": 说明,
            "问题": 问题,
        }
    finally:
        conn.close()
