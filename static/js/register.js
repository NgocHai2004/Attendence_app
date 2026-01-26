// Face Registration JavaScript

let cameraStream = null;
let isCameraOn = false;

// Logout function
function logout() {
    fetch('/api/logout')
        .then(() => {
            window.location.href = '/login';
        })
        .catch(error => {
            console.error('Logout error:', error);
            window.location.href = '/login';
        });
}

// Show status message
function showStatus(message, type = 'info') {
    const element = document.getElementById('registerStatus');
    const colors = {
        success: '#10b981',
        error: '#ef4444',
        info: '#4f46e5',
        warning: '#f59e0b'
    };

    element.innerHTML = `
        <div style="padding: 12px; background: ${colors[type]}20; color: ${colors[type]}; 
                    border-radius: 8px; border-left: 4px solid ${colors[type]}; font-size: 14px;">
            ${message}
        </div>
    `;
}

// Toggle Camera
async function toggleCamera() {
    const btn = document.getElementById('cameraBtn');

    if (isCameraOn) {
        // Turn off camera
        stopCamera();
        btn.textContent = 'BẬT CAMERA';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-primary');
        showStatus('Camera đã tắt', 'info');
    } else {
        // Turn on camera
        try {
            const video = document.getElementById('cameraPreview');

            cameraStream = await navigator.mediaDevices.getUserMedia({
                video: { width: 640, height: 480 }
            });

            video.srcObject = cameraStream;
            isCameraOn = true;
            btn.textContent = 'TẮT CAMERA';
            btn.classList.remove('btn-primary');
            btn.classList.add('btn-danger');
            showStatus('Camera đã được bật', 'success');
        } catch (error) {
            showStatus('Không thể truy cập camera: ' + error.message, 'error');
            console.error('Camera error:', error);
        }
    }
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(track => track.stop());
        cameraStream = null;
        const video = document.getElementById('cameraPreview');
        video.srcObject = null;
        isCameraOn = false;
    }
}

async function captureAndRegister() {
    const name = document.getElementById('personName').value.trim();
    const className = document.getElementById('className').value.trim();

    if (!name) {
        showStatus('Vui lòng nhập tên người', 'warning');
        return;
    }

    if (!className) {
        showStatus('Vui lòng nhập tên lớp', 'warning');
        return;
    }

    if (!isCameraOn) {
        showStatus('Vui lòng bật camera trước', 'warning');
        return;
    }

    try {
        // Capture frame from video
        const video = document.getElementById('cameraPreview');
        const canvas = document.createElement('canvas');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0);

        // Convert to base64
        const imageData = canvas.toDataURL('image/jpeg');

        showStatus('Đang xử lý...', 'info');

        // Send to server
        const response = await fetch('/api/register-face-camera', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ name, class_name: className, image: imageData })
        });

        const data = await response.json();

        if (data.success) {
            showStatus(data.message, 'success');
            document.getElementById('personName').value = '';
            document.getElementById('className').value = '';
        } else {
            showStatus(data.message, 'error');
        }
    } catch (error) {
        showStatus('Lỗi: ' + error.message, 'error');
        console.error('Capture error:', error);
    }
}

// Upload Functions
function previewImage() {
    const fileInput = document.getElementById('imageUpload');
    if (fileInput.files && fileInput.files[0]) {
        showStatus('Đã chọn ảnh: ' + fileInput.files[0].name, 'info');
    }
}

async function uploadAndRegister() {
    const name = document.getElementById('uploadPersonName').value.trim();
    const className = document.getElementById('uploadClassName').value.trim();
    const fileInput = document.getElementById('imageUpload');

    if (!name) {
        showStatus('Vui lòng nhập tên người', 'warning');
        return;
    }

    if (!className) {
        showStatus('Vui lòng nhập tên lớp', 'warning');
        return;
    }

    if (!fileInput.files || fileInput.files.length === 0) {
        showStatus('Vui lòng chọn ảnh', 'warning');
        return;
    }

    try {
        const formData = new FormData();
        formData.append('name', name);
        formData.append('class_name', className);
        formData.append('image', fileInput.files[0]);

        showStatus('Đang upload và xử lý...', 'info');

        const response = await fetch('/api/register-face-upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            showStatus(data.message, 'success');
            document.getElementById('uploadPersonName').value = '';
            document.getElementById('uploadClassName').value = '';
            fileInput.value = '';
        } else {
            showStatus(data.message, 'error');
        }
    } catch (error) {
        showStatus('Lỗi: ' + error.message, 'error');
        console.error('Upload error:', error);
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopCamera();
});

window.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const className = urlParams.get('class_name');

    if (className) {
        const cameraClassInput = document.getElementById('className');
        const uploadClassInput = document.getElementById('uploadClassName');
        const cameraGroup = document.getElementById('cameraClassGroup');
        const uploadGroup = document.getElementById('uploadClassGroup');
        const classInfo = document.getElementById('classInfo');

        if (cameraClassInput) {
            cameraClassInput.value = className;
            cameraClassInput.disabled = true;
        }
        if (uploadClassInput) {
            uploadClassInput.value = className;
            uploadClassInput.disabled = true;
        }
        if (cameraGroup) {
            cameraGroup.style.display = 'none';
        }
        if (uploadGroup) {
            uploadGroup.style.display = 'none';
        }
        if (classInfo) {
            classInfo.textContent = `Lớp đang đăng ký: ${className}`;
        }
    }
});
