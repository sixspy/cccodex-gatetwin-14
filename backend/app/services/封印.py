"""行程封印写闸（口径：版本追加）。

不变量：
- 行程账基行（版本 1）成对后不可原地改；一切出站/历时修正走 行程版本 追加。
- 每个行程键至多一条 是否当前=1（DB 部分唯一索引兜底），杜绝双当前。
- 封印记录基行摘要 + 版本链摘要；基行永不改写，链只向前滚。
- 装载重放对封印行程只读：内容一致命中，内容冲突拒绝并入旁路匣，绝不覆盖。
- 所有写路径走 BEGIN IMMEDIATE，封印与重放交错时串行，不会交错覆盖旧行。
"""

import hashlib
import json

from app.db import 连接, 写事务
from app.seed import 此刻
from app.services import 时间

基行字段 = (
    "行程键",
    "卡号",
    "进站事件编号",
    "出站事件编号",
    "进站站点键",
    "出站站点键",
    "进站事件时",
    "出站事件时",
    "历时秒",
)

版本字段 = ("版本", "出站事件编号", "出站站点键", "出站事件时", "历时秒", "依据")


def _规范(行, 字段) -> str:
    return json.dumps({k: 行[k] for k in 字段}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _摘要(文本: str) -> str:
    return hashlib.sha256(文本.encode("utf-8")).hexdigest()


def 基行摘要(基行) -> str:
    return _摘要(_规范(基行, 基行字段))


def _版本行(行) -> dict:
    return {k: 行[k] for k in 版本字段}


def _链摘要(conn, 基行) -> tuple[str, list]:
    h = 基行摘要(基行)
    版本行 = conn.execute(
        "SELECT * FROM 行程版本 WHERE 行程键=? ORDER BY 版本 ASC", (基行["行程键"],)
    ).fetchall()
    for v in 版本行:
        h = _摘要(h + _规范(_版本行(v), 版本字段))
    return h, 版本行


def 取当前(conn, 行程键: str):
    """主读解析器：基行 + 当前版本覆盖。主读与贯验共用，保证同票。"""
    基行 = conn.execute("SELECT * FROM 行程账 WHERE 行程键=?", (行程键,)).fetchone()
    if not 基行:
        return None
    当前 = conn.execute(
        "SELECT * FROM 行程版本 WHERE 行程键=? AND 是否当前=1", (行程键,)
    ).fetchone()
    if 当前:
        return {
            "行程键": 行程键,
            "卡号": 当前["卡号"],
            "进站事件编号": 基行["进站事件编号"],
            "出站事件编号": 当前["出站事件编号"],
            "进站站点键": 基行["进站站点键"],
            "出站站点键": 当前["出站站点键"],
            "进站事件时": 基行["进站事件时"],
            "出站事件时": 当前["出站事件时"],
            "历时秒": 当前["历时秒"],
            "状态": 基行["状态"],
            "版本": 当前["版本"],
            "基行版本": 基行["版本"],
            "是否基行": 0,
        }
    return {
        "行程键": 行程键,
        "卡号": 基行["卡号"],
        "进站事件编号": 基行["进站事件编号"],
        "出站事件编号": 基行["出站事件编号"],
        "进站站点键": 基行["进站站点键"],
        "出站站点键": 基行["出站站点键"],
        "进站事件时": 基行["进站事件时"],
        "出站事件时": 基行["出站事件时"],
        "历时秒": 基行["历时秒"],
        "状态": 基行["状态"],
        "版本": 基行["版本"],
        "基行版本": 基行["版本"],
        "是否基行": 1,
    }


def _记审计(conn, 行程键: str, 动作: str, 版本: int, 载荷: dict, 时刻: str) -> None:
    conn.execute(
        "INSERT INTO 封印审计(行程键, 动作, 版本, 载荷, 时刻) VALUES (?,?,?,?,?)",
        (行程键, 动作, 版本, json.dumps(载荷, ensure_ascii=False), 时刻),
    )


def _封印行(conn, 行程键: str):
    return conn.execute("SELECT * FROM 行程封印 WHERE 行程键=?", (行程键,)).fetchone()


def _最近拒绝(conn, 行程键: str):
    行 = conn.execute(
        "SELECT * FROM 封印审计 WHERE 行程键=? AND 动作 LIKE '%拒绝' ORDER BY 编号 DESC LIMIT 1",
        (行程键,),
    ).fetchone()
    if not 行:
        return None
    try:
        载荷 = json.loads(行["载荷"])
    except Exception:
        载荷 = {"原因": 行["载荷"]}
    return {"动作": 行["动作"], "版本": 行["版本"], "时刻": 行["时刻"], **载荷}


def 校验链(conn, 行程键: str) -> dict:
    """只读校验：基行摘要、版本链摘要、单当前、版本单调。"""
    基行 = conn.execute("SELECT * FROM 行程账 WHERE 行程键=?", (行程键,)).fetchone()
    if not 基行:
        return {"valid": False, "问题": ["行程不存在"]}
    问题 = []
    封印 = _封印行(conn, 行程键)
    当前行 = conn.execute(
        "SELECT COUNT(*) AS c FROM 行程版本 WHERE 行程键=? AND 是否当前=1", (行程键,)
    ).fetchone()["c"]
    if 当前行 > 1:
        问题.append("双当前版本")
    链, 版本行 = _链摘要(conn, 基行)
    版本序列 = [基行["版本"]] + [v["版本"] for v in 版本行]
    if 版本序列 != sorted(版本序列) or len(set(版本序列)) != len(版本序列):
        问题.append("版本号非严格递增")
    if 封印:
        现基 = 基行摘要(基行)
        if 现基 != 封印["基行摘要"]:
            问题.append("基行被改写")
        if 链 != 封印["链摘要"]:
            问题.append("版本链摘要不符(存在绕过审计的改写)")
        if 封印["封印版本"] > (版本行[-1]["版本"] if 版本行 else 基行["版本"]):
            问题.append("封印版本超前于版本链")
    return {"valid": not 问题, "问题": 问题, "链摘要": 链, "封印": dict(封印) if 封印 else None}


def 读状态(行程键: str) -> dict:
    """只读接口：行程键、封印态、主读出站站、拒绝或当前版本、valid。"""
    conn = 连接()
    try:
        基行 = conn.execute("SELECT * FROM 行程账 WHERE 行程键=?", (行程键,)).fetchone()
        if not 基行:
            return {
                "行程键": 行程键,
                "封印态": "不存在",
                "主读出站站": None,
                "主读版本": 0,
                "当前版本": None,
                "拒绝": None,
                "valid": False,
                "问题": ["行程不存在"],
            }
        当前 = 取当前(conn, 行程键)
        封印 = _封印行(conn, 行程键)
        校验 = 校验链(conn, 行程键)
        拒绝 = _最近拒绝(conn, 行程键)
        return {
            "行程键": 行程键,
            "封印态": 封印["封印态"] if 封印 else "未封印",
            "主读出站站": 当前["出站站点键"],
            "主读版本": 当前["版本"],
            "当前版本": 当前["版本"],
            "拒绝": 拒绝,
            "valid": 校验["valid"],
            "问题": 校验["问题"],
            "封印版本": 封印["封印版本"] if 封印 else None,
            "基行摘要": 封印["基行摘要"] if 封印 else None,
            "链摘要": 校验["链摘要"],
            "口径": "版本追加",
        }
    finally:
        conn.close()


def 封印(行程键: str, 备注: str = "") -> dict:
    """封住行程：记下基行摘要与当前链摘要。已封印则幂等重封（只滚链摘要）。

    基行只读，绝不改写；封印不产生新版本行。
    """
    conn = 连接(自动提交=True)
    try:
        with 写事务(conn):
            return _封印内(conn, 行程键, 备注)
    finally:
        conn.close()


def _封印内(conn, 行程键: str, 备注: str = "") -> dict:
    基行 = conn.execute("SELECT * FROM 行程账 WHERE 行程键=?", (行程键,)).fetchone()
    if not 基行:
        return {"ok": False, "valid": False, "原因": "行程不存在", "行程键": 行程键}
    当前 = 取当前(conn, 行程键)
    链, _ = _链摘要(conn, 基行)
    基摘 = 基行摘要(基行)
    时刻 = 此刻()
    已有 = _封印行(conn, 行程键)
    动作 = "重封" if 已有 else "封印"
    conn.execute(
        """INSERT INTO 行程封印(行程键,封印态,封印版本,基行摘要,链摘要,封印时刻,更新处理时)
           VALUES (?, '已封印', ?, ?, ?, COALESCE(?, ?), ?)
           ON CONFLICT(行程键) DO UPDATE SET
             封印态='已封印', 封印版本=excluded.封印版本,
             基行摘要=excluded.基行摘要, 链摘要=excluded.链摘要,
             更新处理时=excluded.更新处理时""",
        (行程键, 当前["版本"], 基摘, 链, 已有["封印时刻"] if 已有 else None, 时刻, 时刻),
    )
    _记审计(
        conn,
        行程键,
        动作,
        当前["版本"],
        {"备注": 备注, "链摘要": 链, "基行摘要": 基摘},
        时刻,
    )
    return {
        "ok": True,
        "valid": True,
        "行程键": 行程键,
        "封印态": "已封印",
        "封印版本": 当前["版本"],
        "主读出站站": 当前["出站站点键"],
        "当前版本": 当前["版本"],
        "链摘要": 链,
        "动作": 动作,
    }


def 改出站(行程键: str, 出站站点键: str, 出站事件时: str, 依据: str = "人工修正") -> dict:
    """成对后改出站：版本追加，基行保留，新版本行标当前。禁止原地覆盖。"""
    conn = 连接(自动提交=True)
    try:
        with 写事务(conn):
            return _改出站内(conn, 行程键, 出站站点键, 出站事件时, 依据)
    finally:
        conn.close()


def _改出站内(conn, 行程键, 出站站点键, 出站事件时, 依据) -> dict:
    基行 = conn.execute("SELECT * FROM 行程账 WHERE 行程键=?", (行程键,)).fetchone()
    if not 基行:
        return {"ok": False, "valid": False, "原因": "行程不存在", "行程键": 行程键}
    if not conn.execute("SELECT 1 FROM 站点 WHERE 站点键=?", (出站站点键,)).fetchone():
        return {"ok": False, "valid": False, "原因": f"未知站点:{出站站点键}", "行程键": 行程键}
    try:
        处理时 = 此刻()
        历时 = max(0, 时间.差秒(基行["进站事件时"], 出站事件时))
    except Exception as e:
        return {"ok": False, "valid": False, "原因": f"事件时非法:{e}", "行程键": 行程键}

    当前 = 取当前(conn, 行程键)
    if (
        当前["出站站点键"] == 出站站点键
        and 当前["出站事件时"] == 出站事件时
    ):
        # 与当前版本一致：命中，不新增版本行
        return {
            "ok": True,
            "valid": True,
            "行程键": 行程键,
            "命中": True,
            "追加版本": False,
            "当前版本": 当前["版本"],
            "主读出站站": 当前["出站站点键"],
            "拒绝": None,
        }

    新版本 = 当前["版本"] + 1
    conn.execute(
        "UPDATE 行程版本 SET 是否当前=0 WHERE 行程键=? AND 是否当前=1", (行程键,)
    )
    conn.execute(
        """INSERT INTO 行程版本(行程键,版本,卡号,出站事件编号,出站站点键,出站事件时,历时秒,依据,是否当前,处理时)
           VALUES (?,?,?,?,?,?,?,?,1,?)""",
        (
            行程键,
            新版本,
            基行["卡号"],
            当前["出站事件编号"],
            出站站点键,
            出站事件时,
            历时,
            依据,
            处理时,
        ),
    )
    封印 = _封印行(conn, 行程键)
    if 封印:
        链, _ = _链摘要(conn, 基行)
        conn.execute(
            "UPDATE 行程封印 SET 封印版本=?, 链摘要=?, 更新处理时=? WHERE 行程键=?",
            (新版本, 链, 处理时, 行程键),
        )
    _记审计(
        conn,
        行程键,
        "封印后修正" if 封印 else "版本追加",
        新版本,
        {
            "依据": 依据,
            "旧": {"出站站点键": 当前["出站站点键"], "出站事件时": 当前["出站事件时"]},
            "新": {"出站站点键": 出站站点键, "出站事件时": 出站事件时},
        },
        处理时,
    )
    return {
        "ok": True,
        "valid": True,
        "行程键": 行程键,
        "命中": False,
        "追加版本": True,
        "当前版本": 新版本,
        "主读出站站": 出站站点键,
        "主读出站时": 出站事件时,
        "拒绝": None,
    }


def 重放(行程键: str, 出站站点键: str, 出站事件时: str, 依据: str = "装载重放") -> dict:
    """装载重放隔离：封印行程只读，一致命中、冲突拒绝并入旁路，永不覆盖。"""
    conn = 连接(自动提交=True)
    try:
        with 写事务(conn):
            return _重放内(conn, 行程键, 出站站点键, 出站事件时, 依据)
    finally:
        conn.close()


def _重放内(conn, 行程键: str, 出站站点键: str, 出站事件时: str, 依据: str) -> dict:
    基行 = conn.execute("SELECT * FROM 行程账 WHERE 行程键=?", (行程键,)).fetchone()
    if not 基行:
        return {"ok": False, "有效": False, "原因": "行程不存在", "行程键": 行程键}
    当前 = 取当前(conn, 行程键)
    封印记录 = _封印行(conn, 行程键)
    处理时 = 此刻()
    一致 = (
        当前["出站站点键"] == 出站站点键
        and 当前["出站事件时"] == 出站事件时
    )
    if 封印记录 and 一致:
        _记审计(conn, 行程键, "重放命中", 当前["版本"], {"依据": 依据}, 处理时)
        return {
            "ok": True,
            "有效": True,
            "行程键": 行程键,
            "接受": True,
            "命中": True,
            "拒绝": None,
            "当前版本": 当前["版本"],
            "主读出站站": 当前["出站站点键"],
        }
    if 封印记录 and not 一致:
        conn.execute(
            "INSERT INTO 旁路匣(原因, 卡号, 事件编号, 载荷, 时刻) VALUES (?,?,?,?,?)",
            (
                "封印冲突重放",
                基行["卡号"],
                当前["出站事件编号"],
                json.dumps(
                    {
                        "行程键": 行程键,
                        "重放出站": 出站站点键,
                        "重放出站时": 出站事件时,
                        "封印版本": 封印记录["封印版本"],
                        "主读出站站": 当前["出站站点键"],
                    },
                    ensure_ascii=False,
                ),
                处理时,
            ),
        )
        _记审计(
            conn,
            行程键,
            "重放拒绝",
            当前["版本"],
            {"依据": 依据, "拒绝": "封印冲突", "重放出站": 出站站点键},
            处理时,
        )
        return {
            "ok": False,
            "有效": False,
            "行程键": 行程键,
            "接受": False,
            "命中": False,
            "拒绝": "封印冲突",
            "当前版本": 当前["版本"],
            "主读出站站": 当前["出站站点键"],
        }
    if 一致:
        _记审计(conn, 行程键, "重放命中", 当前["版本"], {"依据": 依据}, 处理时)
        return {
            "ok": True,
            "有效": True,
            "行程键": 行程键,
            "接受": True,
            "命中": True,
            "拒绝": None,
            "当前版本": 当前["版本"],
            "主读出站站": 当前["出站站点键"],
        }
    # 未封印且内容不同：走版本追加（全局口径），绝不覆盖基行
    结果 = _改出站内(conn, 行程键, 出站站点键, 出站事件时, 依据)
    return {
        "ok": 结果.get("ok", False),
        "有效": 结果.get("valid", False),
        "行程键": 行程键,
        "接受": 结果.get("ok", False),
        "命中": False,
        "拒绝": 结果.get("拒绝"),
        "当前版本": 结果.get("当前版本"),
        "主读出站站": 结果.get("主读出站站"),
    }


def 列版本(行程键: str) -> list:
    conn = 连接()
    try:
        基行 = conn.execute("SELECT * FROM 行程账 WHERE 行程键=?", (行程键,)).fetchone()
        if not 基行:
            return []
        out = [
            {
                "版本": 基行["版本"],
                "出站站点键": 基行["出站站点键"],
                "出站事件时": 基行["出站事件时"],
                "历时秒": 基行["历时秒"],
                "依据": "成对物化",
                "是否当前": 0,
                "处理时": 基行["处理时"],
                "基行": True,
            }
        ]
        for v in conn.execute(
            "SELECT * FROM 行程版本 WHERE 行程键=? ORDER BY 版本 ASC", (行程键,)
        ):
            out.append(
                {
                    "版本": v["版本"],
                    "出站站点键": v["出站站点键"],
                    "出站事件时": v["出站事件时"],
                    "历时秒": v["历时秒"],
                    "依据": v["依据"],
                    "是否当前": v["是否当前"],
                    "处理时": v["处理时"],
                    "基行": False,
                }
            )
        return out
    finally:
        conn.close()


def 列审计(行程键: str, 限: int = 50) -> list:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 封印审计 WHERE 行程键=? ORDER BY 编号 DESC LIMIT ?",
                (行程键, 限),
            )
        ]
    finally:
        conn.close()


def 全量状态() -> list:
    conn = 连接()
    try:
        键 = [
            r["行程键"]
            for r in conn.execute("SELECT 行程键 FROM 行程账 ORDER BY 处理时 DESC LIMIT 200")
        ]
    finally:
        conn.close()
    return [读状态(k) for k in 键]
