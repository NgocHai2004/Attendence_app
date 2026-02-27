import threading
import time
from datetime import datetime
from services.database_service import db_service
from services.rtsp_service import rtsp_service


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
        print("✓ Scheduler service started")

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
        today = now.date()

        schedules = db_service.get_all_active_schedules()

        for schedule in schedules:
            start_hour = schedule.get('start_hour', 0)
            start_minute = schedule.get('start_minute', 0)
            duration_minutes = schedule.get('duration_minutes', 15)
            last_run_date = schedule.get('last_run_date')

            # Check if already ran today
            if last_run_date:
                if hasattr(last_run_date, 'date'):
                    last_date = last_run_date.date()
                else:
                    last_date = last_run_date
                if last_date == today:
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

        print(f"⏰ Scheduler: Starting attendance for class '{class_name}' "
              f"(type={attendance_type}, duration={duration_minutes}min)")

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
        else:
            print(f"⏰ Scheduler: Failed to start stream for schedule {schedule_id}")

    def _stop_scheduled_session(self, schedule_id):
        """Stop the scheduled RTSP session and update the schedule"""
        try:
            print(f"⏰ Scheduler: Auto-stopping session for schedule {schedule_id}")
            rtsp_service.stop_stream()
            db_service.update_schedule_after_run(schedule_id)
            self.current_schedule_id = None
            print(f"⏰ Scheduler: Session completed successfully")
        except Exception as e:
            print(f"⏰ Scheduler: Error stopping session: {e}")
            self.current_schedule_id = None

    def get_status(self):
        """Get current scheduler status"""
        return {
            'running': self.running,
            'current_schedule_id': self.current_schedule_id,
            'is_session_active': rtsp_service.is_running and self.current_schedule_id is not None
        }


# Global scheduler instance
scheduler = SchedulerService()
