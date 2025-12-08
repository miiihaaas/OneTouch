"""
Celery konfiguracija za OneTouch aplikaciju.
"""
from celery import Celery
import os


def make_celery(app):
    """
    Kreira Celery instancu i integriše sa Flask aplikacijom.

    Args:
        app: Flask aplikacija

    Returns:
        Celery instanca
    """
    celery = Celery(
        app.import_name,
        broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    )

    # Celery konfiguracija
    celery.conf.update(
        # Serialization
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',

        # Timezone
        timezone='Europe/Belgrade',
        enable_utc=True,

        # Worker konfiguracija
        broker_connection_retry_on_startup=True,
        task_acks_late=True,  # Task se acknowledge-uje tek POSLE izvršenja
        task_reject_on_worker_lost=True,  # Re-queue task ako worker padne
        worker_prefetch_multiplier=1,  # Uzmi samo 1 task odjednom

        # Task routing (za buduće proširenje)
        task_routes={
            'onetouch.tasks.email_tasks.*': {'queue': 'emails'},
            'onetouch.tasks.qr_tasks.*': {'queue': 'qr_codes'},
        },

        # Result backend settings
        result_expires=3600,  # Rezultati se čuvaju 1 sat
        result_persistent=True,
    )

    # Flask app context za task-ove
    class ContextTask(celery.Task):
        """Omogućava pristup Flask app context-u unutar Celery task-ova."""
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = ContextTask
    return celery
