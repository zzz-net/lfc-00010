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

function openImportModal() {
  document.getElementById('importModal').classList.add('active');
  document.getElementById('importPreview').innerHTML = '';
  document.getElementById('importResult').innerHTML = '';
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
  
  const preview = document.getElementById('importPreview');
  preview.innerHTML = `
    <div class="import-preview">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>样本编号</th>
            <th>样本类型</th>
          </tr>
        </thead>
        <tbody>
          ${samples.map((s, i) => `
            <tr>
              <td>${i + 1}</td>
              <td>${s.sample_id || '<span style="color: var(--danger);">缺失</span>'}</td>
              <td>${s.sample_type || '-'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
    <div class="import-stats">
      <div class="import-stat">
        <div class="import-stat-value">${samples.length}</div>
        <div class="import-stat-label">待导入总数</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value warning">-</div>
        <div class="import-stat-label">重复项 (导入时检测)</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value success">-</div>
        <div class="import-stat-label">将成功导入</div>
      </div>
    </div>
  `;
  
  document.getElementById('importResult').innerHTML = '';
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
  
  const preview = document.getElementById('importPreview');
  preview.innerHTML = `
    <div class="import-stats">
      <div class="import-stat">
        <div class="import-stat-value success">${data.imported_count}</div>
        <div class="import-stat-label">成功导入</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value warning">${data.duplicate_count}</div>
        <div class="import-stat-label">重复跳过</div>
      </div>
      <div class="import-stat">
        <div class="import-stat-value danger">${data.invalid_count}</div>
        <div class="import-stat-label">无效数据</div>
      </div>
    </div>
  `;
  
  let resultHtml = `<div class="alert alert-success">导入完成！批次号：${data.batch_no}</div>`;
  
  if (data.duplicates.length > 0) {
    resultHtml += `<div style="margin-top: 12px;">
      <p style="font-size: 13px; color: var(--warning); font-weight: 500; margin-bottom: 8px;">重复的样本编号：</p>
      <div style="display: flex; flex-wrap: wrap; gap: 6px;">
        ${data.duplicates.map(d => `<span class="status-badge status-warning" style="background: #fef3c7; color: #92400e;">${d.sample_id}</span>`).join('')}
      </div>
    </div>`;
  }
  
  document.getElementById('importResult').innerHTML = resultHtml;
  
  loadSamples();
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
