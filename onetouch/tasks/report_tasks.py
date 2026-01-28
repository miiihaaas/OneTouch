"""
Celery task-ovi za generisanje PDF izveštaja.
Sve operacije (QR + PDF generacija) se izvršavaju asinhrono.
"""
import os
import logging
from onetouch import celery, db, logger
from onetouch.models import Student, School
from onetouch.tasks.database import create_task_session
from fpdf import FPDF


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
        from onetouch.overviews.routes import get_filtered_transactions_data

        services_with_positive_saldo, selected_service_names, student = get_filtered_transactions_data(
            student_id, selected_services, min_debt_amount
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

        # 2. GENERIŠI PRVI PDF - LISTA DUGOVANJA
        from onetouch.transactions.functions import add_fonts, project_folder
        from onetouch.overviews.routes import add_filter_info_to_pdf

        pdf = FPDF()
        add_fonts(pdf)
        pdf.add_page()

        # Dodavanje informacija o filtriranju
        add_filter_info_to_pdf(pdf, student, min_debt_amount, selected_service_names)

        # Tabela usluga
        pdf.set_fill_color(200, 220, 255)
        pdf.set_font('DejaVuSansCondensed', 'B', 11)
        pdf.cell(80, 10, "Usluga", 1, new_x="RIGHT", new_y="LAST", align="C", fill=True)
        pdf.cell(30, 10, "Zaduženje", 1, new_x="RIGHT", new_y="LAST", align="C", fill=True)
        pdf.cell(30, 10, "Uplate", 1, new_x="RIGHT", new_y="LAST", align="C", fill=True)
        pdf.cell(30, 10, "Saldo", 1, new_x="LMARGIN", new_y="NEXT", align="C", fill=True)

        # Podaci u tabeli
        pdf.set_font('DejaVuSansCondensed', '', 10)

        # Ukupni iznosi
        total_debt = 0
        total_payment = 0
        total_saldo = 0

        for service_data in services_with_positive_saldo:
            service_item = service_data['service_item']
            service_name = f"{service_item.service_item_service.service_name} - {service_item.service_item_name}"
            debt = service_data['debt_amount']
            payment = service_data['payment_amount']
            saldo = service_data['saldo']

            # Dodavanje u ukupni iznos
            total_debt += debt
            total_payment += payment
            total_saldo += saldo

            # Prikaz u tabeli
            pdf.cell(80, 8, service_name, 1, new_x="RIGHT", new_y="LAST")
            pdf.cell(30, 8, f"{debt:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
            pdf.cell(30, 8, f"{payment:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
            pdf.cell(30, 8, f"{saldo:.2f}", 1, new_x="LMARGIN", new_y="NEXT", align="R")

        # Ukupno
        pdf.set_font('DejaVuSansCondensed', 'B', 10)
        pdf.cell(80, 10, "UKUPNO:", 1, new_x="RIGHT", new_y="LAST", align="R")
        pdf.cell(30, 10, f"{total_debt:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
        pdf.cell(30, 10, f"{total_payment:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
        pdf.cell(30, 10, f"{total_saldo:.2f}", 1, new_x="LMARGIN", new_y="NEXT", align="R")

        # Čuvanje prvog PDF-a (lista usluga)
        services_list_path = os.path.join(user_folder, f'services_list_{student_id}.pdf')
        pdf.output(services_list_path)

        logger.info(f'[Report Task {self.request.id}] Services list PDF generated: {services_list_path}')

        # 3. GENERIŠI DRUGI PDF - UPLATNICE (SA ASYNC QR KODOVIMA!)
        from onetouch.transactions.functions import (
            prepare_qr_data, generate_qr_code, add_payment_slip_content,
            PDF, cleanup_qr_codes, setup_pdf_page
        )

        # Kreiranje PDF-a za uplatnice
        payment_slips_pdf = PDF()
        add_fonts(payment_slips_pdf)

        # Generisanje uplatnica za svaku uslugu sa pozitivnim saldom - po 3 na stranici
        payment_slips_count = 0
        for service_data in services_with_positive_saldo:
            service_item = service_data['service_item']
            saldo = service_data['saldo']

            if saldo <= 0:
                continue  # Preskačemo usluge bez dugovanja

            # Koristimo postojeću funkciju za pozicioniranje uplatnica (3 po stranici)
            counter = payment_slips_count + 1  # Brojanje od 1
            y, y_qr = setup_pdf_page(payment_slips_pdf, counter)

            payment_slips_count += 1

            # Priprema svrhe plaćanja
            purpose_of_payment = f"{service_item.service_item_service.service_name} - {service_item.service_item_name}"

            # Određivanje primaoca
            bank_account_number = service_item.bank_account
            recipient_name = ""
            recipient_address = ""

            for account in school.school_bank_accounts.get('bank_accounts', []):
                if account.get('bank_account_number') == bank_account_number:
                    recipient_name = account.get('recipient_name', "")
                    recipient_address = account.get('recipient_address', "")
                    break

            # Određivanje primaoca
            if not recipient_name and not recipient_address:
                primalac = f"{school.school_name}\r\n{school.school_address}, {school.school_zip_code} {school.school_city}"
            elif recipient_name and not recipient_address:
                primalac = recipient_name
            elif not recipient_name and recipient_address:
                primalac = f"{school.school_name}\r\n{school.school_address}, {school.school_zip_code} {school.school_city}"
            else:
                primalac = f"{recipient_name}\r\n{recipient_address}"

            # Podaci za uplatnicu
            payment_data = {
                'student_id': student_id,
                'uplatilac': student.student_name + ' ' + student.student_surname,
                'svrha_uplate': f"{student_id:04d}-{service_data['service_id']:03d} {purpose_of_payment}",
                'primalac': primalac,
                'sifra_placanja': 253 if service_item.reference_number_spiri else 221,
                'valuta': 'RSD',
                'iznos': f'{saldo:.2f}',
                'racun_primaoca': bank_account_number,
                'model': '97' if service_item.reference_number_spiri else '',
                'poziv_na_broj': service_item.reference_number_spiri if service_item.reference_number_spiri else '',
            }

            # Generisanje QR koda (ASYNC - može trajati 1-2s ali ne blokira request!)
            try:
                qr_data = prepare_qr_data(payment_data, payment_data['primalac'])
                qr_code_filename = generate_qr_code(
                    qr_data,
                    payment_data['student_id'],
                    project_folder,
                    student_id  # user_id
                )

                if not qr_code_filename:
                    logger.error(f'[Report Task {self.request.id}] QR code generation failed for service {service_item.id}')
                    # Nastavi sa sledećom uslugom
                    continue

                logger.info(f'[Report Task {self.request.id}] QR code generated for service {service_item.id}')

            except Exception as e:
                logger.error(f'[Report Task {self.request.id}] QR generation error for service {service_item.id}: {str(e)}')
                # Nastavi sa sledećom uslugom
                continue

            # Dodavanje sadržaja uplatnice
            # Kreiraj dummy user objekat sa samo ID-em za kompatibilnost
            class DummyUser:
                def __init__(self, user_id):
                    self.id = user_id

            dummy_user = DummyUser(student_id)
            add_payment_slip_content(payment_slips_pdf, payment_data, y, y_qr, project_folder, dummy_user)

        # Čišćenje privremenih QR kodova
        cleanup_qr_codes(project_folder, student_id)

        # Čuvanje drugog PDF-a (uplatnice)
        payment_slips_path = os.path.join(user_folder, f'payment_slips_{student_id}.pdf')
        payment_slips_pdf.output(payment_slips_path)

        logger.info(f'[Report Task {self.request.id}] Payment slips PDF generated: {payment_slips_path}')
        logger.info(f'[Report Task {self.request.id}] ✅ Complete! Generated {payment_slips_count} payment slips')

        return {
            'status': 'success',
            'student_id': student_id,
            'services_list_path': f'reports/user_{student_id}/services_list_{student_id}.pdf',
            'payment_slips_path': f'reports/user_{student_id}/payment_slips_{student_id}.pdf',
            'payment_slips_count': payment_slips_count,
            'attempt': self.request.retries + 1
        }

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
