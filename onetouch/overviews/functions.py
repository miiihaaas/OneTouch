import os
import logging
from onetouch.models import Student, ServiceItem, TransactionRecord
from datetime import datetime


def get_filtered_transactions_data(student_id, selected_services=None, min_debt_amount=0, session=None):
    """
    Dobavlja i filtrira podatke o transakcijama za učenika.
    
    Args:
        student_id (int): ID učenika
        selected_services (list): Lista ID-eva usluga za filtriranje
        min_debt_amount (float): Minimalni iznos dugovanja
        
    Returns:
        tuple: (services_with_positive_saldo, selected_service_names, student)
            - services_with_positive_saldo: Lista usluga sa pozitivnim saldom
            - selected_service_names: Lista naziva selektovanih usluga
            - student: Objekat učenika
    """
    # Dobavljanje podataka o učeniku
    if session is not None:
        student = session.query(Student).get(student_id)
        if not student:
            return [], [], None
    else:
        student = Student.query.get_or_404(student_id)
    
    # Filter za transakcije - osnovna pretraga po učeniku
    if session is not None:
        query = session.query(TransactionRecord).filter_by(student_id=student_id)
    else:
        query = TransactionRecord.query.filter_by(student_id=student_id)
    
    # Dodatni filter po izabranim uslugama
    selected_service_names = []
    if selected_services and selected_services[0]:  # Provera da nije prazan string u prvom elementu
        service_ids = [int(s) for s in selected_services if s.strip()]
        if service_ids:  # Ako postoje validni ID-evi
            query = query.filter(TransactionRecord.service_item_id.in_(service_ids))
            
            # Prikupljanje naziva izabranih usluga za prikaz
            if session is not None:
                service_items = session.query(ServiceItem).filter(ServiceItem.id.in_(service_ids)).all()
            else:
                service_items = ServiceItem.query.filter(ServiceItem.id.in_(service_ids)).all()
            selected_service_names = [f"{item.service_item_service.service_name} - {item.service_item_name}" for item in service_items]
    
    # Izvršavanje upita
    transaction_records = query.all()
    
    # Grupisanje transakcija po uslugama
    services_data = {}
    for record in transaction_records:
        service_id = record.service_item_id
        if service_id not in services_data:
            services_data[service_id] = {
                'service_item': record.transaction_record_service_item,
                'debt_amount': 0,
                'payment_amount': 0,
                'saldo': 0
            }
        
        if record.student_debt_id:
            services_data[service_id]['debt_amount'] += record.student_debt_total
        elif record.student_payment_id:
            services_data[service_id]['payment_amount'] += abs(record.student_debt_total)
        elif record.fund_transfer_id:
            # Preknjižavanje - tretirati kao uplatu
            services_data[service_id]['payment_amount'] += record.student_debt_total
        elif record.debt_writeoff_id:
            # Rasknjižavanje dugovanja - smanjuje dug
            services_data[service_id]['payment_amount'] += abs(record.student_debt_total)
    
    # Računanje salda za svaku uslugu
    services_with_positive_saldo = []
    for service_id, data in services_data.items():
        data['saldo'] = data['debt_amount'] - data['payment_amount']
        if data['saldo'] > 0:
            services_with_positive_saldo.append({
                'service_id': service_id,
                'service_item': data['service_item'],
                'debt_amount': data['debt_amount'],
                'payment_amount': data['payment_amount'],
                'saldo': data['saldo']
            })
    
    return services_with_positive_saldo, selected_service_names, student


def add_filter_info_to_pdf(pdf, student, min_debt_amount, selected_service_names):
    """
    Dodaje informacije o filtriranju i osnovne podatke o učeniku na PDF.
    
    Args:
        pdf: FPDF objekat
        student: Objekat učenika
        min_debt_amount (float): Minimalni iznos dugovanja
        selected_service_names (list): Lista naziva selektovanih usluga
    """
    # Naslov
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(0, 10, f"Lista dugovanja - {student.student_name} {student.student_surname}", new_x="LMARGIN", new_y="NEXT")
    
    # Informacije o učeniku i kriterijumima
    pdf.set_font('DejaVuSansCondensed', '', 12)
    pdf.cell(0, 10, f"Razred/odeljenje: {student.student_class}/{student.student_section}", new_x="LMARGIN", new_y="NEXT")
    
    # Datum generisanja
    current_date = datetime.now().strftime('%d.%m.%Y.')
    pdf.cell(0, 10, f"Datum generisanja: {current_date}", new_x="LMARGIN", new_y="NEXT")
    
    # Kriterijumi filtriranja
    # pdf.cell(0, 10, f"Minimalni iznos dugovanja: {min_debt_amount:.2f}", new_x="LMARGIN", new_y="NEXT")
    
    # Informacija o filtriranim uslugama
    # if selected_service_names:
    #     pdf.cell(0, 10, "Filtrirano po sledećim uslugama:", new_x="LMARGIN", new_y="NEXT")
    #     for i, service_name in enumerate(selected_service_names):
    #         pdf.cell(0, 8, f"  {i+1}. {service_name}", new_x="LMARGIN", new_y="NEXT")
    # else:
    #     pdf.cell(0, 10, "Prikazane sve usluge sa dugovanjima.", new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(5)


def generate_debt_report_pdfs(services_with_positive_saldo, selected_service_names,
                               student, school, user_folder, student_id, min_debt_amount):
    """
    Generiše PDF izveštaje o dugovanjima za učenika.

    Generiše dva PDF fajla:
    1. Lista dugovanja po uslugama
    2. Uplatnice sa QR kodovima

    Args:
        services_with_positive_saldo: Lista usluga sa pozitivnim saldom
        selected_service_names: Lista naziva selektovanih usluga
        student: Student objekat
        school: School objekat
        user_folder: Putanja do foldera za čuvanje PDF-ova
        student_id: ID učenika
        min_debt_amount: Minimalni iznos dugovanja

    Returns:
        Dict sa statusom i putanjama do generisanih PDF-ova
    """
    from fpdf import FPDF
    from onetouch.transactions.functions import (
        add_fonts, project_folder, prepare_qr_data, generate_qr_code,
        add_payment_slip_content, PDF, cleanup_qr_codes, setup_pdf_page
    )

    logger = logging.getLogger('onetouch')

    try:
        # 1. PRVI PDF - LISTA DUGOVANJA
        pdf = FPDF()
        add_fonts(pdf)
        pdf.add_page()

        add_filter_info_to_pdf(pdf, student, min_debt_amount, selected_service_names)

        pdf.set_fill_color(200, 220, 255)
        pdf.set_font('DejaVuSansCondensed', 'B', 11)
        pdf.cell(80, 10, "Usluga", 1, new_x="RIGHT", new_y="LAST", align="C", fill=True)
        pdf.cell(30, 10, "Zaduženje", 1, new_x="RIGHT", new_y="LAST", align="C", fill=True)
        pdf.cell(30, 10, "Uplate", 1, new_x="RIGHT", new_y="LAST", align="C", fill=True)
        pdf.cell(30, 10, "Saldo", 1, new_x="LMARGIN", new_y="NEXT", align="C", fill=True)

        pdf.set_font('DejaVuSansCondensed', '', 10)

        total_debt = 0
        total_payment = 0
        total_saldo = 0

        for service_data in services_with_positive_saldo:
            service_item = service_data['service_item']
            service_name = f"{service_item.service_item_service.service_name} - {service_item.service_item_name}"
            debt = service_data['debt_amount']
            payment = service_data['payment_amount']
            saldo = service_data['saldo']

            total_debt += debt
            total_payment += payment
            total_saldo += saldo

            pdf.cell(80, 8, service_name, 1, new_x="RIGHT", new_y="LAST")
            pdf.cell(30, 8, f"{debt:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
            pdf.cell(30, 8, f"{payment:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
            pdf.cell(30, 8, f"{saldo:.2f}", 1, new_x="LMARGIN", new_y="NEXT", align="R")

        pdf.set_font('DejaVuSansCondensed', 'B', 10)
        pdf.cell(80, 10, "UKUPNO:", 1, new_x="RIGHT", new_y="LAST", align="R")
        pdf.cell(30, 10, f"{total_debt:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
        pdf.cell(30, 10, f"{total_payment:.2f}", 1, new_x="RIGHT", new_y="LAST", align="R")
        pdf.cell(30, 10, f"{total_saldo:.2f}", 1, new_x="LMARGIN", new_y="NEXT", align="R")

        services_list_path = os.path.join(user_folder, f'services_list_{student_id}.pdf')
        pdf.output(services_list_path)
        logger.info(f'Services list PDF generated: {services_list_path}')

        # 2. DRUGI PDF - UPLATNICE SA QR KODOVIMA
        payment_slips_pdf = PDF()
        add_fonts(payment_slips_pdf)

        payment_slips_count = 0
        for service_data in services_with_positive_saldo:
            service_item = service_data['service_item']
            saldo = service_data['saldo']

            if saldo <= 0:
                continue

            counter = payment_slips_count + 1
            y, y_qr = setup_pdf_page(payment_slips_pdf, counter)
            payment_slips_count += 1

            purpose_of_payment = f"{service_item.service_item_service.service_name} - {service_item.service_item_name}"

            bank_account_number = service_item.bank_account
            recipient_name = ""
            recipient_address = ""

            for account in school.school_bank_accounts.get('bank_accounts', []):
                if account.get('bank_account_number') == bank_account_number:
                    recipient_name = account.get('recipient_name', "")
                    recipient_address = account.get('recipient_address', "")
                    break

            if not recipient_name and not recipient_address:
                primalac = f"{school.school_name}\r\n{school.school_address}, {school.school_zip_code} {school.school_city}"
            elif recipient_name and not recipient_address:
                primalac = recipient_name
            elif not recipient_name and recipient_address:
                primalac = f"{school.school_name}\r\n{school.school_address}, {school.school_zip_code} {school.school_city}"
            else:
                primalac = f"{recipient_name}\r\n{recipient_address}"

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

            try:
                qr_data = prepare_qr_data(payment_data, payment_data['primalac'])
                qr_code_filename = generate_qr_code(
                    qr_data,
                    payment_data['student_id'],
                    project_folder,
                    student_id
                )

                if not qr_code_filename:
                    logger.error(f'QR code generation failed for service {service_item.id}')
                    continue

            except Exception as e:
                logger.error(f'QR generation error for service {service_item.id}: {str(e)}')
                continue

            class DummyUser:
                def __init__(self, user_id):
                    self.id = user_id

            dummy_user = DummyUser(student_id)
            add_payment_slip_content(payment_slips_pdf, payment_data, y, y_qr, project_folder, dummy_user)

        cleanup_qr_codes(project_folder, student_id)

        payment_slips_path = os.path.join(user_folder, f'payment_slips_{student_id}.pdf')
        payment_slips_pdf.output(payment_slips_path)
        logger.info(f'Payment slips PDF generated: {payment_slips_path}')

        return {
            'status': 'success',
            'student_id': student_id,
            'services_list_path': f'reports/user_{student_id}/services_list_{student_id}.pdf',
            'payment_slips_path': f'reports/user_{student_id}/payment_slips_{student_id}.pdf',
            'payment_slips_count': payment_slips_count,
        }

    except Exception as e:
        logger.error(f'Greška pri generisanju PDF izveštaja: {str(e)}')
        return {
            'status': 'error',
            'student_id': student_id,
            'message': str(e)
        }