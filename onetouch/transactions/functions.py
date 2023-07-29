import requests, os, io, time
from PIL import Image
from fpdf import FPDF


def export_payment_stats(data):
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            self.add_font('DejaVuSansCondensed', '', './onetouch/static/fonts/DejaVuSansCondensed.ttf', uni=True)
            self.add_font('DejaVuSansCondensed', 'B', './onetouch/static/fonts/DejaVuSansCondensed-Bold.ttf', uni=True)
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('DejaVuSansCondensed', 'B', 24)
    pdf.set_y(10)
    pdf.cell(0, 10, f'Izvod podataka uplatnice: {data[0]["payment_id"]}', new_y='NEXT', new_x='LMARGIN', align='C', border=0)
    pdf.cell(0, 10, '', new_y='NEXT', new_x='LMARGIN', align='C', border=0)
    pdf.set_font('DejaVuSansCondensed', 'B', 14)
    pdf.cell(50, 10, 'ID usluge', new_y='LAST', align='C', border=1)
    pdf.cell(90, 10, 'Detalji usluge', new_y='LAST', align='C', border=1)
    pdf.cell(50, 10, 'Ukupan iznos', new_y='NEXT', new_x='LMARGIN', align='C', border=1)
    pdf.set_font('DejaVuSansCondensed', '', 14)
    for record in data:
        pdf.cell(50, 10, f'{record["service_item_id"]:03d}', new_y='LAST', align='C', border=1)
        pdf.cell(90, 10, f'{record["name"]}', new_y='LAST', align='C', border=1)
        pdf.cell(50, 10, f'{record["sum_amount"]}', new_y='NEXT', new_x='LMARGIN', align='C', border=1)

    path = "onetouch/static/payment_slips/"
    file_name = f'export.pdf'
    pdf.output(path + file_name)
    return file_name

def uplatnice_gen(records, purpose_of_payment, school_info, school):
    data_list = []
    qr_code_images = []
    
    for i, record in enumerate(records):
        if record.student_debt_total > 0:
            new_data = {
                'uplatilac': record.transaction_record_student.student_name + ' ' + record.transaction_record_student.student_surname,
                'svrha_uplate': purpose_of_payment,
                'primalac': school_info,
                'sifra_placanja': 189,
                'valuta': 'RSD', #! proveri da li je zbog QR koda potrebno drugačije definisati valutu
                'iznos': record.student_debt_total,
                'racun_primaoca': school.school_bank_account,
                'model': '', #! proveriti koji je model zbog QR koda 
                'poziv_na_broj': f"{record.student_id:04d}-{record.service_item_id:03d}",
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
                "S": new_data['svrha_uplate'],
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
                qr_code_image.save(os.path.join('onetouch/static/payment_slips/qr_code/', qr_code_filename))
                qr_code_filepath = os.path.join('onetouch/static/payment_slips/qr_code/', qr_code_filename)
                with open(qr_code_filepath, 'wb') as file:
                    file.write(response.content)
                qr_code_images.append(qr_code_filename)
            else:
                pass
            print(f'{qr_code_images=}')
    time.sleep(3)
    print (f'{data_list=}')
    print(f'{len(data_list)=}')
    # gen_file = uplatnice_gen(data_list, qr_code_images) #! prilagodi ovu funciju
    class PDF(FPDF):
        def __init__(self, **kwargs):
            super(PDF, self).__init__(**kwargs)
            self.add_font('DejaVuSansCondensed', '', './onetouch/static/fonts/DejaVuSansCondensed.ttf', uni=True)
            self.add_font('DejaVuSansCondensed', 'B', './onetouch/static/fonts/DejaVuSansCondensed-Bold.ttf', uni=True)
    pdf = PDF()
    # pdf.add_page()
    counter = 1
    for i, uplatnica in enumerate(data_list):
        print(f'{uplatnica=}')
        if counter % 3 == 1:
            pdf.add_page()
            y = 0
            y_qr = 50
            pdf.line(210/3, 10, 210/3, 237/3)
            pdf.line(2*210/3, 10, 2*210/3, 237/3)
        elif counter % 3 == 2:
            y = 99
            y_qr = 149
            pdf.line(210/3, 110, 210/3, 99+237/3)
            pdf.line(2*210/3, 110, 2*210/3, 99+237/3)
        elif counter % 3 == 0:
            y = 198
            y_qr = 248
            pdf.line(210/3, 210, 210/3, 198+237/3)
            pdf.line(2*210/3, 210, 2*210/3, 198+237/3)
        pdf.set_font('DejaVuSansCondensed', 'B', 16)
        pdf.set_y(y_qr)
        pdf.set_x(2*170/3)
        pdf.image(f'onetouch/static/payment_slips/qr_code/{qr_code_images[i]}' , w=25)
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
    path = "onetouch/static/payment_slips/"
    file_name = f'uplatnice.pdf'
    pdf.output(path + file_name)
    
    
    
    #! briše QR kodove nakon dodavanja na uplatnice
    folder_path = 'onetouch/static/payment_slips/qr_code/'
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
        print("Svi fajlovi su uspješno obrisani.")
    else:
        print("Navedena putanja nije direktorijum.")
    filename = f'static/payment_slips/uplatnice.pdf' #!

    
    return file_name