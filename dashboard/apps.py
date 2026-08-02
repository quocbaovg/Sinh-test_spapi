import os
import sys

from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dashboard"

    def ready(self):
        is_runserver = any(arg == "runserver" or arg.endswith("runserver") for arg in sys.argv)
        # runserver: chỉ start ở process con (RUN_MAIN)
        # lệnh khác / production: start luôn
        if is_runserver and os.environ.get("RUN_MAIN") != "true":
            return
        from .pool import start_workers

        start_workers()
