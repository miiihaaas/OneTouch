"""
Celery tasks za OneTouch aplikaciju.
"""
from onetouch.tasks.email_tasks import send_email_task, send_report_email_task
from onetouch.tasks.payment_tasks import generate_and_send_payment_task
from onetouch.tasks.report_tasks import generate_pdf_reports_task
from onetouch.tasks.qr_tasks import generate_qr_code_async
from onetouch.tasks.healthcheck_tasks import smtp_healthcheck, retry_failed_emails

__all__ = [
    'send_email_task',
    'send_report_email_task',
    'generate_and_send_payment_task',
    'generate_pdf_reports_task',
    'generate_qr_code_async',
    'smtp_healthcheck',
    'retry_failed_emails'
]
