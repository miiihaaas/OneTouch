"""
Celery task-ovi za slanje email-ova.
"""
import smtplib
import socket
from onetouch import celery, mail, db, logger
from onetouch.models import TransactionRecord, Student, School, SMTPErrorLog
from flask_mail import Message
from flask import render_template
from sqlalchemy import update


class EmailTask(celery.Task):
    """
    Base class za email task-ove sa automatskim retry mehanizmom.
    """
    # Automatski retry za određene exception-e
    autoretry_for = (
        smtplib.SMTPServerDisconnected,
        smtplib.SMTPConnectError,
        ConnectionError,
        TimeoutError,
        socket.timeout,
    )

    # Retry konfiguracija
    retry_kwargs = {
        'max_retries': 5,  # Maksimalno 5 pokušaja
        'countdown': 60,   # Početni interval (60 sekundi)
    }

    # Exponential backoff
    retry_backoff = True  # 60s, 120s, 240s, 480s, 600s
    retry_backoff_max = 600  # Maksimalno 10 minuta između pokušaja
    retry_jitter = True  # Dodaj random jitter da spreči "thundering herd"


@celery.task(base=EmailTask, bind=True, name='onetouch.tasks.send_email')
def send_email_task(self, record_id, user_folder, file_name):
    """
    Asinhroni task za slanje email-a sa uplatnicom.

    Args:
        self: Task instanca (bind=True)
        record_id: ID TransactionRecord-a
        user_folder: Putanja do foldera sa PDF-om
        file_name: Ime PDF fajla (npr. 'uplatnica_123.pdf')

    Returns:
        Dict sa statusom slanja:
        - status: 'success', 'skipped', ili 'error'
        - record_id: ID record-a
        - email: Email adresa primaoca
        - attempt: Broj pokušaja

    Raises:
        Exception: Ako slanje ne uspe posle svih retry-a
    """
    try:
        logger.info(f'[Task {self.request.id}] Starting email task for record {record_id}')

        # 1. UČITAJ RECORD IZ BAZE
        record = TransactionRecord.query.get(record_id)
        if not record:
            logger.error(f'[Task {self.request.id}] Record {record_id} not found')
            return {
                'status': 'error',
                'record_id': record_id,
                'message': 'Record not found'
            }

        # 2. POSTAVI FLAG DA JE POSLATO
        # Omogućeno ponovno slanje - korisnik potvrđuje kroz modal
        record.debt_sent = True
        db.session.commit()

        # 4. UČITAJ POTREBNE PODATKE
        student = Student.query.get(record.student_id)
        school = School.query.first()

        if not student:
            logger.error(f'[Task {self.request.id}] Student not found for record {record_id}')
            return {'status': 'error', 'message': 'Student not found'}

        # 5. VALIDACIJA EMAIL ADRESE
        if not student.parent_email or not student.send_mail:
            logger.info(f'[Task {self.request.id}] Student {student.id} has no email or send_mail=False')
            return {
                'status': 'skipped',
                'record_id': record_id,
                'message': 'No email or sending disabled'
            }

        parent_email = student.parent_email
        logger.info(f'[Task {self.request.id}] Preparing email for {parent_email}')

        # 6. PRIPREMA EMAIL-A
        sender_email = 'noreply@uplatnice.online'

        # Pripremi uplatnica data za template
        debt = record.transaction_record_student_debt
        student_full_name = f"{student.student_name} {student.student_surname}"
        uplatnica_data = {
            'student_id': student.id,
            'uplatilac': student_full_name,
            'svrha_uplate': debt.purpose_of_payment if debt else '',
            'iznos': record.student_debt_total,
            'record_id': record.id,
            'slanje_mejla_roditelju': student.send_mail,
        }

        subject = f"{school.school_name} / Uplatnica: {student_full_name}"
        if debt:
            subject += f" - Svrha uplate: {debt.purpose_of_payment}"

        message = Message(subject, sender=sender_email)
        message.recipients = [parent_email]

        # 7. RENDERUJ HTML TEMPLATE
        try:
            message.html = render_template(
                'message_html_send_mail.html',
                school=school,
                uplatnica=uplatnica_data
            )
        except Exception as e:
            logger.error(f'[Task {self.request.id}] Template rendering failed: {str(e)}')
            raise

        # 8. PRILOŽI PDF
        try:
            import os
            full_path = os.path.join(user_folder, file_name)

            if not os.path.exists(full_path):
                logger.error(f'[Task {self.request.id}] PDF file not found: {full_path}')
                raise FileNotFoundError(f'PDF file not found: {full_path}')

            with open(full_path, 'rb') as f:
                pdf_content = f.read()
                message.attach(file_name, 'application/pdf', pdf_content)

            logger.info(f'[Task {self.request.id}] PDF attached: {file_name} ({len(pdf_content)} bytes)')
        except Exception as e:
            logger.error(f'[Task {self.request.id}] PDF attachment failed: {str(e)}')
            # Rollback debt_sent flag
            record.debt_sent = False
            db.session.commit()
            raise

        # 9. POŠALJI EMAIL
        try:
            mail.send(message)
            logger.info(f'[Task {self.request.id}] ✅ Email sent successfully to {parent_email}')

            return {
                'status': 'success',
                'record_id': record_id,
                'email': parent_email,
                'attempt': self.request.retries + 1
            }

        except smtplib.SMTPResponseException as e:
            error_code = e.smtp_code
            error_msg = e.smtp_error.decode('utf-8') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)

            logger.error(f'[Task {self.request.id}] ❌ SMTP error {error_code}: {error_msg}')

            # LOGIRAJ GREŠKU
            SMTPErrorLog.log_error(
                error_type=f'SMTP_{error_code}',
                recipient=parent_email,
                error_msg=error_msg,
                record_id=record_id,
                task_id=self.request.id,
                retry_count=self.request.retries
            )

            # Rollback debt_sent flag
            record.debt_sent = False
            db.session.commit()

            # Neki error kodovi ne treba retry-ovati
            if error_code == 550:  # Mailbox unavailable - loš email
                logger.error(f'[Task {self.request.id}] Invalid email address: {parent_email}')
                return {
                    'status': 'error',
                    'record_id': record_id,
                    'email': parent_email,
                    'message': f'Invalid email address (SMTP 550)'
                }

            # Za ostale greške - retry
            raise self.retry(exc=e)

        except Exception as e:
            logger.error(f'[Task {self.request.id}] ❌ Unexpected error: {type(e).__name__}: {str(e)}')

            # LOGIRAJ GREŠKU
            SMTPErrorLog.log_error(
                error_type=type(e).__name__,
                recipient=parent_email if 'parent_email' in locals() else 'unknown',
                error_msg=str(e),
                record_id=record_id,
                task_id=self.request.id,
                retry_count=self.request.retries
            )

            # Rollback debt_sent flag
            record.debt_sent = False
            db.session.commit()

            # Retry
            raise self.retry(exc=e)

    except Exception as e:
        # Ovo se izvršava ako svi retry-i ne uspeju
        logger.error(f'[Task {self.request.id}] ❌ Failed to send email for record {record_id} after {self.max_retries} attempts')
        logger.error(f'[Task {self.request.id}] Final error: {type(e).__name__}: {str(e)}')

        # LOGIRAJ FINALNU GREŠKU
        try:
            SMTPErrorLog.log_error(
                error_type=f'FINAL_{type(e).__name__}',
                recipient='unknown',
                error_msg=f'Failed after {self.max_retries} attempts: {str(e)}',
                record_id=record_id,
                task_id=self.request.id,
                retry_count=self.max_retries
            )
        except Exception as log_error:
            logger.error(f'[Task {self.request.id}] Failed to log error: {str(log_error)}')

        # TODO: Pošalji notifikaciju adminu
        # send_admin_notification(...)

        return {
            'status': 'error',
            'record_id': record_id,
            'message': f'Failed after {self.max_retries} attempts: {str(e)}'
        }


@celery.task(base=EmailTask, bind=True, name='onetouch.tasks.send_report_email')
def send_report_email_task(self, student_id, report_type, user_folder, file_name, start_date=None, end_date=None):
    """
    Asinhroni task za slanje izveštaja mejlom.

    Args:
        self: Task instanca
        student_id: ID učenika
        report_type: 'student_report' ili 'debt_report'
        user_folder: Putanja do foldera sa PDF-om
        file_name: Ime PDF fajla
        start_date: Početni datum (opciono)
        end_date: Krajnji datum (opciono)

    Returns:
        Dict sa statusom slanja
    """
    try:
        logger.info(f'[Task {self.request.id}] Starting report email task for student {student_id}')

        # 1. UČITAJ PODATKE
        student = Student.query.get(student_id)
        school = School.query.first()

        if not student:
            logger.error(f'[Task {self.request.id}] Student {student_id} not found')
            return {'status': 'error', 'message': 'Student not found'}

        # 2. VALIDACIJA EMAIL ADRESE
        if not student.parent_email:
            logger.info(f'[Task {self.request.id}] Student {student_id} has no email')
            return {'status': 'skipped', 'message': 'No email'}

        parent_email = student.parent_email
        student_name = f'{student.student_name} {student.student_surname}'

        # 3. PRIPREMA EMAIL-A
        if report_type == 'student_report':
            subject = f"{school.school_name} | Izveštaj za učenika: {student_name}"
            template_name = 'message_html_send_report.html'

            # Konvertuj stringove nazad u date objekte za template
            from datetime import datetime
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date and isinstance(start_date, str) else start_date
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date and isinstance(end_date, str) else end_date

            template_data = {
                'student': student,
                'school': school,
                'start_date': start_date_obj,
                'end_date': end_date_obj
            }
        elif report_type == 'debt_report':
            subject = f'{school.school_name} | Izveštaj o dugovanju za učenika {student_name}'
            template_name = 'message_html_debt_report.html'
            template_data = {
                'student': student,
                'school': school
            }
        else:
            raise ValueError(f'Unknown report type: {report_type}')

        message = Message(subject, sender=(school.school_name, 'noreply@uplatnice.online'))
        message.recipients = [parent_email]

        # 4. RENDERUJ HTML TEMPLATE
        try:
            message.html = render_template(template_name, **template_data)
        except Exception as e:
            logger.error(f'[Task {self.request.id}] Template rendering failed: {str(e)}')
            raise

        # 5. PRILOŽI PDF
        try:
            import os
            full_path = os.path.join(user_folder, file_name)

            if not os.path.exists(full_path):
                logger.error(f'[Task {self.request.id}] PDF file not found: {full_path}')
                raise FileNotFoundError(f'PDF file not found: {full_path}')

            with open(full_path, 'rb') as f:
                pdf_content = f.read()
                message.attach(file_name, 'application/pdf', pdf_content)

            logger.info(f'[Task {self.request.id}] PDF attached: {file_name} ({len(pdf_content)} bytes)')
        except Exception as e:
            logger.error(f'[Task {self.request.id}] PDF attachment failed: {str(e)}')
            raise

        # 6. POŠALJI EMAIL
        try:
            mail.send(message)
            logger.info(f'[Task {self.request.id}] ✅ Report email sent successfully to {parent_email}')

            return {
                'status': 'success',
                'student_id': student_id,
                'email': parent_email,
                'report_type': report_type,
                'attempt': self.request.retries + 1
            }

        except smtplib.SMTPResponseException as e:
            error_code = e.smtp_code
            error_msg = e.smtp_error.decode('utf-8') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
            logger.error(f'[Task {self.request.id}] ❌ SMTP error {error_code}: {error_msg}')

            # Logiraj grešku
            SMTPErrorLog.log_error(
                error_type=f'SMTP_{error_code}',
                recipient=parent_email,
                error_msg=error_msg,
                task_id=self.request.id,
                retry_count=self.request.retries
            )

            # Retry za određene greške
            if error_code != 550:
                raise self.retry(exc=e)

            return {'status': 'error', 'message': f'SMTP {error_code}'}

        except Exception as e:
            logger.error(f'[Task {self.request.id}] ❌ Unexpected error: {type(e).__name__}: {str(e)}')
            raise self.retry(exc=e)

    except Exception as e:
        logger.error(f'[Task {self.request.id}] ❌ Failed to send report email after {self.max_retries} attempts')
        return {
            'status': 'error',
            'student_id': student_id,
            'message': f'Failed after {self.max_retries} attempts: {str(e)}'
        }
