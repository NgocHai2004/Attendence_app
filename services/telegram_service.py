import os
import requests
import threading
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


class TelegramService:
    """Service for sending Telegram bot notifications"""

    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.bot_token and self.chat_id)
        # Per-session flag: user can toggle sending telegram per attendance session
        self.send_on_stop = False
        if self.enabled:
            print("✓ Telegram bot configured")
        else:
            print("⚠ Telegram bot not configured (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")

    def configure(self, bot_token, chat_id):
        """Update Telegram bot configuration at runtime"""
        self.bot_token = bot_token.strip() if bot_token else ''
        self.chat_id = chat_id.strip() if chat_id else ''
        self.enabled = bool(self.bot_token and self.chat_id)
        return self.enabled

    def is_configured(self):
        """Check if Telegram bot is properly configured"""
        return self.enabled

    def get_config(self):
        """Get current Telegram configuration"""
        masked_token = ''
        if self.bot_token:
            masked_token = self.bot_token[:8] + '...' + self.bot_token[-4:] if len(self.bot_token) > 12 else '***'
        return {
            'configured': self.enabled,
            'bot_token': self.bot_token,
            'bot_token_masked': masked_token,
            'chat_id': self.chat_id,
            'send_on_stop': self.send_on_stop
        }

    def set_send_on_stop(self, value):
        """Set whether to send notification when attendance session stops"""
        self.send_on_stop = bool(value)

    def send_message(self, text, parse_mode='HTML'):
        """Send a text message via Telegram bot"""
        if not self.enabled:
            print("⚠ Telegram not configured, skipping message")
            return False

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            result = response.json()

            if result.get('ok'):
                print("✓ Telegram message sent successfully")
                return True
            else:
                print(f"✗ Telegram API error: {result.get('description', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"✗ Telegram send error: {e}")
            return False

    def send_message_async(self, text, parse_mode='HTML'):
        """Send a message asynchronously (non-blocking)"""
        thread = threading.Thread(target=self.send_message, args=(text, parse_mode), daemon=True)
        thread.start()

    def send_attendance_summary(self, class_name, attendance_type, present, absent, total,
                                 start_time=None, end_time=None, present_faces=None, is_scheduled=False):
        """Send a formatted attendance summary notification"""
        if not self.enabled:
            return False

        mode_text = "VÀO" if attendance_type == 'in' else "RA"
        source_text = "📅 Lịch tự động" if is_scheduled else "👤 Thủ công"

        now = datetime.now()
        time_str = now.strftime('%d/%m/%Y %H:%M:%S')

        start_str = ''
        end_str = ''
        if start_time:
            if isinstance(start_time, datetime):
                start_str = start_time.strftime('%H:%M:%S')
            else:
                start_str = str(start_time)
        if end_time:
            if isinstance(end_time, datetime):
                end_str = end_time.strftime('%H:%M:%S')
            else:
                end_str = str(end_time)

        # Build the message
        message = f"""📋 <b>KẾT QUẢ ĐIỂM DANH</b>

🏫 <b>Lớp:</b> {class_name}
🎯 <b>Loại:</b> {mode_text}
📌 <b>Nguồn:</b> {source_text}
🕐 <b>Thời gian:</b> {time_str}"""

        if start_str or end_str:
            message += f"\n⏱ <b>Phiên:</b> {start_str} → {end_str}"

        message += f"""

📊 <b>THỐNG KÊ:</b>
✅ Có mặt: <b>{present}/{total}</b>
❌ Vắng mặt: <b>{absent}/{total}</b>"""

        # Add attendance rate
        if total > 0:
            rate = round((present / total) * 100, 1)
            if rate >= 80:
                rate_emoji = "🟢"
            elif rate >= 50:
                rate_emoji = "🟡"
            else:
                rate_emoji = "🔴"
            message += f"\n{rate_emoji} Tỷ lệ: <b>{rate}%</b>"

        # Add present student list (if available and not too many)
        if present_faces and len(present_faces) > 0:
            message += "\n\n👥 <b>DANH SÁCH CÓ MẶT:</b>"
            for i, face in enumerate(present_faces[:30], 1):  # Limit to 30 to avoid message too long
                name = face.get('name', 'N/A')
                msv = face.get('msv', '')
                msv_text = f" ({msv})" if msv else ""
                message += f"\n  {i}. {name}{msv_text}"
            if len(present_faces) > 30:
                message += f"\n  ... và {len(present_faces) - 30} sinh viên khác"

        message += "\n\n━━━━━━━━━━━━━━━━━━"
        message += "\n🤖 <i>Hệ thống điểm danh HAUI</i>"

        return self.send_message(message)

    def send_attendance_summary_async(self, class_name, attendance_type, present, absent, total,
                                       start_time=None, end_time=None, present_faces=None, is_scheduled=False):
        """Send attendance summary asynchronously"""
        thread = threading.Thread(
            target=self.send_attendance_summary,
            args=(class_name, attendance_type, present, absent, total),
            kwargs={
                'start_time': start_time,
                'end_time': end_time,
                'present_faces': present_faces,
                'is_scheduled': is_scheduled
            },
            daemon=True
        )
        thread.start()

    def test_connection(self):
        """Test the Telegram bot connection by sending a test message"""
        if not self.enabled:
            return {'success': False, 'message': 'Telegram chưa được cấu hình'}

        test_msg = """🔔 <b>TEST KẾT NỐI TELEGRAM</b>

✅ Kết nối thành công!
🤖 Bot đã sẵn sàng gửi thông báo điểm danh.

━━━━━━━━━━━━━━━━━━
🤖 <i>Hệ thống điểm danh HAUI</i>"""

        success = self.send_message(test_msg)
        if success:
            return {'success': True, 'message': 'Gửi tin nhắn test thành công!'}
        else:
            return {'success': False, 'message': 'Gửi tin nhắn thất bại. Kiểm tra lại Token và Chat ID.'}


# Global telegram service instance
telegram_service = TelegramService()
