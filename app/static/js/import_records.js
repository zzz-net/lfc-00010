let currentBatchPage = 1;
let batchPerPage = 20;
let batchTotalPages = 1;

let currentItemsPage = 1;
let itemsPerPage = 50;
let itemsTotalPages = 1;
let currentResultFilter = '';
let currentBatchId = null;
let currentBatch = null;

document.addEventListener('DOMContentLoaded', function() {
  loadCurrentUser().then(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const batchId = urlParams.get('batch_id');
    if (batchId) {
      currentBatchId = parseInt(batchId);
      showBatchDetail(currentBatchId);
    } else {
      loadBatches();
    }
  });
});

function goBackToImport() {
  window.location.href = '/samples';
}

function loadBatches() {
  const batchNo = document.getElementById('batchNoSearch').value.trim();
  
  let url = `/api/samples/import/batches?page=${currentBatchPage}&per_page=${batchPerPage}`;
  if (batchNo) {
    url += `&batch_no=${encodeURIComponent(batchNo)}`;
  }
  
  apiRequest(url).then(result => {
    const tbody = document.getElementById('batchesTableBody');
    
    if (!result || !result.ok) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--danger);">加载失败</td></tr>`;
      return;
    }
    
    const data = result.data;
    
    if (data.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 40px; color: var(--gray-400);">暂无导入记录</td></tr>`;
    } else {
      tbody.innerHTML = data.items.map(b => `
        <tr>
          <td><strong>${b.batch_no}</strong></td>
          <td>${b.operator}</td>
          <td>${b.total_count}</td>
          <td style="color: var(--success);">${b.success_count}</td>
          <td style="color: var(--warning);">${b.duplicate_count}</td>
          <td style="color: var(--danger);">${b.invalid_count}</td>
          <td>${formatDateTime(b.created_at)}</td>
          <td>
            <button class="btn btn-sm btn-primary" onclick="showBatchDetail(${b.id})">查看详情</button>
          </td>
        </tr>
      `).join('');
    }
    
    batchTotalPages = Math.ceil(data.total / batchPerPage);
    renderBatchPagination(data.total);
  });
}

function renderBatchPagination(total) {
  const pagination = document.getElementById('batchPagination');
  let html = '';
  
  html += `<button ${currentBatchPage <= 1 ? 'disabled' : ''} onclick="goToBatchPage(${currentBatchPage - 1})">上一页</button>`;
  
  const startPage = Math.max(1, currentBatchPage - 2);
  const endPage = Math.min(batchTotalPages, currentBatchPage + 2);
  
  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="${i === currentBatchPage ? 'active' : ''}" onclick="goToBatchPage(${i})">${i}</button>`;
  }
  
  html += `<button ${currentBatchPage >= batchTotalPages ? 'disabled' : ''} onclick="goToBatchPage(${currentBatchPage + 1})">下一页</button>`;
  html += `<span style="line-height: 36px; margin-left: 12px; color: var(--gray-500); font-size: 14px;">共 ${total} 条</span>`;
  
  pagination.innerHTML = html;
}

function goToBatchPage(page) {
  if (page < 1 || page > batchTotalPages) return;
  currentBatchPage = page;
  loadBatches();
}

function resetBatchFilters() {
  document.getElementById('batchNoSearch').value = '';
  currentBatchPage = 1;
  loadBatches();
}

function showBatchDetail(batchId) {
  currentBatchId = batchId;
  currentItemsPage = 1;
  currentResultFilter = '';
  
  document.getElementById('batchListView').style.display = 'none';
  document.getElementById('batchDetailView').style.display = '';
  
  loadBatchDetail();
}

function backToList() {
  document.getElementById('batchListView').style.display = '';
  document.getElementById('batchDetailView').style.display = 'none';
  currentBatchId = null;
  loadBatches();
}

function loadBatchDetail() {
  let url = `/api/samples/import/batches/${currentBatchId}?page=${currentItemsPage}&per_page=${itemsPerPage}`;
  if (currentResultFilter) {
    url += `&result=${encodeURIComponent(currentResultFilter)}`;
  }
  
  apiRequest(url).then(result => {
    if (!result || !result.ok) {
      showAlert(result.data?.error || '加载失败', 'error');
      return;
    }
    
    const data = result.data;
    currentBatch = data.batch;
    
    document.getElementById('statTotal').textContent = data.batch.total_count;
    document.getElementById('statSuccess').textContent = data.batch.success_count;
    document.getElementById('statDuplicate').textContent = data.batch.duplicate_count;
    document.getElementById('statInvalid').textContent = data.batch.invalid_count;
    
    document.getElementById('detailBatchNo').textContent = data.batch.batch_no;
    document.getElementById('detailOperator').textContent = data.batch.operator;
    document.getElementById('detailTime').textContent = formatDateTime(data.batch.created_at);
    
    const tbody = document.getElementById('batchItemsBody');
    
    if (data.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 40px; color: var(--gray-400);">暂无数据</td></tr>`;
    } else {
      const startIdx = (currentItemsPage - 1) * itemsPerPage;
      tbody.innerHTML = data.items.map((item, idx) => `
        <tr>
          <td>${startIdx + idx + 1}</td>
          <td>${item.sample_id || '<span style="color: var(--gray-400);">-</span>'}</td>
          <td>${item.sample_type || '-'}</td>
          <td>${getResultBadge(item.result)}</td>
          <td>${item.reason || '-'}</td>
        </tr>
      `).join('');
    }
    
    itemsTotalPages = Math.ceil(data.items_total / itemsPerPage);
    renderItemsPagination(data.items_total);
    
    updateFilterButtons();
  });
}

function getResultBadge(result) {
  const map = {
    'success': { text: '成功', class: 'badge-success' },
    'duplicate_batch': { text: '本批重复', class: 'badge-warning' },
    'duplicate_system': { text: '系统已存', class: 'badge-warning' },
    'missing_fields': { text: '字段缺失', class: 'badge-danger' },
    'invalid': { text: '无效', class: 'badge-danger' }
  };
  const info = map[result] || { text: result, class: 'badge-info' };
  return `<span class="badge ${info.class}">${info.text}</span>`;
}

function filterResult(result) {
  currentResultFilter = result;
  currentItemsPage = 1;
  loadBatchDetail();
}

function updateFilterButtons() {
  const buttons = document.querySelectorAll('.result-filter button');
  buttons.forEach(btn => {
    if (btn.dataset.filter === currentResultFilter) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

function renderItemsPagination(total) {
  const pagination = document.getElementById('itemsPagination');
  let html = '';
  
  html += `<button ${currentItemsPage <= 1 ? 'disabled' : ''} onclick="goToItemsPage(${currentItemsPage - 1})">上一页</button>`;
  
  const startPage = Math.max(1, currentItemsPage - 2);
  const endPage = Math.min(itemsTotalPages, currentItemsPage + 2);
  
  for (let i = startPage; i <= endPage; i++) {
    html += `<button class="${i === currentItemsPage ? 'active' : ''}" onclick="goToItemsPage(${i})">${i}</button>`;
  }
  
  html += `<button ${currentItemsPage >= itemsTotalPages ? 'disabled' : ''} onclick="goToItemsPage(${currentItemsPage + 1})">下一页</button>`;
  html += `<span style="line-height: 36px; margin-left: 12px; color: var(--gray-500); font-size: 14px;">共 ${total} 条</span>`;
  
  pagination.innerHTML = html;
}

function goToItemsPage(page) {
  if (page < 1 || page > itemsTotalPages) return;
  currentItemsPage = page;
  loadBatchDetail();
}

function exportBatchResult() {
  if (!currentBatchId) return;
  window.location.href = `/api/export/import-batch/${currentBatchId}`;
}
