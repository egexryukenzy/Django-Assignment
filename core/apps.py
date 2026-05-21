import logging
import os
from django.apps import AppConfig

logger = logging.getLogger(__name__)

class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        import sys
        running_server = any(
            cmd in sys.argv
            for cmd in ("runserver", "gunicorn", "uvicorn", "daphne", "granian")
        )
        is_test = "test" in sys.argv
        if not running_server or is_test:
            return
        if os.environ.get("RUN_MAIN") != "true" and "runserver" in sys.argv:
            return
        self._start_scheduler()

    def _start_scheduler(self):
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
            from django.core.management import call_command

            scheduler = BackgroundScheduler(timezone="Asia/Phnom_Penh")
            scheduler.add_job(
                func=lambda: call_command("send_deadline_reminders"),
                trigger=IntervalTrigger(hours=1),
                id="deadline_reminders",
                name="Deadline Reminder Notifications",
                replace_existing=True,
                max_instances=1,
            )
            scheduler.start()
            logger.info("[APScheduler] Deadline reminder job started — runs every hour.")
        except ImportError:
            logger.warning("[APScheduler] 'apscheduler' not installed.")
        except Exception as exc:
            logger.error(f"[APScheduler] Failed to start scheduler: {exc}")
