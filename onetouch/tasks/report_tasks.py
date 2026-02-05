"""
Celery task-ovi za generisanje PDF izveštaja.
Sve operacije (QR + PDF generacija) se izvršavaju asinhrono.
"""
import os
import logging
from onetouch import celery, db, logger
from onetouch.models import Student, School
from onetouch.tasks.database import create_task_session


class ReportTask(celery.Task):
    """Base class za report task-ove sa retry mehanizmom."""
    autoretry_for = (
        ConnectionError,
        TimeoutError,
    )
    retry_kwargs = {
        'max_retries': 3,
        'countdown': 30,
    }
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True


@celery.task(base=ReportTask, bind=True, name='onetouch.tasks.generate_pdf_reports')
def generate_pdf_reports_task(self, student_id, min_debt_amount, selected_services, user_folder, database_uri):
    """
    Kompletna async generacija PDF izveštaja za učenika.

    Izvršava sledeće korake u pozadini:
    1. Generiše listu dugovanja (PDF)
    2. Generiše QR kodove za sve usluge (HTTP zahtevi - ASYNC!)
    3. Generiše uplatnice (PDF)

    Args:
        self: Task instanca
        student_id: ID učenika
        min_debt_amount: Minimalni iznos duga za filtriranje
        selected_services: Lista ID-jeva selektovanih usluga
        user_folder: Putanja do foldera za PDF-ove
        database_uri: URI za konekciju na bazu podatke škole (SQLALCHEMY_DATABASE_URI)

    Returns:
        Dict sa putanjama do generisanih PDF-ova
    """
    # Kreiraj sesiju za ovaj task
    session = create_task_session(database_uri)

    try:
        logger.info(f'[Report Task {self.request.id}] Starting for student {student_id}')

        # 1. UČITAJ PODATKE
        from onetouch.overviews.functions import get_filtered_transactions_data

        services_with_positive_saldo, selected_service_names, student = get_filtered_transactions_data(
            student_id, selected_services, min_debt_amount, session=session
        )

        if not student:
            logger.error(f'[Report Task {self.request.id}] Student {student_id} not found')
            return {'status': 'error', 'message': 'Student not found'}

        if not services_with_positive_saldo:
            logger.info(f'[Report Task {self.request.id}] Student {student_id} has no debts')
            return {'status': 'error', 'message': 'No debts found'}

        school = session.query(School).first()

        # Ensure user folder exists
        os.makedirs(user_folder, exist_ok=True)

        # Generiši PDF-ove koristeći zajedničku funkciju
        from onetouch.overviews.functions import generate_debt_report_pdfs

        result = generate_debt_report_pdfs(
            services_with_positive_saldo, selected_service_names,
            student, school, user_folder, student_id, min_debt_amount
        )

        if result.get('status') != 'success':
            return result

        result['attempt'] = self.request.retries + 1
        logger.info(f'[Report Task {self.request.id}] ✅ Complete! Generated {result.get("payment_slips_count", 0)} payment slips')

        return result

    except Exception as e:
        logger.error(f'[Report Task {self.request.id}] ❌ Failed after {self.max_retries} attempts')
        logger.error(f'[Report Task {self.request.id}] Final error: {type(e).__name__}: {str(e)}')

        return {
            'status': 'error',
            'student_id': student_id,
            'message': f'Failed after {self.max_retries} attempts: {str(e)}'
        }
    finally:
        # Zatvori sesiju
        session.close()
