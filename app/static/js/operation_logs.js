let currentPage = 1;
let perPage = 20;
let totalPages = 1;

document.addEventListener('DOMContentLoaded', function () {
  loadCurrentUser().then(() => {
    loadOperators();
    loadLogs();
  });
});

function goToSamples() {
  window.location.href = '/samples';
}

async function loadOperators() {
  const r = await apiRequest('/api/logs/operators');
  if (!r || !r.ok) return;
  const sel = document.getElementById('f_operator');
  (r.data.operators || []).forEach(op => {
    sel.innerHTML += `<option value="${op}">${op}</option>`;
  });
}

function getFilterParams() {
  return {
    operator: document.getElementById('f_operator').value,
    operation_type: document.getElementById('f_type').value,
    date_from: document.getElementById('f_date_from').value,
    date_to: document.getElementById('f_date_to').value
  };
}

function doSearch() {
  currentPage = 1;
  loadLogs();
}

function resetFilters() {
  document.getElementById('f_operator').value = '';
  document.getElementById('f_type').value = '';
  document.getElementById('f_date_from').value = '';
  document.getElementById('f_date_to').value = '';
  currentPage = 1;
  loadLogs();
}

async function loadLogs() {
  const f = getFilterParams();
  let url = `/api/logs?page=${currentPage}&per_page=${perPage}`;
  for (const [k, v] of Object.entries(f)) {
    if (v) url += `&${k}=${encodeURIComponent(v)}`;
  }

  const result = await apiRequest(url);
  const tbody = document.getElementById('logsTableBody');

  if (!result || !result.ok) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--danger);">加载失败</td></tr>`;
    return;
  }

  const data = result.data;

  if (data.items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; padding: 40px; color: var(--gray-400);">暂无数据</td></tr>`;
  } else {
    tbody.innerHTML = data.items.map(l => `
      <tr>
        <td>${formatDateTime(l.created_at)}</td>
        <td><strong>${l.operator}</strong></td>
        <td><span class="badge badge-info">${l.operation_type_text}</span></td>
        <td>${l.target_type ? `${l.target_type} #${l.target_id || ''}` : '-'}</td>
        <td style="max-width: 400px;">${l.detail || '-'}</td>
        <td>${l.sample_count || '-'}</td>
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
  loadLogs();
}

function exportLogs() {
  const f = getFilterParams();
  let url = '/api/logs/export?';
  const parts = [];
  for (const [k, v] of Object.entries(f)) {
    if (v) parts.push(`${k}=${encodeURIComponent(v)}`);
  }
  url += parts.join('&');
  window.location.href = url;
}
