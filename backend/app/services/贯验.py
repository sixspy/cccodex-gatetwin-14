from app.db import 连接
from app.seed import 此刻
from app.services import 封印


def 跑贯验() -> dict:
    """行程账与刷卡点互证，并校验封印链与主读同票。

    - 每笔已成对行程对应两笔已成对刷卡、卡号/方向/行程键一致
    - 主读出站站 = 当前版本出站站（版本追加口径下，主读与贯验共用 取当前）
    - 每个行程键至多一条当前版本；封印行程基行摘要与版本链摘要均未漂移
    """
    conn = 连接()
    try:
        问题 = []
        刷卡数 = conn.execute("SELECT COUNT(*) FROM 刷卡点").fetchone()[0]
        基行程 = conn.execute("SELECT * FROM 行程账 WHERE 状态='已成对'").fetchall()
        开腿数 = conn.execute("SELECT COUNT(*) FROM 开腿账 WHERE 状态='在途'").fetchone()[0]
        旁路数 = conn.execute("SELECT COUNT(*) FROM 旁路匣").fetchone()[0]

        行程数 = 0
        已封印数 = 0
        有版本行数 = 0
        for t in 基行程:
            行程数 += 1
            主读 = 封印.取当前(conn, t["行程键"])
            if 主读["版本"] > 1:
                有版本行数 += 1
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
            if 主读["进站站点键"] != 进["站点键"]:
                问题.append(f"行程{t['行程键']}主读进站站与刷卡不一致")
            if 主读["进站事件时"] != 进["事件时"]:
                问题.append(f"行程{t['行程键']}主读进站时与刷卡不一致")
            # 基行不可改：基行出站时须与出站刷卡事件时同票；修正只体现在版本行
            if t["出站事件时"] != 出["事件时"]:
                问题.append(f"行程{t['行程键']}基行出站时与刷卡不一致")
            if t["进站站点键"] != 进["站点键"]:
                问题.append(f"行程{t['行程键']}基行进站站与刷卡不一致")
            if 主读["历时秒"] < 0:
                问题.append(f"行程{t['行程键']}历时为负")

            校验 = 封印.校验链(conn, t["行程键"])
            if not 校验["valid"]:
                问题.append(f"行程{t['行程键']}封印链异常:{'；'.join(校验['问题'])}")
            if 校验["封印"]:
                已封印数 += 1
                if 校验["封印"]["封印版本"] != 主读["版本"]:
                    问题.append(f"行程{t['行程键']}封印版本与主读版本不符")

        双当前 = conn.execute(
            """SELECT 行程键 FROM 行程版本 WHERE 是否当前=1
               GROUP BY 行程键 HAVING COUNT(*) > 1"""
        ).fetchall()
        for r in 双当前:
            问题.append(f"行程{r['行程键']}双当前版本")

        成对刷 = conn.execute(
            "SELECT COUNT(*) FROM 刷卡点 WHERE 命运='已成对'"
        ).fetchone()[0]
        if 成对刷 != 行程数 * 2:
            问题.append(f"已成对刷卡{成对刷} ≠ 行程{行程数}×2")

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
            (此刻(), 刷卡数, 行程数, 开腿数, 旁路数, 通过, 说明),
        )
        conn.commit()
        return {
            "是否通过": bool(通过),
            "刷卡数": 刷卡数,
            "行程数": 行程数,
            "开腿数": 开腿数,
            "旁路数": 旁路数,
            "已封印": 已封印数,
            "有版本行": 有版本行数,
            "口径": "版本追加",
            "说明": 说明,
            "问题": 问题,
        }
    finally:
        conn.close()
