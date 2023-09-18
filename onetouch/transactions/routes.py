import json
import requests, os, io
import xml.etree.ElementTree as ET
from PIL import Image
from datetime import datetime, date, timedelta
from flask import  render_template, url_for, flash, redirect, request, send_file, jsonify
from flask import Blueprint
from flask_login import login_required, current_user
from onetouch import db, bcrypt
from onetouch.models import Teacher, Student, ServiceItem, StudentDebt, StudentPayment, School, TransactionRecord, User
from onetouch.transactions.functions import uplatnice_gen, export_payment_stats

transactions = Blueprint('transactions', __name__)

def load_user(user_id):
    return User.query.get(int(user_id))


# Ova funkcija će proveriti da li je korisnik ulogovan pre nego što pristupi zaštićenoj ruti
@transactions.before_request
def require_login():
    if request.endpoint and not current_user.is_authenticated:
        return redirect(url_for('users.login'))


@transactions.route('/student_debts', methods=['POST', 'GET'])
@login_required
def student_debts():
    teachers = Teacher.query.all()
    students = Student.query.all()
    service_items = ServiceItem.query.all()
    print(f'{service_items=}')
    print(f'{teachers=}')
    return render_template('student_debts.html', 
                            legend = 'Zaduživanje učenika',
                            title = 'Zaduživanje učenika',
                            students=students, 
                            service_items=service_items, 
                            teachers=teachers)

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
    if service_item.service_item_service.payment_per_unit == 'kom':
        komadno = True
    else:
        komadno = False
    
    print(f'{komadno=}')
    
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
    return jsonify(html=html, komadno=komadno)


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
    
    if 'service_item' in data: 
        print('dodavanje novog zaduženja')
        service_item_id = int(data['service_item'])
        debt_class = int(data['class'])
        debt_section = None if data['section'] == '' else int(data['section'])
        installment_number = int(data['installment'])
        purpose_of_payment = data['purpose_of_payment'] #todo: uvezi iz frontenda uz pomoć ajaksa preko data objekta :)
        print(f'{service_item_id=}, {debt_class=}, {debt_section=}, {installment_number=}')
        
        existing_debt = StudentDebt.query.filter_by(
            service_item_id=service_item_id,
            debt_class=debt_class,
            debt_section=debt_section,
            installment_number=installment_number
        ).first()
        
        if existing_debt:
            print(f'Već postoji ovo zaduženje: {existing_debt.id}. Ukoliko ima potrebe, možete editovati podatke.')
            flash(f'Već postoji ovo zaduženje: {existing_debt.id}. Ukoliko ima potrebe, možete editovati podatke.', 'info')
            return str(existing_debt.id)
        
        if len(data['records']) == 0:
            print('Nema zaduženih studenta')
            return 'Nema zaduženih studenta'
            
        
        new_debt = StudentDebt(student_debt_date = datetime.now(),
                                service_item_id = service_item_id,
                                debt_class = debt_class,
                                debt_section = debt_section,
                                installment_number=installment_number,
                                purpose_of_payment=purpose_of_payment)
        
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
            print(f'prečekiranje pred dodele vrednosti za "studetn_debt_installment_value": {service_item_id=}; {ServiceItem.query.get_or_404(service_item_id)}')
            studetn_debt_installment_value = getattr(ServiceItem.query.get_or_404(service_item_id), f'installment_{student_debt_installment_number}')
            print(f'{studetn_debt_installment_value=}')
            student_debt_discount = float(data['records'][i]['discount'])
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
        flash(f'Zaduženje {student_debt_id} je uspešno dodato!', 'success')
        return str(student_debt_id)

    elif 'student_debt_id' in data:
        print('izmena postojećeg zaduženja')
        student_debt_id = int(data['student_debt_id'])
        purpose_of_payment = data['purpose_of_payment']
        print(f'{student_debt_id=}, {purpose_of_payment=}')
        debt = StudentDebt.query.get_or_404(student_debt_id)
        debt.purpose_of_payment = purpose_of_payment
        db.session.commit()
        
        for i in range(len(data['records'])):
            student_id = data['records'][i]['student_id']
            student_debt_amount = data['records'][i]['amount']
            student_debt_discount = data['records'][i]['discount']
            record_for_edit = TransactionRecord.query.filter(
                TransactionRecord.student_debt_id == student_debt_id,
                TransactionRecord.student_id == student_id).first()
            student_debt_total = student_debt_amount * record_for_edit.studetn_debt_installment_value - student_debt_discount
            print(f'{record_for_edit=}')
            record_for_edit.student_debt_amount = student_debt_amount
            record_for_edit.student_debt_discount = student_debt_discount
            record_for_edit.student_debt_total = student_debt_total
            db.session.commit()
        flash(f'Zaduženje {student_debt_id} je uspešno izmenjeno!', 'success')
        return str(student_debt_id)
    
    elif 'student_payment_id' in data: #! izmena pregleda izvoda (payment_archive/<int:>)
        print('izmena postojećeg izvoda')
        transaction_records = TransactionRecord.query.all()
        all_reference_numbers = [f'{record.student_id:04d}-{record.service_item_id:03d}' for record in transaction_records if record.student_debt_id is not None]
        all_reference_numbers.append('0000-000')
        student_payment_id = int(data['student_payment_id'])
        
        number_of_errors = 0
        student_ids = [student.id for student in Student.query.all()]
        service_item_ids = [service_item.id for service_item in ServiceItem.query.all()]
        for i in range(len(data['records'])):
            record_id = data['records'][i]['record_id']
            student_id = data['records'][i]['student_id']
            service_item_id = data['records'][i]['service_item_id']
            # payment_error = False
            print(f'{student_ids=}')
            print(f'{service_item_ids=}')
            print(f'{student_id=}, {service_item_id=}')
            if (student_id not in student_ids) or (service_item_id not in service_item_ids):
                student_id = 1
                service_item_id = 0
                print(f'promenjeni su student_id i service item id!!!')
            record_for_edit = TransactionRecord.query.get_or_404(record_id)
            print(f'{record_for_edit=}')
            print(f'{record_id=}, {student_id=}, {service_item_id=},')
            record_for_edit.student_id = student_id #if student_id in [record.student_id for record in transaction_records] else 0
            record_for_edit.service_item_id = service_item_id #if service_item_id in [record.service_item_id for record in transaction_records] else 0
            
            reference_number = f"{student_id:04d}-{service_item_id:03d}"
            if reference_number == '0001-000':
                number_of_errors += 1
                record_for_edit.payment_error = True
            elif reference_number in all_reference_numbers:
                print(f'{reference_number=} {all_reference_numbers=}')
                print('validan poziv na broj! dodaj kod za ažuriranje podatka u db!')
                record_for_edit.payment_error = False
            else:
                print('nije validan poziv na broj! dodaj kod za ažuriranje podataka u db!')
                print(f'poziv na broj: {reference_number=} ne postoji u listi poziva na broj: {all_reference_numbers=}')
                number_of_errors += 1
                record_for_edit.payment_error = True
            print(f'broj grešaka: {number_of_errors}')
            db.session.commit()
            
        payment = StudentPayment.query.get_or_404(student_payment_id)
        #! ideja je da se doda još jedan atribut za klasu StudentPayment u kome će se skladištiti podatak ukoliko ima greške u uplatnicama
        #! ako ima greške onda se naznači nekako red sa greškom
        payment.number_of_errors = number_of_errors
        db.session.commit()
        flash('Uspešno ste izmenili uplate.','success')
        return str(student_payment_id)
        
    
    


@transactions.route('/debts_archive_list', methods=['get', 'post'])
def debts_archive_list():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date is None or end_date is None:
        start_date = date.today().replace(day=1, month=1).isoformat()
        end_date = date.today().isoformat()
    print(f'{start_date=}, {end_date=}')
    debts = StudentDebt.query.filter(
            (StudentDebt.student_debt_date >= start_date) &
            (StudentDebt.student_debt_date <= (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).isoformat()) #! prvo se end_date prevede u datum sa satima, pa im se doda jedan dan pa se vrati u string...
        ).all()
    print(f'{debts=}')
    return render_template('debts_archive_list.html', 
                            debts=debts,
                            start_date=start_date,
                            end_date=end_date,
                            legend="Arhiva naloga")

@transactions.route('/payments_archive_list', methods=['get', 'post'])
def payments_archive_list():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date is None or end_date is None:
        start_date = date.today().replace(day=1, month=1).isoformat()
        end_date = date.today().isoformat()
    payments = StudentPayment.query.filter(
        StudentPayment.payment_date.between(start_date, (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).isoformat())).all() #! prvo se end_date prevede u datum sa satima, pa im se doda jedan dan pa se vrati u string...
    print(f'{payments=}')
    return render_template('payments_archive_list.html', 
                            payments=payments,
                            start_date=start_date,
                            end_date=end_date,
                            legend="Arhiva izvoda") #todo napravi html fajl


@transactions.route('/single_payment_slip/<int:record_id>', methods=['get', 'post'])
def single_payment_slip(record_id):
    records = []
    record = TransactionRecord.query.get_or_404(record_id)
    print(f'{record=}') #! uvek mora da bude samo jedan record
    debt = StudentDebt.query.get_or_404(record.student_debt_id)
    purpose_of_payment = debt.purpose_of_payment
    school = School.query.first()
    school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
    records.append(record)
    print(f'{records=}')
    #! promenjiva single koja indikuje da se generiše samo jedna uplatnica 'uplatnica.pdf'
    single = True
    send = False
    file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
    file_path = f'static/payment_slips/{file_name}'
    print(f'{file_path=}')
    return send_file(file_path, as_attachment=False)


@transactions.route('/debt_archive/<int:debt_id>', methods=['GET', 'POST'])
def debt_archive(debt_id):
    debt = StudentDebt.query.get_or_404(debt_id)
    purpose_of_payment = debt.purpose_of_payment
    print(f'{purpose_of_payment=}')
    school = School.query.first()
    school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
    teacher = Teacher.query.filter_by(teacher_class=debt.debt_class).filter_by(teacher_section=debt.debt_section).first()
    
    records = TransactionRecord.query.filter_by(student_debt_id=debt_id).all()
    print(f'{records=}')
    
    single = False
    send = False
    file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)

    return render_template('debt_archive.html', 
                            records=records, 
                            debt=debt, 
                            teacher=teacher,
                            purpose_of_payment=purpose_of_payment,
                            legend=f"Pregled zaduženja: {debt.id}",
                            title="Pregled zaduženja")


@transactions.route('/send_payment_slips/<int:debt_id>', methods=['get', 'post'])
def send_payment_slips(debt_id):
    debt = StudentDebt.query.get_or_404(debt_id)
    purpose_of_payment = debt.purpose_of_payment
    school = School.query.first()
    school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city

    records = TransactionRecord.query.filter_by(student_debt_id=debt_id).all()
    single = True
    send = True
    file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
    flash('Uspešno ste poslali mejlove roditeljima.', 'success')
    return redirect(url_for('transactions.debt_archive', debt_id=debt_id))


@transactions.route('/send_single_payment_slip/<int:record_id>', methods=['get', 'post'])
def send_single_payment_slip(record_id):
    debt_id = TransactionRecord.query.get_or_404(record_id).student_debt_id
    debt = StudentDebt.query.get_or_404(debt_id)
    purpose_of_payment = debt.purpose_of_payment
    school = School.query.first()
    school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
    records =[]
    record = TransactionRecord.query.get_or_404(record_id)
    records.append(record)
    single = True
    send = True
    file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
    flash('Uspešno ste poslali mejl roditelju.', 'success')
    return redirect(url_for('transactions.debt_archive', debt_id=debt_id))


# @transactions.route('/send_single_payment_slip/<int:record_id>', methods=['get', 'post'])
# def send_single_payment_slip(record_id):
#     debt_id = TransactionRecord.query.get_or_404(record_id).student_debt_id
#     debt = StudentDebt.query.get_or_404(debt_id)
#     purpose_of_payment = debt.purpose_of_payment
#     school = School.query.first()
#     school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
#     records =[]
#     record = TransactionRecord.query.get_or_404(record_id)
#     records.append(record)
#     send = True
#     single=True
#     file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
#     flash('Uspešno ste poslali mejl roditelju.', 'success')
#     return redirect(url_for('transactions.debt_archive', debt_id=debt_id))


@transactions.route('/debt_archive_delete/<int:debt_id>', methods=['get', 'post'])
def debt_archive_delete(debt_id):
    records = TransactionRecord.query.filter_by(student_debt_id=debt_id).all()
    for record in records:
        db.session.delete(record)
        db.session.commit()
    debt = StudentDebt.query.get_or_404(debt_id)
    db.session.delete(debt)
    db.session.commit()
    flash('Uplata {debt_id} je uspešno obrisana, kao i sva zaduženja učenika iz te uplate.', 'success')
    return redirect(url_for('transactions.debts_archive_list'))


@transactions.route('/payment_archive/<int:payment_id>', methods=['get', 'post'])
def payment_archive(payment_id):
    payment = StudentPayment.query.get_or_404(payment_id)
    records = TransactionRecord.query.filter_by(student_payment_id=payment_id).all()
    students = Student.query.all()
    students_data = [
            {
                'student_id': 0,
                'student_name': "ignorisana",
                'student_surname': "uplata",
                
            }
        ]
    for student in students:
        student_data = {
            'student_id': student.id,
            'student_name': student.student_name,
            'student_surname': student.student_surname,
            
        }
        students_data.append(student_data)
    services = ServiceItem.query.all()
    services_data = [{
            'service_id': 0,
            'service_item_name': "",
            'service_debt': "",
        }]
    for service in services:
        service_data = {
            'service_id': service.id,
            'service_item_name': service.service_item_name,
            'service_debt': service.service_item_service.service_name,
        }
        services_data.append(service_data)
    
    print(f'{records=}')
    unique_service_item_ids = []
    for record in records:
        if record.service_item_id not in unique_service_item_ids:
            unique_service_item_ids.append(record.service_item_id)
    print(f'{unique_service_item_ids=}')
    export_data = []
    record_data = {}
    for unique_service_item_id in unique_service_item_ids:
        # Filtrirajte zapise samo za trenutni unique_service_item_id
        filtered_records = [record for record in records if record.service_item_id == unique_service_item_id]
        print(f'{filtered_records=}')
        # Sabiranje svih vrednosti student_debt_total za trenutni unique_service_item_id
        sum_amount = sum(record.student_debt_total for record in filtered_records)
        
        # Kreiranje record_data za trenutni unique_service_item_id
        record_data = {
            'payment_id': payment.id,
            'service_item_id': unique_service_item_id,
            'sum_amount': sum_amount,
        }
        print(f'{filtered_records[0].service_item_id=}')
        if filtered_records[0].transaction_record_service_item is not None:
            record_data['name'] = filtered_records[0].transaction_record_service_item.service_item_service.service_name + ' - ' + filtered_records[0].transaction_record_service_item.service_item_name
        else:
            record_data['name'] = 'Greška'
        export_data.append(record_data)
        
        gen_file = export_payment_stats(export_data)
        print(f'{gen_file=}')
        print(f'{record_data=}')
    print(f'{export_data=}')
    return render_template('payment_archive.html', 
                            records=records, 
                            payment=payment,
                            students=json.dumps(students_data),
                            services=json.dumps(services_data),
                            export_data = export_data,
                            legend=f"Pregled izvoda: {payment.id}")


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
        # spisak svih izvoda koji postoje u data bazi
        transaction_records = TransactionRecord.query.all()
        all_reference_numbers = [f'{record.student_id:04d}-{record.service_item_id:03d}' for record in transaction_records  if record.student_debt_id is not None]
        print(f'{all_reference_numbers=}')
        
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
            error_mesage = f'Računi nisu isti. Račun izvoda: {racun_izvoda_element}, račun škole: {racun_skole}. Izaberite odgovarajući XML fajl i pokušajte ponovo.'
            print('racuni nisu isti')
            flash(error_mesage, 'danger')
            return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata")

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
            podaci['PozivOdobrenja'] = stavka.find('PozivOdobrenja').text if stavka.find('PozivOdobrenja').text else "-" #! ako nije None onda preuzmi vrednost iz xml, akoj je None onda mu dodeli "-"
            podaci['SvrhaDoznake'] = stavka.find('SvrhaDoznake').text if stavka.find('SvrhaDoznake').text else "-" #! isti princip kao gornji red
            podaci['DatumValute'] = stavka.find('DatumValute').text
            podaci['PodatakZaReklamaciju'] = stavka.find('PodatakZaReklamaciju').text
            podaci['VremeUnosa'] = stavka.find('VremeUnosa').text
            podaci['VremeIzvrsenja'] = stavka.find('VremeIzvrsenja').text
            podaci['StatusNaloga'] = stavka.find('StatusNaloga').text
            podaci['TipSloga'] = stavka.find('TipSloga').text

            #! provera da li je poziv na broj validan
            if len(podaci['PozivOdobrenja']) == 7:
                # proverava da li je forma '0001001' i dodaje crtu tako da bude 0001-001
                formated_poziv_odobrenja = f"{podaci['PozivOdobrenja'][:4]}-{podaci['PozivOdobrenja'][4:]}"
                if formated_poziv_odobrenja in all_reference_numbers:
                    podaci['Validnost'] = True
                else:
                    podaci['Validnost'] = False
            elif len(podaci['PozivOdobrenja']) == 8:
                # proverava da li je forma '0001-001'
                if podaci['PozivOdobrenja'] in all_reference_numbers:
                    podaci['Validnost'] = True
                else:
                    podaci['Validnost'] = False
            else:
                # nije dobar poziv na broj
                podaci['Validnost'] = False
            
            print(f'pre appenda: {podaci=}')
            stavke.append(podaci)
        print(f'{stavke=}')
        
        
        
        flash('Uspešno je učitan XML fajl.', 'success')
        return render_template('posting_payment.html',
                                title="Knjišenje uplata",
                                legend="Knjiženje uplata",
                                stavke=stavke,
                                datum_izvoda_element=datum_izvoda_element,
                                broj_izvoda_element=broj_izvoda_element,
                                iznos_potrazuje_element=iznos_potrazuje_element,
                                broj_pojavljivanja=broj_pojavljivanja)
    if request.method == 'POST' and ('submitBtnSaveData' in request.form):
        print(f'pritisnuto je dugme sačuvajte i rasknjićite uplate')
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
            return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjišenje uplata")
        else:
            # čuvanje podataka u bazu
            new_payment = StudentPayment(payment_date=payment_date,
                                            statment_nubmer=statment_nubmer,
                                            total_payment_amount=total_payment_amount,
                                            number_of_items=number_of_items,
                                            number_of_errors=0
                                        )
            db.session.add(new_payment)
            db.session.commit()
            # print('dodato u db - proveri')
            # print(f'{new_payment.id=}')
            
            uplatioci = request.form.getlist('uplatilac')
            iznosi = request.form.getlist('iznos')
            pozivi_na_broj = request.form.getlist('poziv_na_broj')
            svrha_uplate = request.form.getlist('svrha_uplate')
            print(f'{iznosi=}')
            print(f'{pozivi_na_broj=}')
            print(f'{svrha_uplate=}')
            records = []
            for i in range(len(iznosi)):
                records.append({
                        'uplatilac': uplatioci[i],
                        'iznos': iznosi[i],
                        'poziv_na_broj': pozivi_na_broj[i],
                        'svrha_uplate': svrha_uplate[i]
                    })
            print(f'{records=}')
            number_of_errors = 0
            student_ids = [str(student.id).zfill(4) for student in Student.query.all()]
            service_item_ids = [str(service_item.id).zfill(3) for service_item in ServiceItem.query.all()]
            for record in records:
                payer = record['uplatilac']
                purpose_of_payment = record['svrha_uplate']
                reference_number = record['poziv_na_broj']
                student_id = record['poziv_na_broj'][:4]
                service_item_id = record['poziv_na_broj'][-3:]
                student_debt_total = float(record['iznos'].replace(',', '.'))
                payment_error = False
                print(f'{student_ids=}')
                print(f'{service_item_ids=}')
                print(f'{student_id=}')
                print(f'{service_item_id=}')
                if (student_id not in student_ids) or (service_item_id not in service_item_ids):
                    print(f'nije u listi student_ids: {student_id=}')
                    student_id = 1
                    service_item_id = 0
                    payment_error = True
                    number_of_errors += 1
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
                                                payer=payer,
                                                reference_number=reference_number,
                                                payment_error=payment_error)
                print(f'{new_record.student_id=}')
                print(f'{new_record.service_item_id=}')
                print(f'{new_record.student_debt_total=}')
                print(f'{new_record.purpose_of_payment=}')
                print(f'{new_record.reference_number=}')
                db.session.add(new_record)
                db.session.commit()
            new_payment.number_of_errors = number_of_errors
            db.session.commit()
            flash(f'Uspešno ste uvezli izvod broj: {new_payment.statment_nubmer}), od datuma {new_payment.payment_date.strftime("%d.%m.%Y.")}', 'success')
            return redirect(url_for('transactions.payments_archive_list'))
    return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjišenje uplata")