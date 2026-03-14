"""
CAPTCHA Service - Tạo và xác thực mã CAPTCHA dạng hình ảnh
============================================================

## GIẢI THÍCH TỔNG QUAN:
CAPTCHA (Completely Automated Public Turing test to tell Computers and Humans Apart)
là một cơ chế bảo mật giúp phân biệt người dùng thật và bot tự động.

## NGUYÊN LÝ HOẠT ĐỘNG:
1. Server tạo ra một chuỗi ký tự ngẫu nhiên (ví dụ: "A3X7K")
2. Chuỗi này được vẽ lên hình ảnh với các hiệu ứng nhiễu (noise):
   - Đường kẻ ngẫu nhiên (lines) → làm khó OCR bot
   - Chấm nhiễu (dots) → thêm nhiễu nền
   - Xoay/biến dạng chữ (rotation) → chống nhận dạng tự động
   - Màu sắc ngẫu nhiên → tăng độ phức tạp
3. Hình ảnh được gửi cho người dùng dưới dạng base64
4. Mã CAPTCHA thật được lưu trong session phía server
5. Khi người dùng nhập mã, server so sánh với mã đã lưu

## BẢO MẬT:
- Mã CAPTCHA được lưu phía server (session), KHÔNG gửi cho client
- Mỗi CAPTCHA có thời gian hết hạn (5 phút)
- So sánh không phân biệt hoa/thường (case-insensitive)
- Mỗi lần xác thực sai, CAPTCHA được tạo mới
"""

import random
import string
import io
import base64
import math
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ============================================================
# CẤU HÌNH CAPTCHA
# ============================================================

# Kích thước ảnh CAPTCHA (rộng x cao, pixel)
CAPTCHA_WIDTH = 280
CAPTCHA_HEIGHT = 80

# Số ký tự trong mã CAPTCHA
CAPTCHA_LENGTH = 5

# Thời gian hết hạn (giây) - 5 phút
CAPTCHA_EXPIRE_TIME = 300

# Bộ ký tự được sử dụng (loại bỏ các ký tự dễ nhầm lẫn: 0/O, 1/l/I)
# Điều này giúp người dùng dễ nhận diện hơn
CAPTCHA_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'

# Màu nền CAPTCHA
BG_COLORS = [
    (240, 245, 255),  # Xanh nhạt
    (255, 245, 238),  # Cam nhạt
    (245, 255, 245),  # Xanh lá nhạt
    (255, 248, 240),  # Vàng nhạt
    (248, 240, 255),  # Tím nhạt
]

# Màu chữ CAPTCHA (đậm, dễ đọc)
TEXT_COLORS = [
    (30, 58, 138),    # Xanh đậm (primary)
    (190, 24, 93),    # Hồng đậm
    (21, 128, 61),    # Xanh lá đậm
    (180, 83, 9),     # Cam đậm
    (88, 28, 135),    # Tím đậm
    (185, 28, 28),    # Đỏ đậm
]

# ============================================================
# LƯU TRỮ CAPTCHA TẠM THỜI (In-Memory Store)
# ============================================================
# Sử dụng dictionary để lưu CAPTCHA theo captcha_id
# Trong production nên dùng Redis hoặc database
captcha_store = {}


def _cleanup_expired():
    """
    Dọn dẹp các CAPTCHA đã hết hạn khỏi bộ nhớ.
    Được gọi mỗi khi tạo CAPTCHA mới để tránh memory leak.
    """
    current_time = time.time()
    expired_keys = [
        key for key, value in captcha_store.items()
        if current_time - value['created_at'] > CAPTCHA_EXPIRE_TIME
    ]
    for key in expired_keys:
        del captcha_store[key]


def generate_captcha_text():
    """
    Tạo chuỗi ký tự ngẫu nhiên cho CAPTCHA.
    
    GIẢI THÍCH:
    - random.choices() chọn ngẫu nhiên CAPTCHA_LENGTH ký tự từ CAPTCHA_CHARS
    - Ký tự dễ nhầm (0, O, 1, l, I) đã được loại bỏ khỏi bộ ký tự
    
    Returns:
        str: Chuỗi CAPTCHA, ví dụ "A3X7K"
    """
    return ''.join(random.choices(CAPTCHA_CHARS, k=CAPTCHA_LENGTH))


def generate_captcha_image(text):
    """
    Tạo hình ảnh CAPTCHA từ chuỗi ký tự.
    
    GIẢI THÍCH CHI TIẾT TỪNG BƯỚC:
    
    Bước 1: Tạo canvas (khung vẽ) với màu nền ngẫu nhiên
    Bước 2: Vẽ các đường kẻ nhiễu (noise lines) - khiến bot khó đọc
    Bước 3: Vẽ các chấm nhiễu (noise dots) - thêm nhiễu nền
    Bước 4: Vẽ từng ký tự với:
        - Vị trí hơi lệch ngẫu nhiên (offset)
        - Góc xoay ngẫu nhiên (rotation)  
        - Màu sắc ngẫu nhiên
        - Kích thước hơi khác nhau
    Bước 5: Áp dụng bộ lọc làm mờ nhẹ (blur) - tăng độ khó cho OCR
    Bước 6: Chuyển ảnh thành base64 để gửi qua API
    
    Args:
        text (str): Chuỗi CAPTCHA cần vẽ
        
    Returns:
        str: Ảnh CAPTCHA dạng base64 data URI
    """
    
    # ====== BƯỚC 1: Tạo canvas ======
    # Chọn màu nền ngẫu nhiên từ danh sách
    bg_color = random.choice(BG_COLORS)
    # Image.new('RGB', (width, height), color) tạo ảnh mới
    image = Image.new('RGB', (CAPTCHA_WIDTH, CAPTCHA_HEIGHT), bg_color)
    # ImageDraw.Draw() tạo đối tượng vẽ trên ảnh
    draw = ImageDraw.Draw(image)
    
    # ====== BƯỚC 2: Vẽ đường kẻ nhiễu (Noise Lines) ======
    # Mục đích: Các đường kẻ ngẫu nhiên chồng lên chữ khiến bot OCR
    # khó phân tách được từng ký tự
    for _ in range(random.randint(4, 7)):
        # Tọa độ bắt đầu và kết thúc ngẫu nhiên
        x1 = random.randint(0, CAPTCHA_WIDTH)
        y1 = random.randint(0, CAPTCHA_HEIGHT)
        x2 = random.randint(0, CAPTCHA_WIDTH)
        y2 = random.randint(0, CAPTCHA_HEIGHT)
        # Màu đường kẻ ngẫu nhiên (nhạt hơn chữ)
        line_color = (
            random.randint(100, 200),
            random.randint(100, 200),
            random.randint(100, 200)
        )
        # Độ dày đường kẻ ngẫu nhiên 1-3 pixel
        draw.line([(x1, y1), (x2, y2)], fill=line_color, width=random.randint(1, 3))
    
    # ====== BƯỚC 3: Vẽ chấm nhiễu (Noise Dots) ======
    # Mục đích: Các chấm nhỏ ngẫu nhiên làm "bẩn" nền ảnh,
    # khiến thuật toán phát hiện cạnh (edge detection) của bot bị nhiễu
    for _ in range(random.randint(100, 200)):
        x = random.randint(0, CAPTCHA_WIDTH - 1)
        y = random.randint(0, CAPTCHA_HEIGHT - 1)
        dot_color = (
            random.randint(100, 220),
            random.randint(100, 220),
            random.randint(100, 220)
        )
        # Vẽ chấm nhỏ (hình tròn bán kính 1-2 pixel)
        draw.ellipse([x, y, x + random.randint(1, 3), y + random.randint(1, 3)], fill=dot_color)
    
    # ====== BƯỚC 4: Vẽ từng ký tự ======
    # Chiều rộng cho mỗi ký tự (chia đều canvas)
    char_width = CAPTCHA_WIDTH // (CAPTCHA_LENGTH + 1)
    
    for i, char in enumerate(text):
        # --- Chọn font ---
        # Sử dụng font mặc định của Pillow với kích thước ngẫu nhiên
        try:
            font_size = random.randint(32, 42)
            font = ImageFont.truetype("arial.ttf", font_size)
        except (IOError, OSError):
            # Nếu không tìm thấy arial, dùng font mặc định
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
                                          random.randint(32, 42))
            except (IOError, OSError):
                font = ImageFont.load_default()
        
        # --- Chọn màu chữ ngẫu nhiên ---
        text_color = random.choice(TEXT_COLORS)
        
        # --- Tính vị trí ký tự ---
        # x: Cách đều nhau + offset ngẫu nhiên (-5 đến +5 pixel)
        x = char_width * (i + 0.5) + random.randint(-5, 5)
        # y: Giữa chiều cao + offset ngẫu nhiên (-8 đến +8 pixel)
        y = CAPTCHA_HEIGHT // 2 + random.randint(-8, 8)
        
        # --- Tạo ảnh tạm cho 1 ký tự (để xoay) ---
        # Tạo ảnh trong suốt 50x50 pixel
        char_image = Image.new('RGBA', (50, 50), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_image)
        
        # Vẽ ký tự vào giữa ảnh tạm
        # Sử dụng textbbox để tính kích thước chữ chính xác
        bbox = char_draw.textbbox((0, 0), char, font=font)
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]
        char_draw.text(
            ((50 - char_w) // 2, (50 - char_h) // 2),
            char,
            fill=text_color,
            font=font
        )
        
        # --- Xoay ký tự ngẫu nhiên ---
        # Góc xoay từ -25 đến +25 độ
        # expand=True: mở rộng ảnh để không bị cắt khi xoay
        angle = random.randint(-25, 25)
        char_image = char_image.rotate(angle, expand=True, resample=Image.BICUBIC)
        
        # --- Dán ký tự đã xoay lên canvas chính ---
        # Tính lại vị trí sau khi xoay (vì kích thước ảnh thay đổi)
        paste_x = int(x - char_image.width // 2)
        paste_y = int(y - char_image.height // 2)
        # paste() với mask để giữ nền trong suốt
        image.paste(char_image, (paste_x, paste_y), char_image)
    
    # ====== BƯỚC 5: Thêm đường cong nhiễu phía trước chữ ======
    # Vẽ thêm đường cong sin/cos để tăng độ khó
    for _ in range(random.randint(1, 3)):
        x_start = random.randint(0, 20)
        y_start = random.randint(10, CAPTCHA_HEIGHT - 10)
        curve_color = (
            random.randint(80, 180),
            random.randint(80, 180),
            random.randint(80, 180)
        )
        # Vẽ đường cong bằng cách nối nhiều đoạn thẳng ngắn
        points = []
        amplitude = random.randint(5, 15)  # Biên độ dao động
        frequency = random.uniform(0.02, 0.06)  # Tần số dao động
        for x in range(x_start, CAPTCHA_WIDTH, 3):
            y = y_start + int(amplitude * math.sin(frequency * x))
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=curve_color, width=random.randint(1, 2))
    
    # ====== BƯỚC 6: Áp dụng bộ lọc làm mờ nhẹ ======
    # GaussianBlur làm mờ nhẹ toàn bộ ảnh
    # Mục đích: Loại bỏ các cạnh sắc nét mà bot OCR thường dùng để nhận dạng
    # radius=0.8: mờ rất nhẹ, người vẫn đọc được nhưng bot khó hơn
    image = image.filter(ImageFilter.GaussianBlur(radius=0.8))
    
    # ====== BƯỚC 7: Chuyển ảnh thành base64 ======
    # Lưu ảnh vào buffer (bộ đệm trong RAM)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    buffer.seek(0)
    
    # Mã hóa base64 để nhúng trực tiếp vào HTML <img src="data:...">
    img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    return f"data:image/png;base64,{img_base64}"


def create_captcha():
    """
    Tạo CAPTCHA mới hoàn chỉnh (text + image) và lưu vào store.
    
    GIẢI THÍCH FLOW:
    1. Dọn dẹp CAPTCHA cũ đã hết hạn
    2. Tạo chuỗi ngẫu nhiên (vd: "A3X7K")  
    3. Tạo hình ảnh từ chuỗi đó
    4. Tạo captcha_id duy nhất (UUID-like)
    5. Lưu {captcha_id: text} vào store phía server
    6. Trả về captcha_id + image cho client
    
    Returns:
        dict: {
            'captcha_id': str,    # ID để xác thực sau này
            'captcha_image': str  # Ảnh base64 để hiển thị
        }
    """
    # Dọn dẹp CAPTCHA hết hạn
    _cleanup_expired()
    
    # Tạo mã CAPTCHA
    text = generate_captcha_text()
    
    # Tạo hình ảnh
    image_data = generate_captcha_image(text)
    
    # Tạo ID duy nhất cho CAPTCHA này
    captcha_id = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    
    # Lưu vào store (CHỈ LƯU PHÍA SERVER - client không biết mã)
    captcha_store[captcha_id] = {
        'text': text,                # Mã CAPTCHA thật
        'created_at': time.time(),   # Thời gian tạo
    }
    
    return {
        'captcha_id': captcha_id,
        'captcha_image': image_data
    }


def verify_captcha(captcha_id, user_input):
    """
    Xác thực mã CAPTCHA do người dùng nhập.
    
    GIẢI THÍCH FLOW:
    1. Kiểm tra captcha_id có tồn tại trong store không
    2. Kiểm tra CAPTCHA đã hết hạn chưa (> 5 phút)
    3. So sánh mã người dùng nhập với mã đã lưu (case-insensitive)
    4. XÓA CAPTCHA khỏi store sau khi xác thực (dùng 1 lần duy nhất)
    
    Args:
        captcha_id (str): ID của CAPTCHA (nhận từ client)
        user_input (str): Mã CAPTCHA người dùng nhập
        
    Returns:
        dict: {
            'valid': bool,      # True nếu đúng, False nếu sai
            'message': str      # Thông báo chi tiết
        }
    """
    # Kiểm tra input rỗng
    if not captcha_id or not user_input:
        return {
            'valid': False,
            'message': 'Vui lòng nhập mã CAPTCHA'
        }
    
    # Kiểm tra captcha_id có tồn tại không
    captcha_data = captcha_store.get(captcha_id)
    if not captcha_data:
        return {
            'valid': False,
            'message': 'CAPTCHA không hợp lệ hoặc đã hết hạn. Vui lòng tải lại.'
        }
    
    # Xóa CAPTCHA khỏi store (dùng 1 lần - one-time use)
    # Điều này ngăn chặn việc dùng lại cùng một CAPTCHA nhiều lần (replay attack)
    del captcha_store[captcha_id]
    
    # Kiểm tra hết hạn (5 phút)
    if time.time() - captcha_data['created_at'] > CAPTCHA_EXPIRE_TIME:
        return {
            'valid': False,
            'message': 'CAPTCHA đã hết hạn. Vui lòng tải lại.'
        }
    
    # So sánh mã (KHÔNG phân biệt hoa/thường)
    # .strip() loại bỏ khoảng trắng thừa
    # .upper() chuyển thành chữ in hoa để so sánh
    if user_input.strip().upper() == captcha_data['text'].upper():
        return {
            'valid': True,
            'message': 'CAPTCHA hợp lệ'
        }
    else:
        return {
            'valid': False,
            'message': 'Mã CAPTCHA không đúng. Vui lòng thử lại.'
        }
