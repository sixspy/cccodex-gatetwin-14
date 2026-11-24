import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import 夹具目录, 连接
from app.services import 装载, 贯验, 目录, 封印

路由 = APIRouter(prefix="/api")


class 装载请求(BaseModel):
    批次编号: str = ""
    事件: list = Field(default_factory=list)


class 封印请求(BaseModel):
    行程键: str
    备注: str = ""


class 改出站请求(BaseModel):
    行程键: str
    出站站点键: str
    出站事件时: str
    依据: str = "人工修正"


class 重放请求(BaseModel):
    行程键: str
    出站站点键: str
    出站事件时: str
    依据: str = "装载重放"


@路由.get("/健康")
def 健康():
    return {
        "正常": True,
        "项目": "闸对",
        "骨架": "刷卡点装载→同卡进站出站成对物化→缺腿异向超时旁路→行程账与刷卡点互证",
    }


@路由.get("/总览")
def 取总览():
    return 目录.总览()


@路由.get("/站规")
def 站规():
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 站规")}
    finally:
        conn.close()


@路由.get("/线路")
def 列线路():
    conn = 连接()
    try:
        lines = [dict(r) for r in conn.execute("SELECT * FROM 线路 ORDER BY 线路键")]
        for ln in lines:
            ln["站点"] = [
                dict(s)
                for s in conn.execute(
                    "SELECT * FROM 站点 WHERE 线路键=? ORDER BY 站序", (ln["线路键"],)
                )
            ]
        return lines
    finally:
        conn.close()


@路由.get("/刷卡点")
def 列刷卡(命运: str = ""):
    conn = 连接()
    try:
        if 命运:
            rows = conn.execute(
                "SELECT * FROM 刷卡点 WHERE 命运=? ORDER BY 事件时 DESC LIMIT 200",
                (命运,),
            )
        else:
            rows = conn.execute("SELECT * FROM 刷卡点 ORDER BY 事件时 DESC LIMIT 200")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/开腿账")
def 列开腿(状态: str = ""):
    conn = 连接()
    try:
        if 状态:
            rows = conn.execute(
                "SELECT * FROM 开腿账 WHERE 状态=? ORDER BY 进站事件时 DESC", (状态,)
            )
        else:
            rows = conn.execute("SELECT * FROM 开腿账 ORDER BY 进站事件时 DESC")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/行程账")
def 列行程():
    conn = 连接()
    try:
        基行们 = conn.execute("SELECT * FROM 行程账 ORDER BY 处理时 DESC LIMIT 200").fetchall()
        out = []
        for 基行 in 基行们:
            d = dict(基行)
            主读 = 封印.取当前(conn, 基行["行程键"])
            d["基行出站站点键"] = 基行["出站站点键"]
            d["基行出站事件时"] = 基行["出站事件时"]
            d["出站站点键"] = 主读["出站站点键"]
            d["出站事件时"] = 主读["出站事件时"]
            d["历时秒"] = 主读["历时秒"]
            d["版本"] = 主读["版本"]
            d["是否基行"] = 主读["是否基行"]
            封 = conn.execute(
                "SELECT 封印态 FROM 行程封印 WHERE 行程键=?", (基行["行程键"],)
            ).fetchone()
            d["封印态"] = 封["封印态"] if 封 else "未封印"
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/旁路匣")
def 列旁路():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 旁路匣 ORDER BY 编号 DESC LIMIT 100")]
    finally:
        conn.close()


@路由.get("/批次")
def 列批次():
    conn = 连接()
    try:
        out = []
        for r in conn.execute("SELECT * FROM 装载批次 ORDER BY 时刻 DESC LIMIT 30"):
            d = dict(r)
            try:
                d["报告"] = json.loads(d["报告"])
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.post("/装载")
def 做装载(体: 装载请求):
    return 装载.装一批(体.model_dump())


@路由.post("/装载/夹具")
def 装夹具(名: str = "成对样例"):
    路径 = 夹具目录 / f"{名}.json"
    if not 路径.exists():
        raise HTTPException(404, f"夹具不存在:{名}")
    return 装载.装一批(json.loads(路径.read_text(encoding="utf-8")))


@路由.post("/贯验")
def 做贯验():
    return 贯验.跑贯验()


@路由.get("/贯验")
def 列贯验():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 行程贯验 ORDER BY 编号 DESC LIMIT 20")]
    finally:
        conn.close()


@路由.get("/行程封印")
def 取封印(行程键: str = ""):
    """只读：单行程封印态（行程键、封印态、主读出站站、拒绝/当前版本、valid）。"""
    if not 行程键:
        return 封印.全量状态()
    return 封印.读状态(行程键)


@路由.get("/行程封印/版本")
def 取版本(行程键: str):
    return 封印.列版本(行程键)


@路由.get("/行程封印/审计")
def 取审计(行程键: str):
    return 封印.列审计(行程键)


@路由.post("/行程封印")
def 做封印(体: 封印请求):
    return 封印.封印(体.行程键, 体.备注)


@路由.post("/行程封印/改出站")
def 做改出站(体: 改出站请求):
    return 封印.改出站(体.行程键, 体.出站站点键, 体.出站事件时, 体.依据)


@路由.post("/行程封印/重放")
def 做重放(体: 重放请求):
    return 封印.重放(体.行程键, 体.出站站点键, 体.出站事件时, 体.依据)


@路由.get("/空桩")
def 列空桩():
    from pathlib import Path
    import importlib

    root = Path(__file__).resolve().parent.parent / "modules"
    names = sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()
    )
    out = []
    for n in names:
        try:
            m = importlib.import_module(f"app.modules.{n}")
            out.append({"名": n, "导出": getattr(m, "NAME", n)})
        except Exception as e:
            out.append({"名": n, "错误": str(e)})
    return out
