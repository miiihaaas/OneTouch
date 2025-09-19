import dns.resolver
import smtplib
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


def verify_email(email):
    """Verify if email address is valid and reachable."""
    try:
        # Check email format
        _, domain = parseaddr(email)[1].split('@')
        
        # Get MX records
        mx_records = dns.resolver.resolve(domain, 'MX')
        if not mx_records:
            return False, "No MX records found for domain"
        
        # Try connecting to mail server
        mx_record = str(mx_records[0].exchange)
        with smtplib.SMTP(timeout=10) as server:
            server.connect(mx_record)
            server.helo()
            return True, None
            
    except Exception as e:
        return False, str(e)

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
                        sender=sender_email,
                        recipients=[parent_email])
    
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
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            # self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            # self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
        def header(self) -> None:
            self.set_font('DejaVuSansCondensed', 'B', 22)
            self.cell(0, 10, f'Izvod podataka uplatnice: {student_payment.statment_nubmer} ({student_payment.payment_date.strftime("%d.%m.%Y.")})', new_y='NEXT', new_x='LMARGIN', align='C', border=0)
            self.cell(0, 10, '', new_y='NEXT', new_x='LMARGIN', align='C', border=0)
            self.set_font('DejaVuSansCondensed', 'B', 14)
            self.set_fill_color(200, 200, 200)
            self.cell(30, 10, 'ID usluge', new_y='LAST', align='C', border=1, fill=True)
            self.cell(120, 10, 'Detalji usluge', new_y='LAST', align='C', border=1, fill=True)
            self.cell(40, 10, 'Ukupan iznos', new_y='NEXT', new_x='LMARGIN', align='C', border=1, fill=True)
            
            
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    pdf.set_font('DejaVuSansCondensed', '', 12)
    for record in data:
        if record['service_item_id'] != 0:
            pdf.cell(30, 7, f'{record["service_item_id"]:03d}', new_y='LAST', align='C', border=1)
            pdf.cell(120, 7, f'{record["name"]}', new_y='LAST', align='L', border=1)
            pdf.cell(40, 7, f'{record["sum_amount"]:.2f}', new_y='NEXT', new_x='LMARGIN', align='R', border=1)

    
    
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
            'iznos': record.student_debt_total,
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
            'iznos': record.student_debt_total,
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


def generate_qr_code(qr_data, student_id, project_folder, current_user):
    """Generiše QR kod i vraća naziv fajla."""
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
        folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user.id}')
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
    """Dodaje sadržaj uplatnice na PDF."""
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



def cleanup_qr_codes(project_folder, current_user):
    """Briše QR kodove nakon štampanja."""
    folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user.id}')
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
                                                project_folder, current_user)
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
    
    cleanup_qr_codes(project_folder, current_user)
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
            # Postavite font i veličinu teksta za zaglavlje
            self.set_font('DejaVuSansCondensed', 'B', 12)
            
            # Dodajte informacije o školi
            self.cell(0, 6, f'{school.school_name}', 0, 1, 'R')
            self.cell(0, 6, f' {school.school_address}', 0, 1, 'R')
            self.cell(0, 6, f'{school.school_zip_code} {school.school_city}', 0, 1, 'R')
            pdf.set_font('DejaVuSansCondensed', 'B', 18)
            pdf.cell(40, 8, '', 0, 1, 'R')
            pdf.cell(0, 15, f'Pregled stanja učenika po uslugama', 0, 1, 'C')  # Promenite "new_y" u 0 i uklonite "border"
            pdf.set_font('DejaVuSansCondensed', 'B', 12)
            if service_id != '0':
                pdf.cell(0, 5, f'Usluga: ({int(service_id):03}) {service_name}', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            else:
                pdf.cell(0, 5, f'Usluge: Sve', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            if razred:
                pdf.cell(0, 5, f'Razred: {razred} ', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            else:
                pdf.cell(0, 5, f'Razredi: Svi ', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            if odeljenje:
                pdf.cell(0, 5, f'Odeljenje: {odeljenje}', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            else:
                pdf.cell(0, 5, f'Odeljenja: Sva', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            if dugovanje:
                pdf.cell(0, 5, f'Filtrirani učenici sa dugom', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            elif preplata:
                pdf.cell(0, 5, f'Filtriranji učenici sa preplatom', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            pdf.cell(0, 5, f'Period: od {start_date.strftime("%d.%m.%Y.")} do {end_date.strftime("%d.%m.%Y.")}', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            pdf.cell(40, 8, '', 0, 1, 'R')
            
            pdf.set_font('DejaVuSansCondensed', 'B', 10)
            pdf.set_fill_color(200, 200, 200)  # Postavite svetlo sivu boju za ćelije
            pdf.cell(80, 8, f"Učenik", 1, 0, 'C', 1)
            pdf.cell(10, 8, f"R/O", 1, 0, 'C', 1)
            pdf.cell(30, 8, f"Zaduženje", 1, 0, 'C', 1)
            pdf.cell(30, 8, f"Uplate", 1, 0, 'C', 1)
            pdf.cell(30, 8, f"Saldo", 1, 1, 'C', 1)
    
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    
    sorted_data = sorted(export_data, key=lambda x: (x['student_class'], x['student_section']))

    zaduzenje = 0
    uplate = 0
    for student in sorted_data:
        if student['student_id'] > 1:
            pdf.set_font('DejaVuSansCondensed', '', 10)
            # pdf.set_fill_color(255, 255, 255)  # vrati na belu boju za ćelije
            pdf.cell(80, 8, f"({'{:04d}'.format(student['student_id'])}) {student['student_name']} {student['student_surname']}", 1, 0, 'L')
            pdf.cell(10, 8, f"{ student['student_class'] }/{ student['student_section'] }", 1, 0, 'C')
            pdf.cell(30, 8, f"{ '{:.2f}'.format(student['student_debt']) }", 1, 0, 'R')
            pdf.cell(30, 8, f"{ '{:.2f}'.format(student['student_payment']) }", 1, 0, 'R')
            pdf.cell(30, 8, f"{ '{:.2f}'.format(student['saldo']) }", 1, 1, 'R')
            zaduzenje += student['student_debt']
            uplate += student['student_payment']
    saldo = zaduzenje - uplate
    pdf.set_font('DejaVuSansCondensed', 'B', 10)
    pdf.set_fill_color(200, 200, 200)  # Postavite svetlo sivu boju za ćelije
    pdf.cell(80, 8, f"", 0, 0, 'R')
    pdf.cell(10, 8, f"Suma: ", 0, 0, 'R')
    pdf.cell(30, 8, f"{zaduzenje:.2f}", 1, 0, 'R', 1)
    pdf.cell(30, 8, f"{uplate:.2f}", 1, 0, 'R', 1)
    pdf.cell(30, 8, f"{saldo:.2f}", 1, 1, 'R', 1)
    
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
            # Postavite font i veličinu teksta za zaglavlje
            self.set_font('DejaVuSansCondensed', 'B', 12)
            
            # Dodajte informacije o školi
            self.cell(0, 6, f'{school.school_name}', 0, 1, 'R')
            self.cell(0, 6, f' {school.school_address}', 0, 1, 'R')
            self.cell(0, 6, f'{school.school_zip_code} {school.school_city}', 0, 1, 'R')
    
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    
    pdf.set_font('DejaVuSansCondensed', 'B', 18)
    pdf.cell(40, 8, '', 0, 1, 'R')
    pdf.cell(0, 8, f'Pregled stanja učenika: {student.student_name} {student.student_surname}', 0, 1, 'C')  # Promenite "new_y" u 0 i uklonite "border"
    pdf.cell(0, 8, f'Period: od {start_date.strftime("%d.%m.%Y.")} do {end_date.strftime("%d.%m.%Y.")}', 0, 1, 'C')  # Promenite "new_y" u 0 i uklonite "border"
    pdf.cell(40, 8, '', 0, 1, 'R')
    zaduzenje = 0
    uplate = 0
    for service in unique_services_list:
        pdf.set_font('DejaVuSansCondensed', 'B', 16)
        pdf.cell(0, 8, f'({service["id"]:03}) {service["service_name"]}', 0, 1, 'L')
        pdf.set_fill_color(200, 200, 200)  # Postavite svetlo sivu boju za ćelije
        pdf.set_font('DejaVuSansCondensed', 'B', 12)
        pdf.cell(25, 8, 'Datum', 1, 0, 'C', 1)  # Dodajte border, 40 je širina ćelije
        pdf.cell(85, 8, 'Opis usluge', 1, 0, 'C', 1)  # Dodajte border, 60 je širina ćelije
        pdf.cell(25, 8, 'Zaduženje', 1, 0, 'C', 1)  # Dodajte border, 30 je širina ćelije
        pdf.cell(25, 8, 'Uplate', 1, 0, 'C', 1)  # Dodajte border, 30 je širina ćelije
        pdf.cell(25, 8, 'Saldo', 1, 1, 'C', 1)  # Dodajte border, 30 je širina ćelije i prelazi u novi red
        pdf.set_fill_color(255, 255, 255)
        for record in data:
            if record['service_item_id'] == service['id']:
                pdf.set_font('DejaVuSansCondensed', '', 12)
                pdf.cell(25, 8, f'{record["date"].strftime("%d.%m.%Y.")}', 1, 0, 'C', 1)
                pdf.cell(85, 8, f'{record["description"]} {"(izvod: " + str(record["student_payment_id"]) + ")" if record.get("payment_amount") else ""}', 1, 0, 'L', 1)
                pdf.cell(25, 8, f'{record["debt_amount"]:,.2f}', 1, 0, 'R', 1)
                pdf.cell(25, 8, f'{record["payment_amount"]:,.2f}', 1, 0, 'R', 1)
                pdf.cell(25, 8, f'{record["saldo"]:,.2f}', 1, 1, 'R', 1)
                zaduzenje += record['debt_amount']
                uplate += record['payment_amount']
        pdf.cell(40, 8, '', 0, 1, 'R')
    saldo = zaduzenje - uplate
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(40, 8, '', 0, 1, 'R')  # Uklonili smo border postavljanjem poslednjeg argumenta na 0
    pdf.cell(40, 8, 'Zaduženje:', 0, 0, 'R')
    pdf.cell(40, 8, f'{zaduzenje:,.2f}', 0, 1, 'R')
    pdf.cell(40, 8, 'Uplate:', 0, 0, 'R')
    pdf.cell(40, 8, f'{uplate:,.2f}', 0, 1, 'R')
    pdf.cell(40, 8, 'Saldo:', 0, 0, 'R')
    pdf.cell(40, 8, f'{saldo:,.2f}', 0, 1, 'R')

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
            # Postavite font i veličinu teksta za zaglavlje
            self.set_font('DejaVuSansCondensed', 'B', 12)
            
            # Dodajte informacije o školi
            self.cell(0, 6, f'{school.school_name}', 0, 1, 'R')
            self.cell(0, 6, f' {school.school_address}', 0, 1, 'R')
            self.cell(0, 6, f'{school.school_zip_code} {school.school_city}', 0, 1, 'R')
            self.set_font('DejaVuSansCondensed', 'B', 18)
            self.cell(40, 8, '', 0, 1, 'R')
            self.cell(0, 15, f'Pregled stanja učenika po uslugama', 0, 1, 'C')  # Promenite "new_y" u 0 i uklonite "border"
            self.set_font('DejaVuSansCondensed', 'B', 12)
            if service_id != '0':
                self.cell(0, 5, f'Usluga: ({int(service_id):03}) {service_name}', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            else:
                self.cell(0, 5, f'Usluge: Sve', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            if razred:
                self.cell(0, 5, f'Razred: {razred} ', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            else:
                self.cell(0, 5, f'Razredi: Svi ', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            if odeljenje:
                self.cell(0, 5, f'Odeljenje: {odeljenje}', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            else:
                self.cell(0, 5, f'Odeljenja: Sva', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            self.cell(0, 5, f'Period: od {start_date.strftime("%d.%m.%Y.")} do {end_date.strftime("%d.%m.%Y.")}', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            self.cell(40, 8, '', 0, 1, 'R')
            
            
            self.set_fill_color(200, 200, 200)  # Postavite svetlo sivu boju za ćelije
            self.set_font('DejaVuSansCondensed', 'B', 12)
            self.cell(95, 8, f'Odeljenski starešina', 1, 0, 'L', 1)
            self.cell(30, 8, f'Zaduženje', 1, 0, 'C', 1)
            self.cell(30, 8, f'Uplate', 1, 0, 'C', 1)
            self.cell(30, 8, f'Saldo', 1, 1, 'C', 1)
            
    
    pdf = PDF()
    add_fonts(pdf)
    pdf.add_page()
    
    zaduzenje = 0
    uplate = 0
    for record in data:
        pdf.set_fill_color(255, 255, 255)
        pdf.set_font('DejaVuSansCondensed', 'B', 12)
        pdf.cell(95, 8, f"({record['class'] }/{ record['section']}) {record['teacher']}", 1, 0, 'L', 1)
        pdf.cell(30, 8, f"{record['student_debt']:,.2f}", 1, 0, 'R', 1)
        pdf.cell(30, 8, f"{record['student_payment']:,.2f}", 1, 0, 'R', 1)
        pdf.cell(30, 8, f"{record['saldo']:,.2f}", 1, 1, 'R', 1)
        zaduzenje += record['student_debt']
        uplate += record['student_payment']
    saldo = zaduzenje - uplate
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(40, 8, '', 0, 1, 'R')  # Uklonili smo border postavljanjem poslednjeg argumenta na 0
    pdf.cell(40, 8, 'Zaduzenje:', 0, 0, 'R')
    pdf.cell(40, 8, f'{zaduzenje:,.2f}', 0, 1, 'R')
    pdf.cell(40, 8, 'Uplate:', 0, 0, 'R')
    pdf.cell(40, 8, f'{uplate:,.2f}', 0, 1, 'R')
    pdf.cell(40, 8, 'Saldo:', 0, 0, 'R')
    pdf.cell(40, 8, f'{saldo:,.2f}', 0, 1, 'R')
    
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
                # Postavite font i veličinu teksta za zaglavlje
                self.set_font('DejaVuSansCondensed', 'B', 10)
                # Dodajte informacije o školi
                self.cell(0, 6, f'{school.school_name}', 0, 1, 'R')
                self.cell(0, 6, f' {school.school_address}', 0, 1, 'R')
                self.cell(0, 6, f'{school.school_zip_code} {school.school_city}', 0, 1, 'R')
                self.cell(0, 6, f'Datum: {datetime.now().strftime("%d.%m.%Y.")}', 0, 1, 'R')
                self.set_font('DejaVuSansCondensed', 'B', 18)
                self.cell(40, 8, '', 0, 1, 'R')
                self.cell(0, 15, f'Zaduženje', 0, 1, 'C')  # Promenite "new_y" u 0 i uklonite "border"
                self.set_fill_color(200, 200, 200)  # Postavite svetlo sivu boju za ćelije
                self.set_font('DejaVuSansCondensed', 'B', 10)
                self.cell(10, 8, 'R.Br.', 1, 0, 'C', 1)
                self.cell(40, 8, 'Učenik', 1, 0, 'L', 1)
                self.cell(22, 8, 'Poziv na br', 1, 0, 'L', 1)
                self.cell(58, 8, 'Detalji usluge', 1, 0, 'L', 1)
                self.cell(10, 8, 'Kol', 1, 0, 'C', 1)
                self.cell(15, 8, 'Iznos', 1, 0, 'C', 1)
                self.cell(15, 8, 'Olakšica', 1, 0, 'C', 1)
                self.cell(20, 8, 'Zaduženje', 1, 1, 'C', 1)
        pdf = PDF()
        add_fonts(pdf)
        pdf.add_page()
        pdf.set_fill_color(255, 255, 255)
        total = 0
        red_br = 1
        for record in sorted_records:
            pdf.set_font('DejaVuSansCondensed', '', 10)
            pdf.cell(10, 8, f'{red_br}.', 1, 0, 'C')
            pdf.cell(40, 8, f"{record.transaction_record_student.student_name} {record.transaction_record_student.student_surname}", 1, 0, 'L')
            pdf.cell(22, 8, f'{ "{:04d}-{:03d}".format(record.student_id, record.service_item_id) }', 1, 0, 'C')
            pdf.cell(58, 8, f'{ record.transaction_record_student_debt.student_debt_service_item.service_item_service.service_name } - { record.transaction_record_student_debt.student_debt_service_item.service_item_name }', 1, 0, 'L')
            pdf.cell(10, 8, f'{ record.student_debt_amount }', 1, 0, 'C')
            pdf.cell(15, 8, f'{ "{:.2f}".format(record.studetn_debt_installment_value) }', 1, 0, 'R')
            pdf.cell(15, 8, f'{ "{:.2f}".format(record.student_debt_discount)}', 1, 0, 'R')
            pdf.cell(20, 8, f'{ "{:.2f}".format(record.student_debt_amount * record.studetn_debt_installment_value - record.student_debt_discount)}', 1, 1, 'R')
            total += record.student_debt_amount * record.studetn_debt_installment_value - record.student_debt_discount
            red_br += 1
        pdf.set_fill_color(200, 200, 200)  # Postavite svetlo sivu boju za ćelije
        pdf.cell(0, 8, f'Ukupno: {total:,.2f}', 1, 0, 'R', 1)
        
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