let currentPage = 1;
let perPage = 20;
let totalPages = 1;
let selectedIds = new Set();
let allTemplates = [];
let lastBatchOpId = null;
let undoTimer = null;
let undoSecondsLeft = 0;

document.addEventListener('DOMContentLoaded', function () {
  loadCurrentUser().then(() => {
    loadTemplates().then(() => {
      loadDefaultTemplate().then(() => {
        loadSamples();
      });
    });
    loadStats();
    startUndoStatusPoll();
  });

  ['f_sample_id', 'f_operator', 'f_sample_type'].forEach(id => {
    document.getElementById(id).addEventListener('keypress', function (e) {
      if (e.key === 'Enter') {
        currentPage = 1;
        doSearch();
      }
    });
  });
});

function goToLogs() {
  window.location.href = '/operation-logs';
}

function getFilterParams() {
  return {
    sample_id: document.getElementById('f_sample_id').value.trim(),
    status: document.getElementById('f_status').value,
    sample_type: document.getElementById('f_sample_type').value.trim(),
    operator: document.getElementById('f_operator').value.trim(),
    date_from: document.getElementById('f_date_from').value,
    date_to: document.getElementById('f_date_to').value,
    temp_min: document.getElementById('f_temp_min').value,
    temp_max: document.getElementById('f_temp_max').value
  };
}

function setFilterParams(filters) {
  if (!filters) return;
  document.getElementById('f_sample_id').value = filters.sample_id || '';
  document.getElementById('f_status').value = filters.status || '';
  document.getElementById('f_sample_type').value = filters.sample_type || '';
  document.getElementById('f_operator').value = filters.operator || '';
  document.getElementById('f_date_from').value = filters.date_from || '';
  document.getElementById('f_date_to').value = filters.date_to || '';
  document.getElementById('f_temp_min').value = filters.temp_min || '';
  document.getElementById('f_temp_max').value = filters.temp_max || '';
}

function doSearch() {
  currentPage = 1;
  loadSamples();
}

function resetFilters() {
  document.getElementById('f_sample_id').value = '';
  document.getElementById('f_status').value = '';
  document.getElementById('f_sample_type').value = '';
  document.getElementById('f_operator').value = '';
  document.getElementById('f_date_from').value = '';
  document.getElementById('f_date_to').value = '';
  document.getElementById('f_temp_min').value = '';
  document.getElementById('f_temp_max').value = '';
  document.getElementById('templateSelect').value = '';
  document.getElementById('deleteTplBtn').style.display = 'none';
  currentPage = 1;
  loadSamples();
}

async function loadSamples() {
  const f = getFilterParams();
  let url = `/api/samples?page=${currentPage}&per_page=${perPage}`;
  for (const [k, v] of Object.entries(f)) {
    if (v) url += `&${k}=${encodeURIComponent(v)}`;
  }

  const result = await apiRequest(url);
  const tbody = document.getElementById('samplesTableBody');

  if (!result || !result.ok) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--danger);">加载失败</td></tr>`;
    return;
  }

  const data = result.data;

  if (data.items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 40px; color: var(--gray-400);">暂无数据</td></tr>`;
  } else {
    tbody.innerHTML = data.items.map(s => `
      <tr>
        <td><input type="checkbox" class="sample-check" data-id="${s.id}"
          ${selectedIds.has(s.id) ? 'checked' : ''} onchange="toggleSampleCheck(${s.id}, this)"></td>
        <td><strong>${s.sample_id}</strong></td>
        <td>${s.batch_no}</td>
        <td>${s.sample_type || '-'}</td>
        <td><span class="status-badge ${getStatusClass(s.current_status)}">${s.current_status_text}</span></td>
        <td>${formatDateTime(s.created_at)}</td>
        <td>${formatDateTime(s.updated_at)}</td>
        <td>
          <button class="btn btn-sm btn-primary" onclick="viewDetail(${s.id})">详情</button>
        </td>
      </tr>
    `).join('');
  }

  totalPages = Math.ceil(data.total / perPage);
  renderPagination(data.total);
  updateSelectAllState();
}

function renderPagination(total) {
  const pagination = document.getElementById('pagination');
  let html = '';

  html += `<button ${currentPage <= 1 ? 'disabled' : ''} onclick="goToPage(${currentPage - 1})">上一页</button>`;

  const startPage = Math.max(1, currentPage - 2);
  const endPage = Math.min(totalPages, currentPage + 2);

  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="${i === currentPage ? 'active' : ''}" onclick="goToPage(${i})">${i}</button>`;
  }

  html += `<button ${currentPage >= totalPages ? 'disabled' : ''} onclick="goToPage(${currentPage + 1})">下一页</button>`;
  html += `<span style="line-height: 36px; margin-left: 12px; color: var(--gray-500); font-size: 14px;">共 ${total} 条</span>`;

  pagination.innerHTML = html;
}

function goToPage(page) {
  if (page < 1 || page > totalPages) return;
  currentPage = page;
  loadSamples();
}

function viewDetail(id) {
  window.location.href = `/samples/${id}`;
}

function toggleSampleCheck(id, el) {
  if (el.checked) {
    selectedIds.add(id);
  } else {
    selectedIds.delete(id);
  }
  updateSelectedBar();
  updateSelectAllState();
}

function toggleSelectAll() {
  const selectAll = document.getElementById('selectAll').checked;
  document.querySelectorAll('.sample-check').forEach(cb => {
    const id = parseInt(cb.dataset.id);
    if (selectAll) selectedIds.add(id);
    else selectedIds.delete(id);
    cb.checked = selectAll;
  });
  updateSelectedBar();
}

function updateSelectAllState() {
  const cbs = document.querySelectorAll('.sample-check');
  const selectAllEl = document.getElementById('selectAll');
  if (cbs.length === 0) {
    selectAllEl.checked = false;
    selectAllEl.indeterminate = false;
    return;
  }
  const checked = Array.from(cbs).filter(c => c.checked).length;
  if (checked === 0) {
    selectAllEl.checked = false;
    selectAllEl.indeterminate = false;
  } else if (checked === cbs.length) {
    selectAllEl.checked = true;
    selectAllEl.indeterminate = false;
  } else {
    selectAllEl.checked = false;
    selectAllEl.indeterminate = true;
  }
}

function updateSelectedBar() {
  const bar = document.getElementById('batchActionBar');
  document.getElementById('selectedCount').textContent = selectedIds.size;
  bar.style.display = selectedIds.size > 0 ? 'flex' : 'none';
}

function clearSelection() {
  selectedIds.clear();
  document.querySelectorAll('.sample-check').forEach(cb => cb.checked = false);
  updateSelectedBar();
  updateSelectAllState();
}

async function doBatchStatusUpdate() {
  const newStatus = document.getElementById('batchStatusSelect').value;
  const remark = document.getElementById('batchRemark').value;

  if (!newStatus) {
    showAlert('请选择目标状态', 'error');
    return;
  }
  if (selectedIds.size === 0) {
    showAlert('请先选择样本', 'error');
    return;
  }

  const ids = Array.from(selectedIds);
  const result = await apiRequest('/api/samples/batch-status', {
    method: 'POST',
    body: JSON.stringify({ sample_ids: ids, status: newStatus, remark })
  });

  if (!result || !result.ok) {
    showAlert(result.data?.error || '批量操作失败', 'error');
    return;
  }

  const d = result.data;
  showAlert(`批量操作成功：成功 ${d.success_count} 个，失败 ${d.failed_count} 个`,
    d.failed_count > 0 ? 'warning' : 'success');

  if (d.batch_operation_id) {
    lastBatchOpId = d.batch_operation_id;
    undoSecondsLeft = d.undo_window_seconds || 300;
    showUndoToast(d.success_count, d.new_status_text || newStatus);
  }

  clearSelection();
  document.getElementById('batchRemark').value = '';
  document.getElementById('batchStatusSelect').value = '';
  loadSamples();
  loadStats();
}

function showUndoToast(count, statusText) {
  const toast = document.getElementById('undoToast');
  document.getElementById('undoToastText').textContent = `已将 ${count} 个样本状态变更为 ${statusText}`;
  toast.style.display = 'flex';
  startUndoCountdown();
}

function hideUndoToast() {
  document.getElementById('undoToast').style.display = 'none';
  if (undoTimer) clearInterval(undoTimer);
  undoTimer = null;
}

function startUndoCountdown() {
  if (undoTimer) clearInterval(undoTimer);
  const countdownEl = document.getElementById('undoCountdown');
  const btn = document.getElementById('undoBtn');
  const update = () => {
    const m = Math.floor(undoSecondsLeft / 60);
    const s = undoSecondsLeft % 60;
    countdownEl.textContent = `${m}:${s.toString().padStart(2, '0')}`;
    if (undoSecondsLeft <= 0) {
      btn.disabled = true;
      hideUndoToast();
    }
    undoSecondsLeft--;
  };
  update();
  undoTimer = setInterval(update, 1000);
}

async function undoLastBatch() {
  if (!lastBatchOpId) return;
  if (!confirm('确定要撤回此次批量操作吗？所有受影响的样本将恢复到之前的状态。')) return;

  const result = await apiRequest(`/api/samples/batch-operations/${lastBatchOpId}/revert`, {
    method: 'POST'
  });

  if (!result || !result.ok) {
    showAlert(result.data?.error || '撤回失败', 'error');
    return;
  }

  showAlert(`已成功撤回，恢复 ${result.data.reverted_count} 个样本状态`, 'success');
  hideUndoToast();
  lastBatchOpId = null;
  loadSamples();
  loadStats();
}

let pollTimer = null;
function startUndoStatusPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const r = await apiRequest('/api/samples/batch-operations/recent');
    if (r && r.ok) {
      const ops = r.data.operations || [];
      const pending = ops.find(o => o.can_undo);
      if (pending && !lastBatchOpId) {
        lastBatchOpId = pending.id;
        undoSecondsLeft = pending.seconds_remaining;
        showUndoToast(pending.sample_count, pending.new_status_text);
      }
      if (lastBatchOpId && !pending) {
        hideUndoToast();
        lastBatchOpId = null;
      }
    }
  }, 15000);
}

async function loadStats() {
  const r = await apiRequest('/api/samples/stats');
  if (!r || !r.ok) return;
  const d = r.data;
  document.getElementById('statTotal').textContent = d.total_samples || 0;
  document.getElementById('statMonth').textContent = d.warehoused_this_month || 0;
  ['PENDING', 'WAREHOUSED', 'PACKED', 'HANDED_OVER', 'ARRIVED', 'FROZEN', 'REVIEW_CLOSED'].forEach(s => {
    const el = document.getElementById('stat' + s);
    if (el) el.textContent = d.status_counts?.[s] || 0;
  });
}

function filterByStatus(status) {
  resetFilters();
  document.getElementById('f_status').value = status;
  currentPage = 1;
  loadSamples();
}

function filterByThisMonth() {
  resetFilters();
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  document.getElementById('f_date_from').value = first.toISOString().split('T')[0];
  currentPage = 1;
  loadSamples();
}

async function loadTemplates() {
  const r = await apiRequest('/api/samples/filter-templates');
  if (!r || !r.ok) return;
  allTemplates = r.data.templates || [];
  renderTemplateSelect();
}

function renderTemplateSelect() {
  const sel = document.getElementById('templateSelect');
  sel.innerHTML = '<option value="">-- 选择模板 --</option>';
  allTemplates.forEach(t => {
    const mark = t.is_default ? ' ⭐' : '';
    sel.innerHTML += `<option value="${t.id}">${t.name}${mark}</option>`;
  });
}

async function loadDefaultTemplate() {
  const r = await apiRequest('/api/samples/filter-templates/default');
  if (!r || !r.ok || !r.data.template) return;
  setFilterParams(r.data.template.filters);
  document.getElementById('templateSelect').value = r.data.template.id;
  document.getElementById('deleteTplBtn').style.display = '';
}

function applyTemplate() {
  const id = parseInt(document.getElementById('templateSelect').value);
  if (!id) {
    document.getElementById('deleteTplBtn').style.display = 'none';
    return;
  }
  const t = allTemplates.find(x => x.id === id);
  if (t) {
    setFilterParams(t.filters);
    document.getElementById('deleteTplBtn').style.display = '';
    currentPage = 1;
    loadSamples();
  }
}

function openSaveTemplateModal() {
  document.getElementById('tplName').value = '';
  document.getElementById('tplDefault').checked = false;
  document.getElementById('saveTplAlert').innerHTML = '';
  document.getElementById('saveTemplateModal').classList.add('active');
}

function closeSaveTemplateModal() {
  document.getElementById('saveTemplateModal').classList.remove('active');
}

async function saveTemplate() {
  const name = document.getElementById('tplName').value.trim();
  const isDefault = document.getElementById('tplDefault').checked;
  if (!name) {
    showAlert('请输入模板名称', 'error', 'saveTplAlert');
    return;
  }
  const filters = getFilterParams();
  const r = await apiRequest('/api/samples/filter-templates', {
    method: 'POST',
    body: JSON.stringify({ name, filters, is_default: isDefault })
  });
  if (!r || !r.ok) {
    showAlert(r.data?.error || '保存失败', 'error', 'saveTplAlert');
    return;
  }
  showAlert('模板已保存', 'success', 'saveTplAlert');
  await loadTemplates();
  if (isDefault) {
    document.getElementById('templateSelect').value = r.data.template_id;
    document.getElementById('deleteTplBtn').style.display = '';
  }
  setTimeout(closeSaveTemplateModal, 500);
}

async function deleteCurrentTemplate() {
  const id = parseInt(document.getElementById('templateSelect').value);
  if (!id) return;
  if (!confirm('确定要删除此模板吗？')) return;

  const r = await apiRequest(`/api/samples/filter-templates/${id}`, { method: 'DELETE' });
  if (!r || !r.ok) {
    showAlert(r.data?.error || '删除失败', 'error');
    return;
  }
  showAlert('模板已删除', 'success');
  document.getElementById('templateSelect').value = '';
  document.getElementById('deleteTplBtn').style.display = 'none';
  await loadTemplates();
}


let importPreviewData = null;
let importStep = 'edit';

function goToImportRecords() {
  window.location.href = '/import-records';
}

function openImportModal() {
  document.getElementById('importModal').classList.add('active');
  document.getElementById('importPreview').innerHTML = '';
  document.getElementById('importResult').innerHTML = '';
  importStep = 'edit';
  importPreviewData = null;
  updateImportFooter();
}

function closeImportModal() {
  document.getElementById('importModal').classList.remove('active');
}

function loadSampleData() {
  const sampleData = [
    { sample_id: 'S2024001', sample_type: '全血' },
    { sample_id: 'S2024002', sample_type: '血清' },
    { sample_id: 'S2024003', sample_type: '血浆' },
    { sample_id: 'S2024004', sample_type: '尿液' },
    { sample_id: 'S2024005', sample_type: '唾液' }
  ];
  document.getElementById('importData').value = JSON.stringify(sampleData, null, 2);
  document.getElementById('importBatchNo').value = 'BATCH-20240601-001';
}

function updateImportFooter() {
  const btnPreview = document.getElementById('btnPreviewImport');
  const btnConfirm = document.getElementById('btnConfirmImport');
  const btnBack = document.getElementById('btnBackToEdit');

  if (importStep === 'edit') {
    btnPreview.style.display = '';
    btnConfirm.style.display = 'none';
    btnBack.style.display = 'none';
  } else if (importStep === 'preview') {
    btnPreview.style.display = 'none';
    btnConfirm.style.display = '';
    btnBack.style.display = '';
  } else if (importStep === 'done') {
    btnPreview.style.display = 'none';
    btnConfirm.style.display = 'none';
    btnBack.style.display = 'none';
  }
}

function backToEdit() {
  importStep = 'edit';
  importPreviewData = null;
  document.getElementById('importPreview').innerHTML = '';
  document.getElementById('importResult').innerHTML = '';
  updateImportFooter();
}

async function previewImport() {
  const batchNo = document.getElementById('importBatchNo').value.trim();
  const dataStr = document.getElementById('importData').value.trim();

  if (!batchNo) {
    showAlert('请输入批次号', 'error', 'importResult');
    return;
  }

  let samples;
  try {
    samples = JSON.parse(dataStr);
  } catch (e) {
    showAlert('JSON 格式错误: ' + e.message, 'error', 'importResult');
    return;
  }

  if (!Array.isArray(samples)) {
    showAlert('数据必须是数组格式', 'error', 'importResult');
    return;
  }

  const result = await apiRequest('/api/samples/import/preview', {
    method: 'POST',
    body: JSON.stringify({ batch_no: batchNo, samples })
  });

  if (!result || !result.ok) {
    showAlert(result.data?.error || '预检失败', 'error', 'importResult');
    return;
  }

  const data = result.data;
  importPreviewData = data;
  importStep = 'preview';

  renderPreviewResult(data);
  updateImportFooter();
}

function renderPreviewResult(data) {
  const preview = document.getElementById('importPreview');

  let detailHtml = '';

  if (data.importable_count > 0) {
    detailHtml += `
      <div style="margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 13px; font-weight: 500; color: var(--success);">✅ 可导入 (${data.importable_count})</span>
          <button class="btn btn-sm" onclick="toggleDetail('importable')" style="font-size: 12px;">展开/收起</button>
        </div>
        <div id="detail-importable" class="import-detail-list" style="display: none;">
          <table class="detail-table">
            <thead><tr><th>#</th><th>样本编号</th><th>样本类型</th></tr></thead>
            <tbody>
              ${data.importable.map((s, i) => `
                <tr>
                  <td>${s.index + 1}</td>
                  <td>${s.sample_id}</td>
                  <td>${s.sample_type || '-'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  if (data.duplicate_batch_count > 0) {
    detailHtml += `
      <div style="margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 13px; font-weight: 500; color: var(--warning);">⚠️ 本批次内重复 (${data.duplicate_batch_count})</span>
          <button class="btn btn-sm" onclick="toggleDetail('dup-batch')" style="font-size: 12px;">展开/收起</button>
        </div>
        <div id="detail-dup-batch" class="import-detail-list" style="display: none;">
          <table class="detail-table">
            <thead><tr><th>#</th><th>样本编号</th><th>原因</th></tr></thead>
            <tbody>
              ${data.duplicates_batch.map((s, i) => `
                <tr>
                  <td>${s.index + 1}</td>
                  <td>${s.sample_id}</td>
                  <td style="color: var(--warning);">${s.reason}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  if (data.duplicate_system_count > 0) {
    detailHtml += `
      <div style="margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 13px; font-weight: 500; color: var(--warning);">⚠️ 系统已存在 (${data.duplicate_system_count})</span>
          <button class="btn btn-sm" onclick="toggleDetail('dup-system')" style="font-size: 12px;">展开/收起</button>
        </div>
        <div id="detail-dup-system" class="import-detail-list" style="display: none;">
          <table class="detail-table">
            <thead><tr><th>#</th><th>样本编号</th><th>原因</th></tr></thead>
            <tbody>
              ${data.duplicates_system.map((s, i) => `
                <tr>
                  <td>${s.index + 1}</td>
                  <td>${s.sample_id}</td>
                  <td style="color: var(--warning);">${s.reason}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  if (data.missing_fields_count > 0) {
    detailHtml += `
      <div style="margin-top: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span style="font-size: 13px; font-weight: 500; color: var(--danger);">❌ 字段缺失 (${data.missing_fields_count})</span>
          <button class="btn btn-sm" onclick="toggleDetail('missing')" style="font-size: 12px;">展开/收起</button>
        </div>
        <div id="detail-missing" class="import-detail-list" style="display: none;">
          <table class="detail-table">
            <thead><tr><th>#</th><th>原始数据</th><th>原因</th></tr></thead>
            <tbody>
              ${data.missing_fields.map((s, i) => `
                <tr>
                  <td>${s.index + 1}</td>
                  <td style="font-family: monospace; font-size: 12px;">${JSON.stringify(s.item).substring(0, 40)}</td>
                  <td style="color: var(--danger);">${s.reason}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  preview.innerHTML = `
    <div class="import-stats">
      <div class="import-stat">
        <div class="import-stat-value">${data.total_count}</div>
        <div class="import-stat-label">待导入总数</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value success">${data.importable_count}</div>
        <div class="import-stat-label">可导入</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value warning">${data.duplicate_total_count}</div>
        <div class="import-stat-label">重复</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value danger">${data.missing_fields_count + data.invalid_count}</div>
        <div class="import-stat-label">无效/缺失</div>
      </div>
    </div>
    ${detailHtml}
    <div style="margin-top: 16px; padding: 12px; background: var(--gray-50); border-radius: var(--radius-sm); font-size: 13px; color: var(--gray-600);">
      <strong>预检结论：</strong>可导入 ${data.importable_count} 条，重复 ${data.duplicate_total_count} 条，无效/缺失 ${data.missing_fields_count + data.invalid_count} 条。
      ${data.importable_count > 0 ? '确认后将导入所有可导入的样本，重复和无效的将被跳过。' : '没有可导入的样本，请检查数据。'}
    </div>
  `;

  document.getElementById('importResult').innerHTML = '';
}

function toggleDetail(type) {
  const map = {
    'importable': 'detail-importable',
    'dup-batch': 'detail-dup-batch',
    'dup-system': 'detail-dup-system',
    'missing': 'detail-missing'
  };
  const el = document.getElementById(map[type]);
  if (el) {
    el.style.display = el.style.display === 'none' ? '' : 'none';
  }
}

async function confirmImport() {
  const batchNo = document.getElementById('importBatchNo').value.trim();
  const dataStr = document.getElementById('importData').value.trim();

  if (!batchNo) {
    showAlert('请输入批次号', 'error', 'importResult');
    return;
  }

  let samples;
  try {
    samples = JSON.parse(dataStr);
  } catch (e) {
    showAlert('JSON 格式错误: ' + e.message, 'error', 'importResult');
    return;
  }

  const result = await apiRequest('/api/samples/import', {
    method: 'POST',
    body: JSON.stringify({ batch_no: batchNo, samples })
  });

  if (!result || !result.ok) {
    showAlert(result.data?.error || '导入失败', 'error', 'importResult');
    return;
  }

  const data = result.data;
  importStep = 'done';
  updateImportFooter();

  const preview = document.getElementById('importPreview');
  preview.innerHTML = `
    <div class="import-stats">
      <div class="import-stat">
        <div class="import-stat-value success">${data.success_count}</div>
        <div class="import-stat-label">成功导入</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value warning">${data.duplicate_count}</div>
        <div class="import-stat-label">重复跳过</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value danger">${data.missing_fields_count + data.invalid_count}</div>
        <div class="import-stat-label">无效/缺失</div>
      </div>
    </div>
  `;

  let resultHtml = `<div class="alert alert-success">
    导入完成！批次号：<strong>${data.batch_no}</strong>
    <div style="margin-top: 8px;">
      <button class="btn btn-sm btn-info" onclick="viewImportRecord(${data.batch_id})">📋 查看导入详情</button>
    </div>
  </div>`;

  document.getElementById('importResult').innerHTML = resultHtml;

  loadSamples();
  loadStats();
}

function viewImportRecord(batchId) {
  window.location.href = `/import-records?batch_id=${batchId}`;
}

function exportHandover() {
  const batchNo = prompt('请输入要导出的批次号（留空导出全部）：', '');
  if (batchNo === null) return;

  let url = '/api/export/handover';
  if (batchNo.trim()) {
    url += `?batch_no=${encodeURIComponent(batchNo.trim())}`;
  }

  window.location.href = url;
}
