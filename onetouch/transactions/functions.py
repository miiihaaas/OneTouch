import requests, os, io, time, logging
from datetime import datetime
from flask_login import current_user
import requests, os, io, time
from PIL import Image
from fpdf import FPDF
from flask import flash, redirect, url_for
from flask_login import current_user
from flask_mail import Message
from onetouch.models import School, Student, StudentPayment
from onetouch import mail, app


current_file_path = os.path.abspath(__file__)
logging.debug(f'{current_file_path=}')
project_folder = os.path.dirname(os.path.dirname((current_file_path)))
logging.debug(f'{project_folder=}')

font_path = os.path.join(project_folder, 'static', 'fonts', 'DejaVuSansCondensed.ttf')
font_path_B = os.path.join(project_folder, 'static', 'fonts', 'DejaVuSansCondensed-Bold.ttf')


def add_fonts(pdf):
    pdf.add_font('DejaVuSansCondensed', '', font_path, uni=True)
    pdf.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)


def send_mail(uplatnica, path, file_name):
    school = School.query.first()
    student = Student.query.get_or_404(uplatnica['student_id'])
    if student.parent_email == None or student.send_mail == False:
        return 
    parent_email = student.parent_email
    logging.debug(f'Poslao bi mejl roditelju na: {parent_email}')
    sender_email = 'noreply@uplatnice.online'
    recipient_email = parent_email #!'miiihaaas@gmail.com' #! ispraviti kod da prima mejl roditelj
    subject = f"{school.school_name} / Uplatnica: {uplatnica['uplatilac']} - Svrha uplate: {uplatnica['svrha_uplate']}"
    body = f'''
<html>
<head></head>
<body>
<p>Poštovani,<br></p>
<p>Šaljemo Vam nalog za uplatu koji možete naći u prilogu ovog mejla.<br></p>
<p>S poštovanjem,<br>
{school.school_name}<br>
{school.school_address}</p>
</body>
</html>
'''
        
    message = Message(subject, sender=sender_email, recipients=[recipient_email])
    message.html = body
    
    # Dodajte generirani PDF kao prilog mejlu
    with app.open_resource(path + file_name) as attachment:
        message.attach(file_name, 'application/pdf', attachment.read())
    
    try:
        mail.send(message)
        # return redirect(url_for('main.home'))
    except Exception as e:
        flash('Greska prilikom slanja mejla: ' + str(e), 'danger')
        # return redirect(url_for('main.home'))


def export_payment_stats(data):
    logging.debug(f'{data=}')
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
    file_name = f'export.pdf'
    pdf.output(path + file_name)
    return file_name


def uplatnice_gen(records, purpose_of_payment, school_info, school, single, send):
    data_list = []
    qr_code_images = []
    logging.debug(f'{records=}')
    path = f'{project_folder}/static/payment_slips/'
    
    logging.debug(f'{current_user.id=}')
    #! Generiše QR kodove
    for i, record in enumerate(records):
        if record.student_debt_total > 0: #! u ovom IF bloku dodati kod koji će da generiše ili ne uplatnicu ako je čekirano polje za slanje roditelju na mejl.
            #! ako je čekirano da se šalje roditelju, onda ne treba da generiše uplatnicu zajedno sa ostalim uplatnicama, ali treba da generiše posebno uplatnicu koju će poslati mejlom
            new_data = {
                'student_id': record.transaction_record_student.id,
                'uplatilac': record.transaction_record_student.student_name + ' ' + record.transaction_record_student.student_surname,
                'svrha_uplate': f"{record.student_id:04d}-{record.service_item_id:03d} " + purpose_of_payment,
                'primalac': school_info,
                'sifra_placanja': 189,
                'valuta': 'RSD', #! proveri da li je zbog QR koda potrebno drugačije definisati valutu
                'iznos': record.student_debt_total,
                'racun_primaoca': record.transaction_record_service_item.bank_account,
                'model': '97', #'00', #! proveriti koji je model zbog QR koda 
                'poziv_na_broj': record.transaction_record_service_item.reference_number_spiri, # f"{record.student_id:04d}-{record.service_item_id:03d}",
                'slanje_mejla_roditelju': record.transaction_record_student.send_mail
            }
            data_list.append(new_data)
            
            racun = record.transaction_record_service_item.bank_account
            racun = racun.replace('-', '')  # Uklanja sve crtice iz računa
            racun = racun[:3] + racun[3:].zfill(15)  # Dodaje nule posle prvih 3 cifre računa do ukupne dužine od 18 cifara
            logging.debug(f'test računa za QR kod: {racun=}')
            dug = new_data['iznos']
            dug = "RSD" + str(dug).replace('.', ',')
            qr_data = {
                "K": "PR",
                "V": "01",
                "C": "1",
                "R": racun,
                "N": school_info,
                "I": dug,
                "P": new_data['uplatilac'],
                "SF": new_data['sifra_placanja'],
                "S": new_data['svrha_uplate'] if len(new_data['svrha_uplate']) < 36 else new_data['svrha_uplate'][:35], #! za generisanje QR koda maksimalno može da bude 35 karaktera
                "RO": new_data['model'] + new_data['poziv_na_broj']
            }
            logging.debug(f'{qr_data=}')
            #! dokumentacija: https://ips.nbs.rs/PDF/Smernice_Generator_Validator_latinica_feb2023.pdf
            #! dokumentacija: https://ips.nbs.rs/PDF/pdfPreporukeNovoLat.pdf
            url = 'https://nbs.rs/QRcode/api/qr/v1/gen/250'
            headers = { 'Content-Type': 'application/json' }
            response = requests.post(url, headers=headers, json=qr_data)
            logging.info(f'{response=}')
            if response.status_code == 500:
                logging.info(response.content)
                logging.info(response.headers)
                response_data = response.json()
                if 'error_message' in response_data:
                    error_message = response_data['error_message']
                    logging.debug(f"Error message: {error_message}")

            if response.status_code == 200:
                qr_code_filename = f'qr_{i}.png'
                folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user.id}')
                os.makedirs(folder_path, exist_ok=True)  # Kreira folder ako ne postoji
                qr_code_filepath = os.path.join(folder_path, qr_code_filename)
                
                # Otvori sliku i sačuvaj je direktno na putanju
                Image.open(io.BytesIO(response.content)).save(qr_code_filepath)
                
                # Dodaj naziv fajla u listu
                folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user.id}')
                os.makedirs(folder_path, exist_ok=True)  # Kreira folder ako ne postoji
                qr_code_filepath = os.path.join(folder_path, qr_code_filename)
                
                # Otvori sliku i sačuvaj je direktno na putanju
                Image.open(io.BytesIO(response.content)).save(qr_code_filepath)
                
                # Dodaj naziv fajla u listu
                qr_code_images.append(qr_code_filename)
            else:
                pass
            logging.debug(f'{qr_code_images=}')
    time.sleep(2)
    logging.debug (f'{data_list=}')
    logging.debug(f'{len(data_list)=}')
    # gen_file = uplatnice_gen(data_list, qr_code_images) #! prilagodi ovu funciju

    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            # self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            # self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    pdf = PDF()
    add_fonts(pdf)
    printed_on_uplatnice = 0
    counter = 1
    #!
    for i, uplatnica in enumerate(data_list):
        logging.debug(f'{uplatnica=}')
        logging.debug(f'ulazni parametrii funkcije: {single=} {send=}')
        if not uplatnica['slanje_mejla_roditelju'] and not single:
            logging.info('generisati sve uplatnice, OSIM onih koje se šalju roditelju na mejl!')
            pass #! ovo bi trebalo da preskoči elif i da nastavi u redu if counter % 3 == 1...
        elif single:
            logging.info('odabrano da se generiše samo jedna uplatnica')
            pass
        else:
            continue
        # elif uplatnica['slanje_mejla_roditelju'] and not single:
        #     pass
        # elif not uplatnica['slanje_mejla_roditelju']:
        #     continue #! završava se ovde iteracija for loopa i počinje sledeća iteracija; donji kod neće biti aktiviran
        logging.debug(f'izašao iz IF petlje, red pred if petlju koja određuje u kojoj trećini će se generisati uplatnica')
        if counter % 3 == 1:
            logging.debug(f'prva trećina')
            pdf.add_page()
            y = 0
            y_qr = 50
            pdf.line(210/3, 10, 210/3, 237/3)
            pdf.line(2*210/3, 10, 2*210/3, 237/3)
        elif counter % 3 == 2:
            logging.debug(f'druga trećina')
            y = 99
            y_qr = 149
            pdf.line(210/3, 110, 210/3, 99+237/3)
            pdf.line(2*210/3, 110, 2*210/3, 99+237/3)
        elif counter % 3 == 0:
            logging.debug(f'treća trećina')
            y = 198
            y_qr = 248
            pdf.line(210/3, 210, 210/3, 198+237/3)
            pdf.line(2*210/3, 210, 2*210/3, 198+237/3)
        pdf.set_font('DejaVuSansCondensed', 'B', 16)
        pdf.set_y(y_qr)
        pdf.set_x(2*170/3)
        pdf.image(f'{project_folder}/static/payment_slips/qr_code_{current_user.id}/{qr_code_images[i]}' , w=25)
        if i < len(qr_code_images):
            pdf.image(f'{project_folder}/static/payment_slips/qr_code_{current_user.id}/{qr_code_images[i]}' , w=25)
        else:
            raise ValueError(f'Ne postoji QR kod slika za uplatnicu broj {counter}.')
        pdf.set_y(y+8)
        pdf.cell(2*190/3,8, f"NALOG ZA UPLATU", new_y='LAST', align='R', border=0)
        pdf.cell(190/3,8, f"IZVEŠTAJ O UPLATI", new_y='NEXT', new_x='LMARGIN', align='R', border=0)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        pdf.cell(63,4, f"Uplatilac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(57, 4, f'''{uplatnica['uplatilac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(63,4, f"Svrha uplate", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(57,4, f'''{uplatnica['svrha_uplate']}\r\n{''}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(63,3, f"Primalac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(57,4, f'''{uplatnica['primalac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        # Postavljanje tamno sive boje (RGB: 105, 105, 105)
        pdf.set_text_color(105, 105, 105)
        pdf.set_font('DejaVuSansCondensed', '', 6)
        pdf.cell(63,3, f"", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.cell(63,3, f"Softver razvio Studio Implicit", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.cell(63,3, f"www.implicit.pro", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        # Vraćanje na crnu boju (RGB: 0, 0, 0)
        pdf.set_text_color(0, 0, 0)
        # pdf.set_font('DejaVuSansCondensed', '', 7)
        # pdf.cell(50,4, f"Pečat i potpis uplatioca", new_y='NEXT', new_x='LMARGIN', align='L', border='T')
        # pdf.cell(95,1, f"", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        # pdf.set_x(50)
        # pdf.cell(50,4, f"Mesto i datum prijema", new_y='LAST', align='L', border='T')
        # pdf.set_x(110)
        # pdf.cell(40,5, f"Datum valute", align='L', border='T')
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
        pdf.set_x(141)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        pdf.cell(63,4, f"Uplatilac", new_y='NEXT', align='L', border=0)
        pdf.set_x(141)
        pdf.multi_cell(57, 4, f'''{uplatnica['uplatilac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.set_x(141)
        pdf.cell(63,4, f"Svrha uplate", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.set_x(141)
        pdf.multi_cell(57,4, f'''{uplatnica['svrha_uplate']}\r\n{''}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        
        pdf.line(10, 99, 200, 99)
        pdf.line(10, 198, 200, 198)
        counter += 1


        #! if blok koji menja file_name.
        #! ukoliko je generisanje uplatnica za više đaka (gen sve) da se čuva na 'uplatnice.pdf', 
        #! a ukoliko je za jednog đaka (generišite uplatnicu) da se čuva na 'uplatnica.pdf'
        if single:
            logging.debug('if blok koji potvrđuje da je single')
            logging.debug(f'{uplatnica["uplatilac"]=}')
            file_name = f'uplatnica.pdf'
            pdf.output(path + file_name)
            if uplatnica['slanje_mejla_roditelju'] and send:
                logging.info(f'poslat je mejl za {uplatnica["uplatilac"]}')
                send_mail(uplatnica, path, file_name)
                pdf = PDF()
                add_fonts(pdf)
                if counter % 3 != 1:
                # if counter % 3 != 1:
                    pdf.add_page()
            elif not uplatnica['slanje_mejla_roditelju'] and send:
                logging.info(f'NIJE poslat mejl za {uplatnica["uplatilac"]}. Kreiraj početak pdf stranice za sledeću uplatnicu koja se šalje')
                pdf = PDF()
                add_fonts(pdf)
                if counter % 3 != 1:
                    pdf.add_page()
        else:
            printed_on_uplatnice += 1
    logging.debug(f'{printed_on_uplatnice=}')
    if not single:
        logging.debug(f'debug: ušao sam u "if not single:": {printed_on_uplatnice=}')
        if printed_on_uplatnice == 0:
            logging.debug(f'debug: ušao sam u "if not single: // if printed_on_uplatnice == 0:": {printed_on_uplatnice=}')
            # nije bilo štampe na uplatnicama
            pdf = PDF()
            add_fonts(pdf)
            pdf.add_page()
            pdf.set_font('DejaVuSansCondensed', 'B', 16)
            pdf.multi_cell(0, 20, 'Nema zaduženih učenika ili je svim zaduženim učenicima aktivirana opcija slanja generisanih uplatnica putem e-maila. \nMolimo Vas da prvo proverite da li u nalogu barem jedan učenik ima zaduženje. Ako ste omogućili opciju slanja generisanih uplatnica putem e-maila, ljubazno Vas molimo da se pobrinite da sve uplatnice budu poslate roditeljima elektronskim putem. \nOvim putem Vas molimo da ne štampate ovaj dokument.', align='C')
        file_name = f'uplatnice.pdf'
        pdf.output(path + file_name)
        logging.debug(f'debug if not single: {file_name=}')
    else:
        file_name = f'uplatnica.pdf'

    #! briše QR kodove nakon dodavanja na uplatnice
    folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user.id}')

    # Proveri da li je folder direktorijum i obriši sve fajlove u njemu
    folder_path = os.path.join(project_folder, 'static', 'payment_slips', f'qr_code_{current_user.id}')

    # Proveri da li je folder direktorijum i obriši sve fajlove u njemu
    if os.path.isdir(folder_path):
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)
                logging.info(f"Fajl '{file_path}' je uspešno obrisan.")
        logging.debug("Svi QR kodovi su uspešno obrisani.")
    else:
        logging.debug(f"Navedena putanja '{folder_path}' nije direktorijum.")

    # file_name = f'{project_folder}static/payment_slips/uplatnice.pdf' #!
    # file_name = f'uplatnice.pdf' #!

    logging.info(f'debug na samom kraju uplatice_gen(): {file_name=}')
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
    pdf.output(path + file_name)


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

    logging.debug(f'{zaduzenje=} {uplate=} {saldo=}')
    file_name = 'report_student.pdf'
    path = f'{project_folder}/static/reports/'
    pdf.output(path + file_name)


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
    pdf.output(path + file_name)


def gen_dept_report(records):
    logging.debug(f'records: {records=}')
    sorted_records = sorted(records, key=lambda x: x.student_debt_amount * x.studetn_debt_installment_value - x.student_debt_discount, reverse=True)
    logging.debug(f'sorted_records: {sorted_records=}')
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
    
    file_name = 'dept_report.pdf'
    path = f'{project_folder}/static/reports/'
    pdf.output(path + file_name)