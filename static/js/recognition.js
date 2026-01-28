// RTSP Recognition JavaScript

let recognitionInterval = null;
let isStreamRunning = false;
let lastSummaryUpdate = 0;

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

// RTSP Functions
async function startRTSP() {
    const rtspUrl = document.getElementById('rtspUrl').value.trim();
    const urlParams = new URLSearchParams(window.location.search);
    const class_name = urlParams.get('class_name');

    // Get attendance type
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

    // Allow empty or "0" to use webcam
    const useWebcam = !rtspUrl || rtspUrl === '0';

    try {
        const sourceName = useWebcam ? 'camera máy tính' : 'RTSP';
        showStatus(`Đang kết nối ${sourceName}...`, 'info');

        const requestBody = {
            rtsp_url: rtspUrl || '0',
            class_name: class_name,
            attendance_type: attendance_type
        };

        const response = await fetch('/api/start-rtsp', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        if (data.success) {
            const modeText = attendance_type === 'in' ? 'VÀO' : 'RA';
            showStatus(`Đã bắt đầu điểm danh <strong>${modeText}</strong> cho lớp: <strong>${class_name}</strong>`, 'success');
            isStreamRunning = true;

            // Update button states
            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;

            // Disable mode selection while running
            document.querySelectorAll('input[name="attendanceMode"]').forEach(input => input.disabled = true);

            // Start video feed
            const img = document.getElementById('rtspStream');
            img.src = '/api/video-feed?' + new Date().getTime();

            // Start polling for recognized faces
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
    try {
        const response = await fetch('/api/stop-rtsp');
        const data = await response.json();

        if (data.success) {
            showStatus('RTSP stream đã dừng', 'info');
            isStreamRunning = false;

            // Update button states
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').disabled = true;

            // Stop video feed
            const img = document.getElementById('rtspStream');
            img.src = '';

            // Stop polling
            stopRecognitionPolling();

            // Clear recognized faces
            document.getElementById('recognizedFaces').innerHTML = `
                <p style="text-align: center; color: #64748b; padding: 20px;">
                    Chưa có khuôn mặt nào được nhận diện
                </p>
            `;

            // Re-enable mode selection
            document.querySelectorAll('input[name="attendanceMode"]').forEach(input => input.disabled = false);

            clearAttendanceSummary();
        } else {
            showStatus(data.message, 'error');
        }
    } catch (error) {
        showStatus('Lỗi: ' + error.message, 'error');
        console.error('Stop RTSP error:', error);
    }
}

// Recognition Polling
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
    }, 1000); // Poll every second
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

    if (!class_name || !container) {
        return;
    }

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
    if (now - lastSummaryUpdate < 5000) {
        return;
    }
    lastSummaryUpdate = now;
    const modeInput = document.querySelector('input[name="attendanceMode"]:checked');
    const attendance_type = modeInput ? modeInput.value : null;
    loadAttendanceSummary(attendance_type);
}

// Initialize and event listeners
window.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const class_name = urlParams.get('class_name');

    if (class_name) {
        showStatus(`Sẵn sàng điểm danh cho lớp: <strong>${class_name}</strong>. Vui lòng chọn chế độ VÀO/RA và nhấn BẮT ĐẦU.`, 'info');
    } else {
        showStatus('Thiếu thông tin lớp học. Đang quay lại Dashboard...', 'error');
        setTimeout(() => window.location.href = '/dashboard', 2000);
    }

    // Add listener to radio buttons for immediate feedback
    document.querySelectorAll('input[name="attendanceMode"]').forEach(input => {
        input.addEventListener('change', () => {
            const modeText = input.value === 'in' ? 'VÀO' : 'RA';
            if (class_name && !isStreamRunning) {
                showStatus(`Chế độ đã chọn: <strong>${modeText}</strong> cho lớp: <strong>${class_name}</strong>`, 'info');
            }
        });
    });
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (isStreamRunning) {
        stopRTSP();
    }
    stopRecognitionPolling();
});
