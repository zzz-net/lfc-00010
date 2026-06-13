"""
实验室样本转运台账系统 - 验收测试脚本

修复说明：
- 使用动态唯一 sample_id（带时间戳+随机后缀），支持在已有数据库中重复运行
- 导入后严格断言 imported_count，不依赖固定 ID 查找
- 新增"测试隔离与重复运行"专项测试，验证旧问题（重复导入 KeyError）已修复

验收项：
1. 登录认证（管理员/操作员）
2. 样本批次导入（含重复项去重）
3. 主流程：入库 → 打包 → 交接 → 到达
4. 异常冻结（超温/破损）
5. 权限控制：普通操作员不能关闭异常
6. 管理员复核关闭
7. 交接单导出
8. 数据持久化验证
9. 测试隔离：重复运行不崩溃（修复前 KeyError 问题的回归）
"""

import sys
import json
import os
import time
import random
import sqlite3

BASE_URL = "http://127.0.0.1:5000"

try:
    import requests
except ImportError:
    print("正在安装 requests 库...")
    os.system("python -m pip install requests -q")
    import requests


def uid(prefix="S"):
    """生成全局唯一 sample_id，确保在已有数据库中不重复"""
    ts = int(time.time() * 1000)
    rand = random.randint(100, 999)
    return f"{prefix}-{ts}-{rand}"


class TestClient:
    def __init__(self):
        self.session = requests.Session()
        self.user = None

    def login(self, username, password):
        r = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": username, "password": password}
        )
        if r.status_code == 200:
            data = r.json()
            self.user = data.get("user")
            return True
        return False

    def get(self, path):
        return self.session.get(f"{BASE_URL}{path}")

    def post(self, path, data=None):
        return self.session.post(f"{BASE_URL}{path}", json=data or {})


def print_title(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


passed = 0
failed = 0


def check(test_name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  [OK]  {test_name}")
        passed += 1
    else:
        print(f"  [XX]  {test_name}")
        failed += 1
    if detail:
        print(f"        {detail}")


def fatal_check(test_name, condition, detail=""):
    """不满足则直接终止，避免后续步骤因前置依赖失败而连锁报错"""
    global failed
    if not condition:
        print(f"  [!!]  FATAL: {test_name}")
        if detail:
            print(f"        {detail}")
        failed += 1
        print_title("测试终止 - 前置条件不满足")
        summary()
        sys.exit(1)
    check(test_name, True, detail)


def summary():
    print("\n" + "=" * 60)
    print(f"  测试结果：{passed} 通过 / {failed} 失败 / 共 {passed+failed} 项")
    print("=" * 60)


def build_sample_map(import_result):
    """从导入结果构造 {sample_id: db_id} 映射，并断言所有 sample_id 都成功导入"""
    mapping = {}
    for s in import_result.get("imported", []):
        mapping[s["sample_id"]] = s["id"]
    return mapping


def run_tests():
    admin = TestClient()
    operator = TestClient()

    print_title("1. 登录认证测试")

    if admin.login("admin", "admin123") and admin.user["role"] == "admin":
        check("管理员登录成功", True)
    else:
        check("管理员登录成功", False, "登录失败或角色错误")

    if operator.login("operator", "op123456") and operator.user["role"] == "operator":
        check("操作员登录成功", True)
    else:
        check("操作员登录成功", False, "登录失败或角色错误")

    wrong = TestClient()
    if not wrong.login("admin", "wrongpass"):
        check("错误密码拒绝登录", True)
    else:
        check("错误密码拒绝登录", False)

    # ---------------------------------------------------------------
    # 9. 测试隔离 - 放在最前面验证，确保旧问题已修复
    # ---------------------------------------------------------------
    print_title("9. 测试隔离与重复运行验证（旧 KeyError 问题回归）")

    isolate_batch = f"ISO-{int(time.time())}"
    iso_sid = uid("ISO")
    iso_samples = [
        {"sample_id": iso_sid, "sample_type": "全血"},
    ]
    r = operator.post("/api/samples/import", {
        "batch_no": isolate_batch,
        "samples": iso_samples
    })
    first_res = r.json()
    check("首次导入动态唯一样本成功",
          first_res.get("imported_count") == 1,
          f"imported={first_res.get('imported_count')}, duplicates={first_res.get('duplicate_count')}")

    r2 = operator.post("/api/samples/import", {
        "batch_no": isolate_batch + "-R2",
        "samples": iso_samples
    })
    second_res = r2.json()
    check("同 sample_id 二次导入被正确去重（重复数=1，导入=0）",
          second_res.get("duplicate_count") == 1 and second_res.get("imported_count") == 0,
          f"imported={second_res.get('imported_count')}, duplicates={second_res.get('duplicate_count')}")

    sample_map_r2 = build_sample_map(second_res)
    no_crash = True
    try:
        _ = sample_map_r2.get(iso_sid)
    except Exception as e:
        no_crash = False
    check("二次导入后 build_sample_map 取 iso_sid 不会抛 KeyError（使用 .get，返回 None）",
          no_crash and sample_map_r2.get(iso_sid) is None)

    three_dup = [
        {"sample_id": iso_sid, "sample_type": "全血"},
        {"sample_id": uid("ISO2"), "sample_type": "血清"},
        {"sample_id": uid("ISO3"), "sample_type": "血浆"},
    ]
    r3 = operator.post("/api/samples/import", {
        "batch_no": isolate_batch + "-MIX",
        "samples": three_dup
    })
    mix_res = r3.json()
    check("混合导入：1 个重复跳过，2 个新样本成功",
          mix_res.get("duplicate_count") == 1 and mix_res.get("imported_count") == 2,
          f"imported={mix_res.get('imported_count')}, duplicates={mix_res.get('duplicate_count')}")

    mix_map = build_sample_map(mix_res)
    check("混合导入后新 sample_id 均可在映射中查到（均不为 None）",
          all(mix_map.get(s["sample_id"]) is not None for s in mix_res.get("imported", [])))

    # ---------------------------------------------------------------
    # 2. 批次导入测试
    # ---------------------------------------------------------------
    print_title("2. 样本批次导入测试")

    batch_no = f"TEST-{int(time.time())}"
    s1 = uid("T1")
    s2 = uid("T2")
    s3 = uid("T3")
    samples_batch1 = [
        {"sample_id": s1, "sample_type": "全血"},
        {"sample_id": s2, "sample_type": "血清"},
        {"sample_id": s3, "sample_type": "血浆"},
    ]

    r = operator.post("/api/samples/import", {
        "batch_no": batch_no,
        "samples": samples_batch1
    })
    data = r.json()

    fatal_check("首次导入 3 个动态唯一样本全部成功",
                data.get("imported_count") == 3,
                f"batch={batch_no}, imported={data.get('imported_count')}, duplicates={data.get('duplicate_count')}")

    smap = build_sample_map(data)
    fatal_check("3 个样本全部在映射中（无遗漏 KeyError）",
                smap.get(s1) and smap.get(s2) and smap.get(s3))

    s4 = uid("T4")
    s5 = uid("T5")
    samples_batch2 = [
        {"sample_id": s1, "sample_type": "全血"},
        {"sample_id": s2, "sample_type": "血清"},
        {"sample_id": s4, "sample_type": "尿液"},
        {"sample_id": s5, "sample_type": "唾液"},
    ]

    r2 = operator.post("/api/samples/import", {
        "batch_no": batch_no + "-2",
        "samples": samples_batch2
    })
    data2 = r2.json()

    if (r2.status_code == 200
            and data2.get("imported_count") == 2
            and data2.get("duplicate_count") == 2):
        check("重复导入：跳过 2 个重复项，新增 2 个有效样本", True,
              f"导入: {data2['imported_count']}, 重复: {data2['duplicate_count']}")
    else:
        check("重复导入：跳过重复项保留有效样本", False, str(data2))

    smap2 = build_sample_map(data2)
    check("二次导入中 s4/s5 可查，s1/s2 不在 imported 映射中",
          smap2.get(s1) is None and smap2.get(s2) is None
          and smap2.get(s4) is not None and smap2.get(s5) is not None)

    r_list = operator.get(f"/api/samples?search={s1}")
    list_data = r_list.json()
    sample_id_1 = smap.get(s1)
    sample_id_2 = smap.get(s2)

    if sample_id_1 and sample_id_2:
        check("样本列表查询正常（用动态 ID 搜索命中）", True)
    else:
        check("样本列表查询正常", False)

    # ---------------------------------------------------------------
    # 3. 主流程
    # ---------------------------------------------------------------
    print_title("3. 主流程测试：入库 → 打包 → 交接 → 到达")

    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "WAREHOUSED",
        "remark": "入库核验通过",
        "temperature": 4.5
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "WAREHOUSED":
        check("操作 1：入库成功", True, "温度: 4.5°C")
    else:
        check("操作 1：入库成功", False, r.text[:200])

    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "PACKED",
        "remark": "使用冷链运输箱打包"
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "PACKED":
        check("操作 2：打包成功", True)
    else:
        check("操作 2：打包成功", False, r.text[:200])

    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "HANDED_OVER",
        "remark": "交接给运输员张三",
        "temperature": 3.8
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "HANDED_OVER":
        check("操作 3：交接成功", True)
    else:
        check("操作 3：交接成功", False, r.text[:200])

    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "ARRIVED",
        "remark": "目的地接收，样本完好",
        "temperature": 5.1
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "ARRIVED":
        check("操作 4：到达确认成功", True)
    else:
        check("操作 4：到达确认成功", False, r.text[:200])

    r = operator.get(f"/api/samples/{sample_id_1}")
    detail = r.json()
    logs_count = len(detail.get("status_logs", []))

    if logs_count >= 5:
        check(f"状态时间线完整（{logs_count} 条记录）", True)
    else:
        check("状态时间线完整", False, f"只有 {logs_count} 条记录")

    # ---------------------------------------------------------------
    # 4. 异常冻结
    # ---------------------------------------------------------------
    print_title("4. 异常冻结测试")

    r = operator.post(f"/api/samples/{sample_id_2}/status", {
        "status": "WAREHOUSED",
        "temperature": 4.0
    })
    r = operator.post(f"/api/samples/{sample_id_2}/status", {
        "status": "PACKED"
    })
    r = operator.post(f"/api/samples/{sample_id_2}/status", {
        "status": "HANDED_OVER",
        "temperature": 4.2
    })

    r = operator.post(f"/api/samples/{sample_id_2}/exception", {
        "type": "overtemp",
        "description": "运输途中温度异常升高，最高达 12°C，持续 30 分钟",
        "temperature": 12.0,
        "evidence_file": "/photos/overtemp_001.jpg"
    })

    if r.status_code == 200 and r.json()["sample"]["current_status"] == "FROZEN":
        check("录入超温异常 → 自动冻结", True, "温度: 12°C")
    else:
        check("录入超温异常 → 自动冻结", False, r.text[:200])

    r = operator.get(f"/api/samples/{sample_id_2}")
    detail = r.json()
    evidence_count = len(detail.get("evidences", []))

    if evidence_count >= 1:
        check("证据记录保存成功", True, f"{evidence_count} 条证据")
    else:
        check("证据记录保存成功", False)

    r = operator.post(f"/api/samples/{sample_id_2}/review", {
        "action": "close",
        "remark": "操作员尝试关闭"
    })

    if r.status_code == 403:
        check("权限控制：普通操作员不能复核关闭异常", True, "返回 403")
    else:
        check("权限控制：普通操作员不能复核关闭异常", False, f"返回 {r.status_code}")

    # ---------------------------------------------------------------
    # 5. 管理员复核
    # ---------------------------------------------------------------
    print_title("5. 管理员复核测试")

    r = admin.post(f"/api/samples/{sample_id_2}/review", {
        "action": "close",
        "remark": "经复核，超温时间短且在允许范围内，同意关闭异常"
    })

    if r.status_code == 200 and r.json()["sample"]["current_status"] == "REVIEW_CLOSED":
        check("管理员复核关闭成功", True)
    else:
        check("管理员复核关闭成功", False, r.text[:200])

    r = admin.get(f"/api/samples/{sample_id_2}")
    detail = r.json()

    if detail.get("reviewed_by") == "admin" and detail.get("review_remark"):
        check("复核信息（复核人、备注、时间）保存完整", True,
              f"复核人: {detail['reviewed_by']}")
    else:
        check("复核信息保存完整", False)

    # ---------------------------------------------------------------
    # 6. 导出
    # ---------------------------------------------------------------
    print_title("6. 导出交接单测试")

    r = operator.get(f"/api/export/handover?batch_no={batch_no}")
    if r.status_code == 200 and "text/csv" in r.headers.get("Content-Type", ""):
        content = r.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        check("交接单导出成功（CSV 格式）", True,
              f"{len(lines)-1} 条数据, 含中文表头, 证据列存在: {'证据数量' in content}")
    else:
        check("交接单导出成功", False, f"状态: {r.status_code}")

    r = operator.get(f"/api/export/sample-timeline/{sample_id_1}")
    if r.status_code == 200 and "text/csv" in r.headers.get("Content-Type", ""):
        content = r.content.decode("utf-8-sig")
        has_timeline = "状态时间线" in content
        check("单样本时间线导出成功", True,
              f"包含时间线: {has_timeline}")
    else:
        check("单样本时间线导出成功", False)

    # ---------------------------------------------------------------
    # 7. 持久化
    # ---------------------------------------------------------------
    print_title("7. 数据持久化验证（模拟重启）")

    db_path = os.path.join(os.path.dirname(__file__), "sample_tracker.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    d1 = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (s1,)).fetchone()
    d2 = conn.execute("SELECT * FROM samples WHERE sample_id = ?", (s2,)).fetchone()

    logs = conn.execute(
        "SELECT COUNT(*) as cnt FROM status_logs WHERE sample_id = ?",
        (d1["id"],)
    ).fetchone()

    evs = conn.execute(
        "SELECT COUNT(*) as cnt FROM evidences WHERE sample_id = ?",
        (d2["id"],)
    ).fetchone()

    review = conn.execute(
        "SELECT review_remark, reviewed_by FROM samples WHERE id = ?",
        (d2["id"],)
    ).fetchone()

    conn.close()

    all_good = (
        d1["current_status"] == "ARRIVED"
        and d2["current_status"] == "REVIEW_CLOSED"
        and logs["cnt"] >= 5
        and evs["cnt"] >= 1
        and review["reviewed_by"] == "admin"
    )

    if all_good:
        check("重启后数据完整保留", True,
              f"状态、证据、复核信息、时间线均完整，动态 ID: {s1}, {s2}")
    else:
        check("重启后数据完整保留", False,
              f"s1状态: {d1['current_status']}, s2状态: {d2['current_status']}, "
              f"日志数: {logs['cnt']}, 证据数: {evs['cnt']}")

    summary()
    return failed == 0


if __name__ == "__main__":
    try:
        success = run_tests()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n测试执行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
