import xml.etree.ElementTree as ET
from datetime import datetime
from flask import  render_template, url_for, flash, redirect, request, abort
from flask import Blueprint
from flask_login import login_required, current_user
from onetouch import db, bcrypt
from onetouch.models import Teacher, Student, ServiceItem, StudentDebt, StudentPayment, School, TransactionRecord

transactions = Blueprint('transactions', __name__)


@transactions.route('/student_debts', methods=['POST', 'GET'])
@login_required
def student_debts():
    teachers = Teacher.query.all()
    students = Student.query.all()
    service_items = ServiceItem.query.all()
    print(f'{service_items=}')
    print(f'{teachers=}')
    return render_template('student_debts.html', students=students, service_items=service_items, teachers=teachers)

#! Ajax
@transactions.route('/get_service_items', methods=['POST'])
def get_service_items():
    service_item_class = request.form.get('classes', 0, type=int)
    print(f'from AJAX service items: {service_item_class=}')
    options = [(0, "Selektujte uslugu")]
    service_items = ServiceItem.query.filter_by(archived=False).all()
    for service_item in service_items:
        if str(service_item_class) in service_item.service_item_class:
            options.append((service_item.id, service_item.service_item_service.service_name + " - " + service_item.service_item_name))
            print(options)
    html = ''
    for option in options:
        html += '<option value="{0}">{1}</option>'.format(option[0], option[1])
    return html


@transactions.route('/get_installments', methods=['POST'])
def get_installments():
    print(request.form)
    service_item_id = int(request.form.get('installments'))
    print(f'from AJAX installments: {service_item_id=}')
    options = [(0, "Selektujte ratu")]
    service_item = ServiceItem.query.get_or_404(service_item_id)
    
    if service_item_id == 1:
        options.append((1, f'Rata 1'))
        installment_attr = f'price'
        installment_option = getattr(service_item, installment_attr)
        print(f'{installment_option=}')
    else:
        for i in range(1, service_item.installment_number + 1):
            options.append((i, f'Rata {i}'))
            installment_attr = f'installment_{i}'
            installment_option = getattr(service_item, installment_attr)
            print(f'{installment_option=}')
    
    html = ''
    for option in options:
        html += '<option value="{0}">{1}</option>'.format(option[0], option[1])
    return html


@transactions.route('/get_installment_values', methods=['POST'])
def get_installment_values():
    print(request.form)
    service_item_id = int(request.form.get('installments'))
    installment_number = int(request.form.get('installment_values'))
    print(f'{service_item_id=} {installment_number=}')
    service_item = ServiceItem.query.get_or_404(service_item_id)
    print(service_item)
    if service_item.installment_number == 1:
        installment_attr = 'price'
    else:
        installment_attr = f'installment_{installment_number}'
    installment_value_result = {"result" : getattr(service_item,installment_attr)} 
    print(f'{installment_value_result=}')
    return installment_value_result


@transactions.route('/submit_records', methods=['post'])
def submit_records():
    data = request.get_json()
    print(f'{data=}')
    print(f'{type(data)=}')
    
    service_item_id = int(data['service_item'])
    debt_class = int(data['class'])
    debt_section = None if data['section'] == '' else int(data['section'])
    installment_number = int(data['installment'])
    print(f'{service_item_id=}, {debt_class=}, {debt_section=}, {installment_number=}')
    
    existing_debt = StudentDebt.query.filter_by(
        service_item_id=service_item_id,
        debt_class=debt_class,
        debt_section=debt_section,
        installment_number=installment_number
    ).first()
    
    if existing_debt:
        print(f'Već postoji ovo zaduženje: {existing_debt.id}. Ukoliko ima potrebe, možete editovati podatke.')
        flash(f'Već postoji ovo zadušenje: {existing_debt.id}. Ukoliko ima potrebe, možete editovati podatke.', 'info')
        return str(existing_debt.id)
    
    if len(data['records']) == 0:
        print('Nema studenta')
        return 'Nema studenta'
        
    
    new_debt = StudentDebt(student_debt_date = datetime.now(),
                            service_item_id = service_item_id,
                            debt_class = debt_class,
                            debt_section = debt_section,
                            installment_number=installment_number)
    
    print(f'{new_debt=}')
    db.session.add(new_debt)
    db.session.commit()
    
    print(f'{new_debt.id=}')
    
    
    
    student_debt_id = new_debt.id
    student_payment_id = None
    for i in range(len(data['records'])):
        student_id = data['records'][i]['student_id']
        #! service_item_id = ima već definisano na početku funkcije, ako bude trebalo napiši kod za to
        student_debt_installment_number = int(data['installment'])
        print(f'{student_debt_installment_number=}')
        student_debt_amount = data['records'][i]['amount']
        studetn_debt_installment_value = getattr(ServiceItem.query.get_or_404(service_item_id), f'installment_{student_debt_installment_number}')
        student_debt_discount = data['records'][i]['discount']
        print(f'{type(student_debt_amount)=}, {type(studetn_debt_installment_value)=}, {type(student_debt_discount)=}')
        print(f'{student_debt_amount=}, {studetn_debt_installment_value=}, {student_debt_discount=}')
        student_debt_total = student_debt_amount * studetn_debt_installment_value - student_debt_discount
        print(f'{student_debt_id=}, {student_payment_id=}, {student_id=}, {service_item_id=}, {student_debt_installment_number=}, {student_debt_amount=}')
        print(f'{studetn_debt_installment_value=}, {student_debt_discount=}, {student_debt_total=}')
        new_record = TransactionRecord(student_debt_id = student_debt_id,
                                        student_payment_id = student_payment_id,
                                        student_id = student_id,
                                        service_item_id = service_item_id,
                                        student_debt_installment_number = student_debt_installment_number,
                                        student_debt_amount = student_debt_amount,
                                        studetn_debt_installment_value = studetn_debt_installment_value,
                                        student_debt_discount = student_debt_discount,
                                        student_debt_total = student_debt_total)
        db.session.add(new_record)
        db.session.commit()
    
    return str(student_debt_id)


@transactions.route('/debts_archive_list', methods=['get', 'post'])
def debts_archive_list():
    debts = StudentDebt.query.all()
    print(f'{debts=}')
    return render_template('debts_archive_list.html', debts=debts)


@transactions.route('/debt_archive/<int:debt_id>', methods=['get', 'post'])
def debt_archive(debt_id):
    debt = StudentDebt.query.get_or_404(debt_id)
    teacher = Teacher.query.filter_by(teacher_class=debt.debt_class).filter_by(teacher_section=debt.debt_section).first()
    records = TransactionRecord.query.filter_by(student_debt_id=debt_id).all()
    print(f'{records=}')
    return render_template('debt_archive.html', 
                            records=records, 
                            debt=debt, 
                            teacher=teacher,
                            legend=f"Pregled zadušenja: {debt.id}")


@transactions.route('/posting_payment', methods=['POST', 'GET'])
def posting_payment():
    if request.method == 'POST' and ('submitBtnImportData' in request.form):
        file = request.files['fileInput']
        if file.filename == '':
            error_mesage = 'Niste izabrali XML fajl'
            print('niste izabrali XML fajl.')
            flash(error_mesage, 'danger')
            return render_template('posting_payment.html', error_mesage=error_mesage)
        tree = ET.parse(file)
        root = tree.getroot()

        racun_skole = School.query.get(1).school_bank_account
        datum_izvoda_element = root.find('.//DatumIzvoda').text
        racun_izvoda_element = root.find('.//RacunIzvoda').text
        broj_izvoda_element = root.find('.//BrojIzvoda').text
        iznos_potrazuje_element = root.find('.//IznosPotrazuje').text
        # Pronalaženje broja pojavljivanja elementa <Stavka>
        broj_pojavljivanja = len(root.findall('.//Stavka'))
        
        existing_payments = StudentPayment.query.filter_by(
                                                payment_date=datetime.strptime(datum_izvoda_element, '%d.%m.%Y'), #todo: podesiti filtere datetime.strptime(datum_izvoda_element, '%d.%m.%Y')
                                                statment_nubmer=int(broj_izvoda_element)).first() #todo: podesiti filtere
        print(f'{existing_payments=}')
        if existing_payments:
            print('postoji vec uplata u bazi')
            error_mesage = f'Izabrani izvod ({broj_izvoda_element}) već postoji u bazi.'
            flash(error_mesage, 'danger')
            # return render_template('posting_payment.html', error_mesage=error_mesage) #todo izmeniti atribute u render_template tako da se učitaju stavke i error mesage

        # Ispis rezultata
        print("Broj pojavljivanja elementa <Stavka>: ", broj_pojavljivanja)
        print(f'{datum_izvoda_element=}')
        print(f'{broj_izvoda_element=}')
        print(f'{iznos_potrazuje_element=}')
        print(f'{racun_skole=}, {racun_izvoda_element=}')
        if racun_izvoda_element != racun_skole:
            error_mesage = f'Računi nisu isti. Račun izvoda: {racun_izvoda_element.text}, račun škole: {racun_skole}. Izaberite odgovarajući XML fajl i pokušajte ponovo.'
            print('racuni nisu isti')
            flash(error_mesage, 'danger')
            return render_template('posting_payment.html', error_mesage=error_mesage)

        stavke = []
        for stavka in root.findall('Stavka'):
            podaci = {}
            podaci['RacunZaduzenja'] = stavka.find('RacunZaduzenja').text
            podaci['NazivZaduzenja'] = stavka.find('NazivZaduzenja').text
            podaci['MestoZaduzenja'] = stavka.find('MestoZaduzenja').text
            podaci['IzvorInformacije'] = stavka.find('IzvorInformacije').text
            podaci['ModelPozivaZaduzenja'] = stavka.find('ModelPozivaZaduzenja').text
            podaci['PozivZaduzenja'] = stavka.find('PozivZaduzenja').text
            podaci['SifraPlacanja'] = stavka.find('SifraPlacanja').text
            podaci['Iznos'] = stavka.find('Iznos').text
            podaci['RacunOdobrenja'] = stavka.find('RacunOdobrenja').text
            podaci['NazivOdobrenja'] = stavka.find('NazivOdobrenja').text
            podaci['MestoOdobrenja'] = stavka.find('MestoOdobrenja').text
            podaci['ModelPozivaOdobrenja'] = stavka.find('ModelPozivaOdobrenja').text
            podaci['PozivOdobrenja'] = stavka.find('PozivOdobrenja').text
            podaci['SvrhaDoznake'] = stavka.find('SvrhaDoznake').text
            podaci['DatumValute'] = stavka.find('DatumValute').text
            podaci['PodatakZaReklamaciju'] = stavka.find('PodatakZaReklamaciju').text
            podaci['VremeUnosa'] = stavka.find('VremeUnosa').text
            podaci['VremeIzvrsenja'] = stavka.find('VremeIzvrsenja').text
            podaci['StatusNaloga'] = stavka.find('StatusNaloga').text
            podaci['TipSloga'] = stavka.find('TipSloga').text

            stavke.append(podaci)
        print(f'{stavke=}')
        flash('Uspešno je učitan XML fajl.', 'success')
        return render_template('posting_payment.html', legend="Knjiženje uplata",
                                stavke=stavke,
                                datum_izvoda_element=datum_izvoda_element,
                                broj_izvoda_element=broj_izvoda_element,
                                iznos_potrazuje_element=iznos_potrazuje_element,
                                broj_pojavljivanja=broj_pojavljivanja)
    if request.method == 'POST' and ('submitBtnSaveData' in request.form):
        print(f'pritisnuto je dugme sačuvajte irsknjićite uplate')
        # Dohvaćanje vrijednosti iz obrasca
        payment_date = datetime.strptime(request.form['payment_date'], '%d.%m.%Y')
        statment_nubmer = int(request.form['statment_nubmer'])
        total_payment_amount = float(request.form['total_payment_amount'].replace(',', '.'))
        number_of_items = int(request.form['number_of_items'])
        print(f'{payment_date=}')
        print(f'{statment_nubmer=}')
        print(f'{total_payment_amount=}')
        print(f'{number_of_items=}')
        existing_payments = StudentPayment.query.filter_by(
                                                payment_date=payment_date,
                                                statment_nubmer=statment_nubmer).first()
        print(f'{existing_payments=}')
        if existing_payments:
            print('postoji vec uplata u bazi')
            error_mesage = f'Uplata za dati datum ({payment_date}) i broj računa ({statment_nubmer}) već postoji u bazi. Izaberite novi XML fajl i pokušajte ponovo.'
            flash(error_mesage, 'danger')
            return render_template('posting_payment.html', error_mesage=error_mesage)
        # Spremanje podataka u bazu
        new_payment = StudentPayment(
            payment_date=payment_date,
            statment_nubmer=statment_nubmer,
            total_payment_amount=total_payment_amount,
            number_of_items=number_of_items
        )
        db.session.add(new_payment)
        db.session.commit()
        # print('dodato u db - proveri')
        # print(f'{new_payment.id=}')
        
        iznosi = request.form.getlist('iznos')
        pozivi_na_broj = request.form.getlist('poziv_na_broj')
        svrha_uplate = request.form.getlist('svrha_uplate')
        print(f'{iznosi=}')
        print(f'{pozivi_na_broj=}')
        print(f'{svrha_uplate=}')
        records = []
        for i in range(len(iznosi)):
            records.append({
                    'iznos': iznosi[i],
                    'poziv_na_broj': pozivi_na_broj[i],
                    'svrha_uplate': svrha_uplate[i]
                })
        print(f'{records=}')
        
        for record in records:
            purpose_of_payment = record['svrha_uplate']
            reference_number = record['poziv_na_broj']
            student_id = record['poziv_na_broj'][:4]
            service_item_id = record['poziv_na_broj'][-3:]
            student_debt_total = float(record['iznos'].replace(',', '.'))
            new_record = TransactionRecord(student_debt_id = None,
                                            student_payment_id = new_payment.id,
                                            student_id = student_id,
                                            service_item_id = service_item_id,
                                            student_debt_installment_number = None,
                                            student_debt_amount = None,
                                            studetn_debt_installment_value = None,
                                            student_debt_discount = None,
                                            student_debt_total = student_debt_total,
                                            purpose_of_payment=purpose_of_payment,
                                            reference_number=reference_number)
            print(f'{new_record.student_id=}')
            print(f'{new_record.service_item_id=}')
            print(f'{new_record.student_debt_total=}')
            print(f'{new_record.purpose_of_payment=}')
            print(f'{new_record.reference_number=}')
            db.session.add(new_record)
            db.session.commit()
        
    return render_template('posting_payment.html', legend="Knjiženje uplata")