const API_BASE = '';

let currentUser = null;

async function apiRequest(url, options = {}) {
  const defaultOptions = {
    headers: {
      'Content-Type': 'application/json'
    },
    credentials: 'same-origin'
  };
  
  const opts = { ...defaultOptions, ...options };
  
  try {
    const response = await fetch(url, opts);
    const data = await response.json();
    
    if (response.status === 401) {
      window.location.href = '/login';
      return;
    }
    
    return { ok: response.ok, status: response.status, data };
  } catch (err) {
    console.error('API request failed:', err);
    return { ok: false, error: err.message };
  }
}

function showAlert(message, type = 'error', containerId = 'alert-container') {
  const container = document.getElementById(containerId);
  if (!container) return;
  
  container.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
  
  if (type === 'success' || type === 'info') {
    setTimeout(() => {
      const alertEl = container.querySelector('.alert');
      if (alertEl) alertEl.remove();
    }, 3000);
  }
}

function formatDateTime(isoString) {
  if (!isoString) return '-';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
}

function getStatusClass(status) {
  const map = {
    'PENDING': 'status-pending',
    'WAREHOUSED': 'status-warehoused',
    'PACKED': 'status-packed',
    'HANDED_OVER': 'status-handed_over',
    'ARRIVED': 'status-arrived',
    'FROZEN': 'status-frozen',
    'REVIEW_CLOSED': 'status-review_closed'
  };
  return map[status] || '';
}

function getStatusText(status) {
  const map = {
    'PENDING': '待入库',
    'WAREHOUSED': '已入库',
    'PACKED': '已打包',
    'HANDED_OVER': '已交接',
    'ARRIVED': '已到达',
    'FROZEN': '异常冻结',
    'REVIEW_CLOSED': '已复核关闭'
  };
  return map[status] || status;
}

function getRoleText(role) {
  return role === 'admin' ? '管理员' : '操作员';
}

async function loadCurrentUser() {
  try {
    const result = await apiRequest('/api/auth/me');
    if (result && result.ok) {
      currentUser = result.data;
      updateUserDisplay();
      return currentUser;
    }
  } catch (e) {
    console.error('Failed to load user:', e);
  }
  return null;
}

function updateUserDisplay() {
  if (!currentUser) return;
  
  const userInfo = document.getElementById('userInfo');
  const userRole = document.getElementById('userRole');
  
  if (userInfo) userInfo.textContent = currentUser.username;
  if (userRole) userRole.textContent = getRoleText(currentUser.role);
}

async function logout() {
  const result = await apiRequest('/api/auth/logout', { method: 'POST' });
  if (result && result.ok) {
    window.location.href = '/login';
  }
}

function isAdmin() {
  return currentUser && currentUser.role === 'admin';
}
