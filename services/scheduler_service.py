import threading
import time
from datetime import datetime
from services.database_service import db_service
from services.rtsp_service import rtsp_service
from services.telegram_service import telegram_service


class SchedulerService:
    """Background scheduler that auto-starts attendance sessions based on schedules"""

    def __init__(self):
        self.thread = None
        self.running = False
        self.current_schedule_id = None  # ID of schedule currently running
        self._stop_timer = None  # Timer to auto-stop the session

    def start(self):
        """Start the scheduler background thread"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("[OK] Scheduler service started")

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self._stop_timer:
            self._stop_timer.cancel()
        if self.thread:
            self.thread.join(timeout=5)
        print("✓ Scheduler service stopped")

    def _run_loop(self):
        """Main scheduler loop - checks every 30 seconds"""
        while self.running:
            try:
                self._check_schedules()
            except Exception as e:
                print(f"Scheduler error: {e}")
            time.sleep(30)

    def _check_schedules(self):
        """Check if any schedule needs to be triggered"""
        # Don't start a new session if RTSP is already running (manual or scheduled)
        if rtsp_service.is_running:
            return

        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        today_str = now.strftime('%Y-%m-%d')

        schedules = db_service.get_all_active_schedules()

        for schedule in schedules:
            start_hour = schedule.get('start_hour', 0)
            start_minute = schedule.get('start_minute', 0)
            duration_minutes = schedule.get('duration_minutes', 15)
            selected_dates = schedule.get('selected_dates', [])
            completed_dates = schedule.get('completed_dates', [])

            # Check if today is a selected date and not yet completed
            if today_str not in selected_dates:
                continue
            if today_str in completed_dates:
                continue

            # Check if it's time to run (within a 2-minute window)
            if current_hour == start_hour and abs(current_minute - start_minute) <= 1:
                self._start_scheduled_session(schedule, duration_minutes)
                break  # Only run one schedule at a time

    def _start_scheduled_session(self, schedule, duration_minutes):
        """Start an RTSP session for a schedule"""
        schedule_id = schedule['id']
        class_name = schedule.get('class_name')
        attendance_type = schedule.get('attendance_type', 'in')
        rtsp_url = schedule.get('rtsp_url', '0')
        user_id = schedule.get('user_id')
        send_telegram = schedule.get('send_telegram', False)

        print(f"⏰ Scheduler: Starting attendance for class '{class_name}' "
              f"(type={attendance_type}, duration={duration_minutes}min)")

        # Store schedule info for use when stopping
        self._current_schedule_info = {
            'class_name': class_name,
            'attendance_type': attendance_type,
            'send_telegram': send_telegram
        }

        success = rtsp_service.start_stream(rtsp_url, class_name, user_id, attendance_type)

        if success:
            self.current_schedule_id = schedule_id
            # Set timer to auto-stop after duration
            self._stop_timer = threading.Timer(
                duration_minutes * 60,
                self._stop_scheduled_session,
                args=[schedule_id]
            )
            self._stop_timer.daemon = True
            self._stop_timer.start()
            print(f"⏰ Scheduler: Will auto-stop in {duration_minutes} minutes")

            # Send Telegram start notification if enabled
            if send_telegram and telegram_service.is_configured():
                telegram_service.send_message_async(
                    f"⏰ <b>ĐIỂM DANH TỰ ĐỘNG BẮT ĐẦU</b>\n\n"
                    f"🏫 <b>Lớp:</b> {class_name}\n"
                    f"🎯 <b>Loại:</b> {'VÀO' if attendance_type == 'in' else 'RA'}\n"
                    f"⏱ <b>Thời lượng:</b> {duration_minutes} phút\n\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 <i>Hệ thống điểm danh HAUI</i>"
                )
        else:
            print(f"⏰ Scheduler: Failed to start stream for schedule {schedule_id}")
            self._current_schedule_info = None

    def _stop_scheduled_session(self, schedule_id):
        """Stop the scheduled RTSP session and update the schedule"""
        try:
            schedule_info = getattr(self, '_current_schedule_info', None)
            send_telegram = schedule_info.get('send_telegram', False) if schedule_info else False

            # If telegram should be sent for this scheduled session, temporarily enable it
            original_send_on_stop = telegram_service.send_on_stop
            if send_telegram:
                telegram_service.set_send_on_stop(True)

            print(f"⏰ Scheduler: Auto-stopping session for schedule {schedule_id}")
            rtsp_service.stop_stream()
            db_service.update_schedule_after_run(schedule_id)

            # Restore original send_on_stop setting
            telegram_service.set_send_on_stop(original_send_on_stop)

            self.current_schedule_id = None
            self._current_schedule_info = None
            print(f"⏰ Scheduler: Session completed successfully")
        except Exception as e:
            print(f"⏰ Scheduler: Error stopping session: {e}")
            self.current_schedule_id = None
            self._current_schedule_info = None

    def get_status(self):
        """Get current scheduler status"""
        return {
            'running': self.running,
            'current_schedule_id': self.current_schedule_id,
            'is_session_active': rtsp_service.is_running and self.current_schedule_id is not None
        }


# Global scheduler instance
scheduler = SchedulerService()
