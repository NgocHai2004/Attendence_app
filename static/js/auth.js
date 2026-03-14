/**
 * Authentication JavaScript - Với tích hợp CAPTCHA
 * ==================================================
 * 
 * GIẢI THÍCH TỔNG QUAN:
 * File này xử lý logic đăng nhập, đăng ký VÀ CAPTCHA.
 * 
 * FLOW CAPTCHA:
 * 1. Khi trang load → gọi refreshCaptcha() để lấy CAPTCHA từ server
 * 2. Server trả về { captcha_id, captcha_image }
 * 3. captcha_image được hiển thị trong thẻ <img>
 * 4. captcha_id được lưu vào input hidden
 * 5. Khi submit form → gửi kèm captcha_id + captcha_text (người dùng nhập)
 * 6. Server xác thực CAPTCHA trước khi xử lý login/register
 * 7. Nếu CAPTCHA sai → tự động tải CAPTCHA mới
 */

// ============================================================
// CAPTCHA FUNCTIONS
// ============================================================

/**
 * Tải CAPTCHA mới từ server.
 * 
 * GIẢI THÍCH:
 * - Gọi GET /api/captcha/generate để lấy CAPTCHA mới
 * - Cập nhật hình ảnh CAPTCHA trên giao diện
 * - Lưu captcha_id vào input hidden để gửi kèm form
 * - Xóa ô nhập CAPTCHA cũ
 * - Thêm animation xoay cho nút refresh
 */
async function refreshCaptcha() {
    try {
        // Thêm animation xoay cho nút refresh
        const refreshBtn = document.querySelector('.captcha-refresh-btn');
        if (refreshBtn) {
            refreshBtn.classList.add('spinning');
            setTimeout(() => refreshBtn.classList.remove('spinning'), 600);
        }

        // Gọi API lấy CAPTCHA mới
        const response = await fetch('/api/captcha/generate');
        const data = await response.json();
        
        if (data.success) {
            // Cập nhật hình ảnh CAPTCHA
            // data.captcha_image là chuỗi base64: "data:image/png;base64,..."
            const captchaImage = document.getElementById('captchaImage');
            if (captchaImage) {
                captchaImage.src = data.captcha_image;
            }
            
            // Lưu captcha_id (dùng để xác thực khi submit)
            const captchaId = document.getElementById('captchaId');
            if (captchaId) {
                captchaId.value = data.captcha_id;
            }
            
            // Xóa nội dung ô nhập CAPTCHA cũ
            const captchaInput = document.getElementById('captchaInput');
            if (captchaInput) {
                captchaInput.value = '';
                captchaInput.focus(); // Focus vào ô nhập để thuận tiện
            }
        } else {
            console.error('Failed to load CAPTCHA:', data.message);
        }
    } catch (error) {
        console.error('Error loading CAPTCHA:', error);
    }
}

// ============================================================
// ALERT FUNCTION
// ============================================================

/**
 * Hiển thị thông báo lỗi/thành công.
 */
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

// ============================================================
// LOGIN FORM HANDLER
// ============================================================

const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        
        // ====== LẤY THÔNG TIN CAPTCHA ======
        const captchaId = document.getElementById('captchaId').value;
        const captchaText = document.getElementById('captchaInput').value;
        
        // Kiểm tra CAPTCHA đã nhập chưa
        if (!captchaText) {
            showAlert('Vui lòng nhập mã CAPTCHA');
            document.getElementById('captchaInput').focus();
            return;
        }
        
        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                // Gửi kèm captcha_id và captcha_text
                body: JSON.stringify({ 
                    email, 
                    password,
                    captcha_id: captchaId,
                    captcha_text: captchaText
                })
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
                
                // ====== TẢI LẠI CAPTCHA KHI CÓ LỖI ======
                // Luôn tải CAPTCHA mới sau mỗi lần submit (dù đúng hay sai)
                // Vì CAPTCHA cũ đã bị xóa phía server (one-time use)
                refreshCaptcha();
            }
        } catch (error) {
            showAlert('Lỗi kết nối đến server');
            console.error('Login error:', error);
            refreshCaptcha();
        }
    });
}

// ============================================================
// REGISTER FORM HANDLER
// ============================================================

const registerForm = document.getElementById('registerForm');
if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        
        // ====== LẤY THÔNG TIN CAPTCHA ======
        const captchaId = document.getElementById('captchaId').value;
        const captchaText = document.getElementById('captchaInput').value;
        
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
        
        // Kiểm tra CAPTCHA đã nhập chưa
        if (!captchaText) {
            showAlert('Vui lòng nhập mã CAPTCHA');
            document.getElementById('captchaInput').focus();
            return;
        }
        
        try {
            const response = await fetch('/api/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                // Gửi kèm captcha_id và captcha_text
                body: JSON.stringify({ 
                    username, 
                    email, 
                    password,
                    captcha_id: captchaId,
                    captcha_text: captchaText
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                showAlert('Đăng ký thành công! Đang chuyển đến trang đăng nhập...', 'success');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1500);
            } else {
                showAlert(data.message || 'Đăng ký thất bại');
                
                // ====== TẢI LẠI CAPTCHA KHI CÓ LỖI ======
                refreshCaptcha();
            }
        } catch (error) {
            showAlert('Lỗi kết nối đến server');
            console.error('Register error:', error);
            refreshCaptcha();
        }
    });
}

// ============================================================
// TẢI CAPTCHA KHI TRANG ĐƯỢC LOAD
// ============================================================

/**
 * GIẢI THÍCH:
 * - DOMContentLoaded: sự kiện khi HTML đã load xong
 * - Tự động gọi refreshCaptcha() để hiển thị CAPTCHA đầu tiên
 * - Người dùng không cần thao tác gì, CAPTCHA sẽ tự hiển thị
 */
document.addEventListener('DOMContentLoaded', function() {
    // Chỉ tải CAPTCHA nếu có phần tử captchaImage trên trang
    if (document.getElementById('captchaImage')) {
        refreshCaptcha();
    }
});
