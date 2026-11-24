"""既有主链回归：四个夹具依次装载 + 总览/贯验，确认封印改造未破坏 happy path。"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["数据目录"] = tempfile.mkdtemp(prefix="gatetwin-reg-")
os.environ["夹具目录"] = str(Path(__file__).resolve().parent.parent / "fixtures")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

c = TestClient(app)
c.__enter__()


def 断言(条件, 说明):
    if not 条件:
        print(f"✗ {说明}")
        raise SystemExit(1)
    print(f"✓ {说明}")


for 名 in ("成对样例", "缺腿超时样例", "重复进站样例", "出站孤儿样例"):
    r = c.post("/api/装载/夹具", params={"名": 名}).json()
    print(f"{名}: 入流{r['入流']} 开腿{r['开腿']} 成对{r['成对']} 旁路{r['旁路']} 超时{r['超时旁路']}")

总 = c.get("/api/总览").json()
print("总览:", {k: 总[k] for k in ("刷卡点", "行程数", "在途开腿", "旁路匣")})
断言(总["行程数"] == 4, "成对样例2 + 缺腿1 + 重复进站1 = 4 笔行程")
断言(总["在途开腿"] == 0, "缺腿样例的 t1 已被超时旁路，无在途开腿")

验 = c.post("/api/贯验").json()
print("贯验:", 验["是否通过"], 验["说明"])
断言(验["是否通过"], "四夹具跑完后贯验通过")

# 缺腿 / 孤儿 / 重复进站 都进了旁路匣
旁因 = {r["原因"] for r in c.get("/api/旁路匣").json()}
断言({"缺腿超时", "出站孤儿", "重复进站"} <= 旁因, f"旁路原因齐全：{sorted(旁因)}")

# 既有行程全部自动封印且链有效
for r in c.get("/api/行程账").json():
    状 = c.get("/api/行程封印", params={"行程键": r["行程键"]}).json()
    断言(状["封印态"] == "已封印" and 状["valid"], f"{r['行程键']} 已封印且链有效")

print("\n回归通过")
