// Authentication JavaScript

// Show alert message
function showAlert(message, type = 'error') {
    const alertContainer = document.getElementById('alertContainer');
    const alertClass = type === 'success' ? 'alert-success' : 'alert-error';
    
    alertContainer.innerHTML = `
        <div class="alert ${alertClass}">
            ${message}
        </div>
    `;
    
    setTimeout(() => {
        alertContainer.innerHTML = '';
    }, 5000);
}

// Login Form Handler
const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        
        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Store user info in localStorage
                if (data.user) {
                    localStorage.setItem('userRole', data.user.role || 'user');
                    localStorage.setItem('username', data.user.username || '');
                }
                showAlert('Đăng nhập thành công! Đang chuyển hướng...', 'success');
                setTimeout(() => {
                    window.location.href = '/dashboard';
                }, 1000);
            } else {
                showAlert(data.message || 'Đăng nhập thất bại');
            }
        } catch (error) {
            showAlert('Lỗi kết nối đến server');
            console.error('Login error:', error);
        }
    });
}

// Register Form Handler
const registerForm = document.getElementById('registerForm');
if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        
        // Validate passwords match
        if (password !== confirmPassword) {
            showAlert('Mật khẩu không khớp!');
            return;
        }
        
        // Validate password length
        if (password.length < 6) {
            showAlert('Mật khẩu phải có ít nhất 6 ký tự');
            return;
        }
        
        try {
            const response = await fetch('/api/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, email, password })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showAlert('Đăng ký thành công! Đang chuyển đến trang đăng nhập...', 'success');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1500);
            } else {
                showAlert(data.message || 'Đăng ký thất bại');
            }
        } catch (error) {
            showAlert('Lỗi kết nối đến server');
            console.error('Register error:', error);
        }
    });
}
