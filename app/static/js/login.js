function fillCredentials(username, password) {
  document.getElementById('username').value = username;
  document.getElementById('password').value = password;
}

document.getElementById('loginForm').addEventListener('submit', async function(e) {
  e.preventDefault();
  
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  
  if (!username || !password) {
    showAlert('请输入用户名和密码', 'error');
    return;
  }
  
  const result = await apiRequest('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  });
  
  if (result && result.ok) {
    showAlert('登录成功，正在跳转...', 'success');
    setTimeout(() => {
      window.location.href = '/samples';
    }, 500);
  } else {
    showAlert(result.data?.error || '登录失败', 'error');
  }
});

window.onload = function() {
  document.getElementById('username').focus();
};
