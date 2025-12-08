"""
Celery tasks za OneTouch aplikaciju.
"""
from onetouch.tasks.email_tasks import send_email_task

__all__ = ['send_email_task']
