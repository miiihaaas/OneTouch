"""
Celery task-ovi za kompletnu generaciju uplatnica.
Sve operacije (QR + PDF + Email) se izvršavaju asinhrono.
"""
import os
import logging
import smtplib
from onetouch import celery, mail, db, logger
from onetouch.models import TransactionRecord, Student, School, SMTPErrorLog
from onetouch.tasks.database import create_task_session
from flask_mail import Message
from flask import render_template
from sqlalchemy import update


class PaymentTask(celery.Task):
    """Base class za payment task-ove sa retry mehanizmom."""
    autoretry_for = (
        ConnectionError,
        TimeoutError,
        smtplib.SMTPServerDisconnected,
        smtplib.SMTPConnectError,
    )
    retry_kwargs = {
        'max_retries': 3,
        'countdown': 30,
    }
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True


@celery.task(base=PaymentTask, bind=True, name='onetouch.tasks.generate_and_send_payment')
def generate_and_send_payment_task(self, record_id, purpose_of_payment, school_info, user_folder, database_uri):
    """
    Kompletna async generacija uplatnice i slanje mejla.

    Izvršava sledeće korake u pozadini:
    1. Generiše QR kod (HTTP zahtev na NBS server) - 1-2s
    2. Generiše PDF - 0.5s
    3. Šalje mejl - 1-2s

    Args:
        self: Task instanca
        record_id: ID TransactionRecord-a
        purpose_of_payment: Svrha uplate
        school_info: Informacije o školi
        user_folder: Putanja do foldera za PDF
        database_uri: URI za konekciju na bazu podatke škole (SQLALCHEMY_DATABASE_URI)

    Returns:
        Dict sa statusom
    """
    # Kreiraj sesiju za ovaj task
    session = create_task_session(database_uri)

    try:
        logger.info(f'[Payment Task {self.request.id}] Starting for record {record_id}')

        # 1. UČITAJ PODATKE
        record = session.query(TransactionRecord).get(record_id)
        if not record:
            logger.error(f'[Payment Task {self.request.id}] Record {record_id} not found')
            return {'status': 'error', 'message': 'Record not found'}

        student = record.transaction_record_student
        school = session.query(School).first()

        # DEBUG: Provera koji podaci se koriste
        logger.info(f'[Payment Task {self.request.id}] DEBUG database_uri: {database_uri}')
        logger.info(f'[Payment Task {self.request.id}] DEBUG school from session: {school.school_name if school else "None"}')
        logger.info(f'[Payment Task {self.request.id}] DEBUG school_info param: {school_info}')

        # 2. VALIDACIJA
        if not student.parent_email or not student.send_mail:
            logger.info(f'[Payment Task {self.request.id}] Student {student.id} has no email or send_mail=False')
            return {'status': 'skipped', 'message': 'No email or sending disabled'}

        # 3. PROVERI DA LI JE VEĆ POSLATO (pre atomic update-a)
        if record.debt_sent is True:
            logger.info(f'[Payment Task {self.request.id}] Record {record_id} already sent, skipping')
            return {'status': 'skipped', 'record_id': record_id, 'message': 'Already sent'}

        # 4. ATOMIČKI POSTAVI FLAG (RACE CONDITION ZAŠTITA)
        result = session.execute(
            update(TransactionRecord)
            .where(TransactionRecord.id == record_id)
            .where(TransactionRecord.debt_sent.isnot(True))
            .values(debt_sent=True)
        )
        session.commit()

        if result.rowcount == 0:
            logger.info(f'[Payment Task {self.request.id}] Record {record_id} already processed by another task')
            return {'status': 'skipped', 'record_id': record_id, 'message': 'Already sent by another task'}

        # 5. GENERIŠI QR KOD
        from onetouch.transactions.functions import (
            prepare_payment_data, prepare_qr_data, generate_qr_code, project_folder
        )

        try:
            payment_data = prepare_payment_data(record, purpose_of_payment, school_info, school)
            logger.info(f'[Payment Task {self.request.id}] DEBUG primalac after prepare: {payment_data["primalac"]}')
            qr_data = prepare_qr_data(payment_data, payment_data['primalac'])

            # Generiši QR kod (HTTP zahtev - potencijalno sporo!)
            qr_code_filename = generate_qr_code(
                qr_data,
                payment_data['student_id'],
                project_folder,
                student.id
            )

            if not qr_code_filename:
                logger.error(f'[Payment Task {self.request.id}] QR code generation failed')
                raise Exception('QR code generation failed')

            logger.info(f'[Payment Task {self.request.id}] QR code generated: {qr_code_filename}')

        except Exception as e:
            logger.error(f'[Payment Task {self.request.id}] QR generation error: {str(e)}')
            # Rollback debt_sent flag
            record.debt_sent = False
            session.commit()
            raise

        # 6. GENERIŠI PDF
        from onetouch.transactions.functions import (
            setup_pdf_page, add_payment_slip_content, PDF, add_fonts, cleanup_qr_codes
        )

        try:
            pdf = PDF()
            add_fonts(pdf)
            y, y_qr = setup_pdf_page(pdf, 1)

            # Kreiraj dummy user objekat sa samo ID-em za kompatibilnost
            class DummyUser:
                def __init__(self, user_id):
                    self.id = user_id

            dummy_user = DummyUser(student.id)
            add_payment_slip_content(pdf, payment_data, y, y_qr, project_folder, dummy_user)

            file_name = f'uplatnica_{record.id}.pdf'
            pdf_path = os.path.join(user_folder, file_name)

            # Ensure user folder exists
            os.makedirs(user_folder, exist_ok=True)
            pdf.output(pdf_path)

            logger.info(f'[Payment Task {self.request.id}] PDF generated: {pdf_path}')

            # Cleanup QR codes
            cleanup_qr_codes(project_folder, student.id)

        except Exception as e:
            logger.error(f'[Payment Task {self.request.id}] PDF generation error: {str(e)}')
            # Rollback debt_sent flag
            record.debt_sent = False
            session.commit()
            # Cleanup QR codes on error
            try:
                cleanup_qr_codes(project_folder, student.id)
            except:
                pass
            raise

        # 7. POŠALJI EMAIL
        parent_email = student.parent_email
        subject = f"{school.school_name} / Uplatnica: {student.student_name} {student.student_surname}"
        if record.transaction_record_student_debt:
            subject += f" - Svrha uplate: {record.transaction_record_student_debt.purpose_of_payment}"

        message = Message(subject, sender='noreply@uplatnice.online')
        message.recipients = [parent_email]

        # Renderuj template
        uplatnica_data = {
            'student_id': student.id,
            'uplatilac': f"{student.student_name} {student.student_surname}",
            'svrha_uplate': record.transaction_record_student_debt.purpose_of_payment if record.transaction_record_student_debt else '',
            'iznos': record.student_debt_total,
            'record_id': record.id,
            'slanje_mejla_roditelju': student.send_mail,
        }

        try:
            message.html = render_template(
                'message_html_send_mail.html',
                school=school,
                uplatnica=uplatnica_data
            )
        except Exception as e:
            logger.error(f'[Payment Task {self.request.id}] Template rendering failed: {str(e)}')
            # Rollback debt_sent flag
            record.debt_sent = False
            session.commit()
            raise

        # Priloži PDF
        try:
            with open(pdf_path, 'rb') as f:
                pdf_content = f.read()
                message.attach(file_name, 'application/pdf', pdf_content)

            logger.info(f'[Payment Task {self.request.id}] PDF attached ({len(pdf_content)} bytes)')
        except Exception as e:
            logger.error(f'[Payment Task {self.request.id}] PDF attachment failed: {str(e)}')
            # Rollback debt_sent flag
            record.debt_sent = False
            session.commit()
            raise

        # Pošalji
        try:
            mail.send(message)
            logger.info(f'[Payment Task {self.request.id}] ✅ Complete! Email sent to {parent_email}')

            return {
                'status': 'success',
                'record_id': record_id,
                'email': parent_email,
                'attempt': self.request.retries + 1
            }

        except smtplib.SMTPResponseException as e:
            # SMTP error handling
            error_code = e.smtp_code
            error_msg = e.smtp_error.decode('utf-8') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
            logger.error(f'[Payment Task {self.request.id}] ❌ SMTP error {error_code}: {error_msg}')

            # Logiraj grešku
            SMTPErrorLog.log_error(
                error_type=f'SMTP_{error_code}',
                recipient=parent_email,
                error_msg=error_msg,
                record_id=record_id,
                task_id=self.request.id,
                retry_count=self.request.retries,
                session=session
            )

            # Rollback debt_sent flag
            record.debt_sent = False
            session.commit()

            # Retry za određene greške
            if error_code != 550:
                raise self.retry(exc=e)

            return {'status': 'error', 'message': f'SMTP {error_code}'}

        except Exception as e:
            logger.error(f'[Payment Task {self.request.id}] ❌ Email sending error: {type(e).__name__}: {str(e)}')

            # Rollback debt_sent flag
            record.debt_sent = False
            session.commit()

            # Retry
            raise self.retry(exc=e)

    except Exception as e:
        logger.error(f'[Payment Task {self.request.id}] ❌ Failed after {self.max_retries} attempts')
        logger.error(f'[Payment Task {self.request.id}] Final error: {type(e).__name__}: {str(e)}')

        # LOGIRAJ FINALNU GREŠKU
        try:
            SMTPErrorLog.log_error(
                error_type=f'FINAL_{type(e).__name__}',
                recipient='unknown',
                error_msg=f'Failed after {self.max_retries} attempts: {str(e)}',
                record_id=record_id,
                task_id=self.request.id,
                retry_count=self.max_retries,
                session=session
            )
        except Exception as log_error:
            logger.error(f'[Payment Task {self.request.id}] Failed to log error: {str(log_error)}')

        return {
            'status': 'error',
            'record_id': record_id,
            'message': f'Failed after {self.max_retries} attempts: {str(e)}'
        }
    finally:
        # Zatvori sesiju
        session.close()
