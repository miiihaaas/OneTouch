"""
Celery task-ovi za healthcheck SMTP servera.
"""
from onetouch import celery, mail, logger
from onetouch.models import School
from onetouch.tasks.database import create_task_session, get_all_school_databases
from datetime import datetime
import smtplib


@celery.task(name='onetouch.tasks.smtp_healthcheck')
def smtp_healthcheck():
    """
    Proverava zdravlje SMTP servera.
    Izvršava se periodično (npr. svakih 5 minuta).

    Returns:
        dict: Status healthcheck-a
    """
    try:
        logger.info('[SMTP Healthcheck] Starting...')

        # Testiraj konekciju - ako se konekcija uspostavi, server je zdrav
        with mail.connect() as conn:
            # Flask-Mail automatski testira konekciju kada se konektuje
            # Ako smo došli ovde, konekcija je uspešna
            logger.info('[SMTP Healthcheck] ✅ SMTP server is healthy')
            return {
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'message': 'SMTP server connection successful'
            }

    except smtplib.SMTPServerDisconnected as e:
        logger.error('[SMTP Healthcheck] ❌ Server disconnected')
        # TODO: Pošalji alert adminu
        return {
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': 'Server disconnected',
            'details': str(e)
        }
    except smtplib.SMTPException as e:
        logger.error(f'[SMTP Healthcheck] ❌ SMTP error: {str(e)}')
        return {
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': 'SMTP error',
            'details': str(e)
        }
    except Exception as e:
        logger.error(f'[SMTP Healthcheck] ❌ Healthcheck failed: {str(e)}')
        # TODO: Pošalji alert adminu
        return {
            'status': 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'error': type(e).__name__,
            'details': str(e)
        }


@celery.task(name='onetouch.tasks.retry_failed_emails')
def retry_failed_emails():
    """
    Pronalazi sve neuspele mejlove (debt_sent=False + ima error log)
    i pokušava da ih ponovo pošalje.

    Izvršava se periodično (npr. svakih 6 sati).

    MULTI-TENANT: Iterira kroz sve škole i retry-uje njihove failed emails.
    """
    from onetouch.models import TransactionRecord, SMTPErrorLog
    from onetouch.tasks.email_tasks import send_email_task
    from sqlalchemy import and_
    from datetime import timedelta
    import os
    from onetouch.transactions.functions import project_folder

    try:
        logger.info('[Retry Failed Emails] Starting...')

        # Dobij sve school database URI-jeve
        all_school_uris = get_all_school_databases()

        total_retry_count = 0

        # Iteriraj kroz sve škole
        for database_uri in all_school_uris:
            try:
                # Kreiraj sesiju za ovu školu
                session = create_task_session(database_uri)

                try:
                    # Pronađi sve record-e koji nisu poslati ali imaju error log
                    # i greška je starija od 1 sat
                    one_hour_ago = datetime.utcnow() - timedelta(hours=1)

                    # Dobijamo distinct record IDs iz error log-a
                    failed_record_ids = (session.query(SMTPErrorLog.record_id)
                                         .filter(
                                             and_(
                                                 SMTPErrorLog.resolved == False,
                                                 SMTPErrorLog.timestamp <= one_hour_ago,
                                                 SMTPErrorLog.error_type != 'SMTP_550',  # Ne retry-uj loše email adrese
                                                 SMTPErrorLog.record_id.isnot(None)
                                             )
                                         )
                                         .distinct()
                                         .limit(50)  # Max 50 odjednom po školi
                                         .all())

                    # Uzmi record-e koji nisu poslati
                    failed_records = []
                    for (record_id,) in failed_record_ids:
                        record = session.query(TransactionRecord).get(record_id)
                        if record and record.debt_sent == False:
                            failed_records.append(record)

                    retry_count = 0
                    for record in failed_records:
                        # Proveri da li ima studenta
                        if not record.transaction_record_student:
                            continue

                        # Queue-uj ponovo sa database_uri
                        # Pretpostavljamo da je user_id = 1 (admin) ako nema drugačijih informacija
                        user_folder = os.path.join(project_folder, 'static', 'payment_slips', f'user_1')
                        file_name = f'uplatnica_{record.id}.pdf'

                        # Proveri da li PDF postoji
                        full_path = os.path.join(user_folder, file_name)
                        if not os.path.exists(full_path):
                            logger.warning(f'[Retry Failed Emails] PDF not found for record {record.id}: {full_path}')
                            continue

                        # VAŽNO: Prosleđujemo database_uri da task zna na koju bazu da se konektuje
                        send_email_task.delay(record.id, user_folder, file_name, database_uri)
                        retry_count += 1

                    total_retry_count += retry_count
                    logger.info(f'[Retry Failed Emails] Re-queued {retry_count} emails for school: {database_uri.split("/")[-1]}')

                finally:
                    # Zatvori sesiju za ovu školu
                    session.close()

            except Exception as school_error:
                logger.error(f'[Retry Failed Emails] Error processing school {database_uri}: {str(school_error)}')
                continue  # Nastavi sa sledećom školom

        logger.info(f'[Retry Failed Emails] Total re-queued {total_retry_count} emails across all schools')
        return {
            'status': 'success',
            'retry_count': total_retry_count,
            'timestamp': datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f'[Retry Failed Emails] Error: {str(e)}')
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }
