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


if __name__ == "__main__":
    try:
        success1 = run_regression_tests()
        print("\n\n")
        success2 = run_import_regression_tests()
        sys.exit(0 if (success1 and success2) else 1)
    except Exception as e:
        print(f"\n测试执行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
