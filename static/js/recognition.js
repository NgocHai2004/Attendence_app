let recognitionInterval = null;
let isStreamRunning = false;
let lastSummaryUpdate = 0;
let browserCameraStream = null;
let captureInterval = null;
let telegramEnabled = false;

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

function showStatus(message, type = 'info') {
    const element = document.getElementById('rtspStatus');
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

function getCameraMode() {
    const modeInput = document.querySelector('input[name="cameraMode"]:checked');
    return modeInput ? modeInput.value : 'browser';
}

async function startRTSP() {
    const cameraMode = getCameraMode();
    const urlParams = new URLSearchParams(window.location.search);
    const class_name = urlParams.get('class_name');

    const modeInput = document.querySelector('input[name="attendanceMode"]:checked');
    if (!modeInput) {
        showStatus('Vui lòng chọn chế độ điểm danh (VÀO hoặc RA)!', 'warning');
        return;
    }
    const attendance_type = modeInput.value;

    if (!class_name) {
        showStatus('Thiếu thông tin lớp học. Vui lòng quay lại Dashboard!', 'error');
        setTimeout(() => window.location.href = '/dashboard', 2000);
        return;
    }

    if (cameraMode === 'browser') {
        await startBrowserCamera(class_name, attendance_type);
    } else {
        await startServerCamera(class_name, attendance_type);
    }
}

async function startBrowserCamera(class_name, attendance_type) {
    try {
        showStatus('Đang kết nối camera trình duyệt...', 'info');

        await fetch('/api/browser-session/start', { method: 'POST' });

        const video = document.getElementById('browserCamera');
        const rtspImg = document.getElementById('rtspStream');
        
        browserCameraStream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480 }
        });
        
        video.srcObject = browserCameraStream;
        video.style.display = 'block';
        rtspImg.style.display = 'none';
        
        isStreamRunning = true;
        document.getElementById('startBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;
        document.querySelectorAll('input[name="attendanceMode"]').forEach(input => input.disabled = true);
        document.querySelectorAll('input[name="cameraMode"]').forEach(input => input.disabled = true);

        const modeText = attendance_type === 'in' ? 'VÀO' : 'RA';
        showStatus(`Đang điểm danh <strong>${modeText}</strong> cho lớp: <strong>${class_name}</strong>`, 'success');

        captureInterval = setInterval(() => {
            captureAndRecognize(class_name, attendance_type);
        }, 1000);

        loadAttendanceSummary(attendance_type);

    } catch (error) {
        showStatus('Không thể truy cập camera: ' + error.message, 'error');
        console.error('Camera error:', error);
    }
}

async function captureAndRecognize(class_name, attendance_type) {
    if (!isStreamRunning) return;

    const video = document.getElementById('browserCamera');
    const canvas = document.getElementById('captureCanvas');
    
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0);
    
    const imageData = canvas.toDataURL('image/jpeg', 0.8);

    try {
        const response = await fetch('/api/recognize-frame', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                image: imageData,
                class_name: class_name,
                attendance_type: attendance_type
            })
        });

        const data = await response.json();
        if (data.success && data.faces && data.faces.length > 0) {
            updateRecognizedFaces(data.faces);
        }
        refreshAttendanceSummary();
    } catch (error) {
        console.error('Recognition error:', error);
    }
}

async function startServerCamera(class_name, attendance_type) {
    const rtspUrl = document.getElementById('rtspUrl').value.trim();
    const useWebcam = !rtspUrl || rtspUrl === '0';

    try {
        const sourceName = useWebcam ? 'camera server' : 'RTSP';
        showStatus(`Đang kết nối ${sourceName}...`, 'info');

        const response = await fetch('/api/start-rtsp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                rtsp_url: rtspUrl || '0',
                class_name: class_name,
                attendance_type: attendance_type
            })
        });

        const data = await response.json();

        if (data.success) {
            const modeText = attendance_type === 'in' ? 'VÀO' : 'RA';
            showStatus(`Đang điểm danh <strong>${modeText}</strong> cho lớp: <strong>${class_name}</strong>`, 'success');
            isStreamRunning = true;

            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;
            document.querySelectorAll('input[name="attendanceMode"]').forEach(input => input.disabled = true);
            document.querySelectorAll('input[name="cameraMode"]').forEach(input => input.disabled = true);

            const img = document.getElementById('rtspStream');
            const video = document.getElementById('browserCamera');
            img.style.display = 'block';
            video.style.display = 'none';
            img.src = '/api/video-feed?' + new Date().getTime();

            startRecognitionPolling();
            loadAttendanceSummary(attendance_type);
        } else {
            showStatus(data.message, 'error');
        }
    } catch (error) {
        showStatus('Lỗi: ' + error.message, 'error');
        console.error('RTSP error:', error);
    }
}

async function stopRTSP() {
    const cameraMode = getCameraMode();
    const urlParams = new URLSearchParams(window.location.search);
    const class_name = urlParams.get('class_name');
    const modeInput = document.querySelector('input[name="attendanceMode"]:checked');
    const attendance_type = modeInput ? modeInput.value : 'in';

    if (cameraMode === 'browser') {
        if (captureInterval) {
            clearInterval(captureInterval);
            captureInterval = null;
        }
        if (browserCameraStream) {
            browserCameraStream.getTracks().forEach(track => track.stop());
            browserCameraStream = null;
        }
        document.getElementById('browserCamera').srcObject = null;
        
        await fetch('/api/browser-session/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ class_name, attendance_type })
        });
        
        showStatus('Camera đã dừng', 'info');
    } else {
        try {
            await fetch('/api/stop-rtsp');
            showStatus('RTSP stream đã dừng', 'info');
            stopRecognitionPolling();
            document.getElementById('rtspStream').src = '';
        } catch (error) {
            showStatus('Lỗi: ' + error.message, 'error');
        }
    }

    isStreamRunning = false;
    document.getElementById('startBtn').disabled = false;
    document.getElementById('stopBtn').disabled = true;
    document.querySelectorAll('input[name="attendanceMode"]').forEach(input => input.disabled = false);
    document.querySelectorAll('input[name="cameraMode"]').forEach(input => input.disabled = false);

    document.getElementById('recognizedFaces').innerHTML = `
        <p style="text-align: center; color: #64748b; padding: 20px;">
            Chưa có khuôn mặt nào được nhận diện
        </p>
    `;
    clearAttendanceSummary();
}

function startRecognitionPolling() {
    if (recognitionInterval) {
        clearInterval(recognitionInterval);
    }

    recognitionInterval = setInterval(async () => {
        if (!isStreamRunning) {
            stopRecognitionPolling();
            return;
        }

        try {
            const response = await fetch('/api/recognized-faces');
            const data = await response.json();

            if (data.success && data.faces && data.faces.length > 0) {
                updateRecognizedFaces(data.faces);
            }
            refreshAttendanceSummary();
        } catch (error) {
            console.error('Recognition polling error:', error);
        }
    }, 1000);
}

function stopRecognitionPolling() {
    if (recognitionInterval) {
        clearInterval(recognitionInterval);
        recognitionInterval = null;
    }
}

function updateRecognizedFaces(faces) {
    const container = document.getElementById('recognizedFaces');

    if (faces.length === 0) {
        container.innerHTML = `
            <p style="text-align: center; color: #64748b; padding: 20px;">
                Chưa có khuôn mặt nào được nhận diện
            </p>
        `;
        return;
    }

    let html = '';
    faces.forEach(face => {
        const isUnknown = face.name === 'Unknown';
        const confidenceColor = isUnknown ? '#ef4444' : '#10b981';
        const faceImageSrc = face.face_image ? `data:image/jpeg;base64,${face.face_image}` : '';
        const dbImageSrc = face.db_image ? `data:image/jpeg;base64,${face.db_image}` : '';
        const showFaceImage = !isUnknown && faceImageSrc;

        const modeLabel = face.attendance_type === 'in' ? 'VÀO' : 'RA';
        const modeClass = face.attendance_type === 'in' ? 'mode-in-label' : 'mode-out-label';
        const now = new Date();
        const dateTimeStr = now.toLocaleDateString('vi-VN') + ' ' + now.toLocaleTimeString('vi-VN');

        html += `
            <div class="face-item-new">
                <div class="face-col-recognition">
                    ${showFaceImage ? `
                        <img src="${faceImageSrc}" alt="Face" class="face-img" />
                        <div class="face-img-label" style="color: ${confidenceColor};">${isUnknown ? '---' : face.confidence + '%'}</div>
                    ` : ''}
                </div>
                <div class="face-col-db">
                    ${dbImageSrc ? `<img src="${dbImageSrc}" alt="DB Face" class="face-img" />` : ''}
                    <div class="face-img-label">${face.name}</div>
                </div>
                <div class="face-status-section">
                    <div class="status-row">MSV: ${face.msv || '---'}</div>
                    <div class="status-row"><span class="${modeClass}">${modeLabel}</span></div>
                    <div class="status-datetime">${dateTimeStr}</div>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function clearAttendanceSummary() {
    const container = document.getElementById('attendanceSummary');
    if (container) {
        container.innerHTML = '';
    }
}

async function loadAttendanceSummary(attendance_type) {
    const urlParams = new URLSearchParams(window.location.search);
    const class_name = urlParams.get('class_name');
    const container = document.getElementById('attendanceSummary');

    if (!class_name || !container) return;

    const typeQuery = attendance_type ? `&attendance_type=${encodeURIComponent(attendance_type)}` : '';

    try {
        const response = await fetch(`/api/attendance-summary?class_name=${encodeURIComponent(class_name)}${typeQuery}&session=1`);
        const data = await response.json();

        if (data.success) {
            const summary = data.summary || { present: 0, absent: 0, total: 0 };
            container.innerHTML = `
                <div class="summary-card">Có mặt: ${summary.present}/${summary.total}</div>
                <div class="summary-card">Vắng: ${summary.absent}/${summary.total}</div>
            `;
        } else {
            container.innerHTML = '';
        }
    } catch (error) {
        container.innerHTML = '';
    }
}

function refreshAttendanceSummary() {
    const now = Date.now();
    if (now - lastSummaryUpdate < 5000) return;
    lastSummaryUpdate = now;
    const modeInput = document.querySelector('input[name="attendanceMode"]:checked');
    const attendance_type = modeInput ? modeInput.value : null;
    loadAttendanceSummary(attendance_type);
}

// Telegram toggle function
async function toggleTelegram(checked) {
    telegramEnabled = checked;
    try {
        const response = await fetch('/api/telegram/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ send_on_stop: checked })
        });
        const data = await response.json();
        if (data.success) {
            showStatus(checked ? '📱 Telegram: Sẽ gửi thông báo khi dừng điểm danh' : '📱 Telegram: Đã tắt thông báo', 'info');
        }
    } catch (error) {
        console.error('Telegram toggle error:', error);
    }
}

// Load initial Telegram config
async function loadTelegramConfig() {
    try {
        const response = await fetch('/api/telegram/config');
        const data = await response.json();
        if (data.success && data.config) {
            const toggle = document.getElementById('telegramToggle');
            if (toggle) {
                toggle.checked = data.config.send_on_stop || false;
                telegramEnabled = toggle.checked;
                // If not configured, disable the toggle
                if (!data.config.configured) {
                    toggle.disabled = true;
                    const telegramToggleDiv = toggle.closest('.telegram-toggle');
                    if (telegramToggleDiv) {
                        telegramToggleDiv.style.opacity = '0.6';
                        telegramToggleDiv.querySelector('div > div:last-child').textContent =
                            'Chưa cấu hình Telegram. Vào Dashboard → Cài đặt Telegram để cấu hình.';
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error loading telegram config:', error);
    }
}

window.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const class_name = urlParams.get('class_name');

    if (class_name) {
        showStatus(`Sẵn sàng điểm danh cho lớp: <strong>${class_name}</strong>. Vui lòng chọn chế độ và nhấn BẮT ĐẦU.`, 'info');
    } else {
        showStatus('Thiếu thông tin lớp học. Đang quay lại Dashboard...', 'error');
        setTimeout(() => window.location.href = '/dashboard', 2000);
    }

    // Load Telegram configuration
    loadTelegramConfig();

    document.querySelectorAll('input[name="attendanceMode"]').forEach(input => {
        input.addEventListener('change', () => {
            const modeText = input.value === 'in' ? 'VÀO' : 'RA';
            if (class_name && !isStreamRunning) {
                showStatus(`Chế độ đã chọn: <strong>${modeText}</strong> cho lớp: <strong>${class_name}</strong>`, 'info');
            }
        });
    });

    document.querySelectorAll('input[name="cameraMode"]').forEach(input => {
        input.addEventListener('change', () => {
            const rtspGroup = document.getElementById('rtspUrlGroup');
            if (input.value === 'server') {
                rtspGroup.style.display = 'flex';
            } else {
                rtspGroup.style.display = 'none';
            }
        });
    });
});

window.addEventListener('beforeunload', () => {
    if (isStreamRunning) {
        stopRTSP();
    }
    stopRecognitionPolling();
});
