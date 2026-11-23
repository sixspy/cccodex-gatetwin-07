#!/usr/bin/env python3
"""经真实 uvicorn 端口验证：/api/换绑 读写、写闸 400、装载同票换绑、贯验。"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
import urllib.parse

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
FIXTURES = os.path.join(BACKEND, "..", "fixtures")
数据目录 = tempfile.mkdtemp(prefix="gatetwin-http-")
env = dict(os.environ, 数据目录=数据目录, 夹具目录=FIXTURES)
端口 = 18607

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", BACKEND,
     "--host", "127.0.0.1", "--port", str(端口)],
    cwd=BACKEND, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
失败 = []
try:
    健康url = "http://127.0.0.1:%d/api%s" % (端口, urllib.parse.quote("/健康", safe="/"))
    for _ in range(50):
        try:
            urllib.request.urlopen(健康url, timeout=1)
            break
        except Exception:
            time.sleep(0.3)
    else:
        proc.terminate()
        print(proc.stdout.read())
        raise RuntimeError("服务未起")

    def 调(方法, 路径, 体=None):
        if "?" in 路径:
            base, qs = 路径.split("?", 1)
            qs = urllib.parse.urlencode(urllib.parse.parse_qsl(qs))
            路径 = base + "?" + qs
            url = ("http://127.0.0.1:%d/api%s?%s"
                   % (端口, urllib.parse.quote(base, safe="/"), qs))
        else:
            url = "http://127.0.0.1:%d/api%s" % (端口, urllib.parse.quote(路径, safe="/"))
        req = urllib.request.Request(
            url, method=方法,
            data=json.dumps(体).encode() if 体 is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            # 写闸拒收：FastAPI 把报告包在 detail 里（JSON 字符串）
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                try:
                    body = json.loads(body["detail"])
                except Exception:
                    pass
            return e.code, body

    # 1. 先灌一条在途腿
    s, r = 调("POST", "/装载", {"批次编号": "http-1", "事件": [
        {"事件编号": "h1", "卡号": "卡旧", "站点键": "站A", "方向": "进站",
         "事件时": "2026-11-23T08:00:00Z", "处理时": "2026-11-23T08:00:01Z"}]})
    assert s == 200 and r["开腿"] == 1, r

    # 2. 写闸生效
    s, r = 调("POST", "/换绑", {"旧卡": "卡旧", "新卡": "卡新", "事件时": "2026-11-23T08:30:00Z"})
    assert s == 200 and r["valid"] is True and len(r["处置列表"]) == 1, (s, r)
    换绑键 = r["换绑键"]
    print("✓ POST /换绑 生效：", 换绑键, r["处置列表"][0]["旁路原因"])

    # 3. 写闸拒收 → 400，且 valid=false 已留审计
    s, r = 调("POST", "/换绑", {"旧卡": "卡同", "新卡": "卡同"})
    assert s == 400 and r["valid"] is False and r["处置列表"] == [], (s, r)
    print("✓ POST /换绑 同卡拒收 400，闸门：", r["审计"]["闸门"])

    # 4. 只读接口：旧卡/新卡/处置列表/审计/valid
    s, r = 调("GET", "/换绑?旧卡=" + urllib.parse.quote("卡旧"))
    assert s == 200 and len(r) == 1, (s, r)
    for f in ("旧卡", "新卡", "处置列表", "审计", "valid"):
        assert f in r[0], f
    assert r[0]["valid"] is True
    print("✓ GET /换绑 只读字段齐全：旧卡/新卡/处置列表/审计/valid")

    # 5. 换绑后旧卡出站 → 孤儿（不配套已切断腿）
    s, r = 调("POST", "/装载", {"批次编号": "http-2", "事件": [
        {"事件编号": "h2", "卡号": "卡旧", "站点键": "站B", "方向": "出站",
         "事件时": "2026-11-23T09:00:00Z", "处理时": "2026-11-23T09:00:01Z"}]})
    assert r["成对"] == 0 and r["旁路"] == 1, r
    s, 行程 = 调("GET", "/行程账")
    assert len(行程) == 0, 行程
    print("✓ 换绑后旧卡出站 → 孤儿旁路，无行程")

    # 6. 新卡进站再出站 → 自成对，行程卡号=新卡
    s, r = 调("POST", "/装载", {"批次编号": "http-3", "事件": [
        {"事件编号": "h3", "卡号": "卡新", "站点键": "站A", "方向": "进站",
         "事件时": "2026-11-23T09:10:00Z", "处理时": "2026-11-23T09:10:01Z"},
        {"事件编号": "h4", "卡号": "卡新", "站点键": "站C", "方向": "出站",
         "事件时": "2026-11-23T09:20:00Z", "处理时": "2026-11-23T09:20:01Z"}]})
    assert r["成对"] == 1, r
    s, 行程 = 调("GET", "/行程账")
    assert 行程[0]["卡号"] == "卡新" and 行程[0]["进站事件编号"] == "h3", 行程
    print("✓ 新卡出站自成对，行程卡号=卡新（不与原进站 h1 成对）")

    # 7. 开腿账页带旁路原因
    s, 腿 = 调("GET", "/开腿账")
    h1腿 = [x for x in 腿 if x["开腿键"] == "腿-h1"][0]
    assert h1腿["旁路原因"] == "换绑切断" and h1腿["卡号"] == "卡旧", h1腿
    print("✓ /开腿账 暴露旁路原因，开腿行卡号未改写")

    # 8. 贯验通过
    s, r = 调("POST", "/贯验")
    assert s == 200 and r["是否通过"] is True, r
    print("✓ /贯验 通过：", r["说明"])

    # 9. 夹具装载（换绑切断样例）
    s, r = 调("POST", "/装载/夹具?名=" + urllib.parse.quote("换绑切断样例"))
    assert s == 200 and r["换绑"] == 1, (s, r)
    print("✓ 换绑切断样例夹具装载：换绑1，明细", [d.get("命运") for d in r["明细"]])

    print("\nHTTP 冒烟全部通过")
except Exception as e:
    失败.append(str(e))
    raise
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
if 失败:
    sys.exit(1)
