let currentPage = 1;
let perPage = 20;
let totalPages = 1;

document.addEventListener('DOMContentLoaded', function() {
  loadCurrentUser().then(() => {
    loadSamples();
  });
  
  document.getElementById('searchInput').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') {
      currentPage = 1;
      loadSamples();
    }
  });
  
  document.getElementById('statusFilter').addEventListener('change', function() {
    currentPage = 1;
    loadSamples();
  });
});

async function loadSamples() {
  const search = document.getElementById('searchInput').value.trim();
  const status = document.getElementById('statusFilter').value;
  
  let url = `/api/samples?page=${currentPage}&per_page=${perPage}`;
  if (search) url += `&search=${encodeURIComponent(search)}`;
  if (status) url += `&status=${encodeURIComponent(status)}`;
  
  const result = await apiRequest(url);
  
  const tbody = document.getElementById('samplesTableBody');
  
  if (!result || !result.ok) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--danger);">加载失败</td></tr>`;
    return;
  }
  
  const data = result.data;
  
  if (data.items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; padding: 40px; color: var(--gray-400);">暂无数据</td></tr>`;
  } else {
    tbody.innerHTML = data.items.map(s => `
      <tr>
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

function resetFilters() {
  document.getElementById('searchInput').value = '';
  document.getElementById('statusFilter').value = '';
  currentPage = 1;
  loadSamples();
}

function viewDetail(id) {
  window.location.href = `/samples/${id}`;
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
