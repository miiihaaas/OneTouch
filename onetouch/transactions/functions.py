import requests, os, io, time
from PIL import Image
from fpdf import FPDF
from flask import flash, redirect, url_for
from flask_mail import Message
from onetouch.models import School, Student, StudentPayment
from onetouch import mail, app


current_file_path = os.path.abspath(__file__)
print(f'{current_file_path=}')
project_folder = os.path.dirname(os.path.dirname((current_file_path)))
print(f'{project_folder=}')
font_path = os.path.join(project_folder, 'static', 'fonts', 'DejaVuSansCondensed.ttf')
font_path_B = os.path.join(project_folder, 'static', 'fonts', 'DejaVuSansCondensed-Bold.ttf')


def send_mail(uplatnica, path, file_name):
    school = School.query.first()
    student = Student.query.get_or_404(uplatnica['student_id'])
    if student.parent_email == None or student.send_mail == False:
        return 
    parent_email = student.parent_email
    print(f'Poslao bi mejl roditelju na: {parent_email}')
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
    print(f'{data=}')
    student_payment = StudentPayment.query.get_or_404(data[0]['payment_id'])
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('DejaVuSansCondensed', 'B', 22)
    pdf.set_y(10)
    pdf.cell(0, 10, f'Izvod podataka uplatnice: {student_payment.statment_nubmer} ({student_payment.payment_date.strftime("%d.%m.%Y.")})', new_y='NEXT', new_x='LMARGIN', align='C', border=0)
    pdf.cell(0, 10, '', new_y='NEXT', new_x='LMARGIN', align='C', border=0)
    pdf.set_font('DejaVuSansCondensed', 'B', 14)
    pdf.set_fill_color(200, 200, 200)
    pdf.cell(30, 10, 'ID usluge', new_y='LAST', align='C', border=1, fill=True)
    pdf.cell(120, 10, 'Detalji usluge', new_y='LAST', align='C', border=1, fill=True)
    pdf.cell(40, 10, 'Ukupan iznos', new_y='NEXT', new_x='LMARGIN', align='C', border=1, fill=True)
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
    print('debug generisanja uplatnice kod aktivne opcije slanja na mejl')
    print(f'{records=}')
    path = f'{project_folder}/static/payment_slips/'
    
    for i, record in enumerate(records):
        if record.student_debt_total > 0: #! u ovom IF bloku dodati kod koji će da generiše ili ne uplatnicu ako je čekirano polje za slanje roditelju na mejl.
            #! ako je čekirano da se šalje roditelju, onda ne treba da generiše uplatnicu zajedno sa ostalim uplatnicama, ali treba da generiše posebno uplatnicu koju će poslati mejlom
            new_data = {
                'student_id': record.transaction_record_student.id,
                'uplatilac': record.transaction_record_student.student_name + ' ' + record.transaction_record_student.student_surname,
                'svrha_uplate': purpose_of_payment,
                'primalac': school_info,
                'sifra_placanja': 189,
                'valuta': 'RSD', #! proveri da li je zbog QR koda potrebno drugačije definisati valutu
                'iznos': record.student_debt_total,
                'racun_primaoca': school.school_bank_account,
                'model': '00', #! proveriti koji je model zbog QR koda 
                'poziv_na_broj': f"{record.student_id:04d}-{record.service_item_id:03d}",
                'slanje_mejla_roditelju': record.transaction_record_student.send_mail
            }
            data_list.append(new_data)
            
            racun = school.school_bank_account
            racun = racun.replace('-', '')  # Uklanja sve crtice iz računa
            racun = racun[:3] + racun[3:].zfill(15)  # Dodaje nule posle prvih 3 cifre računa do ukupne dužine od 18 cifara
            print(f'test računa za QR kod: {racun=}')
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
            print(f'{qr_data=}')
            #! dokumentacija: https://ips.nbs.rs/PDF/Smernice_Generator_Validator_latinica_feb2023.pdf
            url = 'https://nbs.rs/QRcode/api/qr/v1/gen/250'
            headers = { 'Content-Type': 'application/json' }
            response = requests.post(url, headers=headers, json=qr_data)
            print(f'{response=}')
            if response.status_code == 500:
                print(response.content)
                print(response.headers)
                response_data = response.json()
                if 'error_message' in response_data:
                    error_message = response_data['error_message']
                    print(f"Error message: {error_message}")

            if response.status_code == 200:
                qr_code_image = Image.open(io.BytesIO(response.content))
                qr_code_filename = f'qr_{i}.png'
                qr_code_image.save(os.path.join(project_folder, 'static', 'payment_slips', 'qr_code', qr_code_filename))
                qr_code_filepath = os.path.join(project_folder, 'static', 'payment_slips', 'qr_code', qr_code_filename)
                with open(qr_code_filepath, 'wb') as file:
                    file.write(response.content)
                qr_code_images.append(qr_code_filename)
            else:
                pass
            print(f'{qr_code_images=}')
    time.sleep(2)
    print (f'{data_list=}')
    print(f'{len(data_list)=}')
    # gen_file = uplatnice_gen(data_list, qr_code_images) #! prilagodi ovu funciju

    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            print(f'{font_path=}')
            self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    pdf = PDF()
    # pdf.add_page()
    printed_on_uplatnice = 0
    counter = 1
    for i, uplatnica in enumerate(data_list):
        print(f'{uplatnica=}')
        print(f'ulazni parametrii funkcije: {single=} {send=}')
        if not uplatnica['slanje_mejla_roditelju'] and not single:
            print('generisati sve uplatnice, OSIM onih koje se šalju roditelju na mejl!')
            pass #! ovo bi trebalo da preskoči elif i da nastavi u redu if counter % 3 == 1...
        elif single:
            print('odabrano da se generiše samo jedna uplatnica')
            pass
        else:
            continue
        # elif uplatnica['slanje_mejla_roditelju'] and not single:
        #     pass
        # elif not uplatnica['slanje_mejla_roditelju']:
        #     continue #! završava se ovde iteracija for loopa i počinje sledeća iteracija; donji kod neće biti aktiviran
        print(f'izašao iz IF petlje, red pred if petlju koja određuje u kojoj trećini će se generisati uplatnica')
        if counter % 3 == 1:
            print(f'prva trećina')
            pdf.add_page()
            y = 0
            y_qr = 50
            pdf.line(210/3, 10, 210/3, 237/3)
            pdf.line(2*210/3, 10, 2*210/3, 237/3)
        elif counter % 3 == 2:
            print(f'druga trećina')
            y = 99
            y_qr = 149
            pdf.line(210/3, 110, 210/3, 99+237/3)
            pdf.line(2*210/3, 110, 2*210/3, 99+237/3)
        elif counter % 3 == 0:
            print(f'treća trećina')
            y = 198
            y_qr = 248
            pdf.line(210/3, 210, 210/3, 198+237/3)
            pdf.line(2*210/3, 210, 2*210/3, 198+237/3)
        pdf.set_font('DejaVuSansCondensed', 'B', 16)
        pdf.set_y(y_qr)
        pdf.set_x(2*170/3)
        pdf.image(f'{project_folder}/static/payment_slips/qr_code/{qr_code_images[i]}' , w=25)
        pdf.set_y(y+8)
        pdf.cell(2*190/3,8, f"NALOG ZA UPLATU", new_y='LAST', align='R', border=0)
        pdf.cell(190/3,8, f"IZVEŠTAJ O UPLATI", new_y='NEXT', new_x='LMARGIN', align='R', border=0)
        pdf.set_font('DejaVuSansCondensed', '', 10)
        pdf.cell(63,4, f"Uplatilac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(57, 4, f'''{uplatnica['uplatilac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(63,4, f"Svrha uplate", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(57,4, f'''{uplatnica['svrha_uplate']}\r\n{''}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(63,4, f"Primalac", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
        pdf.multi_cell(57,4, f'''{uplatnica['primalac']}\r\n{''}''', new_y='NEXT', new_x='LMARGIN', align='L', border=1)
        pdf.cell(95,1, f"", new_y='NEXT', new_x='LMARGIN', align='L', border=0)
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
            print('if blok koji potvrđuje da je single')
            print(f'{uplatnica["uplatilac"]=}')
            file_name = f'uplatnica.pdf'
            pdf.output(path + file_name)
            if uplatnica['slanje_mejla_roditelju'] and send:
                print(f'poslat je mejl za {uplatnica["uplatilac"]}')
                send_mail(uplatnica, path, file_name)
                pdf = PDF()
                if counter % 3 != 1:
                # if counter % 3 != 1:
                    pdf.add_page()
            elif send:
                print(f'NIJE poslat mejl za {uplatnica["uplatilac"]}')
                pdf = PDF()
                if counter % 3 != 1:
                    pdf.add_page()
        else:
            printed_on_uplatnice += 1
    print(f'{printed_on_uplatnice=}')
    if not single:
        if printed_on_uplatnice == 0:
            # nije bilo štamše na uplatnicama
            pdf = PDF()
            pdf.add_page()
            pdf.set_font('DejaVuSansCondensed', 'B', 16)
            pdf.multi_cell(0, 20, 'Svim zaduženim učenicima je aktivirana opcija slanja generisanih uplatnica putem e-maila. \n Ne zaboravite da pošaljete mejlove roditeljima. \nMolimo Vas da ne štampate ovaj dokument.', align='C')
        file_name = f'uplatnice.pdf'
        pdf.output(path + file_name)


    #! briše QR kodove nakon dodavanja na uplatnice
    folder_path = f'{project_folder}/static/payment_slips/qr_code/'
    # Provjeri da li je putanja zaista direktorijum
    if os.path.isdir(folder_path):
        # Prolazi kroz sve fajlove u direktorijumu
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            # Provjeri da li je trenutni element fajl
            if os.path.isfile(file_path) and os.path.exists(file_path):
                # Obriši fajl
                os.remove(file_path)
                print(f"Fajl '{file_path}' je uspješno obrisan.")
        print("Svi QR kodovi su uspješno obrisani.")
    else:
        print("Navedena putanja nije direktorijum.")
    filename = f'{project_folder}static/payment_slips/uplatnice.pdf' #!

    
    return file_name


def gen_report_student_list(export_data, start_date, end_date, filtered_records, service_id, razred, odeljenje):
    school = School.query.first()
    service_name = ''
    for record in filtered_records:
        if record.service_item_id == int(service_id):
            service_name = record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
            continue
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            print(f'{font_path=}')
            self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    
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
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            print(f'{font_path=}')
            self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    
        def header(self):
            # Postavite font i veličinu teksta za zaglavlje
            self.set_font('DejaVuSansCondensed', 'B', 12)
            
            # Dodajte informacije o školi
            self.cell(0, 6, f'{school.school_name}', 0, 1, 'R')
            self.cell(0, 6, f' {school.school_address}', 0, 1, 'R')
            self.cell(0, 6, f'{school.school_zip_code} {school.school_city}', 0, 1, 'R')
    
    pdf = PDF()
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

    print(f'{zaduzenje=} {uplate=} {saldo=}')
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
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            print(f'{font_path=}')
            self.add_font('DejaVuSansCondensed', '', font_path, uni=True)
            self.add_font('DejaVuSansCondensed', 'B', font_path_B, uni=True)
    
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
            pdf.cell(0, 5, f'Period: od {start_date.strftime("%d.%m.%Y.")} do {end_date.strftime("%d.%m.%Y.")}', 0, 1, 'L')  # Promenite "new_y" u 0 i uklonite "border"
            pdf.cell(40, 8, '', 0, 1, 'R')
            
            
            pdf.set_fill_color(200, 200, 200)  # Postavite svetlo sivu boju za ćelije
            pdf.set_font('DejaVuSansCondensed', 'B', 12)
            pdf.cell(95, 8, f'Odeljenski starešina', 1, 0, 'L', 1)
            pdf.cell(30, 8, f'Zaduženje', 1, 0, 'C', 1)
            pdf.cell(30, 8, f'Uplate', 1, 0, 'C', 1)
            pdf.cell(30, 8, f'Saldo', 1, 1, 'C', 1)
            
    
    pdf = PDF()
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
