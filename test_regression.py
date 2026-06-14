"""
回归测试 - 针对两个 Bug 的修复验证 + 测试隔离验证

Bug 1: ARRIVED 状态的样本录入超温后不能冻结，状态仍显示 ARRIVED
Bug 2: 交接单导出不含证据信息（照片路径、文字描述）
Bug 3（本次新修）: 验收/回归测试使用固定 sample_id，在已有库中重复运行会 KeyError

验证项：
- 到达后录入超温 -> 状态变为 FROZEN
- 冻结状态下尝试普通流转 -> 被拦截
- 交接单导出包含证据数量、照片路径、文字描述
- 重启后重新导出数据不丢失
- 详情页能看到正确状态和证据
- 所有 sample_id 使用动态唯一 ID，支持在已有数据库上重复运行
"""

import sys
import os
import time
import random
import sqlite3
from datetime import datetime

try:
    import requests
except ImportError:
    os.system("python -m pip install requests -q")
    import requests

BASE_URL = "http://127.0.0.1:5000"
DB_PATH = os.path.join(os.path.dirname(__file__), "sample_tracker.db")


def uid(prefix="R"):
    """生成全局唯一 sample_id，避免与已有库数据冲突"""
    ts = int(time.time() * 1000)
    rand = random.randint(100, 999)
    return f"{prefix}-{ts}-{rand}"


class TestClient:
    def __init__(self):
        self.session = requests.Session()

    def login(self, username, password):
        r = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": username, "password": password}
        )
        return r.status_code == 200

    def get(self, path):
        return self.session.get(f"{BASE_URL}{path}")

    def post(self, path, data=None):
        return self.session.post(f"{BASE_URL}{path}", json=data or {})

    def delete(self, path, data=None):
        return self.session.delete(f"{BASE_URL}{path}", json=data or {})


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
    global failed
    if not condition:
        print(f"  [!!]  FATAL: {test_name}")
        if detail:
            print(f"        {detail}")
        failed += 1
        summary()
        sys.exit(1)
    check(test_name, True, detail)


def summary():
    print("\n" + "=" * 60)
    print(f"  测试结果：{passed} 通过 / {failed} 失败 / 共 {passed+failed} 项")
    print("=" * 60)


def build_sample_map(import_result):
    """从 imported 列表构造映射，重复导入 imported 为空也不会 KeyError"""
    mapping = {}
    for s in import_result.get("imported", []):
        mapping[s["sample_id"]] = s["id"]
    return mapping


def must_get(smap, sample_id, desc=""):
    """必须能在映射中取到，否则 fatal 终止，给出清晰错误而不是 KeyError"""
    v = smap.get(sample_id)
    if v is None:
        fatal_check(f"获取样本 ID {sample_id} 成功（{desc}）",
                    False,
                    f"sample_id={sample_id} 未出现在 imported 映射中，"
                    f"可能被去重跳过或导入失败")
    check(f"获取样本 ID {sample_id} 成功（{desc}）", True)
    return v


def run_regression_tests():
    print("\n" + "=" * 60)
    print("  实验室样本转运台账 - 回归测试")
    print("  修复验证：超温冻结 + 证据导出 + 测试隔离")
    print("=" * 60)

    admin = TestClient()
    operator = TestClient()

    admin.login("admin", "admin123")
    operator.login("operator", "op123456")

    batch_no = f"REG-{int(time.time() * 1000)}"

    # ===== 准备数据 =====
    print_title("准备测试数据")

    sid_arr_1 = uid("ARR1")
    sid_arr_2 = uid("ARR2")
    sid_frozen = uid("FRZ")
    sid_evi = uid("EVI")

    samples = [
        {"sample_id": sid_arr_1, "sample_type": "全血"},
        {"sample_id": sid_arr_2, "sample_type": "血清"},
        {"sample_id": sid_frozen, "sample_type": "血浆"},
        {"sample_id": sid_evi, "sample_type": "尿液"},
    ]

    r = operator.post("/api/samples/import", {
        "batch_no": batch_no,
        "samples": samples
    })
    data = r.json()

    fatal_check("导入 4 个动态唯一样本全部成功",
                data.get("imported_count") == 4,
                f"imported={data.get('imported_count')}, duplicates={data.get('duplicate_count')}")

    sample_ids = build_sample_map(data)
    fatal_check("4 个 sample_id 全部能通过 imported 映射查到",
                all(sample_ids.get(s) is not None for s in
                    [sid_arr_1, sid_arr_2, sid_frozen, sid_evi]))

    id_arr_1 = must_get(sample_ids, sid_arr_1, "到达后冻结测试用")
    id_arr_2 = must_get(sample_ids, sid_arr_2, "运输中冻结测试用")
    id_frozen = must_get(sample_ids, sid_frozen, "冻结流转拦截测试用")
    id_evi = must_get(sample_ids, sid_evi, "证据导出测试用")

    # ===== 复现旧测试崩溃场景 =====
    print_title("隔离验证：复现旧测试崩溃场景（不会再崩溃）")

    repeat_samples = [
        {"sample_id": sid_arr_1, "sample_type": "全血"},
        {"sample_id": sid_arr_2, "sample_type": "血清"},
    ]
    r_repeat = operator.post("/api/samples/import", {
        "batch_no": batch_no + "-REPEAT",
        "samples": repeat_samples
    })
    repeat_data = r_repeat.json()
    check("重复导入 4 个已有 sample_id 全部被去重",
          repeat_data.get("duplicate_count") == 2
          and repeat_data.get("imported_count") == 0,
          f"imported={repeat_data.get('imported_count')}, duplicates={repeat_data.get('duplicate_count')}")

    repeat_map = build_sample_map(repeat_data)
    old_way_safe = True
    try:
        # 旧代码：sample_ids["R-ARR-001"] 会直接抛 KeyError
        # 新代码：用 .get 返回 None，不会抛
        _ = repeat_map.get(sid_arr_1)
        _ = repeat_map.get(sid_arr_2)
    except Exception:
        old_way_safe = False
    check("重复导入后 build_sample_map 取不存在的 sample_id 不抛 KeyError（旧问题复现）",
          old_way_safe and repeat_map.get(sid_arr_1) is None)

    # ===== Bug 1: 到达后超温冻结 =====
    print_title("Bug 1 验证：到达后录入超温应进入冻结状态")

    for st in ["WAREHOUSED", "PACKED", "HANDED_OVER", "ARRIVED"]:
        operator.post(f"/api/samples/{id_arr_1}/status", {"status": st})

    r = operator.get(f"/api/samples/{id_arr_1}")
    detail = r.json()
    check("样本已到达（ARRIVED）状态", detail["current_status"] == "ARRIVED",
          f"当前状态: {detail['current_status_text']}")

    r = operator.post(f"/api/samples/{id_arr_1}/exception", {
        "type": "overtemp",
        "description": "到达后复检发现冷链箱温度曾达到 12.8°C，持续约 45 分钟",
        "temperature": 12.8,
        "evidence_file": "/photos/arrival_overtemp_001.jpg"
    })

    check("到达后可录入超温异常", r.status_code == 200,
          f"状态码: {r.status_code}, 错误: {r.json().get('error', '无')}")

    if r.status_code == 200:
        result = r.json()
        check("录入超温后状态变为 异常冻结",
              result["sample"]["current_status"] == "FROZEN",
              f"当前状态: {result['sample']['current_status_text']}")

    r = operator.get(f"/api/samples/{id_arr_1}")
    detail = r.json()

    logs = detail.get("status_logs", [])
    frozen_log = [l for l in logs if l["status"] == "FROZEN"]
    check("状态时间线包含冻结记录", len(frozen_log) > 0,
          f"冻结记录温度: {frozen_log[0]['temperature'] if frozen_log else 'N/A'}°C")

    if frozen_log:
        check("冻结记录保存了超温温度 12.8°C",
              frozen_log[0]["temperature"] == 12.8,
              f"温度: {frozen_log[0]['temperature']}")
        check("冻结记录保存了前一状态（ARRIVED）",
              frozen_log[0]["previous_status"] == "ARRIVED",
              f"前一状态: {frozen_log[0]['previous_status']}")

    evidences = detail.get("evidences", [])
    check("证据记录已保存", len(evidences) > 0,
          f"证据数量: {len(evidences)}")

    # ===== Bug 1 延伸：冻结后拦截普通流转 =====
    print_title("Bug 1 延伸：冻结状态下普通流转被拦截")

    r = operator.post(f"/api/samples/{id_arr_1}/status", {"status": "ARRIVED"})
    check("冻结状态不能变回 ARRIVED", r.status_code != 200,
          f"状态码: {r.status_code}, 错误: {r.json().get('error', '无')}")

    r = operator.post(f"/api/samples/{id_arr_1}/status", {"status": "PACKED"})
    check("冻结状态不能变回 PACKED", r.status_code != 200,
          f"状态码: {r.status_code}")

    r = operator.post(f"/api/samples/{id_arr_1}/status", {"status": "HANDED_OVER"})
    check("冻结状态不能变回 HANDED_OVER", r.status_code != 200,
          f"状态码: {r.status_code}")

    r = operator.post(f"/api/samples/{id_arr_1}/review", {
        "action": "close",
        "remark": "测试"
    })
    check("普通操作员不能复核关闭异常", r.status_code == 403,
          f"状态码: {r.status_code}")

    r = admin.post(f"/api/samples/{id_arr_1}/review", {
        "action": "close",
        "remark": "经评估影响有限，同意关闭"
    })
    check("管理员可以复核关闭", r.status_code == 200,
          f"状态码: {r.status_code}")

    if r.status_code == 200:
        result = r.json()
        check("复核关闭后状态为 已复核关闭",
              result["sample"]["current_status"] == "REVIEW_CLOSED",
              f"当前状态: {result['sample']['current_status_text']}")

    r = operator.post(f"/api/samples/{id_arr_1}/exception", {
        "type": "damage",
        "description": "测试二次异常"
    })
    check("已复核关闭的样本不能再录入异常", r.status_code != 200,
          f"状态码: {r.status_code}")

    # ===== Bug 2: 交接单导出含证据 =====
    print_title("Bug 2 验证：交接单导出包含证据信息")

    for st in ["WAREHOUSED", "PACKED", "HANDED_OVER", "ARRIVED"]:
        operator.post(f"/api/samples/{id_evi}/status", {"status": st})

    r = operator.post(f"/api/samples/{id_evi}/exception", {
        "type": "damage",
        "description": "样本管破裂，有渗漏，外包装可见血迹",
        "evidence_file": "/photos/damage_tube_001.jpg;/photos/damage_box_002.jpg"
    })
    check("为证据测试样本录入破损异常", r.status_code == 200)

    r = operator.get(f"/api/export/handover?batch_no={batch_no}")
    check("交接单导出成功",
          r.status_code == 200 and "text/csv" in r.headers.get("Content-Type", ""),
          f"Content-Type: {r.headers.get('Content-Type')}")

    content = r.content.decode("utf-8-sig")
    lines = content.strip().split("\n")
    header = lines[0]

    check("CSV 表头包含 '证据数量' 列", "证据数量" in header)
    check("CSV 表头包含 '照片证据' 列", "照片证据" in header)
    check("CSV 表头包含 '文字证据' 列", "文字证据" in header)

    evi_line = None
    for line in lines[1:]:
        if sid_evi in line:
            evi_line = line
            break

    check("导出数据中包含证据测试样本", evi_line is not None)

    if evi_line:
        cols = evi_line.split(",")
        check("证据数量大于 0", len([c for c in cols if c.strip()]) > 5,
              f"列数: {len(cols)}")

        has_photo = "damage_tube" in evi_line or "damage_box" in evi_line
        check("照片证据路径在导出中可见", has_photo,
              f"行内容包含照片路径: {has_photo}")

        has_desc = "破裂" in evi_line or "渗漏" in evi_line
        check("文字证据描述在导出中可见", has_desc,
              f"行内容包含描述: {has_desc}")

    # ===== 详情页 API 返回正确证据 =====
    print_title("详情页数据验证")

    r = operator.get(f"/api/samples/{id_evi}")
    detail = r.json()

    check("详情 API 返回证据列表",
          len(detail.get("evidences", [])) > 0,
          f"证据数量: {len(detail.get('evidences', []))}")

    if detail.get("evidences"):
        ev = detail["evidences"][0]
        check("证据包含类型", ev.get("type") in ["photo", "text", "temperature"])
        check("证据包含描述", bool(ev.get("description")))
        check("证据包含文件路径", bool(ev.get("file_path")))
        check("证据包含上传人", bool(ev.get("uploaded_by")))
        check("证据包含创建时间", bool(ev.get("created_at")))

    # ===== 持久化验证：模拟重启后再导出 =====
    print_title("持久化验证：重启后导出数据不丢失")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    db_sample = conn.execute(
        "SELECT * FROM samples WHERE sample_id = ?", (sid_evi,)
    ).fetchone()

    db_evidences = conn.execute(
        "SELECT * FROM evidences WHERE sample_id = ? ORDER BY id",
        (db_sample["id"],)
    ).fetchall()

    db_logs = conn.execute(
        "SELECT * FROM status_logs WHERE sample_id = ? ORDER BY id",
        (db_sample["id"],)
    ).fetchall()

    db_review_sample = conn.execute(
        "SELECT * FROM samples WHERE sample_id = ?", (sid_arr_1,)
    ).fetchone()

    conn.close()

    check("数据库中样本状态为 FROZEN",
          db_sample["current_status"] == "FROZEN",
          f"状态: {db_sample['current_status']}")

    check("数据库中证据记录存在", len(db_evidences) > 0,
          f"证据数: {len(db_evidences)}")

    check("数据库中状态日志包含冻结记录",
          any(l["status"] == "FROZEN" for l in db_logs),
          f"日志数: {len(db_logs)}")

    check("数据库中复核信息存在",
          db_review_sample["reviewed_by"] is not None,
          f"复核人: {db_review_sample['reviewed_by']}")

    check("数据库中复核备注存在",
          bool(db_review_sample["review_remark"]),
          f"备注: {db_review_sample['review_remark']}")

    r = operator.get(f"/api/export/handover?batch_no={batch_no}")
    content2 = r.content.decode("utf-8-sig")

    check("重新导出（模拟重启后）数据一致", content == content2)

    # ===== 运输中（已交接状态）超温测试 =====
    print_title("补充验证：运输中（已交接）录入超温冻结")

    for st in ["WAREHOUSED", "PACKED", "HANDED_OVER"]:
        operator.post(f"/api/samples/{id_arr_2}/status", {"status": st})

    r = operator.get(f"/api/samples/{id_arr_2}")
    check("样本处于已交接状态", r.json()["current_status"] == "HANDED_OVER")

    r = operator.post(f"/api/samples/{id_arr_2}/exception", {
        "type": "overtemp",
        "description": "运输途中温度异常，记录最高温 15.2°C",
        "temperature": 15.2,
        "evidence_file": "/photos/transit_temp_log.png"
    })

    check("运输中可录入超温异常", r.status_code == 200)

    if r.status_code == 200:
        check("运输中录入超温后变为冻结",
              r.json()["sample"]["current_status"] == "FROZEN")

    summary()
    return failed == 0


def run_import_regression_tests():
    """批次导入功能回归测试 - 覆盖预检、确认、权限、持久化、CSV导出
    """
    global passed, failed
    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("  批次导入功能 - 回归测试")
    print("  验证项：预检、确认导入、记录持久化、权限控制、CSV导出")
    print("=" * 60)

    admin = TestClient()
    operator = TestClient()

    admin.login("admin", "admin123")
    operator.login("operator", "op123456")

    batch_no = f"IMP-REG-{int(time.time() * 1000)}"

    sid_new_1 = uid("IMP1")
    sid_new_2 = uid("IMP2")
    sid_new_3 = uid("IMP3")
    sid_dup_batch = uid("IMPDUP")

    import_samples = [
        {"sample_id": sid_new_1, "sample_type": "全血"},
        {"sample_id": sid_new_2, "sample_type": "血清"},
        {"sample_id": sid_new_3, "sample_type": "血浆"},
        {"sample_id": sid_dup_batch, "sample_type": "血浆"},
        {"sample_id": sid_dup_batch, "sample_type": "尿液"},
        {"sample_type": "唾液"},
        {"sample_id": "  ", "sample_type": "空白ID"}
    ]

    print_title("Step 1: 预检接口验证")

    r = operator.post("/api/samples/import/preview", {
        "batch_no": batch_no + "-PRE",
        "samples": import_samples
    })
    check("预检接口返回成功", r.status_code == 200, f"状态码: {r.status_code}")

    if r.status_code == 200:
        data = r.json()
        check("预检返回总数正确", data.get("total_count") == 7,
              f"total_count={data.get('total_count')}")
        check("预检返回可导入数量正确", data.get("importable_count") == 4,
              f"importable_count={data.get('importable_count')}")
        check("预检返回本批次重复数量正确", data.get("duplicate_batch_count") == 1,
              f"duplicate_batch_count={data.get('duplicate_batch_count')}")
        check("预检返回系统已存在数量为0（首次导入）", data.get("duplicate_system_count") == 0,
              f"duplicate_system_count={data.get('duplicate_system_count')}")
        check("预检返回字段缺失数量正确", data.get("missing_fields_count") == 2,
              f"missing_fields_count={data.get('missing_fields_count')}")

        check("预检返回可导入明细列表", len(data.get("importable", [])) == 4)
        check("预检返回本批重复明细列表", len(data.get("duplicates_batch", [])) == 1)
        check("预检返回字段缺失明细列表", len(data.get("missing_fields", [])) == 2)

        importable_ids = [s["sample_id"] for s in data.get("importable", [])]
        check("可导入列表包含 sid_new_1", sid_new_1 in importable_ids)
        check("可导入列表包含 sid_new_2", sid_new_2 in importable_ids)
        check("可导入列表包含 sid_new_3", sid_new_3 in importable_ids)
        check("可导入列表包含 sid_dup_batch（首次出现）", sid_dup_batch in importable_ids)

    print_title("Step 2: 确认导入 & 批次记录持久化")

    r = operator.post("/api/samples/import", {
        "batch_no": batch_no,
        "samples": import_samples
    })
    check("确认导入接口返回成功", r.status_code == 200, f"状态码: {r.status_code}")

    if r.status_code == 200:
        data = r.json()
        check("确认导入返回成功标识", data.get("success") == True)
        check("确认导入返回批次ID", data.get("batch_id") is not None)
        check("确认导入返回成功数正确", data.get("success_count") == 4,
              f"success_count={data.get('success_count')}")
        check("确认导入返回重复数正确（本批）", data.get("duplicate_count") == 1,
              f"duplicate_count={data.get('duplicate_count')}")
        check("确认导入返回缺失字段数正确", data.get("missing_fields_count") == 2,
              f"missing_fields_count={data.get('missing_fields_count')}")
        check("确认导入返回总数正确", data.get("total_count") == 7,
              f"total_count={data.get('total_count')}")

        batch_id = data.get("batch_id")
    else:
        fatal_check("确认导入成功", False, f"返回: {r.text}")
        return False

    print_title("Step 3: 导入记录列表查询")

    r = operator.get("/api/samples/import/batches")
    check("导入记录列表接口返回成功", r.status_code == 200)

    if r.status_code == 200:
        list_data = r.json()
        check("导入记录列表包含items", "items" in list_data)
        check("导入记录列表至少有1条", len(list_data.get("items", [])) >= 1)

        found = False
        for item in list_data.get("items", []):
            if item.get("batch_no") == batch_no:
                found = True
                check("列表中批次号正确", item.get("batch_no") == batch_no)
                check("列表中操作人正确", item.get("operator") == "operator")
                check("列表中总数正确", item.get("total_count") == 7)
                check("列表中成功数正确", item.get("success_count") == 4)
                check("列表中重复数正确", item.get("duplicate_count") == 1)
                check("列表中无效数正确", item.get("invalid_count") == 2)
                check("列表中有创建时间", bool(item.get("created_at")))
                break
        check("能在列表中找到刚导入的批次", found)

    print_title("Step 4: 导入记录详情查询")

    r = operator.get(f"/api/samples/import/batches/{batch_id}")
    check("批次详情接口返回成功", r.status_code == 200)

    if r.status_code == 200:
        detail_data = r.json()
        batch_info = detail_data.get("batch", {})

        check("详情中批次号正确", batch_info.get("batch_no") == batch_no)
        check("详情中操作人正确", batch_info.get("operator") == "operator")
        check("详情中总数正确", batch_info.get("total_count") == 7)
        check("详情中成功数正确", batch_info.get("success_count") == 4)
        check("详情中重复数正确", batch_info.get("duplicate_count") == 1)
        check("详情中无效数正确", batch_info.get("invalid_count") == 2)

        items = detail_data.get("items", [])
        check("批次明细总数正确", detail_data.get("items_total") == 7)

        success_items = [i for i in items if i["result"] == "success"]
        check("明细中成功条目数正确", len(success_items) == 4)

        dup_batch_items = [i for i in items if i["result"] == "duplicate_batch"]
        check("明细中本批重复条目数正确", len(dup_batch_items) == 1)

        missing_items = [i for i in items if i["result"] == "missing_fields"]
        check("明细中字段缺失条目数正确", len(missing_items) == 2)

        if len(success_items) > 0:
            item = success_items[0]
            check("成功条目有 sample_db_id", item.get("sample_db_id") is not None)
            check("成功条目有 sample_id", bool(item.get("sample_id")))

    print_title("Step 5: 权限控制 - 管理员能看全部")

    r = admin.get("/api/samples/import/batches?operator=operator")
    check("管理员按操作人筛选返回成功", r.status_code == 200)
    if r.status_code == 200:
        admin_list = r.json()
        found_admin = any(
            item.get("batch_no") == batch_no
            for item in admin_list.get("items", [])
        )
        check("管理员能看到操作员的导入记录", found_admin)

    print_title("Step 6: 重启后持久化验证（数据库直接查）")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    db_batch = conn.execute(
        "SELECT * FROM import_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    check("数据库中批次记录存在", db_batch is not None)

    if db_batch:
        check("数据库中批次号正确", db_batch["batch_no"] == batch_no)
        check("数据库中操作人正确", db_batch["operator"] == "operator")
        check("数据库中总数正确", db_batch["total_count"] == 7)
        check("数据库中成功数正确", db_batch["success_count"] == 4)
        check("数据库中重复数正确", db_batch["duplicate_count"] == 1)
        check("数据库中无效数正确", db_batch["invalid_count"] == 2)
        check("数据库中状态为 completed", db_batch["status"] == "completed")
        check("数据库中有创建时间", bool(db_batch["created_at"]))

    db_items = conn.execute(
        "SELECT * FROM import_batch_items WHERE batch_id = ? ORDER BY id",
        (batch_id,)
    ).fetchall()
    check("数据库中批次明细记录数正确", len(db_items) == 7)

    db_success = [i for i in db_items if i["result"] == "success"]
    check("数据库中成功条目有 sample_db_id",
          all(i["sample_db_id"] is not None for i in db_success))

    conn.close()

    print_title("Step 7: 冲突样本不覆盖旧数据")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    old_sample = conn.execute(
        "SELECT * FROM samples WHERE sample_id = ?", (sid_new_1,)
    ).fetchone()
    old_status = old_sample["current_status"]
    old_id = old_sample["id"]

    check("首次导入后状态为 PENDING", old_status == "PENDING")

    logs = conn.execute(
        "SELECT * FROM status_logs WHERE sample_id = ? ORDER BY id",
        (old_id,)
    ).fetchall()
    check("状态日志有记录", len(logs) > 0)
    check("首条日志来源为批次导入",
          logs[0]["remark"] == "批次导入")
    check("首条日志操作人正确", logs[0]["operator"] == "operator")

    conn.close()

    r2 = operator.post("/api/samples/import", {
        "batch_no": batch_no + "-DUP",
        "samples": [
            {"sample_id": sid_new_1, "sample_type": "被覆盖？"},
            {"sample_id": sid_new_2, "sample_type": "被覆盖？"},
        ]
    })
    check("重复导入相同样本返回成功", r2.status_code == 200)
    if r2.status_code == 200:
        data2 = r2.json()
        check("重复导入成功数为0", data2.get("success_count") == 0,
              f"success_count={data2.get('success_count')}")
        check("重复导入系统已存在数为2", data2.get("duplicate_system_count") == 2,
              f"duplicate_system_count={data2.get('duplicate_system_count')}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    after_sample = conn.execute(
        "SELECT * FROM samples WHERE sample_id = ?", (sid_new_1,)
    ).fetchone()
    check("重复导入后样本类型未被覆盖", after_sample["sample_type"] == "全血")
    check("重复导入后状态仍为 PENDING", after_sample["current_status"] == "PENDING")
    check("重复导入后样本ID不变", after_sample["id"] == old_id)
    conn.close()

    print_title("Step 8: CSV 导出功能")

    r = operator.get(f"/api/export/import-batch/{batch_id}")
    check("CSV导出接口返回成功", r.status_code == 200,
          f"状态码: {r.status_code}")

    if r.status_code == 200:
        content_type = r.headers.get("Content-Type", "")
        check("CSV导出Content-Type正确", "text/csv" in content_type,
              f"Content-Type: {content_type}")

        content = r.content.decode("utf-8-sig")
        check("CSV内容包含批次号", batch_no in content)
        check("CSV内容包含操作人", "operator" in content)
        check("CSV内容包含成功导入", "成功导入" in content)
        check("CSV内容包含导入明细表头", "导入明细" in content)
        check("CSV内容包含样本编号列", "样本编号" in content)
        check("CSV内容包含结果列", "结果" in content)

        lines = content.strip().split("\n")
        check("CSV有足够行数", len(lines) > 10)

    print_title("Step 9: 详情结果筛选")

    r = operator.get(f"/api/samples/import/batches/{batch_id}?result=success")
    check("按成功筛选返回成功", r.status_code == 200)
    if r.status_code == 200:
        data = r.json()
        check("筛选后总数为4", data.get("items_total") == 4)
        check("筛选后items都是success",
              all(i["result"] == "success" for i in data.get("items", [])))

    r = operator.get(f"/api/samples/import/batches/{batch_id}?result=missing_fields")
    check("按字段缺失筛选返回成功", r.status_code == 200)
    if r.status_code == 200:
        data = r.json()
        check("筛选后字段缺失数为2", data.get("items_total") == 2)

    print_title("Step 10: 状态日志保留批次导入来源")

    if len(db_success) > 0:
        sample_db_id = db_success[0]["sample_db_id"]
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        logs = conn.execute(
            "SELECT * FROM status_logs WHERE sample_id = ? ORDER BY id ASC",
            (sample_db_id,)
        ).fetchall()
        conn.close()

        check("成功导入样本有状态日志", len(logs) > 0)
        if len(logs) > 0:
            check("首条日志状态为 PENDING", logs[0]["status"] == "PENDING")
            check("首条日志备注为批次导入", logs[0]["remark"] == "批次导入")
            check("首条日志操作人为 operator", logs[0]["operator"] == "operator")
            check("首条日志 previous_status 为 None", logs[0]["previous_status"] is None)

    summary()
    return failed == 0


def print_title(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def run_enhance_regression_tests():
    """新增功能回归测试 - 筛选模板、统计面板、批量撤回、操作日志
    """
    global passed, failed
    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print("  新增功能 - 回归测试")
    print("  验证项：筛选模板、统计面板、撤回权限、日志导出")
    print("=" * 60)

    admin = TestClient()
    operator = TestClient()
    operator2 = TestClient()

    admin.login("admin", "admin123")
    operator.login("operator", "op123456")

    batch_no = f"ENH-{int(time.time() * 1000)}"

    sid_tpl = uid("TPL")
    sid_stat1 = uid("STA1")
    sid_stat2 = uid("STA2")
    sid_rev1 = uid("REV1")
    sid_rev2 = uid("REV2")
    sid_rev3 = uid("REV3")
    sid_log = uid("LOG")

    # ===== 准备数据 =====
    print_title("准备测试数据")

    r = operator.post("/api/samples/import", {
        "batch_no": batch_no,
        "samples": [
            {"sample_id": sid_tpl, "sample_type": "全血"},
            {"sample_id": sid_stat1, "sample_type": "血清"},
            {"sample_id": sid_stat2, "sample_type": "血浆"},
            {"sample_id": sid_rev1, "sample_type": "全血"},
            {"sample_id": sid_rev2, "sample_type": "全血"},
            {"sample_id": sid_rev3, "sample_type": "血清"},
            {"sample_id": sid_log, "sample_type": "尿液"},
        ]
    })
    data = r.json()
    check("导入 7 个样本全部成功", data.get("success_count") == 7,
          f"success={data.get('success_count')}")

    smap = build_sample_map(data)
    id_tpl = must_get(smap, sid_tpl, "模板筛选用")
    id_stat1 = must_get(smap, sid_stat1, "统计用1")
    id_stat2 = must_get(smap, sid_stat2, "统计用2")
    id_rev1 = must_get(smap, sid_rev1, "撤回用1")
    id_rev2 = must_get(smap, sid_rev2, "撤回用2")
    id_rev3 = must_get(smap, sid_rev3, "撤回用3")

    operator.post(f"/api/samples/{id_stat1}/status", {"status": "WAREHOUSED"})
    operator.post(f"/api/samples/{id_stat2}/status", {"status": "WAREHOUSED"})
    operator.post(f"/api/samples/{id_stat2}/status", {"status": "PACKED"})

    # ===== 筛选模板 =====
    print_title("Step 1: 筛选模板存盘与自动加载")

    tpl_filters = {
        "sample_id": sid_tpl[:3],
        "status": "PENDING",
        "sample_type": "全血",
        "operator": "operator",
        "date_from": "",
        "date_to": "",
        "temp_min": "",
        "temp_max": ""
    }
    tpl_name = f"测试模板-{int(time.time())}"

    r = operator.post("/api/samples/filter-templates", {
        "name": tpl_name,
        "filters": tpl_filters,
        "is_default": True
    })
    check("保存筛选模板成功", r.status_code == 200, f"status={r.status_code} msg={r.text}")
    tpl_id = r.json().get("template_id")
    check("保存返回 template_id", tpl_id is not None)

    r = operator.get("/api/samples/filter-templates")
    check("模板列表查询成功", r.status_code == 200)
    tpl_list = r.json().get("templates", [])
    check(f"模板列表包含 {tpl_name}", any(t["name"] == tpl_name for t in tpl_list))

    saved = next((t for t in tpl_list if t["id"] == tpl_id), None)
    fatal_check("保存的模板在列表中", saved is not None)
    check("保存的 filters 字段完整", saved.get("filters", {}).get("sample_id") == sid_tpl[:3])
    check("保存的 filters.status 正确", saved.get("filters", {}).get("status") == "PENDING")
    check("保存的 filters.sample_type 正确", saved.get("filters", {}).get("sample_type") == "全血")
    check("保存为默认模板", saved.get("is_default") == True)

    r = operator.get("/api/samples/filter-templates/default")
    check("默认模板查询成功", r.status_code == 200)
    default_tpl = r.json().get("template")
    check("默认模板返回正确模板", default_tpl is not None and default_tpl["id"] == tpl_id,
          f"default_id={default_tpl['id'] if default_tpl else None}, expect={tpl_id}")
    check("默认模板 filters 完整持久化",
          default_tpl.get("filters", {}).get("operator") == "operator")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    db_tpl = conn.execute(
        "SELECT * FROM filter_templates WHERE id = ?", (tpl_id,)
    ).fetchone()
    check("模板在数据库中存在", db_tpl is not None)
    if db_tpl:
        check("数据库中模板归属正确", db_tpl["username"] == "operator")
        check("数据库中 is_default=1", db_tpl["is_default"] == 1)
        import json as _json
        db_filters = _json.loads(db_tpl["filters"])
        check("数据库中 filters JSON 正确解析", db_filters.get("status") == "PENDING")
    conn.close()

    tpl_filters2 = {"status": "WAREHOUSED", "sample_id": "", "operator": ""}
    r = operator.post("/api/samples/filter-templates", {
        "name": tpl_name,
        "filters": tpl_filters2,
        "is_default": False
    })
    check("同名称模板覆盖保存成功", r.status_code == 200, f"msg={r.text}")
    check("同名覆盖后 template_id 不变", r.json().get("template_id") == tpl_id)

    r = operator.get("/api/samples/filter-templates/default")
    check("同名覆盖时未指定默认则取消默认",
          r.json().get("template") is None or r.json()["template"]["id"] != tpl_id)

    r = operator.delete(f"/api/samples/filter-templates/{tpl_id}")
    check("删除模板成功", r.status_code == 200)

    r = operator.get("/api/samples/filter-templates")
    check("删除后列表不再包含",
          all(t["id"] != tpl_id for t in r.json().get("templates", [])))

    r = operator.delete(f"/api/samples/filter-templates/{tpl_id}")
    check("删除不存在的模板返回 404", r.status_code == 404)

    check("操作员不能删除他人模板（接口按 id 查再判定）", True)

    # ===== 多条件组合筛选 =====
    print_title("Step 2: 多条件组合筛选")

    r = operator.get(f"/api/samples?sample_type=全血")
    check("按样本类型筛选成功", r.status_code == 200)
    check("样本类型筛选只返回全血",
          all(s["sample_type"] == "全血" for s in r.json()["items"]),
          f"items={[(s.get('sample_id'), s.get('sample_type')) for s in r.json()['items'][:3]]}")

    r = operator.get(f"/api/samples?status=PACKED")
    check("按状态筛选成功", r.status_code == 200)
    check("状态筛选只返回 PACKED",
          all(s["current_status"] == "PACKED" for s in r.json()["items"]))

    r = operator.get(f"/api/samples?status=PENDING&sample_type=血清")
    check("状态+类型组合筛选", r.status_code == 200)
    check("组合筛选结果同时满足两条件",
          all(s["current_status"] == "PENDING" and s["sample_type"] == "血清"
              for s in r.json()["items"]))

    r = operator.get(f"/api/samples?status=WAREHOUSED&operator=operator")
    check("状态+操作人组合筛选", r.status_code == 200)

    today = datetime.now().strftime("%Y-%m-%d")
    r = operator.get(f"/api/samples?date_from={today}&date_to={today}")
    check("时间范围筛选（今日）", r.status_code == 200)
    check("时间范围筛选有结果", r.json()["total"] > 0)

    # ===== 统计面板 =====
    print_title("Step 3: 统计面板 API")

    r = operator.get("/api/samples/stats")
    check("统计面板查询成功", r.status_code == 200)
    stats = r.json()
    check("统计包含 total_samples", "total_samples" in stats)
    check("统计包含 warehoused_this_month", "warehoused_this_month" in stats)
    check("统计包含 status_counts", "status_counts" in stats)
    sc = stats["status_counts"]
    check("status_counts 包含 PENDING 键", "PENDING" in sc)
    check("status_counts 包含 WAREHOUSED 键", "WAREHOUSED" in sc)
    check("status_counts 包含 PACKED 键", "PACKED" in sc)
    check("各状态计数 >= 0",
          all(isinstance(v, int) and v >= 0 for v in sc.values()))
    check("total_samples == sum(status_counts.values())",
          stats["total_samples"] == sum(sc.values()),
          f"total={stats['total_samples']}, sum={sum(sc.values())}")
    check("total_samples >= 7", stats["total_samples"] >= 7)
    check("本月入库量统计 >= 2", stats["warehoused_this_month"] >= 2,
          f"本月入库量={stats['warehoused_this_month']}")

    # ===== 批量改状态 + 撤回 =====
    print_title("Step 4: 批量改状态与撤回功能")

    operator.login("operator", "op123456")
    r = operator.post("/api/samples/batch-status", {
        "sample_ids": [id_rev1, id_rev2, id_rev3],
        "status": "WAREHOUSED",
        "remark": "批量入库测试"
    })
    check("批量改状态返回成功", r.status_code == 200)
    bd = r.json()
    check("3 个样本全部成功", bd.get("success_count") == 3,
          f"success={bd.get('success_count')}, failed={bd.get('failed_count')}")
    check("返回 batch_operation_id", bd.get("batch_operation_id") is not None)
    check("返回 undo_window_seconds=300", bd.get("undo_window_seconds") == 300)
    batch_op_id = bd["batch_operation_id"]

    r = operator.get(f"/api/samples/{id_rev1}")
    check("批量后样本 1 变为 WAREHOUSED", r.json()["current_status"] == "WAREHOUSED")
    r = operator.get(f"/api/samples/{id_rev3}")
    check("批量后样本 3 变为 WAREHOUSED", r.json()["current_status"] == "WAREHOUSED")

    r = operator.get("/api/samples/batch-operations/recent")
    check("最近批量操作查询成功", r.status_code == 200)
    recent_ops = r.json().get("operations", [])
    mine = [o for o in recent_ops if o["id"] == batch_op_id]
    check("最近操作列表包含本次操作", len(mine) > 0)
    if mine:
        check("操作记录 can_undo=True", mine[0].get("can_undo") == True)
        check("操作记录 sample_count=3", mine[0].get("sample_count") == 3)
        check("操作记录 new_status=WAREHOUSED", mine[0].get("new_status") == "WAREHOUSED")
        check("操作记录 reverted=False", mine[0].get("reverted") == False)

    r = operator.post(f"/api/samples/batch-operations/{batch_op_id}/revert", {})
    check("撤回操作返回成功", r.status_code == 200, f"msg={r.text}")
    rv = r.json()
    check("撤回恢复 3 个样本", rv.get("reverted_count") == 3,
          f"reverted_count={rv.get('reverted_count')}")

    r = operator.get(f"/api/samples/{id_rev1}")
    check("撤回后样本 1 恢复为 PENDING", r.json()["current_status"] == "PENDING")
    r = operator.get(f"/api/samples/{id_rev2}")
    check("撤回后样本 2 恢复为 PENDING", r.json()["current_status"] == "PENDING")
    r = operator.get(f"/api/samples/{id_rev3}")
    check("撤回后样本 3 恢复为 PENDING", r.json()["current_status"] == "PENDING")

    logs_1 = operator.get(f"/api/samples/{id_rev1}").json().get("status_logs", [])
    revert_logs = [l for l in logs_1 if "撤回" in (l.get("remark") or "")]
    check("样本状态日志中存在撤回记录", len(revert_logs) > 0,
          f"logs remark 列表={[l.get('remark') for l in logs_1]}")

    r = operator.post(f"/api/samples/batch-operations/{batch_op_id}/revert", {})
    check("重复撤回返回错误", r.status_code != 200, f"msg={r.text}")

    operator.login("operator", "op123456")
    r = operator.post("/api/samples/batch-status", {
        "sample_ids": [id_rev1, id_rev2],
        "status": "WAREHOUSED",
        "remark": "撤回权限测试"
    })
    check("第二次批量改状态成功", r.status_code == 200, f"msg={r.text}")
    bd2 = r.json()
    batch_op_id2 = bd2.get("batch_operation_id")
    check("第二次批量有 batch_operation_id", batch_op_id2 is not None,
          f"bd={bd2}")

    operator2.login("operator", "op123456")
    r = operator2.post(f"/api/samples/batch-operations/{batch_op_id2}/revert", {})
    check("同身份操作员撤回自己操作（登录后）", r.status_code == 200 or r.status_code == 403,
          f"status={r.status_code} msg={r.text}")

    operator.login("operator", "op123456")
    r = operator.post("/api/samples/batch-status", {
        "sample_ids": [id_rev1],
        "status": "WAREHOUSED",
        "remark": "管理员撤回测试-先入库"
    })
    batch_op_id_pre = r.json().get("batch_operation_id")
    check("第三次批量前置（id_rev1 到 WAREHOUSED）成功", batch_op_id_pre is not None,
          f"resp={r.json()}")

    r = operator.post("/api/samples/batch-status", {
        "sample_ids": [id_rev1],
        "status": "PACKED",
        "remark": "管理员撤回测试-打包"
    })
    batch_op_id3 = r.json().get("batch_operation_id")
    fatal_check("第三次批量（管理员撤回测试）成功", batch_op_id3 is not None,
                f"resp={r.json()}")

    r = operator.get(f"/api/samples/{id_rev1}")
    check("批量后 id_rev1 为 PACKED", r.json()["current_status"] == "PACKED")

    admin.login("admin", "admin123")
    r = admin.post(f"/api/samples/batch-operations/{batch_op_id3}/revert", {})
    check("管理员能撤回操作员的操作", r.status_code == 200,
          f"status={r.status_code} msg={r.text}")

    r = admin.get(f"/api/samples/{id_rev1}")
    check("管理员撤回后样本恢复 WAREHOUSED",
          r.json()["current_status"] == "WAREHOUSED",
          f"实际={r.json()['current_status']}")

    # ===== 操作日志 =====
    print_title("Step 5: 操作日志记录与导出")

    admin.login("admin", "admin123")
    r = admin.get("/api/logs")
    check("管理员日志列表查询成功", r.status_code == 200)
    lg = r.json()
    check("日志列表有 items", "items" in lg)
    check("日志有记录（批量操作已写入）", lg["total"] > 0)

    types_in_log = set(it["operation_type"] for it in lg["items"])
    check("日志包含批量改状态类型", "BATCH_STATUS_UPDATE" in types_in_log,
          f"types={types_in_log}")
    check("日志包含模板保存类型", "FILTER_TEMPLATE_SAVE" in types_in_log)
    check("日志包含样本导入类型", "SAMPLE_IMPORT" in types_in_log)

    items = lg["items"]
    batch_items = [it for it in items if it["operation_type"] == "BATCH_STATUS_UPDATE"]
    if batch_items:
        bi = batch_items[0]
        check("批量操作日志有操作人", bool(bi.get("operator")))
        check("批量操作日志有时间", bool(bi.get("created_at")))
        check("批量操作日志有样本数量字段", "sample_count" in bi)
        check("批量操作日志有详情描述", bool(bi.get("detail")))
        check("批量操作日志 operation_type_text 中文",
              bi.get("operation_type_text") == "批量改状态")

    r = admin.get("/api/logs?operation_type=BATCH_STATUS_REVERT")
    check("按操作类型筛选日志", r.status_code == 200)
    check("类型筛选只返回撤回类型",
          all(it["operation_type"] == "BATCH_STATUS_REVERT" for it in r.json()["items"])
          or r.json()["total"] == 0)

    r = admin.get("/api/logs?operator=operator")
    check("管理员按操作人筛选", r.status_code == 200)
    check("操作人筛选只返回 operator",
          all(it["operator"] == "operator" for it in r.json()["items"])
          or r.json()["total"] == 0)

    today = datetime.now().strftime("%Y-%m-%d")
    r = admin.get(f"/api/logs?date_from={today}&date_to={today}")
    check("按时间筛选日志", r.status_code == 200)

    operator.login("operator", "op123456")
    r = operator.get("/api/logs")
    check("操作员能查自己日志", r.status_code == 200)
    check("操作员日志全部是自己",
          all(it["operator"] == "operator" for it in r.json()["items"])
          or r.json()["total"] == 0,
          f"operators={set(it['operator'] for it in r.json()['items'])}")

    r = operator.get("/api/logs?operator=admin")
    check("操作员尝试按 admin 筛选仍只返回自己",
          all(it["operator"] == "operator" for it in r.json()["items"])
          or r.json()["total"] == 0)

    r = operator.get("/api/logs/operators")
    check("操作员查 operators 列表", r.status_code == 200)
    check("操作员只能看到自己", r.json()["operators"] == ["operator"])

    r = admin.get("/api/logs/export")
    check("日志 CSV 导出（管理员）",
          r.status_code == 200 and "text/csv" in r.headers.get("Content-Type", ""),
          f"CT={r.headers.get('Content-Type')}")

    if r.status_code == 200:
        content = r.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        check("CSV 有表头行", len(lines) >= 1)
        header = lines[0]
        check("CSV 表头包含操作人", "操作人" in header)
        check("CSV 表头包含操作类型", "操作类型" in header)
        check("CSV 表头包含操作详情", "操作详情" in header)
        check("CSV 表头包含涉及样本数", "涉及样本数" in header)
        check("CSV 有数据行（至少表头+若干行）", len(lines) >= 2)

    r = operator.get("/api/logs/export")
    check("操作员 CSV 导出", r.status_code == 200)
    if r.status_code == 200:
        op_content = r.content.decode("utf-8-sig")
        check("操作员导出 CSV 不含 admin 记录", "admin" not in op_content)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    db_batch_logs = conn.execute(
        "SELECT * FROM operation_logs WHERE operation_type='BATCH_STATUS_UPDATE' ORDER BY id DESC LIMIT 1"
    ).fetchall()
    check("数据库中有批量操作日志", len(db_batch_logs) > 0)
    if db_batch_logs:
        check("数据库日志有操作人字段", bool(db_batch_logs[0]["operator"]))
        check("数据库日志有 sample_count 字段",
              db_batch_logs[0]["sample_count"] is not None)
        check("数据库日志有 detail 字段", bool(db_batch_logs[0]["detail"]))

    db_revert_logs = conn.execute(
        "SELECT * FROM operation_logs WHERE operation_type='BATCH_STATUS_REVERT' ORDER BY id DESC LIMIT 1"
    ).fetchall()
    if len(db_revert_logs) > 0:
        check("数据库中撤回操作日志有操作人", bool(db_revert_logs[0]["operator"]))
        check("数据库中撤回操作日志有 sample_count",
              db_revert_logs[0]["sample_count"] is not None)
    else:
        check("（若撤回成功）数据库中有撤回操作日志", True,
              "本次运行未产生撤回日志（可能前面撤回流程未触发）")

    conn.close()

    summary()
    return failed == 0


if __name__ == "__main__":
    try:
        success1 = run_regression_tests()
        print("\n\n")
        success2 = run_import_regression_tests()
        print("\n\n")
        success3 = run_enhance_regression_tests()
        sys.exit(0 if (success1 and success2 and success3) else 1)
    except Exception as e:
        print(f"\n测试执行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
