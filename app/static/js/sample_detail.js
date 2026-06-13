let sampleData = null;

document.addEventListener('DOMContentLoaded', function() {
  loadCurrentUser().then(() => {
    loadSampleDetail();
  });
});

async function loadSampleDetail() {
  const result = await apiRequest(`/api/samples/${SAMPLE_ID}`);
  
  if (!result || !result.ok) {
    alert('加载失败: ' + (result.data?.error || '未知错误'));
    return;
  }
  
  sampleData = result.data;
  renderSampleDetail();
}

function renderSampleDetail() {
  const s = sampleData;
  
  document.getElementById('infoSampleId').textContent = s.sample_id;
  document.getElementById('infoBatchNo').textContent = s.batch_no;
  document.getElementById('infoSampleType').textContent = s.sample_type || '-';
  document.getElementById('infoStatus').textContent = s.current_status_text;
  document.getElementById('infoCreatedAt').textContent = formatDateTime(s.created_at);
  document.getElementById('infoUpdatedAt').textContent = formatDateTime(s.updated_at);
  
  const badge = document.getElementById('statusBadge');
  badge.className = `status-badge ${getStatusClass(s.current_status)}`;
  badge.textContent = s.current_status_text;
  
  if (s.reviewed_by) {
    document.getElementById('reviewInfo').style.display = 'block';
    document.getElementById('infoReviewedBy').textContent = s.reviewed_by;
    document.getElementById('infoReviewedAt').textContent = formatDateTime(s.reviewed_at);
    document.getElementById('infoReviewRemark').textContent = s.review_remark || '-';
  }
  
  renderTimeline(s.status_logs);
  renderEvidence(s.evidences);
  renderActions(s);
}

function renderTimeline(logs) {
  const timeline = document.getElementById('timeline');
  
  if (!logs || logs.length === 0) {
    timeline.innerHTML = '<p style="color: var(--gray-500);">暂无状态记录</p>';
    return;
  }
  
  timeline.innerHTML = logs.map(log => `
    <div class="timeline-item status-${log.status.toLowerCase()}">
      <div class="timeline-dot"></div>
      <div class="timeline-content">
        <div class="timeline-status">${log.status_text}</div>
        <div class="timeline-meta">
          <span>👤 ${log.operator}</span>
          <span>🕐 ${formatDateTime(log.created_at)}</span>
          ${log.temperature !== null ? `<span>🌡️ ${log.temperature}°C</span>` : ''}
        </div>
        ${log.remark ? `<div class="timeline-remark">${log.remark}</div>` : ''}
      </div>
    </div>
  `).join('');
}

function renderEvidence(evidences) {
  const list = document.getElementById('evidenceList');
  
  if (!evidences || evidences.length === 0) {
    list.innerHTML = '<p style="color: var(--gray-500); text-align: center; padding: 20px;">暂无证据记录</p>';
    return;
  }
  
  const typeIcons = {
    'photo': '📷',
    'document': '📄',
    'text': '📝',
    'temperature': '🌡️'
  };
  
  const typeNames = {
    'photo': '照片证据',
    'document': '文件证据',
    'text': '文字记录',
    'temperature': '温度记录'
  };
  
  list.innerHTML = evidences.map(e => `
    <div class="evidence-item">
      <div class="evidence-icon">${typeIcons[e.type] || '📄'}</div>
      <div class="evidence-content">
        <div class="evidence-type">${typeNames[e.type] || e.type}</div>
        <div class="evidence-desc">${e.description || '(无描述)'}</div>
        ${e.file_path ? `<div class="evidence-desc" style="margin-top: 4px;">📎 文件: ${e.file_path}</div>` : ''}
        <div class="evidence-meta">
          👤 ${e.uploaded_by} · 🕐 ${formatDateTime(e.created_at)}
        </div>
      </div>
    </div>
  `).join('');
}

function renderActions(s) {
  const bar = document.getElementById('actionBar');
  const status = s.current_status;
  const isFrozen = status === 'FROZEN';
  const isClosed = status === 'REVIEW_CLOSED';
  const isArrived = status === 'ARRIVED';
  
  let buttons = [];
  
  if (status === 'PENDING') {
    buttons.push({ text: '入库', action: 'WAREHOUSED', class: 'btn-success', showTemp: true });
  }
  
  if (status === 'WAREHOUSED') {
    buttons.push({ text: '打包', action: 'PACKED', class: 'btn-accent', showTemp: false });
    buttons.push({ text: '录入异常', action: 'exception', class: 'btn-danger', showTemp: false });
  }
  
  if (status === 'PACKED') {
    buttons.push({ text: '交接', action: 'HANDED_OVER', class: 'btn-primary', showTemp: true });
    buttons.push({ text: '录入异常', action: 'exception', class: 'btn-danger', showTemp: false });
  }
  
  if (status === 'HANDED_OVER') {
    buttons.push({ text: '到达确认', action: 'ARRIVED', class: 'btn-success', showTemp: true });
    buttons.push({ text: '录入异常', action: 'exception', class: 'btn-danger', showTemp: false });
  }
  
  if (isFrozen) {
    if (isAdmin()) {
      buttons.push({ text: '复核处理', action: 'review', class: 'btn-accent', showTemp: false });
    } else {
      buttons.push({ text: '🔒 异常冻结中 (需管理员复核)', action: '', class: 'btn', disabled: true, showTemp: false });
    }
  }
  
  if (isClosed || isArrived) {
    buttons.push({ text: '✓ 流程已完成', action: '', class: 'btn', disabled: true, showTemp: false });
  }
  
  buttons.push({ text: '导出时间线', action: 'export', class: 'btn', showTemp: false });
  
  bar.innerHTML = buttons.map(b => {
    if (b.action === '') {
      return `<button class="btn ${b.class}" disabled>${b.text}</button>`;
    }
    if (b.action === 'exception') {
      return `<button class="btn ${b.class}" onclick="openExceptionModal()">${b.text}</button>`;
    }
    if (b.action === 'review') {
      return `<button class="btn ${b.class}" onclick="openReviewModal()">${b.text}</button>`;
    }
    if (b.action === 'export') {
      return `<button class="btn ${b.class}" onclick="exportTimeline()">${b.text}</button>`;
    }
    return `<button class="btn ${b.class}" onclick="openStatusModal('${b.action}', '${b.text}', ${b.showTemp})">${b.text}</button>`;
  }).join('');
}

function openStatusModal(action, title, showTemp) {
  document.getElementById('statusAction').value = action;
  document.getElementById('statusModalTitle').textContent = title;
  document.getElementById('statusRemark').value = '';
  document.getElementById('statusTemp').value = '';
  document.getElementById('tempGroup').style.display = showTemp ? 'block' : 'none';
  document.getElementById('statusModal').classList.add('active');
}

function closeStatusModal() {
  document.getElementById('statusModal').classList.remove('active');
}

async function confirmStatusChange() {
  const action = document.getElementById('statusAction').value;
  const remark = document.getElementById('statusRemark').value.trim();
  const tempStr = document.getElementById('statusTemp').value;
  const temperature = tempStr ? parseFloat(tempStr) : null;
  
  const result = await apiRequest(`/api/samples/${SAMPLE_ID}/status`, {
    method: 'POST',
    body: JSON.stringify({ status: action, remark, temperature })
  });
  
  if (!result || !result.ok) {
    alert('操作失败: ' + (result.data?.error || '未知错误'));
    return;
  }
  
  closeStatusModal();
  loadSampleDetail();
}

function openExceptionModal() {
  document.getElementById('exceptionType').value = 'overtemp';
  document.getElementById('exceptionTemp').value = '';
  document.getElementById('exceptionDesc').value = '';
  document.getElementById('exceptionEvidence').value = '';
  document.getElementById('exceptionModal').classList.add('active');
}

function closeExceptionModal() {
  document.getElementById('exceptionModal').classList.remove('active');
}

async function submitException() {
  const type = document.getElementById('exceptionType').value;
  const tempStr = document.getElementById('exceptionTemp').value;
  const description = document.getElementById('exceptionDesc').value.trim();
  const evidenceFile = document.getElementById('exceptionEvidence').value.trim();
  
  if (!description) {
    alert('请填写异常描述');
    return;
  }
  
  const temperature = tempStr ? parseFloat(tempStr) : null;
  
  const result = await apiRequest(`/api/samples/${SAMPLE_ID}/exception`, {
    method: 'POST',
    body: JSON.stringify({
      type,
      description,
      temperature,
      evidence_file: evidenceFile
    })
  });
  
  if (!result || !result.ok) {
    alert('操作失败: ' + (result.data?.error || '未知错误'));
    return;
  }
  
  closeExceptionModal();
  loadSampleDetail();
}

function openReviewModal() {
  document.getElementById('reviewAction').value = 'close';
  document.getElementById('reviewRemark').value = '';
  document.getElementById('reviewModal').classList.add('active');
}

function closeReviewModal() {
  document.getElementById('reviewModal').classList.remove('active');
}

async function submitReview() {
  const action = document.getElementById('reviewAction').value;
  const remark = document.getElementById('reviewRemark').value.trim();
  
  if (!remark) {
    alert('请填写复核备注');
    return;
  }
  
  const result = await apiRequest(`/api/samples/${SAMPLE_ID}/review`, {
    method: 'POST',
    body: JSON.stringify({ action, remark })
  });
  
  if (!result || !result.ok) {
    alert('操作失败: ' + (result.data?.error || '未知错误'));
    return;
  }
  
  closeReviewModal();
  loadSampleDetail();
}

function exportTimeline() {
  window.location.href = `/api/export/sample-timeline/${SAMPLE_ID}`;
}
