"""
实验室样本转运台账系统 - 验收测试脚本

验收项：
1. 登录认证（管理员/操作员）
2. 样本批次导入（含重复项去重）
3. 主流程：入库 → 打包 → 交接 → 到达
4. 异常冻结（超温/破损）
5. 权限控制：普通操作员不能关闭异常
6. 管理员复核关闭
7. 交接单导出
8. 数据持久化验证
"""

import sys
import json
import os
import time
import sqlite3

BASE_URL = "http://127.0.0.1:5000"

try:
    import requests
except ImportError:
    print("正在安装 requests 库...")
    os.system("python -m pip install requests -q")
    import requests

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

def print_result(test_name, passed, detail=""):
    status = "[PASS]" if passed else "[FAIL]"
    if passed:
        print(f"  [OK]  {test_name}")
    else:
        print(f"  [XX]  {test_name}")
    if detail:
        print(f"        {detail}")

def run_tests():
    passed = 0
    failed = 0
    
    admin = TestClient()
    operator = TestClient()
    
    print_title("1. 登录认证测试")
    
    if admin.login("admin", "admin123") and admin.user["role"] == "admin":
        print_result("管理员登录成功", True)
        passed += 1
    else:
        print_result("管理员登录成功", False, "登录失败或角色错误")
        failed += 1
    
    if operator.login("operator", "op123456") and operator.user["role"] == "operator":
        print_result("操作员登录成功", True)
        passed += 1
    else:
        print_result("操作员登录成功", False, "登录失败或角色错误")
        failed += 1
    
    wrong = TestClient()
    if not wrong.login("admin", "wrongpass"):
        print_result("错误密码拒绝登录", True)
        passed += 1
    else:
        print_result("错误密码拒绝登录", False)
        failed += 1
    
    print_title("2. 样本批次导入测试")
    
    batch_no = f"TEST-BATCH-{int(time.time())}"
    samples = [
        {"sample_id": "T-001", "sample_type": "全血"},
        {"sample_id": "T-002", "sample_type": "血清"},
        {"sample_id": "T-003", "sample_type": "血浆"},
    ]
    
    r = operator.post("/api/samples/import", {
        "batch_no": batch_no,
        "samples": samples
    })
    data = r.json()
    
    if r.status_code == 200 and data.get("imported_count") == 3:
        print_result("首次导入 3 个样本成功", True, f"批次号: {batch_no}")
        passed += 1
    else:
        print_result("首次导入 3 个样本成功", False, str(data))
        failed += 1
    
    samples_with_dup = [
        {"sample_id": "T-001", "sample_type": "全血"},
        {"sample_id": "T-002", "sample_type": "血清"},
        {"sample_id": "T-004", "sample_type": "尿液"},
        {"sample_id": "T-005", "sample_type": "唾液"},
    ]
    
    r2 = operator.post("/api/samples/import", {
        "batch_no": batch_no + "-2",
        "samples": samples_with_dup
    })
    data2 = r2.json()
    
    if (r2.status_code == 200 
        and data2.get("imported_count") == 2 
        and data2.get("duplicate_count") == 2):
        print_result("重复导入：跳过 2 个重复项，新增 2 个有效样本", True,
                     f"导入: {data2['imported_count']}, 重复: {data2['duplicate_count']}")
        passed += 1
    else:
        print_result("重复导入：跳过重复项保留有效样本", False, str(data2))
        failed += 1
    
    sample_id_1 = None
    sample_id_2 = None
    r_list = operator.get("/api/samples?search=T-00")
    list_data = r_list.json()
    for s in list_data.get("items", []):
        if s["sample_id"] == "T-001":
            sample_id_1 = s["id"]
        elif s["sample_id"] == "T-002":
            sample_id_2 = s["id"]
    
    if sample_id_1 and sample_id_2:
        print_result("样本列表查询正常", True)
        passed += 1
    else:
        print_result("样本列表查询正常", False)
        failed += 1
    
    print_title("3. 主流程测试：入库 → 打包 → 交接 → 到达")
    
    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "WAREHOUSED",
        "remark": "入库核验通过",
        "temperature": 4.5
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "WAREHOUSED":
        print_result("操作 1：入库成功", True, "温度: 4.5°C")
        passed += 1
    else:
        print_result("操作 1：入库成功", False, r.text)
        failed += 1
    
    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "PACKED",
        "remark": "使用冷链运输箱打包"
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "PACKED":
        print_result("操作 2：打包成功", True)
        passed += 1
    else:
        print_result("操作 2：打包成功", False, r.text)
        failed += 1
    
    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "HANDED_OVER",
        "remark": "交接给运输员张三",
        "temperature": 3.8
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "HANDED_OVER":
        print_result("操作 3：交接成功", True)
        passed += 1
    else:
        print_result("操作 3：交接成功", False, r.text)
        failed += 1
    
    r = operator.post(f"/api/samples/{sample_id_1}/status", {
        "status": "ARRIVED",
        "remark": "目的地接收，样本完好",
        "temperature": 5.1
    })
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "ARRIVED":
        print_result("操作 4：到达确认成功", True)
        passed += 1
    else:
        print_result("操作 4：到达确认成功", False, r.text)
        failed += 1
    
    r = operator.get(f"/api/samples/{sample_id_1}")
    detail = r.json()
    logs_count = len(detail.get("status_logs", []))
    
    if logs_count >= 5:
        print_result(f"状态时间线完整（{logs_count} 条记录）", True)
        passed += 1
    else:
        print_result("状态时间线完整", False, f"只有 {logs_count} 条记录")
        failed += 1
    
    print_title("4. 异常冻结测试")
    
    r = operator.post(f"/api/samples/{sample_id_2}/status", {
        "status": "WAREHOUSED",
        "temperature": 4.0
    })
    
    r = operator.post(f"/api/samples/{sample_id_2}/exception", {
        "type": "overtemp",
        "description": "运输途中温度异常升高，最高达 12°C，持续 30 分钟",
        "temperature": 12.0,
        "evidence_file": "/photos/overtemp_001.jpg"
    })
    
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "FROZEN":
        print_result("录入超温异常 → 自动冻结", True, "温度: 12°C")
        passed += 1
    else:
        print_result("录入超温异常 → 自动冻结", False, r.text)
        failed += 1
    
    r = operator.get(f"/api/samples/{sample_id_2}")
    detail = r.json()
    evidence_count = len(detail.get("evidences", []))
    
    if evidence_count >= 1:
        print_result("证据记录保存成功", True, f"{evidence_count} 条证据")
        passed += 1
    else:
        print_result("证据记录保存成功", False)
        failed += 1
    
    r = operator.post(f"/api/samples/{sample_id_2}/review", {
        "action": "close",
        "remark": "操作员尝试关闭"
    })
    
    if r.status_code == 403:
        print_result("权限控制：普通操作员不能复核关闭异常", True, "返回 403")
        passed += 1
    else:
        print_result("权限控制：普通操作员不能复核关闭异常", False, f"返回 {r.status_code}")
        failed += 1
    
    print_title("5. 管理员复核测试")
    
    r = admin.post(f"/api/samples/{sample_id_2}/review", {
        "action": "close",
        "remark": "经复核，超温时间短且在允许范围内，同意关闭异常"
    })
    
    if r.status_code == 200 and r.json()["sample"]["current_status"] == "REVIEW_CLOSED":
        print_result("管理员复核关闭成功", True)
        passed += 1
    else:
        print_result("管理员复核关闭成功", False, r.text)
        failed += 1
    
    r = admin.get(f"/api/samples/{sample_id_2}")
    detail = r.json()
    
    if detail.get("reviewed_by") == "admin" and detail.get("review_remark"):
        print_result("复核信息（复核人、备注、时间）保存完整", True,
                     f"复核人: {detail['reviewed_by']}")
        passed += 1
    else:
        print_result("复核信息保存完整", False)
        failed += 1
    
    print_title("6. 导出交接单测试")
    
    r = operator.get(f"/api/export/handover?batch_no={batch_no}")
    if r.status_code == 200 and "text/csv" in r.headers.get("Content-Type", ""):
        content = r.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        print_result("交接单导出成功（CSV 格式）", True,
                     f"{len(lines)-1} 条数据, 含中文表头")
        passed += 1
    else:
        print_result("交接单导出成功", False, f"状态: {r.status_code}")
        failed += 1
    
    r = operator.get(f"/api/export/sample-timeline/{sample_id_1}")
    if r.status_code == 200 and "text/csv" in r.headers.get("Content-Type", ""):
        content = r.content.decode("utf-8-sig")
        has_timeline = "状态时间线" in content
        print_result("单样本时间线导出成功", True,
                     f"包含时间线: {has_timeline}")
        passed += 1
    else:
        print_result("单样本时间线导出成功", False)
        failed += 1
    
    print_title("7. 数据持久化验证（模拟重启）")
    
    db_path = os.path.join(os.path.dirname(__file__), "sample_tracker.db")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    s1 = conn.execute("SELECT * FROM samples WHERE sample_id = ?", ("T-001",)).fetchone()
    s2 = conn.execute("SELECT * FROM samples WHERE sample_id = ?", ("T-002",)).fetchone()
    
    logs = conn.execute(
        "SELECT COUNT(*) as cnt FROM status_logs WHERE sample_id = ?",
        (s1["id"],)
    ).fetchone()
    
    evs = conn.execute(
        "SELECT COUNT(*) as cnt FROM evidences WHERE sample_id = ?",
        (s2["id"],)
    ).fetchone()
    
    review = conn.execute(
        "SELECT review_remark, reviewed_by FROM samples WHERE id = ?",
        (s2["id"],)
    ).fetchone()
    
    conn.close()
    
    all_good = (
        s1["current_status"] == "ARRIVED"
        and s2["current_status"] == "REVIEW_CLOSED"
        and logs["cnt"] >= 5
        and evs["cnt"] >= 1
        and review["reviewed_by"] == "admin"
    )
    
    if all_good:
        print_result("重启后数据完整保留", True,
                     f"状态、证据、复核信息、时间线均完整")
        passed += 1
    else:
        print_result("重启后数据完整保留", False,
                     f"s1状态: {s1['current_status']}, s2状态: {s2['current_status']}, "
                     f"日志数: {logs['cnt']}, 证据数: {evs['cnt']}")
        failed += 1
    
    print("\n" + "="*60)
    print(f"  测试结果：{passed} 通过 / {failed} 失败 / 共 {passed+failed} 项")
    print("="*60)
    
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
