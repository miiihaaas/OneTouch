# import dns.resolver
# import smtplib
import re
import requests, os, io, time, logging
from datetime import datetime
from email.utils import parseaddr
from flask_login import current_user
from PIL import Image
from fpdf import FPDF
from flask import render_template
from flask_mail import Message
from onetouch.models import School, Student, StudentPayment, TransactionRecord, db
from onetouch import mail, app

logger = logging.getLogger('onetouch')

#! koristi se u posting_payment ruti
def provera_validnosti_poziva_na_broj(podaci, all_reference_numbers):
    """
    Provera da li poziv na broj koji se nalazi u podacima
    pripada nekom od brojeva u all_reference_numbers

    Args:
        podaci (dict): Dicionar koji sadrži informacije o korisniku
        all_reference_numbers (list): Lista svih brojeva koji se mogu
            pojaviti u aplikaciji

    Returns:
        dict: Izmenjeni dicionar sa dodatim ključem 'Validnost' koji
            označava da li je poziv na broj validan ili ne
    """
    if len(podaci['PozivNaBrojApp']) == 7:
        # proverava da li je forma '0001001' i dodaje crtu tako da bude 0001-001
        formated_poziv_odobrenja = f"{podaci['PozivNaBrojApp'][:4]}-{podaci['PozivNaBrojApp'][4:]}"
        if formated_poziv_odobrenja in all_reference_numbers:
            podaci['Validnost'] = True
        else:
            podaci['Validnost'] = False
    elif len(podaci['PozivNaBrojApp']) == 8:
        # proverava da li je forma '0001-001'
        if podaci['PozivNaBrojApp'] in all_reference_numbers:
            podaci['Validnost'] = True
        else:
            podaci['Validnost'] = False
    else:
        # nije dobar poziv na broj
        podaci['Validnost'] = False
    return podaci


def izvuci_poziv_na_broj_iz_svrhe_uplate(input_string): #! funkcija koja iz svrhe uplate prepoznaje poziv na broj
    # Definiše regex pattern koji odgovara generalizovanom formatu
    pattern = r'(?<!\d)(\d{4}[ -]?\d{3})(?!\d)'
    
    # Traži pattern u celom input stringu
    match = re.search(pattern, input_string)
    
    if match:
        poziv_na_broj = match.group(1)
        # Ako je pronađen format sa razmakom, zameni ga sa crticom
        if ' ' in poziv_na_broj:
            poziv_na_broj = poziv_na_broj.replace(' ', '-')
        return poziv_na_broj
    else:
        return '-'  #! namerno umesto None


#! koristi se za generisanje i slanje pdf uplatnica
current_file_path = os.path.abspath(__file__)
# logger.debug(f'{current_file_path=}')
project_folder = os.path.dirname(os.path.dirname((current_file_path)))
# logger.debug(f'{project_folder=}')

font_path = os.path.join(project_folder, 'static', 'fonts', 'DejaVuSansCondensed.ttf')
font_path_B = os.path.join(project_folder, 'static', 'fonts', 'DejaVuSansCondensed-Bold.ttf')


def add_fonts(pdf):
    pdf.add_font('DejaVuSansCondensed', '', font_path, uni=True)
    pdf.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)


# def verify_email(email):
#     """Verify if email address is valid and reachable."""
#     try:
#         # Check email format
#         _, domain = parseaddr(email)[1].split('@')
        
#         # Get MX records
#         mx_records = dns.resolver.resolve(domain, 'MX')
#         if not mx_records:
#             return False, "No MX records found for domain"
        
#         # Try connecting to mail server
#         mx_record = str(mx_records[0].exchange)
#         with smtplib.SMTP(timeout=10) as server:
#             server.connect(mx_record)
#             server.helo()
#             return True, None
            
#     except Exception as e:
#         return False, str(e)

import re
from onetouch import logger


def verify_email(email):
    """
    Verify if email address is valid (FORMAT ONLY, no DNS/SMTP checks).
    
    Ova funkcija proverava samo format email adrese bez DNS ili SMTP provera,
    što omogućava da radi sa domenima koji imaju privatne ili nedostupne MX zapise.
    
    Args:
        email: Email adresa za validaciju
    
    Returns:
        tuple: (is_valid: bool, error_message: str|None)
    """
    if not email or not isinstance(email, str):
        return False, "Email adresa je prazna"
    
    email = email.strip().lower()
    
    # Osnovna provera dužine
    if len(email) > 320:  # RFC 5321
        return False, "Email adresa je predugačka"
    
    # Provera da li ima @ znak
    if email.count('@') != 1:
        return False, "Email adresa mora imati tačno jedan @ znak"
    
    try:
        local, domain = email.split('@')
    except ValueError:
        return False, "Nevažeći format email adrese"
    
    # Validacija local dela (pre @)
    if not local or len(local) > 64:
        return False, "Nevažeći deo pre @ znaka"
    
    local_pattern = r'^[a-zA-Z0-9._%+-]+$'
    if not re.match(local_pattern, local):
        return False, "Nevažeći karakteri pre @ znaka"
    
    # Validacija domena (posle @)
    if not domain or len(domain) > 255:
        return False, "Nevažeći domen"
    
    # Fleksibilna validacija domena - podržava više subdomena
    # Prihvata: ni.os.jt.rs, school.edu.rs, example.com, itd.
    domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
    if not re.match(domain_pattern, domain):
        return False, f"Nevažeći format domena: {domain}"
    
    # Specijalna provera za .rs domene - uvek su validni bez obzira na broj subdomena
    if domain.endswith('.rs'):
        logger.debug(f"Email {email} prihvaćen kao .rs domen")
        return True, None
    
    # Za ostale domene, proveri broj subdomena (opciono)
    if domain.count('.') > 4:  # Limit na 4 tačke
        return False, f"Previše subdomena u domenu: {domain}"
    
    logger.debug(f"Email {email} je validan")
    return True, None

def send_error_notification(school, student, parent_email, error_message):
    """Send notification about email delivery failure."""
    try:
        sender_email = 'noreply@uplatnice.online'
        admin_email = current_user.user_mail
        student_name = f'{student.student_name} {student.student_surname}'
        subject = f"Neuspešno slanje uplatnice - {student_name}"
        
        message = Message(subject, 
                            sender=sender_email,
                            recipients=[admin_email])
        
        message.html = render_template(
            'message_html_admin_email_notification.html',
            student_name=student_name,
            parent_email=parent_email,
            error_message=error_message
        )
        
        mail.send(message)
        logger.info(f'Sent error notification for student {student.student_name}')
        
    except Exception as e:
        logger.error(f'Failed to send error notification: {str(e)}')

def send_mail(uplatnica, user_folder, file_name):
    """Send email with payment slip and verify delivery."""
    school = School.query.first()
    student = Student.query.get_or_404(uplatnica['student_id'])
    
    # Early return if email sending is disabled or no email
    if student.parent_email is None or student.send_mail is False:
        return
    
    parent_email = student.parent_email
    logger.debug(f'Attempting to send email to: {parent_email}')
    
    # Verify email before sending
    is_valid, error = verify_email(parent_email)
    if not is_valid:
        logger.error(f'Invalid email address for student {student.student_name}: {error}')
        send_error_notification(school, student, parent_email, error)
        return
    
    # Prepare email
    sender_email = 'noreply@uplatnice.online'
    subject = f"{school.school_name} / Uplatnica: {uplatnica['uplatilac']} - Svrha uplate: {uplatnica['svrha_uplate']}"
    
    message = Message(subject, 
                        sender=sender_email)
    message.recipients = [parent_email]
    
    message.html = render_template('message_html_send_mail.html',
                                    school=school,
                                    uplatnica=uplatnica)
    
    # Attach PDF
    try:
        full_path = f'{user_folder}/{file_name}'
        with app.open_resource(full_path) as attachment:
            message.attach(file_name, 'application/pdf', attachment.read())
    except Exception as e:
        error_msg = f'Error attaching PDF: {str(e)}'
        logger.error(error_msg)
        send_error_notification(school, student, parent_email, error_msg)
        return
    
    # Send email
    try:
        mail.send(message)
        logger.info(f'Successfully sent email to {parent_email}')
        
        # Ažuriraj debt_sent status na True za ovu transakciju
        # Pronađi odgovarajući TransactionRecord po student_id i ažuriraj status
        if 'record_id' in uplatnica:
            record = TransactionRecord.query.get(uplatnica['record_id'])
            if record:
                record.debt_sent = True
                db.session.commit()
                logger.info(f'Ažuriran debt_sent status za transakciju ID: {uplatnica["record_id"]}')
            else:
                logger.warning(f'Nije pronađen TransactionRecord sa ID: {uplatnica["record_id"]}')
    except Exception as e:
        error_msg = f'Error sending email: {str(e)}'
        logger.error(error_msg)
        send_error_notification(school, student, parent_email, error_msg)


def export_payment_stats(data):
    logger.debug(f'{data=}')
    student_payment = StudentPayment.query.get_or_404(data[0]['payment_id'])
    school = School.query.first()
    
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
        
        def header(self) -> None:
            # Zaglavlje sa informacijama o školi
            self.set_font('DejaVuSansCondensed', 'B', 10)
            self.set_text_color(80, 80, 80)
            self.cell(0, 5, f'{school.school_name}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_address}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_zip_code} {school.school_city}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.set_text_color(0, 0, 0)
            self.ln(3)
            
            
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    
    # Glavni naslov
    pdf.ln(5)
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(0, 8, f'Izvod podataka uplatnice: {student_payment.statment_nubmer}', new_x='LMARGIN', new_y='NEXT', align='C')
    
    # Datum
    pdf.set_font('DejaVuSansCondensed', '', 11)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 6, f'Datum: {student_payment.payment_date.strftime("%d.%m.%Y.")}', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)
    
    # Zaglavlje tabele
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font('DejaVuSansCondensed', 'B', 10)
    pdf.cell(30, 7, 'ID usluge', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(120, 7, 'Detalji usluge', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(40, 7, 'Ukupan iznos', border=1, new_x='LMARGIN', new_y='NEXT', align='C', fill=True)
    
    # Redovi tabele
    pdf.set_font('DejaVuSansCondensed', '', 10)
    total = 0
    for record in data:
        if record['service_item_id'] != 0:
            pdf.cell(30, 7, f'{record["service_item_id"]:03d}', border=1, new_x='RIGHT', new_y='TOP', align='C')
            pdf.cell(120, 7, f'{record["name"]}', border=1, new_x='RIGHT', new_y='TOP', align='L')
            pdf.cell(40, 7, f'{record["sum_amount"]:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R')
            total += record["sum_amount"]
    
    # Ukupna suma - ulepšan prikaz
    pdf.ln(3)
    pdf.set_fill_color(200, 220, 240)
    pdf.set_font('DejaVuSansCondensed', 'B', 11)
    pdf.cell(0, 8, f'Ukupno: {total:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R', fill=True)

    
    
    path = f"{project_folder}/static/payment_slips/"
    user_folder = f'{project_folder}/static/payment_slips/user_{current_user.id}'
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    
    file_name = f'export.pdf'
    pdf.output(user_folder + '/' + file_name)
    return file_name


def prepare_payment_data(record, purpose_of_payment, school_info):
    """Priprema podatke za uplatnicu iz zapisa."""
    
    # Dobavi podatke o bankovnom računu
    school = School.query.first()
    bank_account_number = record.transaction_record_service_item.bank_account
    
    # Pronađi podaci o primaocu iz bankovnog računa
    recipient_name = ""
    recipient_address = ""
    for account in school.school_bank_accounts.get('bank_accounts', []):
        if account.get('bank_account_number') == bank_account_number:
            recipient_name = account.get('recipient_name', "")
            recipient_address = account.get('recipient_address', "")
            break
            
    # Implementacija logike za primaoca
    if not recipient_name and not recipient_address:
        # Slučaj 1: Ako su oba polja prazna, koristi naziv i adresu škole
        primalac = f"{school.school_name}\r\n{school.school_address}, {school.school_zip_code} {school.school_city}"
    elif recipient_name and not recipient_address:
        # Slučaj 2: Ako je upisan naziv primaoca, ali ne i adresa, koristi samo naziv
        primalac = recipient_name
    elif not recipient_name and recipient_address:
        # Slučaj 3: Ako je upisana adresa, a ne i naziv, koristi naziv i adresu škole
        primalac = f"{school.school_name}\r\n{school.school_address}, {school.school_zip_code} {school.school_city}"
    else:
        # Ako su oba polja popunjena, koristi oba
        primalac = f"{recipient_name}\r\n{recipient_address}"
    
    if record.transaction_record_service_item.reference_number_spiri == "":
        data = {
            'student_id': record.transaction_record_student.id,
            'uplatilac': record.transaction_record_student.student_name + ' ' + record.transaction_record_student.student_surname,
            'svrha_uplate': f"{record.student_id:04d}-{record.service_item_id:03d} " + purpose_of_payment,
            'primalac': primalac,
            'sifra_placanja': 221,
            'valuta': 'RSD',
            'iznos': f'{record.student_debt_total:.2f}',
            'racun_primaoca': bank_account_number,
            'model': '',
            'poziv_na_broj': '',
            'slanje_mejla_roditelju': record.transaction_record_student.send_mail,
            'record_id': record.id
        }
    else:
        data = {
            'student_id': record.transaction_record_student.id,
            'uplatilac': record.transaction_record_student.student_name + ' ' + record.transaction_record_student.student_surname,
            'svrha_uplate': f"{record.student_id:04d}-{record.service_item_id:03d} " + purpose_of_payment,
            'primalac': primalac,
            'sifra_placanja': 253,
            'valuta': 'RSD',
            'iznos': f'{record.student_debt_total:.2f}',
            'racun_primaoca': bank_account_number,
            'model': '97',
            'poziv_na_broj': record.transaction_record_service_item.reference_number_spiri,
            'slanje_mejla_roditelju': record.transaction_record_student.send_mail,
            'record_id': record.id
        }
    
    return data


def prepare_qr_data(payment_data, school_info):
    """Priprema podatke za QR kod."""
    logger.debug(f"Model: {payment_data.get('model', 'None')} (tip: {type(payment_data.get('model', None))})")
    logger.debug(f"Poziv na broj: {payment_data.get('poziv_na_broj', 'None')} (tip: {type(payment_data.get('poziv_na_broj', None))})")

    racun = payment_data['racun_primaoca'].replace('-', '')
    racun = racun[:3] + racun[3:].zfill(15)
    dug = "RSD" + str(payment_data['iznos']).replace('.', ',')
    
    # Koristi primalac iz payment_data umesto school_info
    primalac_name = payment_data['primalac'].split('\r\n')[0]  # Uzima samo prvu liniju za QR kod
    
    qr_data = {
        "K": "PR",
        "V": "01",
        "C": "1",
        "R": racun,
        "N": primalac_name if len(primalac_name) < 70 else primalac_name[:70],
        "I": dug,
        "P": payment_data['uplatilac'],
        "SF": payment_data['sifra_placanja'],
        "S": payment_data['svrha_uplate'].strip() if len(payment_data['svrha_uplate'].strip()) < 36 else payment_data['svrha_uplate'][:35].strip()
    }
    
    # Dodaj RO polje samo ako postoje i model i poziv na broj
    if payment_data.get('model') and payment_data.get('poziv_na_broj'):
        qr_data["RO"] = payment_data['model'] + payment_data['poziv_na_broj']

    return qr_data


def generate_qr_code(qr_data, student_id, project_folder, current_user_id):
    """Generiše QR kod i vraća naziv fajla.
    
    Args:
        qr_data: Dictionary sa podacima za QR kod
        student_id: ID učenika
        project_folder: Putanja do korena projekta
        current_user_id: ID trenutnog korisnika
    """
    url = 'https://nbs.rs/QRcode/api/qr/v1/gen/250'
    headers = {'Content-Type': 'application/json'}
    
    # Detaljno logovanje podataka pre slanja
    logger.debug("QR kod podaci koji se šalju:")
    for key, value in qr_data.items():
        logger.debug(f"{key}: {value} (dužina: {len(str(value))})")
    
    response = requests.post(url, headers=headers, json=qr_data)
    
    if response.status_code == 500:
        logger.info(f'{response.content=}')
        logger.info(f'{response.headers=}')
        if 'error_message' in response.json():
            logger.debug(f"Error message: {response.json()['error_message']}")
        return None
        
    if response.status_code == 200:
        qr_code_filename = f'qr_{student_id}.png'
        folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user_id}')
        os.makedirs(folder_path, exist_ok=True)
        qr_code_filepath = os.path.join(folder_path, qr_code_filename)
        Image.open(io.BytesIO(response.content)).save(qr_code_filepath)
        return qr_code_filename
    
    return None


def setup_pdf_page(pdf, counter):
    """Postavlja pozicije i linije za novu stranu PDF-a."""
    if counter % 3 == 1:
        pdf.add_page()
        y, y_qr = 0, 50
        pdf.line(210/3, 10, 210/3, 237/3)
        pdf.line(2*210/3, 10, 2*210/3, 237/3)
    elif counter % 3 == 2:
        y, y_qr = 99, 149
        pdf.line(210/3, 110, 210/3, 99+237/3)
        pdf.line(2*210/3, 110, 2*210/3, 99+237/3)
    else:  # counter % 3 == 0
        y, y_qr = 198, 248
        pdf.line(210/3, 210, 210/3, 198+237/3)
        pdf.line(2*210/3, 210, 2*210/3, 198+237/3)
    return y, y_qr


def add_payment_slip_content(pdf, uplatnica, y, y_qr, project_folder, current_user):
    """Dodaje sadržaj uplatnice na PDF.
    
    Args:
        pdf: PDF objekat na koji se dodaje sadržaj
        uplatnica: Dictionary sa podacima za uplatnicu
        y: Vertikalna pozicija
        y_qr: Vertikalna pozicija QR koda
        project_folder: Putanja do korena projekta
        current_user: Objekat trenutnog korisnika
    """
    # QR kod
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.set_y(y_qr)
    pdf.set_x(2*170/3)
    
    qr_code_filename = f'qr_{uplatnica["student_id"]}.png'
    qr_code_path = os.path.join(project_folder, 'static', 'payment_slips', 
                               f'qr_code_{current_user.id}', qr_code_filename)
    
    if os.path.exists(qr_code_path):
        pdf.image(qr_code_path, w=25)
        print(f'success {qr_code_path=}')
    else:
        print(f'failure {qr_code_path=}')
        raise ValueError(f'Ne postoji QR kod slika za studenta {uplatnica["student_id"]}.')
    
    # Leva strana uplatnice
    pdf.set_y(y+8)
    pdf.cell(2*190/3,8, f"NALOG ZA UPLATU", new_y='LAST', align='R', border=0)
    pdf.cell(190/3,8, f"IZVEŠTAJ O UPLATI", new_y='NEXT', new_x='LMARGIN', align='R', border=0)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    
    # Osnovni podaci - leva strana
    pdf.cell(63,4, f"Uplatilac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
    pdf.multi_cell(57, 4, f'''{uplatnica['uplatilac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
    pdf.cell(63,4, f"Svrha uplate", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
    pdf.multi_cell(57,4, f'''{uplatnica['svrha_uplate']}\r\n{''}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
    pdf.cell(63,3, f"Primalac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
    pdf.multi_cell(57,4, f'''{uplatnica['primalac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
    
    # Potpis
    pdf.set_text_color(105, 105, 105)
    pdf.set_font('DejaVuSansCondensed', '', 6)
    pdf.cell(63,3, f"Softver razvio Studio Implicit", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
    pdf.cell(63,3, f"www.implicit.pro", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.set_text_color(0, 0, 0)

    # Detalji plaćanja - leva strana
    pdf.set_y(y + 15)
    pdf.set_x(73)
    pdf.set_font('DejaVuSansCondensed', '', 8)
    pdf.multi_cell(13,3, f"Šifra plaćanja", new_y='LAST', align='L', border=0)
    pdf.multi_cell(7,3, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(13,3, f"Valuta", new_y='LAST', align='L', border=0)
    pdf.multi_cell(10,3, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(13,3, f"Iznos", new_y='NEXT', align='L', border=0)
    
    pdf.set_x(73)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.multi_cell(13,6, f"{uplatnica['sifra_placanja']}", new_y='LAST', align='L', border=1)
    pdf.multi_cell(7,6, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(13,6, f"RSD", new_y='LAST', align='L', border=1)
    pdf.multi_cell(10,6, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(22,6, f"{uplatnica['iznos']}", new_y='NEXT', align='L', border=1)
    
    pdf.set_x(73)
    pdf.set_font('DejaVuSansCondensed', '', 8)
    pdf.multi_cell(65,5, f"Račun primaoca", new_y='NEXT', align='L', border=0)
    pdf.set_x(73)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.multi_cell(65,6, f"{uplatnica['racun_primaoca']}", new_y='NEXT', align='L', border=1)
    
    pdf.set_x(73)
    pdf.set_font('DejaVuSansCondensed', '', 8)
    pdf.multi_cell(65,5, f"Model i poziv na broj (odobrenje)", new_y='NEXT', align='L', border=0)
    pdf.set_x(73)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.multi_cell(10,6, f"{uplatnica['model']}", new_y='LAST', align='L', border=1)
    pdf.multi_cell(10,6, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(45,6, f"{uplatnica['poziv_na_broj']}", new_y='LAST', align='L', border=1)

    # Desna strana uplatnice (kopija)
    pdf.set_y(y + 15)
    pdf.set_x(141)
    pdf.set_font('DejaVuSansCondensed', '', 8)
    pdf.multi_cell(13,3, f"Šifra plaćanja", new_y='LAST', align='L', border=0)
    pdf.multi_cell(7,3, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(13,3, f"Valuta", new_y='LAST', align='L', border=0)
    pdf.multi_cell(10,3, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(13,3, f"Iznos", new_y='NEXT', align='L', border=0)
    
    pdf.set_x(141)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.multi_cell(13,6, f"{uplatnica['sifra_placanja']}", new_y='LAST', align='L', border=1)
    pdf.multi_cell(7,6, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(13,6, f"RSD", new_y='LAST', align='L', border=1)
    pdf.multi_cell(10,6, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(22,6, f"{uplatnica['iznos']}", new_y='NEXT', align='L', border=1)
    
    pdf.set_x(141)
    pdf.set_font('DejaVuSansCondensed', '', 8)
    pdf.multi_cell(65,5, f"Račun primaoca", new_y='NEXT', align='L', border=0)
    pdf.set_x(141)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.multi_cell(65,6, f"{uplatnica['racun_primaoca']}", new_y='NEXT', align='L', border=1)
    
    pdf.set_x(141)
    pdf.set_font('DejaVuSansCondensed', '', 8)
    pdf.multi_cell(65,5, f"Model i poziv na broj (odobrenje)", new_y='NEXT', align='L', border=0)
    pdf.set_x(141)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.multi_cell(10,6, f"{uplatnica['model']}", new_y='LAST', align='L', border=1)
    pdf.multi_cell(10,6, f"", new_y='LAST', align='L', border=0)
    pdf.multi_cell(45,6, f"{uplatnica['poziv_na_broj']}", new_y='NEXT', align='L', border=1)

    # Podaci o uplatiocu i svrsi - desna strana
    pdf.set_x(141)
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.cell(63,4, f"Uplatilac", new_y='NEXT', align='L', border=0)
    pdf.set_x(141)
    pdf.multi_cell(57, 4, f'''{uplatnica['uplatilac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
    pdf.set_x(141)
    pdf.cell(63,4, f"Svrha uplate", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
    pdf.set_x(141)
    pdf.multi_cell(57,4, f'''{uplatnica['svrha_uplate']}\r\n{''}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
    
    # Linije razdvajanja
    pdf.line(10, 99, 200, 99)
    pdf.line(10, 198, 200, 198)



def cleanup_qr_codes(project_folder, current_user_id):
    """Briše QR kodove nakon štampanja.
    
    Args:
        project_folder: Putanja do korena projekta
        current_user_id: ID trenutnog korisnika
    """
    folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user_id}')
    if os.path.isdir(folder_path):
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                logger.info(f"Fajl '{file_path}' je uspešno obrisan.")
        logger.debug("Svi QR kodovi su uspešno obrisani.")
    else:
        logger.debug(f"Navedena putanja '{folder_path}' nije direktorijum.")


class PDF(FPDF):
    """Klasa za generisanje PDF uplatnica."""
    def __init__(self, **kwargs):
        super(PDF, self).__init__(**kwargs)


def uplatnice_gen(records, purpose_of_payment, school_info, school, single, send):
    """Glavna funkcija za generisanje uplatnica."""
    data_list = []
    qr_code_images = []
    
    # Kreiranje user-specifičnog foldera za PDF
    user_folder = f'{project_folder}/static/payment_slips/user_{current_user.id}'
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    
    # Priprema podataka i generisanje QR kodova
    for record in records:
        if record.student_debt_total > 0:
            payment_data = prepare_payment_data(record, purpose_of_payment, school_info)
            data_list.append(payment_data)
            
            # Koristi prilagođeni primalac iz payment_data
            qr_data = prepare_qr_data(payment_data, payment_data['primalac'])
            qr_code_filename = generate_qr_code(qr_data, payment_data['student_id'], 
                                                project_folder, current_user.id)
            if qr_code_filename:
                qr_code_images.append(qr_code_filename)
    
    # Kreiranje PDF-a
    pdf = PDF()
    add_fonts(pdf)
    printed_on_uplatnice = 0
    counter = 1
    
    # Generisanje uplatnica
    for uplatnica in data_list:
        if not uplatnica['slanje_mejla_roditelju'] and not single:
            pass
        elif single:
            pass
        else:
            continue
            
        y, y_qr = setup_pdf_page(pdf, counter)
        add_payment_slip_content(pdf, uplatnica, y, y_qr, project_folder, current_user)
        counter += 1
        
        if single:
            file_name = 'uplatnica.pdf'
            pdf.output(f'{user_folder}/{file_name}')
            if uplatnica['slanje_mejla_roditelju'] and send:
                send_mail(uplatnica, user_folder, file_name)
                pdf = PDF()
                add_fonts(pdf)
                if counter % 3 != 1:
                    pdf.add_page()
            elif not uplatnica['slanje_mejla_roditelju'] and send:
                pdf = PDF()
                add_fonts(pdf)
                if counter % 3 != 1:
                    pdf.add_page()
        else:
            printed_on_uplatnice += 1
    
    # Finalizacija PDF-a
    if not single:
        file_name = 'uplatnice.pdf'
        if printed_on_uplatnice == 0:
            pdf = PDF()
            add_fonts(pdf)
            pdf.add_page()
            pdf.set_font('DejaVuSansCondensed', 'B', 16)
            pdf.multi_cell(0, 20, 'Nema zaduženih učenika ili je svim zaduženim učenicima aktivirana opcija slanja generisanih uplatnica putem e-maila...', align='C')
        pdf.output(f'{user_folder}/{file_name}')
    
    cleanup_qr_codes(project_folder, current_user.id)
    return file_name


def uplatnice_gen_selected(records, purpose_of_payment, school_info, school, single, send):
    """Generiše uplatnice samo za selektovane učenike."""
    data_list = []
    qr_code_images = []
    
    # Kreiranje user-specifičnog foldera za PDF
    user_folder = f'{project_folder}/static/payment_slips/user_{current_user.id}'
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    
    # Priprema podataka i generisanje QR kodova
    for record in records:
        if record.student_debt_total > 0:
            payment_data = prepare_payment_data(record, purpose_of_payment, school_info)
            data_list.append(payment_data)
            
            # Koristi prilagođeni primalac iz payment_data
            qr_data = prepare_qr_data(payment_data, payment_data['primalac'])
            qr_code_filename = generate_qr_code(qr_data, payment_data['student_id'], 
                                                project_folder, current_user.id)
            if qr_code_filename:
                qr_code_images.append(qr_code_filename)
    
    # Kreiranje PDF-a
    pdf = PDF()
    add_fonts(pdf)
    counter = 1
    
    if not data_list:
        # Ako nema uplatnica za štampanje, kreiraj prazan PDF sa objašnjenjem
        pdf.add_page()
        pdf.set_font('DejaVuSansCondensed', 'B', 16)
        pdf.multi_cell(0, 20, 'Nema selektovanih učenika sa važećim uplatnicama.', align='C')
        file_name = 'selektovane_uplatnice.pdf'
        pdf.output(f'{user_folder}/{file_name}')
    else:
        # Generisanje uplatnica
        for uplatnica in data_list:
            y, y_qr = setup_pdf_page(pdf, counter)
            add_payment_slip_content(pdf, uplatnica, y, y_qr, project_folder, current_user)
            counter += 1
        
        file_name = 'selektovane_uplatnice.pdf'
        pdf.output(f'{user_folder}/{file_name}')
    
    # Čišćenje privremenih QR kodova
    cleanup_qr_codes(project_folder, current_user.id)
    return file_name


def gen_report_student_list(export_data, start_date, end_date, filtered_records, service_id, razred, odeljenje, dugovanje, preplata):
    school = School.query.first()
    service_name = ''
    for record in filtered_records:
        if record.service_item_id == int(service_id):
            service_name = record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
            continue
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            # self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            # self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    
        def header(self):
            # Zaglavlje sa informacijama o školi
            self.set_font('DejaVuSansCondensed', 'B', 10)
            self.set_text_color(80, 80, 80)
            self.cell(0, 5, f'{school.school_name}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_address}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_zip_code} {school.school_city}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.set_text_color(0, 0, 0)
            self.ln(3)
    
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    
    # Glavni naslov
    pdf.ln(5)
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(0, 8, f'Pregled stanja učenika po uslugama', new_x='LMARGIN', new_y='NEXT', align='C')
    
    # Filteri
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.set_text_color(60, 60, 60)
    if service_id != '0':
        pdf.cell(0, 5, f'Usluga: ({int(service_id):03}) {service_name}', new_x='LMARGIN', new_y='NEXT', align='L')
    else:
        pdf.cell(0, 5, f'Usluge: Sve', new_x='LMARGIN', new_y='NEXT', align='L')
    if razred:
        pdf.cell(0, 5, f'Razred: {razred}', new_x='LMARGIN', new_y='NEXT', align='L')
    else:
        pdf.cell(0, 5, f'Razredi: Svi', new_x='LMARGIN', new_y='NEXT', align='L')
    if odeljenje:
        pdf.cell(0, 5, f'Odeljenje: {odeljenje}', new_x='LMARGIN', new_y='NEXT', align='L')
    else:
        pdf.cell(0, 5, f'Odeljenja: Sva', new_x='LMARGIN', new_y='NEXT', align='L')
    if dugovanje:
        pdf.cell(0, 5, f'Filtrirani učenici sa dugom', new_x='LMARGIN', new_y='NEXT', align='L')
    elif preplata:
        pdf.cell(0, 5, f'Filtrirani učenici sa preplatom', new_x='LMARGIN', new_y='NEXT', align='L')
    pdf.cell(0, 5, f'Period: od {start_date.strftime("%d.%m.%Y.")} do {end_date.strftime("%d.%m.%Y.")}', new_x='LMARGIN', new_y='NEXT', align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    
    # Zaglavlje tabele
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font('DejaVuSansCondensed', 'B', 9)
    pdf.cell(80, 6, "Učenik", border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(10, 6, "R/O", border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(30, 6, "Zaduženje", border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(30, 6, "Uplate", border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(30, 6, "Saldo", border=1, new_x='LMARGIN', new_y='NEXT', align='C', fill=True)
    
    sorted_data = sorted(export_data, key=lambda x: (x['student_class'], x['student_section']))

    # Redovi tabele
    zaduzenje = 0
    uplate = 0
    pdf.set_font('DejaVuSansCondensed', '', 9)
    for student in sorted_data:
        if student['student_id'] > 1:
            pdf.cell(80, 6, f"({student['student_id']:04d}) {student['student_name']} {student['student_surname']}", border=1, new_x='RIGHT', new_y='TOP', align='L')
            pdf.cell(10, 6, f"{student['student_class']}/{student['student_section']}", border=1, new_x='RIGHT', new_y='TOP', align='C')
            pdf.cell(30, 6, f"{student['student_debt']:.2f}", border=1, new_x='RIGHT', new_y='TOP', align='R')
            pdf.cell(30, 6, f"{student['student_payment']:.2f}", border=1, new_x='RIGHT', new_y='TOP', align='R')
            pdf.cell(30, 6, f"{student['saldo']:.2f}", border=1, new_x='LMARGIN', new_y='NEXT', align='R')
            zaduzenje += student['student_debt']
            uplate += student['student_payment']
    
    saldo = zaduzenje - uplate
    
    # Završni saldo - ulepšan prikaz
    pdf.ln(3)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('DejaVuSansCondensed', 'B', 11)
    
    x_start = 90
    pdf.set_x(x_start)
    pdf.cell(30, 7, 'Zaduženje:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 7, f'{zaduzenje:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R')
    
    pdf.set_x(x_start)
    pdf.cell(30, 7, 'Uplate:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 7, f'{uplate:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R')
    
    pdf.set_x(x_start)
    pdf.set_fill_color(200, 220, 240)
    pdf.set_font('DejaVuSansCondensed', 'B', 12)
    pdf.cell(30, 8, 'Saldo:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 8, f'{saldo:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R', fill=True)
    
    file_name = 'report_student_list.pdf'
    path = f'{project_folder}/static/reports/'
    user_folder = f'{project_folder}/static/reports/user_{current_user.id}'
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    pdf.output(f'{user_folder}/{file_name}')


def gen_report_student(data, unique_services_list, student, start_date, end_date):
    school = School.query.first()
    class PDF(FPDF):
        # def __init__(self, **kwargs):
        #     super(PDF, self).__init__(**kwargs)
        #     self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
        #     self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    
        def header(self):
            # Zaglavlje sa informacijama o školi
            self.set_font('DejaVuSansCondensed', 'B', 10)
            self.set_text_color(80, 80, 80)
            self.cell(0, 5, f'{school.school_name}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_address}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_zip_code} {school.school_city}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.set_text_color(0, 0, 0)
            self.ln(3)
    
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    
    # Glavni naslov
    pdf.ln(5)
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(0, 8, f'Pregled stanja učenika: {student.student_name} {student.student_surname}', new_x='LMARGIN', new_y='NEXT', align='C')
    
    # Period
    pdf.set_font('DejaVuSansCondensed', '', 11)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 6, f'Period: od {start_date.strftime("%d.%m.%Y.")} do {end_date.strftime("%d.%m.%Y.")}', new_x='LMARGIN', new_y='NEXT', align='C')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(8)
    
    zaduzenje = 0
    uplate = 0
    for service in unique_services_list:
        # Naziv usluge
        pdf.set_font('DejaVuSansCondensed', 'B', 13)
        pdf.cell(0, 7, f'({service["id"]:03}) {service["service_name"]}', new_x='LMARGIN', new_y='NEXT', align='L')
        
        # Zaglavlje tabele
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font('DejaVuSansCondensed', 'B', 9)
        pdf.cell(24, 6, 'Datum', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(88, 6, 'Opis usluge', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(25, 6, 'Zaduženje', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(25, 6, 'Uplate', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(23, 6, 'Saldo', border=1, new_x='LMARGIN', new_y='NEXT', align='C', fill=True)
        
        # Redovi tabele
        pdf.set_fill_color(255, 255, 255)
        for record in data:
            if record['service_item_id'] == service['id']:
                pdf.set_font('DejaVuSansCondensed', '', 9)
                
                # Priprema teksta za opis usluge
                opis_text = record["description"]
                if record.get("payment_amount") and record.get("student_payment_id"):
                    opis_text += f' (izvod: {record["student_payment_id"]})'
                
                # Računanje broja linija za visinu reda
                temp_lines = pdf.multi_cell(88, 4, opis_text, split_only=True)
                num_lines = len(temp_lines)
                row_height = num_lines * 4
                
                # Pamćenje početne pozicije
                y_start = pdf.get_y()
                x_start = pdf.get_x()
                
                # Datum kolona
                pdf.rect(x_start, y_start, 24, row_height)
                pdf.set_xy(x_start, y_start + (row_height - 4) / 2)
                pdf.cell(24, 4, f'{record["date"].strftime("%d.%m.%Y.")}', border=0, new_x='RIGHT', new_y='TOP', align='C')
                
                # Opis usluge kolona sa multi_cell
                pdf.set_xy(x_start + 24, y_start)
                pdf.multi_cell(88, 4, opis_text, border=1, align='L')
                
                # Zaduženje kolona
                pdf.set_xy(x_start + 112, y_start)
                pdf.rect(x_start + 112, y_start, 25, row_height)
                pdf.set_xy(x_start + 112, y_start + (row_height - 4) / 2)
                pdf.cell(25, 4, f'{record["debt_amount"]:.2f}', border=0, new_x='RIGHT', new_y='TOP', align='R')
                
                # Uplate kolona
                pdf.set_xy(x_start + 137, y_start)
                pdf.rect(x_start + 137, y_start, 25, row_height)
                pdf.set_xy(x_start + 137, y_start + (row_height - 4) / 2)
                pdf.cell(25, 4, f'{record["payment_amount"]:.2f}', border=0, new_x='RIGHT', new_y='TOP', align='R')
                
                # Saldo kolona
                pdf.set_xy(x_start + 162, y_start)
                pdf.rect(x_start + 162, y_start, 23, row_height)
                pdf.set_xy(x_start + 162, y_start + (row_height - 4) / 2)
                pdf.cell(23, 4, f'{record["saldo"]:.2f}', border=0, new_x='LMARGIN', new_y='TOP', align='R')
                
                # Postavljanje pozicije na početak sledećeg reda
                pdf.set_xy(x_start, y_start + row_height)
                
                zaduzenje += record['debt_amount']
                uplate += record['payment_amount']
        
        pdf.ln(5)
    saldo = zaduzenje - uplate
    
    # Završni saldo - ulepšan prikaz
    pdf.ln(3)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('DejaVuSansCondensed', 'B', 11)
    
    # Tabela za saldo
    x_start = 120
    pdf.set_x(x_start)
    pdf.cell(35, 7, 'Zaduženje:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 7, f'{zaduzenje:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R')
    
    pdf.set_x(x_start)
    pdf.cell(35, 7, 'Uplate:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 7, f'{uplate:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R')
    
    pdf.set_x(x_start)
    pdf.set_fill_color(200, 220, 240)
    pdf.set_font('DejaVuSansCondensed', 'B', 12)
    pdf.cell(35, 8, 'Saldo:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 8, f'{saldo:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R', fill=True)

    logger.debug(f'{zaduzenje=} {uplate=} {saldo=}')
    file_name = 'report_student.pdf'
    path = f'{project_folder}/static/reports/'
    user_folder = f'{project_folder}/static/reports/user_{current_user.id}'
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    pdf.output(f'{user_folder}/{file_name}')


def gen_report_school(data, start_date, end_date, filtered_records, service_id, razred, odeljenje):
    school = School.query.first()
    service_name = ''
    for record in filtered_records:
        if record.service_item_id == int(service_id):
            service_name = record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
            continue
    class PDF(FPDF):
        # def __init__(self, **kwargs):
        #     super(PDF, self).__init__(**kwargs)
        #     self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
        #     self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    
        def header(self):
            # Zaglavlje sa informacijama o školi
            self.set_font('DejaVuSansCondensed', 'B', 10)
            self.set_text_color(80, 80, 80)
            self.cell(0, 5, f'{school.school_name}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_address}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.cell(0, 5, f'{school.school_zip_code} {school.school_city}', new_x='LMARGIN', new_y='NEXT', align='R')
            self.set_text_color(0, 0, 0)
            self.ln(3)
            
    
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    
    # Glavni naslov
    pdf.ln(5)
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(0, 8, f'Pregled stanja učenika po uslugama', new_x='LMARGIN', new_y='NEXT', align='C')
    
    # Filteri
    pdf.set_font('DejaVuSansCondensed', '', 10)
    pdf.set_text_color(60, 60, 60)
    if service_id != '0':
        pdf.cell(0, 5, f'Usluga: ({int(service_id):03}) {service_name}', new_x='LMARGIN', new_y='NEXT', align='L')
    else:
        pdf.cell(0, 5, f'Usluge: Sve', new_x='LMARGIN', new_y='NEXT', align='L')
    if razred:
        pdf.cell(0, 5, f'Razred: {razred}', new_x='LMARGIN', new_y='NEXT', align='L')
    else:
        pdf.cell(0, 5, f'Razredi: Svi', new_x='LMARGIN', new_y='NEXT', align='L')
    if odeljenje:
        pdf.cell(0, 5, f'Odeljenje: {odeljenje}', new_x='LMARGIN', new_y='NEXT', align='L')
    else:
        pdf.cell(0, 5, f'Odeljenja: Sva', new_x='LMARGIN', new_y='NEXT', align='L')
    pdf.cell(0, 5, f'Period: od {start_date.strftime("%d.%m.%Y.")} do {end_date.strftime("%d.%m.%Y.")}', new_x='LMARGIN', new_y='NEXT', align='L')
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    
    # Zaglavlje tabele
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font('DejaVuSansCondensed', 'B', 9)
    pdf.cell(95, 6, 'Odeljenski starešina', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 6, 'Zaduženje', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(30, 6, 'Uplate', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
    pdf.cell(30, 6, 'Saldo', border=1, new_x='LMARGIN', new_y='NEXT', align='C', fill=True)
    
    # Redovi tabele
    zaduzenje = 0
    uplate = 0
    pdf.set_font('DejaVuSansCondensed', '', 9)
    for record in data:
        pdf.cell(95, 6, f"({record['class']}/{record['section']}) {record['teacher']}", border=1, new_x='RIGHT', new_y='TOP', align='L')
        pdf.cell(30, 6, f"{record['student_debt']:.2f}", border=1, new_x='RIGHT', new_y='TOP', align='R')
        pdf.cell(30, 6, f"{record['student_payment']:.2f}", border=1, new_x='RIGHT', new_y='TOP', align='R')
        pdf.cell(30, 6, f"{record['saldo']:.2f}", border=1, new_x='LMARGIN', new_y='NEXT', align='R')
        zaduzenje += record['student_debt']
        uplate += record['student_payment']
    
    saldo = zaduzenje - uplate
    
    # Završni saldo - ulepšan prikaz
    pdf.ln(3)
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font('DejaVuSansCondensed', 'B', 11)
    
    x_start = 95
    pdf.set_x(x_start)
    pdf.cell(30, 7, 'Zaduženje:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 7, f'{zaduzenje:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R')
    
    pdf.set_x(x_start)
    pdf.cell(30, 7, 'Uplate:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 7, f'{uplate:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R')
    
    pdf.set_x(x_start)
    pdf.set_fill_color(200, 220, 240)
    pdf.set_font('DejaVuSansCondensed', 'B', 12)
    pdf.cell(30, 8, 'Saldo:', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
    pdf.cell(30, 8, f'{saldo:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R', fill=True)
    
    file_name = 'report_school.pdf'
    path = f'{project_folder}/static/reports/'
    user_folder = f'{project_folder}/static/reports/user_{current_user.id}'
    if not os.path.exists(user_folder):
        os.makedirs(user_folder)
    pdf.output(f'{user_folder}/{file_name}')


def gen_debt_report(records):
    try:
        logger.debug(f'records: {records=}')
        sorted_records = sorted(records, key=lambda x: x.student_debt_amount * x.studetn_debt_installment_value - x.student_debt_discount, reverse=True)
        logger.debug(f'sorted_records: {sorted_records=}')
        school = School.query.first()
        class PDF(FPDF):
            # def __init__(self, **kwargs):
            #     super(PDF, self).__init__(**kwargs)
            #     self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            #     self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
        
            def header(self):
                # Zaglavlje sa informacijama o školi
                self.set_font('DejaVuSansCondensed', 'B', 10)
                self.set_text_color(80, 80, 80)
                self.cell(0, 5, f'{school.school_name}', new_x='LMARGIN', new_y='NEXT', align='R')
                self.cell(0, 5, f'{school.school_address}', new_x='LMARGIN', new_y='NEXT', align='R')
                self.cell(0, 5, f'{school.school_zip_code} {school.school_city}', new_x='LMARGIN', new_y='NEXT', align='R')
                self.set_text_color(0, 0, 0)
                self.ln(3)
        pdf = PDF()
        add_fonts(pdf)
        pdf.add_page()
        
        # Glavni naslov
        pdf.ln(5)
        pdf.set_font('DejaVuSansCondensed', 'B', 16)
        pdf.cell(0, 8, f'Zaduženje', new_x='LMARGIN', new_y='NEXT', align='C')
        
        # Datum
        pdf.set_font('DejaVuSansCondensed', '', 11)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 6, f'Datum: {datetime.now().strftime("%d.%m.%Y.")}', new_x='LMARGIN', new_y='NEXT', align='C')
        pdf.set_text_color(0, 0, 0)
        pdf.ln(5)
        
        # Zaglavlje tabele
        pdf.set_fill_color(220, 220, 220)
        pdf.set_font('DejaVuSansCondensed', 'B', 8)
        pdf.cell(8, 6, 'Br.', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(35, 6, 'Učenik', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
        pdf.cell(18, 6, 'Poziv', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(63, 6, 'Detalji usluge', border=1, new_x='RIGHT', new_y='TOP', align='L', fill=True)
        pdf.cell(10, 6, 'Kol', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(18, 6, 'Iznos', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(18, 6, 'Olakšica', border=1, new_x='RIGHT', new_y='TOP', align='C', fill=True)
        pdf.cell(20, 6, 'Zaduženje', border=1, new_x='LMARGIN', new_y='NEXT', align='C', fill=True)
        
        # Redovi tabele
        total = 0
        red_br = 1
        pdf.set_font('DejaVuSansCondensed', '', 8)
        for record in sorted_records:
            # Priprema podataka
            service_details = f'{record.transaction_record_student_debt.student_debt_service_item.service_item_service.service_name} - {record.transaction_record_student_debt.student_debt_service_item.service_item_name}'
            zaduzenje_total = record.student_debt_amount * record.studetn_debt_installment_value - record.student_debt_discount
            
            # Računanje visine reda
            temp_lines = pdf.multi_cell(63, 4, service_details, split_only=True)
            num_lines = len(temp_lines)
            row_height = num_lines * 4
            
            # Pamćenje pozicije
            y_start = pdf.get_y()
            x_start = pdf.get_x()
            
            # R.Br.
            pdf.rect(x_start, y_start, 8, row_height)
            pdf.set_xy(x_start, y_start + (row_height - 4) / 2)
            pdf.cell(8, 4, f'{red_br}.', border=0, new_x='RIGHT', new_y='TOP', align='C')
            
            # Učenik
            pdf.rect(x_start + 8, y_start, 35, row_height)
            pdf.set_xy(x_start + 8, y_start + (row_height - 4) / 2)
            pdf.cell(35, 4, f"{record.transaction_record_student.student_name} {record.transaction_record_student.student_surname}", border=0, new_x='RIGHT', new_y='TOP', align='L')
            
            # Poziv na broj
            pdf.rect(x_start + 43, y_start, 18, row_height)
            pdf.set_xy(x_start + 43, y_start + (row_height - 4) / 2)
            pdf.cell(18, 4, f'{record.student_id:04d}-{record.service_item_id:03d}', border=0, new_x='RIGHT', new_y='TOP', align='C')
            
            # Detalji usluge - multi_cell
            pdf.set_xy(x_start + 61, y_start)
            pdf.multi_cell(63, 4, service_details, border=1, align='L')
            
            # Kol
            pdf.rect(x_start + 124, y_start, 10, row_height)
            pdf.set_xy(x_start + 124, y_start + (row_height - 4) / 2)
            pdf.cell(10, 4, f'{record.student_debt_amount}', border=0, new_x='RIGHT', new_y='TOP', align='C')
            
            # Iznos
            pdf.rect(x_start + 134, y_start, 18, row_height)
            pdf.set_xy(x_start + 134, y_start + (row_height - 4) / 2)
            pdf.cell(18, 4, f'{record.studetn_debt_installment_value:.2f}', border=0, new_x='RIGHT', new_y='TOP', align='R')
            
            # Olakšica
            pdf.rect(x_start + 152, y_start, 18, row_height)
            pdf.set_xy(x_start + 152, y_start + (row_height - 4) / 2)
            pdf.cell(18, 4, f'{record.student_debt_discount:.2f}', border=0, new_x='RIGHT', new_y='TOP', align='R')
            
            # Zaduženje
            pdf.rect(x_start + 170, y_start, 20, row_height)
            pdf.set_xy(x_start + 170, y_start + (row_height - 4) / 2)
            pdf.cell(20, 4, f'{zaduzenje_total:.2f}', border=0, new_x='LMARGIN', new_y='TOP', align='R')
            
            # Postavljanje pozicije na početak sledećeg reda
            pdf.set_xy(x_start, y_start + row_height)
            
            total += zaduzenje_total
            red_br += 1
        
        # Završna suma - ulepšan prikaz
        pdf.ln(3)
        pdf.set_fill_color(200, 220, 240)
        pdf.set_font('DejaVuSansCondensed', 'B', 11)
        pdf.cell(0, 8, f'Ukupno: {total:.2f}', border=1, new_x='LMARGIN', new_y='NEXT', align='R', fill=True)
        
        file_name = 'debt_report.pdf'
        # path = f'{project_folder}/static/reports/'
        user_folder = f'{project_folder}/static/reports/user_{current_user.id}'
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        pdf.output(f'{user_folder}/{file_name}')
        return True
    except Exception as e:
        logger.error(f'Greska u generisanju izveštaja: {e}')
        return False