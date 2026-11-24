"""按夹具「成对后改出站样例」验证甲/乙可区分口径 + 重放冲突。

夹具即规格：甲主读出站站不变且无版本行；乙主读出站站已变且有版本行；
重放冲突拒绝且不改主读。
"""
import json
import os
import sys
import tempfile
from pathlib import Path

根 = Path(__file__).resolve().parent.parent
夹具 = json.loads((根 / "fixtures" / "成对后改出站样例.json").read_text(encoding="utf-8"))

os.environ["数据目录"] = tempfile.mkdtemp(prefix="gatetwin-fix-")
os.environ["夹具目录"] = str(根 / "fixtures")
sys.path.insert(0, str(根 / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
c.__enter__()


def 断言(条件, 说明):
    if not 条件:
        print(f"✗ {说明}")
        raise SystemExit(1)
    print(f"✓ {说明}")


def 行(键):
    return next(r for r in c.get("/api/行程账").json() if r["行程键"] == 键)


def 版(键):
    return c.get("/api/行程封印/版本", params={"行程键": 键}).json()


c.post("/api/装载", json=夹具["装载"])

甲 = 夹具["甲"]
r甲 = 行(甲["行程键"])
断言(r甲["出站站点键"] == 甲["期望"]["主读出站站不变"], f"甲主读出站站不变={r甲['出站站点键']}")
断言(len(版(甲["行程键"])) == 1 and 甲["期望"]["有版本行"] is False, "甲无版本行")
断言(r甲["版本"] == 甲["期望"]["当前版本"], "甲当前版本=1")

乙 = 夹具["乙"]
c.post("/api/行程封印/改出站", json={"行程键": 乙["行程键"], **乙["修正"]})
r乙 = 行(乙["行程键"])
断言(r乙["出站站点键"] == 乙["期望"]["主读出站站变为"], f"乙主读出站站已变={r乙['出站站点键']}")
断言(r乙["基行出站站点键"] == 乙["期望"]["基行出站站保留"], "乙基行出站站保留")
断言(len(版(乙["行程键"])) == 2 and 乙["期望"]["有版本行"] is True, "乙有版本行（2 条）")
断言(r乙["版本"] == 乙["期望"]["当前版本"], "乙当前版本=2")
状乙 = c.get("/api/行程封印", params={"行程键": 乙["行程键"]}).json()
断言(状乙["主读出站站"] == "站C" and 状乙["valid"], "乙封印态主读=站C 且 valid")

冲 = 夹具["重放冲突"]
旁 = len(c.get("/api/旁路匣").json())
r = c.post("/api/行程封印/重放", json={"行程键": 冲["行程键"], **冲["载荷"]}).json()
断言(r["接受"] == 冲["期望"]["接受"] and r["拒绝"] == 冲["期望"]["拒绝"], "重放冲突被拒绝")
断言(行(冲["行程键"])["出站站点键"] == 冲["期望"]["主读出站站不变"], "重放冲突不改主读")
断言(len(c.get("/api/旁路匣").json()) == 旁 + 1, "重放冲突落旁路")
断言(len(版(冲["行程键"])) == 1, "重放冲突不新增版本行")

验 = c.post("/api/贯验").json()
断言(验["是否通过"], f"贯验通过（{验['说明']}）")

print("\n夹具口径通过")
