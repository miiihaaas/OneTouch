import json, logging
import requests, os, io, re
import xml.etree.ElementTree as ET
from PIL import Image
from datetime import datetime, date, timedelta
from flask import  render_template, url_for, flash, redirect, request, send_file, jsonify, send_from_directory
from flask import Blueprint
from flask_login import login_required, current_user
from onetouch import db, bcrypt
from onetouch.models import Teacher, Student, ServiceItem, StudentDebt, StudentPayment, School, TransactionRecord, User, FundTransfer, DebtWriteOff
from onetouch.transactions.functions import izvuci_poziv_na_broj_iz_svrhe_uplate, provera_validnosti_poziva_na_broj, uplatnice_gen, export_payment_stats, gen_debt_report, uplatnice_gen_selected
from onetouch.overviews.functions import get_filtered_transactions_data
from sqlalchemy.exc import SQLAlchemyError

transactions = Blueprint('transactions', __name__)

@transactions.route('/student_debts', methods=['POST', 'GET'])
@login_required
def student_debts():
    school = School.query.first()
    license_expired = False
    if school and school.license_expiry_date:
        days_left = school.days_until_license_expiry()
        if days_left is not None and days_left <= 0:
            license_expired = True
            
    if license_expired:
        flash('Vaša licenca je istekla, ne možete vršiti zaduživanje učenika.', 'danger')
        return redirect(url_for('main.home'))
    
    route_name = request.endpoint
    teachers = Teacher.query.all()
    students = Student.query.all()
    service_items = ServiceItem.query.all()
    logging.debug(f'{service_items=}')
    logging.debug(f'{teachers=}')
    return render_template('student_debts.html', 
                            legend = 'Zaduživanje učenika',
                            title = 'Zaduživanje učenika',
                            students=students, 
                            service_items=service_items, 
                            teachers=teachers,
                            route_name=route_name,
                            school=school)


@transactions.route('/add_new_student', methods=['POST']) #! dodaje novog studenta u postojeće zaduženje (npr došao novi učenik tokom školse godine i treba da se zaduži za osiguranje...)
def add_new_student():
    try:
        student_debt_id = request.form.get('student_debt_id')
        service_item_id = request.form.get('service_item_id')
        student_debt_installment_number = request.form.get('student_debt_installment_number')
        studetn_debt_installment_value = request.form.get('studetn_debt_installment_value')
        student_id = request.form.get('student_id')

        if not all([student_debt_id, service_item_id, student_debt_installment_number, student_id]):
            raise ValueError("Svi obavezni podaci moraju biti popunjeni")

        logging.debug(f'{student_debt_id=} {service_item_id=} {student_debt_installment_number=} {studetn_debt_installment_value=} {student_id=}')
        
        new_student_record = TransactionRecord(
            student_debt_id=student_debt_id,
            student_id=student_id,
            service_item_id=service_item_id,
            student_debt_installment_number=student_debt_installment_number,
            student_debt_amount=0,
            studetn_debt_installment_value=studetn_debt_installment_value,
            student_debt_discount=0,
            student_debt_total=0
        )
        
        db.session.add(new_student_record)
        db.session.commit()
        flash('Učenik je uspešno zadužen!', 'success')
        
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'danger')
        logging.error(f'Greška pri validaciji podataka: {str(e)}')
        return redirect(url_for('transactions.debt_archive', debt_id=student_debt_id))
        
    except SQLAlchemyError as e:
        db.session.rollback()
        flash('Došlo je do greške pri čuvanju podataka. Pokušajte ponovo.', 'danger')
        logging.error(f'SQLAlchemy greška: {str(e)}')
        return redirect(url_for('transactions.debt_archive', debt_id=student_debt_id))
        
    except Exception as e:
        db.session.rollback()
        flash('Došlo je do neočekivane greške. Molimo kontaktirajte administratora.', 'danger')
        logging.error(f'Neočekivana greška: {str(e)}')
        return redirect(url_for('transactions.debt_archive', debt_id=student_debt_id))
        
    return redirect(url_for('transactions.debt_archive', debt_id=student_debt_id))


@transactions.route('/get_payment_slip/<string:filename>')
@login_required
def get_payment_slip(filename):
    """Preuzimanje PDF fajla iz user-specifičnog foldera."""
    user_folder = f'static/payment_slips/user_{current_user.id}'
    return send_from_directory(user_folder, filename)


@transactions.route('/get_report/<string:filename>')
@login_required
def get_report(filename):
    """Preuzimanje PDF fajla iz user-specifičnog foldera."""
    user_folder = f'static/reports/user_{current_user.id}'
    return send_from_directory(user_folder, filename)


@transactions.route('/get_service_items', methods=['POST'])
def get_service_items():
    try:
        service_item_class = request.form.get('classes', 0, type=int)
        logging.debug(f'from AJAX service items: {service_item_class=}')
        
        options = [(0, "Selektujte uslugu")]
        
        service_items = ServiceItem.query.filter_by(archived=False).all()
        if service_items is None:
            raise ValueError("Nije moguće učitati listu usluga")
            
        service_items = [item for item in service_items if item.id != 0] #! treba da eliminiše uslugu sa id=0 koji se koristi za "grešku"
        
        for service_item in service_items:
            if str(service_item_class) in service_item.service_item_class:
                options.append((
                    service_item.id,
                    service_item.service_item_service.service_name + " - " + service_item.service_item_name
                ))
                logging.debug(options)
        
        html = ''
        for option in options:
            html += '<option value="{0}">{1}</option>'.format(option[0], option[1])
        
        return html
        
    except SQLAlchemyError as e:
        logging.error(f'Greška pri učitavanju usluga iz baze: {str(e)}')
        return '<option value="0">Greška pri učitavanju usluga</option>'
        
    except ValueError as e:
        logging.error(f'Greška pri validaciji podataka: {str(e)}')
        return '<option value="0">Greška pri validaciji podataka</option>'
        
    except Exception as e:
        logging.error(f'Neočekivana greška u get_service_items: {str(e)}')
        return '<option value="0">Došlo je do greške pri učitavanju</option>'


@transactions.route('/get_installments', methods=['POST'])
def get_installments():
    try:
        logging.debug(request.form)
        service_item_id = int(request.form.get('installments'))
        if not service_item_id:
            raise ValueError("ID usluge nije prosleđen")
            
        logging.debug(f'from AJAX installments: {service_item_id=}')
        options = [(0, "Selektujte ratu")]
        
        service_item = ServiceItem.query.get_or_404(service_item_id)
        if service_item is None:
            raise ValueError("Usluga nije pronađena")
            
        komadno = service_item.service_item_service.payment_per_unit == 'kom'
        logging.debug(f'{komadno=}')
        
        if service_item.installment_number == 1:
            options.append((1, f'Rata 1'))
            installment_attr = f'price'
            installment_option = getattr(service_item, installment_attr)
            logging.debug(f'{installment_option=}')
        else:
            for i in range(1, service_item.installment_number + 1):
                options.append((i, f'Rata {i}'))
                installment_attr = f'installment_{i}'
                installment_option = getattr(service_item, installment_attr)
                logging.debug(f'{installment_option=}')
        
        html = ''
        for option in options:
            html += '<option value="{0}">{1}</option>'.format(option[0], option[1])
            
        return jsonify(html=html, komadno=komadno)
        
    except ValueError as e:
        logging.error(f'Greška pri validaciji podataka: {str(e)}')
        return jsonify(
            html='<option value="0">Greška pri učitavanju rata</option>',
            komadno=False
        )
        
    except SQLAlchemyError as e:
        logging.error(f'Greška pri učitavanju iz baze: {str(e)}')
        return jsonify(
            html='<option value="0">Greška pri učitavanju podataka iz baze</option>',
            komadno=False
        )
        
    except Exception as e:
        logging.error(f'Neočekivana greška u get_installments: {str(e)}')
        return jsonify(
            html='<option value="0">Došlo je do neočekivane greške</option>',
            komadno=False
        )


@transactions.route('/get_installment_values', methods=['POST'])
def get_installment_values():
    try:
        logging.debug(request.form)
        service_item_id = int(request.form.get('installments'))
        installment_number = int(request.form.get('installment_values'))
        logging.debug(f'{service_item_id=} {installment_number=}')
        
        service_item = ServiceItem.query.get_or_404(service_item_id)
        logging.debug(service_item)
        
        if service_item.installment_number == 1:
            installment_attr = 'price'
        else:
            installment_attr = f'installment_{installment_number}'
            
        installment_value = getattr(service_item, installment_attr)
        installment_value_result = {"result": installment_value}
        logging.debug(f'{installment_value_result=}')
        return installment_value_result
        
    except ValueError as e:
        logging.error(f"Greška pri konverziji vrednosti: {str(e)}")
        return {"error": "Nevažeći format broja"}, 400
    except AttributeError as e:
        logging.error(f"Greška pri pristupu atributu: {str(e)}")
        return {"error": "Nevažeći broj rate"}, 400
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        return {"error": "Došlo je do greške pri obradi zahteva"}, 500


@transactions.route('/submit_records', methods=['post']) #! dodati try-except blok za ovu rutu
def submit_records():
    data = request.get_json()
    logging.debug(f'{type(data)=}')
    
    #! dodavanje novog zaduženja
    if 'service_item' in data: 
        logging.debug('dodavanje novog zaduženja')
        service_item_id = int(data['service_item'])
        debt_class = int(data['class'])
        debt_section = None if data['section'] == '' else int(data['section'])
        installment_number = int(data['installment'])
        purpose_of_payment = data['purpose_of_payment'] #todo: uvezi iz frontenda uz pomoć ajaksa preko data objekta :)
        logging.debug(f'{service_item_id=}, {debt_class=}, {debt_section=}, {installment_number=}')
        
        existing_debt = StudentDebt.query.filter_by(
            service_item_id=service_item_id,
            debt_class=debt_class,
            debt_section=debt_section,
            installment_number=installment_number
        ).first()
        
        if existing_debt:
            flash(f'Već postoji ovo zaduženje: {existing_debt.id}. Ukoliko ima potrebe, možete editovati podatke.', 'info')
            return str(existing_debt.id)
        
        if len(data['records']) == 0:
            return 'Nema zaduženih studenta'
        
        #! proverava koliko service_item ima rata
        service_item = ServiceItem.query.get_or_404(service_item_id)
        
        student_debt_id_first = None
        
        for installment in range(1, service_item.installment_number + 1):
            installment_attr = f'installment_{installment}'
            if service_item.installment_number == 1:
                purpose_of_payment = f'{service_item.service_item_service.service_name} - {service_item.service_item_name}'
            else:
                purpose_of_payment = f'{service_item.service_item_service.service_name} - {service_item.service_item_name} / Rata {installment}'
            installment_value_result = getattr(service_item, installment_attr)
            logging.debug(f'{installment_attr=}, {installment_value_result=}')
        
            new_debt = StudentDebt(student_debt_date = datetime.now(),
                                    service_item_id = service_item_id,
                                    debt_class = debt_class,
                                    debt_section = debt_section,
                                    installment_number=installment, #! ovo je installment iz for loopa koji je zapravo installment_number iz niza (1, 2, 3 ...)
                                    purpose_of_payment=purpose_of_payment)
            
            logging.debug(f'{new_debt=}')
            db.session.add(new_debt)
            db.session.commit()
        
            logging.debug(f'{new_debt.id=}')
            
            if installment == 1:
                student_debt_id_first = new_debt.id
        
            student_debt_id = new_debt.id
            student_payment_id = None
            for i in range(len(data['records'])):
                student_id = data['records'][i]['student_id']
                #! service_item_id = ima već definisano na početku funkcije, ako bude trebalo napiši kod za to
                student_debt_installment_number = installment #! bia je ova vrednost: int(data['installment']), ali ovo je installment iz for loopa koji je zapravo installment_number iz niza (1, 2, 3 ...)
                logging.debug(f'{student_debt_installment_number=}')
                student_debt_amount = data['records'][i]['amount']
                logging.debug(f'prečekiranje pred dodele vrednosti za "studetn_debt_installment_value": {service_item_id=}; {ServiceItem.query.get_or_404(service_item_id)}')
                studetn_debt_installment_value = getattr(ServiceItem.query.get_or_404(service_item_id), f'installment_{student_debt_installment_number}')
                logging.debug(f'{studetn_debt_installment_value=}')
                student_debt_discount = float(data['records'][i]['discount'])
                logging.debug(f'{type(student_debt_amount)=}, {type(studetn_debt_installment_value)=}, {type(student_debt_discount)=}')
                logging.debug(f'{student_debt_amount=}, {studetn_debt_installment_value=}, {student_debt_discount=}')
                student_debt_total = student_debt_amount * studetn_debt_installment_value - student_debt_discount
                logging.debug(f'{student_debt_id=}, {student_payment_id=}, {student_id=}, {service_item_id=}, {student_debt_installment_number=}, {student_debt_amount=}')
                logging.debug(f'{studetn_debt_installment_value=}, {student_debt_discount=}, {student_debt_total=}')
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
        return str(student_debt_id_first)
        # return str(student_debt_id)
    #! izmena postojećeg zaduženja
    elif 'student_debt_id' in data:
        logging.debug('izmena postojećeg zaduženja')
        student_debt_id = int(data['student_debt_id'])
        purpose_of_payment = data['purpose_of_payment']
        logging.debug(f'{student_debt_id=}, {purpose_of_payment=}')
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
            logging.debug(f'{record_for_edit=}')
            record_for_edit.student_debt_amount = student_debt_amount
            record_for_edit.student_debt_discount = student_debt_discount
            record_for_edit.student_debt_total = student_debt_total
            db.session.commit()
        flash(f'Zaduženje {student_debt_id} je uspešno izmenjeno!', 'success')
        return str(student_debt_id)
    #! izmena postojećeg izvoda
    elif 'student_payment_id' in data: #! izmena pregleda izvoda (payment_archive/<int:>)
        logging.debug('izmena postojećeg izvoda')
        transaction_records = TransactionRecord.query.all()
        all_reference_numbers = [f'{record.student_id:04d}-{record.service_item_id:03d}' for record in transaction_records if record.student_debt_id is not None]
        all_reference_numbers.append('0000-000')
        student_payment_id = int(data['student_payment_id'])
        
        number_of_errors = 0
        student_ids = [student.id for student in Student.query.all()]
        service_item_ids = [service_item.id for service_item in ServiceItem.query.all()]
        service_item_ids.append(0)
        for i in range(len(data['records'])):
            record_id = data['records'][i]['record_id']
            student_id = data['records'][i]['student_id']
            service_item_id = data['records'][i]['service_item_id']
            # payment_error = False
            logging.debug(f'{student_ids=}')
            logging.debug(f'{service_item_ids=}')
            logging.debug(f'{student_id=}, {service_item_id=}')
            if (student_id not in student_ids) or (service_item_id not in service_item_ids):
                student_id = 1
                service_item_id = 0
                logging.debug(f'promenjeni su student_id i service item id!!!')
            record_for_edit = TransactionRecord.query.get_or_404(record_id)
            logging.debug(f'{record_for_edit=}')
            logging.debug(f'{record_id=}, {student_id=}, {service_item_id=},')
            record_for_edit.student_id = student_id #if student_id in [record.student_id for record in transaction_records] else 0
            record_for_edit.service_item_id = service_item_id #if service_item_id in [record.service_item_id for record in transaction_records] else 0
            
            reference_number = f"{student_id:04d}-{service_item_id:03d}"
            if reference_number == '0001-000':
                number_of_errors += 1
                record_for_edit.payment_error = True
            elif reference_number in all_reference_numbers:
                logging.debug(f'{reference_number=} {all_reference_numbers=}')
                logging.info('validan poziv na broj! dodaj kod za ažuriranje podatka u db!')
                record_for_edit.payment_error = False
            else:
                logging.info('nije validan poziv na broj! dodaj kod za ažuriranje podataka u db!')
                logging.info(f'poziv na broj: {reference_number=} ne postoji u listi poziva na broj: {all_reference_numbers=}')
                number_of_errors += 1
                record_for_edit.payment_error = True
            logging.debug(f'broj grešaka: {number_of_errors}')
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
    if not current_user.is_authenticated:
        flash('Morate biti ulogovani da biste pristupili ovoj stranici.', 'danger')
        return redirect(url_for('users.login'))
    try:
        route_name = request.endpoint
        school = School.query.first()
        danas = date.today()
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date is None or end_date is None:
            start_date = danas.replace(month=9, day=1, year=2020)
            if danas.month < 9:
                end_date = danas.replace(month=8, day=31)
            else:
                end_date = danas.replace(month=8, day=31, year=danas.year+1)
        
        logging.debug(f'{start_date=}, {end_date=}')
        
        if isinstance(start_date, str):
            # Konvertuj start_date i end_date u datetime.date objekte
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        debts = StudentDebt.query.filter(
                (StudentDebt.student_debt_date >= start_date) &
                (StudentDebt.student_debt_date <= (end_date + timedelta(days=1)).isoformat())
            ).all()
            
        logging.debug(f'{debts=}')
        
        return render_template('debts_archive_list.html', 
                                debts=debts,
                                start_date=start_date,
                                end_date=end_date,
                                legend="Arhiva naloga",
                                route_name=route_name,
                                school=school)
                                
    except ValueError as e:
        logging.error(f"Greška pri konverziji datuma: {str(e)}")
        flash("Nevažeći format datuma", "danger")
        return redirect(url_for('transactions.debts_archive_list'))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.debts_archive_list'))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri obradi zahteva", "danger")
        return redirect(url_for('transactions.debts_archive_list'))


@transactions.route('/payments_archive_list', methods=['get', 'post'])
def payments_archive_list():
    try:
        route_name = request.endpoint
        school = School.query.first()
        
        if not school:
            raise ValueError("Škola nije pronađena u bazi podataka")
        
        bank_accounts = [bank_account['reference_number_spiri'][2:11] for bank_account in school.school_bank_accounts['bank_accounts']]
        
        filtered_bank_account_number = request.args.get('bank_account')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        if start_date is None or end_date is None:
            start_date = date.today().replace(day=1, month=9, year=2020).isoformat()
            end_date = date.today().isoformat()
        
        payments = StudentPayment.query.filter(
            StudentPayment.payment_date.between(start_date, 
            (datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)).isoformat())).all()
            
        logging.debug(f'{payments=}')
        logging.debug(f'{filtered_bank_account_number=}')
        
        if filtered_bank_account_number:
            payments = [payment for payment in payments if payment.bank_account == filtered_bank_account_number]
            
        return render_template('payments_archive_list.html', 
                                bank_accounts=bank_accounts,
                                payments=payments,
                                start_date=start_date,
                                end_date=end_date,
                                filtered_bank_account_number=filtered_bank_account_number,
                                legend="Arhiva izvoda",
                                route_name=route_name)
                                
    except ValueError as e:
        logging.error(f"Greška pri konverziji datuma ili podacima škole: {str(e)}")
        flash("Nevažeći format datuma ili problem sa podacima škole", "danger")
        return redirect(url_for('transactions.payments_archive_list'))
    except (KeyError, AttributeError) as e:
        logging.error(f"Greška pri pristupu podacima škole: {str(e)}")
        flash("Problem pri pristupu podacima o bankovnim računima", "danger")
        return redirect(url_for('transactions.payments_archive_list'))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.payments_archive_list'))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri obradi zahteva", "danger")
        return redirect(url_for('transactions.payments_archive_list'))


@transactions.route('/single_payment_slip/<int:record_id>', methods=['get', 'post'])
def single_payment_slip(record_id):
    try:
        records = []
        record = TransactionRecord.query.get_or_404(record_id)
        logging.debug(f'{record=}')
        
        if not record:
            raise ValueError(f"Transakcija sa ID {record_id} nije pronađena")
            
        debt = StudentDebt.query.get_or_404(record.student_debt_id)
        if not debt:
            raise ValueError(f"Zaduženje za transakciju {record_id} nije pronađeno")
            
        purpose_of_payment = debt.purpose_of_payment
        
        school = School.query.first()
        if not school:
            raise ValueError("Podaci o školi nisu pronađeni")
            
        school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
        records.append(record)
        logging.debug(f'{records=}')
        
        single = True
        send = False
        file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
        
        if not file_name:
            raise ValueError("Greška pri generisanju uplatnice")
        
        
        #! koristi se za generisanje i slanje pdf uplatnica
        current_file_path = os.path.abspath(__file__)
        # logger.debug(f'{current_file_path=}')
        project_folder = os.path.dirname(os.path.dirname((current_file_path)))
        
        user_folder = f'{project_folder}/static/payment_slips/user_{current_user.id}'
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        file_path = f'{user_folder}/{file_name}'
        logging.debug(f'{file_path=}')
        
        return send_file(file_path, as_attachment=False)
        
    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('transactions.payments_archive_list'))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.payments_archive_list'))
    except FileNotFoundError as e:
        logging.error(f"Fajl nije pronađen: {str(e)}")
        flash("Generisana uplatnica nije pronađena", "danger")
        return redirect(url_for('transactions.payments_archive_list'))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri generisanju uplatnice", "danger")
        return redirect(url_for('transactions.payments_archive_list'))


@transactions.route('/service_total_payment_slip/<int:service_id>/<int:student_id>', methods=['GET'])
@login_required
def service_total_payment_slip(service_id, student_id):
    """Generiše uplatnicu za ukupan preostali dug za određenu uslugu"""
    try:
        # Pronalaženje studenta
        student = Student.query.get_or_404(student_id)
        if not student:
            raise ValueError(f"Učenik sa ID {student_id} nije pronađen")
            
        # Pronalaženje usluge
        service_item = ServiceItem.query.get_or_404(service_id)
        if not service_item:
            raise ValueError(f"Usluga sa ID {service_id} nije pronađena")
            
        # Pronalaženje škole
        school = School.query.first()
        if not school:
            raise ValueError("Podaci o školi nisu pronađeni")
            
        school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
        
        # Kreiramo privremeni TransactionRecord objekat koji će sadržati potrebne podatke
        # Uzimamo samo iznos preostalog duga i detalje usluge
        temp_record = TransactionRecord()
        temp_record.id = 0  # Privremeni ID
        temp_record.student_id = student_id
        temp_record.transaction_record_student = student
        temp_record.service_item_id = service_id
        temp_record.transaction_record_service_item = service_item
        
        # Računamo ukupan saldo za ovu uslugu za ovog učenika
        transaction_records = TransactionRecord.query.filter_by(student_id=student_id, service_item_id=service_id).all()
        
        data = []
        # Obrada transakcija kao u overview_student
        for record in transaction_records:
            try:
                if record.student_debt_id:
                    rata = sum(1 for item in data if item["service_item_id"] == record.service_item_id) + 1
                    description = f'{record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name} / Rata {rata}'
                    date_ = record.transaction_record_student_debt.student_debt_date
                elif record.student_payment_id:
                    description = f'{record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                    date_ = record.transaction_record_student_payment.payment_date
                    
                if record.student_debt_total:
                    record_data = {
                        'id': record.id,
                        'service_item_id': record.service_item_id,
                        'student_payment_id': record.student_payment_id,
                        'date': date_,
                        'description': description,
                        'debt_amount': record.student_debt_total if record.student_debt_id else 0,
                        'payment_amount': record.student_debt_total if record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id else 0,
                    }
                    
                    if record_data['service_item_id'] in [item['service_item_id'] for item in data]:
                        saldo_sum = [item['saldo'] for item in data if item['service_item_id'] == record_data['service_item_id']]
                        record_data['saldo'] = saldo_sum[-1] + record_data['debt_amount'] - record_data['payment_amount']
                    else:
                        record_data['saldo'] = record_data['debt_amount'] - record_data['payment_amount']
                        
                    data.append(record_data)
            except Exception as e:
                logging.error(f'Greška pri obradi transakcije (ID: {record.id}): {str(e)}')
                continue
                
        # Sortiramo podatke po datumu
        data.sort(key=lambda x: x['date'])
        
        # Uzimamo saldo iz poslednje transakcije
        remaining_balance = data[-1]['saldo'] if data else 0
        
        print(f'{data=}')
        print(f'{remaining_balance=}')
        
        logging.debug(f"preostali saldo={remaining_balance}")
        
        if remaining_balance <= 0:
            flash("Ne postoji preostali dug za ovu uslugu.", "warning")
            return redirect(url_for('overviews.overview_student', student_id=student_id))
        
        # Priprema svrhe plaćanja sa naznakom da se radi o preostalom dugu
        purpose_of_payment = service_item.service_item_service.service_name + ' - ' + service_item.service_item_name
        if "Ekskurzija" in purpose_of_payment:
            purpose_of_payment += " --- bez Rata 1..."
            
        # Umesto da koristimo privremeni objekat, direktno ćemo generisati uplatnicu
        # Potrebni podaci za generisanje uplatnice
        current_file_path = os.path.abspath(__file__)
        project_folder = os.path.dirname(os.path.dirname((current_file_path)))
        user_folder = f'{project_folder}/static/payment_slips/user_{current_user.id}'
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
        
        # Kreiramo PDF dokument direktno
        from fpdf import FPDF
        
        # Dobavljamo podatke o bankovnom računu
        bank_account_number = service_item.bank_account
        
        # Implementacija logike za primaoca
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
        
        # Kreiramo podatke potrebne za generisanje PDF-a sa svim potrebnim parametrima
        # ali bez čuvanja podataka u bazi
        
        payment_data = {
            'student_id': student_id,
            'uplatilac': student.student_name + ' ' + student.student_surname,
            'svrha_uplate': f"{student_id:04d}-{service_id:03d} " + purpose_of_payment,
            'primalac': primalac,
            'sifra_placanja': 253 if service_item.reference_number_spiri else 221,
            'valuta': 'RSD',
            'iznos': remaining_balance,
            'racun_primaoca': bank_account_number,
            'model': '97' if service_item.reference_number_spiri else '',
            'poziv_na_broj': service_item.reference_number_spiri if service_item.reference_number_spiri else '',
        }
        
        # Generisanje PDF-a bez korišćenja privremenog TransactionRecord objekta
        file_name = 'uplatnica_saldo.pdf'
        file_path = f'{user_folder}/{file_name}'
        
        try:
            # Poziv funkcije za direktno generisanje uplatnice
            from onetouch.transactions.functions import add_fonts, setup_pdf_page, add_payment_slip_content, PDF, prepare_qr_data, generate_qr_code, cleanup_qr_codes
            
            pdf = PDF()
            add_fonts(pdf)
            y, y_qr = setup_pdf_page(pdf, 1)
            
            # Generisanje QR koda ako je potrebno
            qr_data = prepare_qr_data(payment_data, payment_data['primalac'])
            qr_code_filename = generate_qr_code(qr_data, payment_data['student_id'], project_folder, current_user.id)
            
            # Dodavanje sadržaja uplatnice
            add_payment_slip_content(pdf, payment_data, y, y_qr, project_folder, current_user)
            
            # Generisanje PDF-a
            pdf.output(file_path)
            
            # Čišćenje privremenih QR kodova
            cleanup_qr_codes(project_folder, current_user.id)
            
            # Slanje fajla korisniku
            return send_file(file_path, as_attachment=False)
            
        except Exception as e:
            logging.error(f"Greška pri generisanju PDF-a: {str(e)}")
            raise ValueError(f"Greška pri generisanju uplatnice: {str(e)}")
        
    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('overviews.overview_student', student_id=student_id))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('overviews.overview_student', student_id=student_id))
    except FileNotFoundError as e:
        logging.error(f"Fajl nije pronađen: {str(e)}")
        flash("Generisana uplatnica nije pronađena", "danger")
        return redirect(url_for('overviews.overview_student', student_id=student_id))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri generisanju uplatnice", "danger")
        return redirect(url_for('overviews.overview_student', student_id=student_id))


@transactions.route('/debt_archive/<int:debt_id>', methods=['GET', 'POST'])
def debt_archive(debt_id):
    if not current_user.is_authenticated:
        flash('Morate biti ulogovani da biste pristupili ovoj stranici.', 'danger')
        return redirect(url_for('users.login'))
    try:
        route_name = request.endpoint
        
        # Provera zaduženja
        debt = StudentDebt.query.get_or_404(debt_id)
        if not debt:
            raise ValueError(f"Zaduženje sa ID {debt_id} nije pronađeno")
            
        purpose_of_payment = debt.purpose_of_payment
        logging.debug(f'{purpose_of_payment=}')
        
        # Provera škole
        school = School.query.first()
        if not school:
            raise ValueError("Podaci o školi nisu pronađeni")
            
        school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
        
        # Pronalaženje razrednog starešine
        teacher = Teacher.query.filter_by(teacher_class=debt.debt_class).filter_by(teacher_section=debt.debt_section).first()
        if not teacher:
            logging.warning(f"Nije pronađen razredni starešina za odeljenje {debt.debt_class}-{debt.debt_section}")
        
        # Pronalaženje transakcija
        records = TransactionRecord.query.filter_by(student_debt_id=debt_id).all()
        logging.debug(f'provera broja učenika: {records=}, {len(records)=}')
        
        # Pronalaženje učenika
        students = Student.query.filter_by(student_class=debt.debt_class).filter_by(student_section=debt.debt_section).all()
        logging.debug(f'provera broja učenika: {students=}, {len(students)=}')
        
        # Provera novih učenika
        record_ids = set([record.transaction_record_student.id for record in records])
        new_students = [student for student in students if student.id not in record_ids]
        logging.debug(f'{record_ids=}; {new_students=}')
        
        # Generisanje uplatnice
        single = False
        send = False
        file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
        if not file_name:
            raise ValueError("Greška pri generisanju uplatnice")
        
        # Generisanje izveštaja
        if not gen_debt_report(records):
            raise ValueError("Greška pri generisanju izveštaja")

        return render_template('debt_archive.html',
                                records=records,
                                debt=debt,
                                teacher=teacher,
                                new_students=new_students,
                                purpose_of_payment=purpose_of_payment,
                                school=school,
                                legend=f"Pregled zaduženja: {debt.id}",
                                title="Pregled zaduženja",
                                route_name=route_name)
                                
    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('transactions.debts_archive_list'))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.debts_archive_list'))
    except FileNotFoundError as e:
        logging.error(f"Fajl nije pronađen: {str(e)}")
        flash("Greška pri generisanju dokumenta", "danger")
        return redirect(url_for('transactions.debts_archive_list'))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri obradi zahteva", "danger")
        return redirect(url_for('transactions.debts_archive_list'))


@transactions.route('/send_payment_slips/<int:debt_id>', methods=['get', 'post'])
def send_payment_slips(debt_id):
    try:
        # SERVER-SIDE VALIDACIJA - provera da li je slanje mejlova omogućeno
        school = School.query.first()
        if not school or not school.sending_email:
            flash('Slanje mejlova roditeljima je trenutno onemogućeno u podešavanjima škole.', 'warning')
            return redirect(url_for('transactions.debt_archive', debt_id=debt_id))

        # Provera zaduženja
        debt = StudentDebt.query.get_or_404(debt_id)
        if not debt:
            raise ValueError(f"Zaduženje sa ID {debt_id} nije pronađeno")

        purpose_of_payment = debt.purpose_of_payment

        # Kreiranje school_info (school već dohvaćen u SERVER-SIDE validaciji)
        school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city

        # Pronalaženje transakcija
        records = TransactionRecord.query.filter_by(student_debt_id=debt_id).all()
        if not records:
            raise ValueError("Nema pronađenih transakcija za ovo zaduženje")
            
        # Generisanje i slanje uplatnica
        single = True
        send = True
        file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
        if not file_name:
            raise ValueError("Greška pri generisanju i slanju uplatnica")
            
        flash('Uspešno ste poslali mejlove roditeljima.', 'success')
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
        
    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except FileNotFoundError as e:
        logging.error(f"Fajl nije pronađen: {str(e)}")
        flash("Greška pri generisanju uplatnica", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except smtplib.SMTPException as e:
        logging.error(f"Greška pri slanju mejla: {str(e)}")
        flash("Greška pri slanju mejlova roditeljima", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri obradi zahteva", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))


@transactions.route('/print_selected_slips/<int:debt_id>', methods=['GET'])
@login_required
def print_selected_slips(debt_id):
    """Generiše uplatnice za selektovane učenike."""
    try:
        # Dobavljanje ID-jeva selektovanih učenika iz URL parametra
        record_ids = request.args.get('ids', '')
        if not record_ids:
            flash('Niste izabrali nijednog učenika za štampanje uplatnica.', 'warning')
            return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
        
        record_id_list = [int(id) for id in record_ids.split(',')]
        logging.debug(f'Štampanje uplatnica za sledeće zapise: {record_id_list}')
        
        # Provera zaduženja
        debt = StudentDebt.query.get_or_404(debt_id)
        if not debt:
            raise ValueError(f"Zaduženje sa ID {debt_id} nije pronađeno")
            
        purpose_of_payment = debt.purpose_of_payment
        
        # Provera škole
        school = School.query.first()
        if not school:
            raise ValueError("Podaci o školi nisu pronađeni")
            
        school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city
        
        # Pronalaženje transakcija po ID-jevima
        records = TransactionRecord.query.filter(TransactionRecord.id.in_(record_id_list)).all()
        
        if not records:
            raise ValueError(f"Nisu pronađene transakcije sa zadatim ID-jevima")
        
        # Generisanje PDF-a sa selektovanim uplatnicama
        single = False
        send = False
        file_name = uplatnice_gen_selected(records, purpose_of_payment, school_info, school, single, send)
        
        if not file_name:
            raise ValueError("Greška pri generisanju uplatnica")
            
        # Vraćanje generisanog PDF-a
        user_folder = f'static/payment_slips/user_{current_user.id}'
        file_path = f'{user_folder}/{file_name}'
        return send_from_directory(user_folder, file_name, as_attachment=False)
        
    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri generisanju uplatnica", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))


@transactions.route('/send_single_payment_slip/<int:record_id>', methods=['get', 'post'])
def send_single_payment_slip(record_id):
    try:
        # SERVER-SIDE VALIDACIJA - provera da li je slanje mejlova omogućeno
        school = School.query.first()
        if not school or not school.sending_email:
            flash('Slanje mejlova roditeljima je trenutno onemogućeno u podešavanjima škole.', 'warning')
            # Pokušaj da dobije debt_id za redirekciju
            record = TransactionRecord.query.get(record_id)
            debt_id = record.student_debt_id if record else None
            if debt_id:
                return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
            else:
                return redirect(url_for('transactions.debts_archive_list'))

        # Pronalaženje transakcije i zaduženja
        record = TransactionRecord.query.get_or_404(record_id)
        if not record:
            raise ValueError(f"Transakcija sa ID {record_id} nije pronađena")
            
        debt_id = record.student_debt_id
        debt = StudentDebt.query.get_or_404(debt_id)
        if not debt:
            raise ValueError(f"Zaduženje sa ID {debt_id} nije pronađeno")

        purpose_of_payment = debt.purpose_of_payment

        # Kreiranje school_info (school već dohvaćen u SERVER-SIDE validaciji)
        school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city

        # Priprema liste sa jednom transakcijom
        records = [record]
        
        # Generisanje i slanje uplatnice
        single = True
        send = True
        file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)
        if not file_name:
            raise ValueError("Greška pri generisanju i slanju uplatnice")
            
        flash('Uspešno ste poslali mejl roditelju.', 'success')
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
        
    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id if 'debt_id' in locals() else None))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id if 'debt_id' in locals() else None))
    except FileNotFoundError as e:
        logging.error(f"Fajl nije pronađen: {str(e)}")
        flash("Greška pri generisanju uplatnice", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id if 'debt_id' in locals() else None))
    except smtplib.SMTPException as e:
        logging.error(f"Greška pri slanju mejla: {str(e)}")
        flash("Greška pri slanju mejla roditelju", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id if 'debt_id' in locals() else None))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri obradi zahteva", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id if 'debt_id' in locals() else None))


@transactions.route('/send_selected_payment_slips/<int:debt_id>', methods=['GET'])
@login_required
def send_selected_payment_slips(debt_id):
    """Šalje uplatnice mejlom roditeljima selektovanih učenika."""
    try:
        # SERVER-SIDE VALIDACIJA - provera da li je slanje mejlova omogućeno
        school = School.query.first()
        if not school or not school.sending_email:
            flash('Slanje mejlova roditeljima je trenutno onemogućeno u podešavanjima škole.', 'warning')
            return redirect(url_for('transactions.debt_archive', debt_id=debt_id))

        # Dobavljanje ID-jeva selektovanih učenika iz URL parametra
        record_ids = request.args.get('ids', '')
        if not record_ids:
            flash('Niste izabrali nijednog učenika za slanje uplatnica.', 'warning')
            return redirect(url_for('transactions.debt_archive', debt_id=debt_id))

        record_id_list = [int(id) for id in record_ids.split(',')]
        logging.debug(f'Slanje uplatnica mejlom za sledeće zapise: {record_id_list}')

        # Provera zaduženja
        debt = StudentDebt.query.get_or_404(debt_id)
        if not debt:
            raise ValueError(f"Zaduženje sa ID {debt_id} nije pronađeno")

        purpose_of_payment = debt.purpose_of_payment

        # Kreiranje school_info (school već dohvaćen u SERVER-SIDE validaciji)
        school_info = school.school_name + ', ' + school.school_address + ', ' + str(school.school_zip_code) + ' ' + school.school_city

        # Pronalaženje transakcija po ID-jevima
        records = TransactionRecord.query.filter(TransactionRecord.id.in_(record_id_list)).all()

        if not records:
            raise ValueError(f"Nisu pronađene transakcije sa zadatim ID-jevima")

        # Generisanje i slanje uplatnica samo za selektovane učenike
        single = True
        send = True
        file_name = uplatnice_gen(records, purpose_of_payment, school_info, school, single, send)

        if not file_name:
            raise ValueError("Greška pri generisanju i slanju uplatnica")

        flash(f'Uspešno ste poslali uplatnice roditeljima {len(records)} učenika.', 'success')
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))

    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri učitavanju podataka iz baze", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except FileNotFoundError as e:
        logging.error(f"Fajl nije pronađen: {str(e)}")
        flash("Greška pri generisanju uplatnica", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except smtplib.SMTPException as e:
        logging.error(f"Greška pri slanju mejla: {str(e)}")
        flash("Greška pri slanju mejlova roditeljima", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri obradi zahteva", "danger")
        return redirect(url_for('transactions.debt_archive', debt_id=debt_id))


@transactions.route('/debt_archive_delete/<int:debt_id>', methods=['get', 'post'])
def debt_archive_delete(debt_id):
    if not current_user.is_authenticated:
        flash('Morate biti ulogovani da biste pristupili ovoj stranici.', 'danger')
        return redirect(url_for('users.login'))
    try:
        # Provera da li zaduženje postoji
        debt = StudentDebt.query.get_or_404(debt_id)
        if not debt:
            raise ValueError(f"Zaduženje sa ID {debt_id} nije pronađeno")
            
        # Pronalaženje i brisanje povezanih transakcija
        records = TransactionRecord.query.filter_by(student_debt_id=debt_id).all()
        for record in records:
            try:
                db.session.delete(record)
                db.session.commit()
            except SQLAlchemyError as e:
                db.session.rollback()
                raise SQLAlchemyError(f"Greška pri brisanju transakcije {record.id}: {str(e)}")
                
        # Brisanje zaduženja
        try:
            db.session.delete(debt)
            db.session.commit()
        except SQLAlchemyError as e:
            db.session.rollback()
            raise SQLAlchemyError(f"Greška pri brisanju zaduženja {debt_id}: {str(e)}")
            
        flash(f'Nalog {debt_id} je uspešno obrisan, kao i sva zaduženja učenika iz tog naloga.', 'success')
        return redirect(url_for('transactions.debts_archive_list'))
        
    except ValueError as e:
        logging.error(f"Greška sa podacima: {str(e)}")
        flash(str(e), "danger")
        return redirect(url_for('transactions.debts_archive_list'))
    except SQLAlchemyError as e:
        logging.error(f"Greška pri pristupu bazi podataka: {str(e)}")
        flash("Greška pri brisanju podataka iz baze", "danger")
        return redirect(url_for('transactions.debts_archive_list'))
    except Exception as e:
        logging.error(f"Neočekivana greška: {str(e)}")
        flash("Došlo je do greške pri brisanju naloga", "danger")
        return redirect(url_for('transactions.debts_archive_list'))


@transactions.route('/payment_archive/<int:payment_id>', methods=['get', 'post'])
def payment_archive(payment_id):
    try:
        route_name = request.endpoint
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

        unique_service_item_ids = []
        for record in records:
            if record.service_item_id not in unique_service_item_ids:
                unique_service_item_ids.append(record.service_item_id)
        export_data = []
        record_data = {}
        for unique_service_item_id in unique_service_item_ids:
            # Filtrirajte zapise samo za trenutni unique_service_item_id
            filtered_records = [record for record in records if record.service_item_id == unique_service_item_id]
            # Sabiranje svih vrednosti student_debt_total za trenutni unique_service_item_id
            sum_amount = sum(record.student_debt_total for record in filtered_records)
            
            # Kreiranje record_data za trenutni unique_service_item_id
            record_data = {
                'payment_id': payment.id,
                'service_item_id': unique_service_item_id,
                'sum_amount': sum_amount,
            }
            if filtered_records[0].transaction_record_service_item is not None:
                record_data['name'] = filtered_records[0].transaction_record_service_item.service_item_service.service_name + ' - ' + filtered_records[0].transaction_record_service_item.service_item_name
            else:
                record_data['name'] = 'Greška'
            export_data.append(record_data)
            
            gen_file = export_payment_stats(export_data)
        return render_template('payment_archive.html', 
                            records=records, #! ovo je za prvu tabelu
                            payment=payment,
                            # students=students_data,
                            # services=services_data,
                            students=json.dumps(students_data),
                            services=json.dumps(services_data),
                            export_data = export_data, #! ovo je za treću tabelu
                            legend=f"Pregled izvoda: {payment.statment_nubmer} ({payment.payment_date.strftime('%d.%m.%Y.')})",
                            route_name=route_name)
    except Exception as e:
        db.session.rollback()
        flash(f'Došlo je do greške prilikom učitavanja arhive plaćanja: {str(e)}', 'danger')
        return redirect(url_for('transactions.payments'))


@transactions.route('/posting_payment', methods=['POST', 'GET'])
def posting_payment():
    try:
        route_name = request.endpoint
        school = School.query.first()
        license_expired = False
        if school and school.license_expiry_date:
            days_left = school.days_until_license_expiry()
            if days_left is not None and days_left <= 0:
                license_expired = True
        if license_expired:
            flash('Vaša licenca je istekla, ne možete vršiti knjiženje uplata.', 'danger')
            return redirect(url_for('main.home'))
        error_mesage = None
        if request.method == 'POST' and ('submitBtnImportData' in request.form):
            try:
                file = request.files['fileInput']
                if file.filename == '':
                    error_mesage = 'Niste izabrali XML fajl'
                    flash(error_mesage, 'danger')
                    return render_template('posting_payment.html', error_mesage=error_mesage)
                
                # Čitanje fajla i čišćenje invalid XML karaktera
                xml_content = file.read()
                # Dekodovanje sa zamenom problematičnih karaktera
                try:
                    xml_string = xml_content.decode('utf-8', errors='replace')
                except UnicodeDecodeError:
                    # Ako utf-8 ne uspe, pokušaj sa drugim enkodingom
                    try:
                        xml_string = xml_content.decode('windows-1252', errors='replace')
                    except UnicodeDecodeError:
                        xml_string = xml_content.decode('iso-8859-2', errors='replace')
                
                # Zamena replacement karaktera i drugih invalid XML karaktera
                # XML dozvoljava samo određene karaktere: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
                def clean_invalid_xml_chars(text):
                    """Uklanja ili zamenjuje invalid XML karaktere"""
                    # Uklanjanje BOM karaktera ako postoje
                    if text.startswith('\ufeff'):
                        text = text[1:]
                    
                    # Eksplicitna zamena najčešćih problematičnih karaktera
                    problematic_chars = {
                        '�': ' ',           # Replacement character
                        '\x00': '',         # NULL byte
                        '\x0b': ' ',        # Vertical tab
                        '\x0c': ' ',        # Form feed
                        '\x1a': ' ',        # Substitute character
                        '\x1b': ' ',        # Escape
                        '\x7f': ' ',        # Delete
                        '\x80': ' ',        # Windows-1252 problematični karakteri
                        '\x81': ' ',
                        '\x8d': ' ',
                        '\x8f': ' ',
                        '\x90': ' ',
                        '\x9d': ' ',
                    }
                    
                    for old_char, new_char in problematic_chars.items():
                        text = text.replace(old_char, new_char)
                    
                    # Uklanjanje svih ostalih kontrolnih karaktera koji nisu dozvoljeni u XML-u
                    valid_chars = (
                        lambda c: c == '\n' or c == '\r' or c == '\t' or 
                        (ord(c) >= 0x20 and ord(c) <= 0xD7FF) or
                        (ord(c) >= 0xE000 and ord(c) <= 0xFFFD)
                    )
                    return ''.join(c if valid_chars(c) else ' ' for c in text)
                
                xml_string = clean_invalid_xml_chars(xml_string)
                
                # Parsiranje očišćenog XML-a
                tree = ET.ElementTree(ET.fromstring(xml_string.encode('utf-8')))
                root = tree.getroot()

                #! nova logika za SPIRI .xml fajl
                pozivi_na_broj = [bank_account['reference_number_spiri'] for bank_account in School.query.get(1).school_bank_accounts['bank_accounts'] if bank_account['reference_number_spiri'] != '']
                print(f'{pozivi_na_broj=}')
                pozivi_na_broj = [broj[2:11] for broj in pozivi_na_broj]
                print(f'{pozivi_na_broj=}')
                
                broj_racuna_bez_poziva = [bank_account['bank_account_number'] for bank_account in School.query.get(1).school_bank_accounts['bank_accounts'] if bank_account['reference_number_spiri'] == '']
                print(f'{broj_racuna_bez_poziva=}')

                pozivi_na_broj = pozivi_na_broj + broj_racuna_bez_poziva

                # racun_skole = [bank_account['bank_account_number'] for bank_account in School.query.get(1).school_bank_accounts['bank_accounts']]
                datum_izvoda_element = root.find('.//DatumIzvoda').text
                racun_izvoda_element = root.find('.//RacunIzvoda').text
                broj_izvoda_element = root.find('.//BrojIzvoda').text
                iznos_potrazuje_element = root.find('.//IznosPotrazuje').text
                logging.debug(f'{racun_izvoda_element=}')
                # Pronalaženje broja pojavljivanja elementa <Stavka>
                broj_pojavljivanja = len(root.findall('.//Stavka'))
                
                existing_payments = StudentPayment.query.filter_by(
                                                        payment_date=datetime.strptime(datum_izvoda_element, '%d.%m.%Y'), #todo: podesiti filtere datetime.strptime(datum_izvoda_element, '%d.%m.%Y')
                                                        statment_nubmer=int(broj_izvoda_element)).first() #todo: podesiti filtere
                # spisak svih izvoda koji postoje u data bazi
                transaction_records = TransactionRecord.query.all()
                all_reference_numbers = [f'{record.student_id:04d}-{record.service_item_id:03d}' for record in transaction_records  if record.student_debt_id is not None]
                logging.debug(f'{all_reference_numbers=}')
                
                logging.debug(f'{existing_payments=}')
                if existing_payments:
                    error_mesage = f'Izabrani izvod ({broj_izvoda_element}) već postoji u bazi.'
                    flash(error_mesage, 'danger')
                    # return render_template('posting_payment.html', error_mesage=error_mesage) #todo izmeniti atribute u render_template tako da se učitaju stavke i error mesage

                # Ispis rezultata
                logging.debug("Broj pojavljivanja elementa <Stavka>: ", broj_pojavljivanja)
                logging.debug(f'{datum_izvoda_element=}')
                logging.debug(f'{broj_izvoda_element=}')
                logging.debug(f'{iznos_potrazuje_element=}')
                logging.debug(f'{pozivi_na_broj=}, {racun_izvoda_element=}')
                # if racun_izvoda_element not in racun_skole:
                if racun_izvoda_element not in pozivi_na_broj:
                    error_mesage = f'Računi nisu isti. Račun izvoda: {racun_izvoda_element}, račun škole: {pozivi_na_broj}. Izaberite odgovarajući XML fajl i pokušajte ponovo.'
                    flash(error_mesage, 'danger')
                    return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata", route_name=route_name)

                stavke = []
                for stavka in root.findall('Stavka'):
                    podaci = {}
                    podaci['RacunZaduzenja'] = stavka.find('RacunZaduzenja').text #! onaj ko plaća
                    podaci['NazivZaduzenja'] = stavka.find('NazivZaduzenja').text
                    podaci['MestoZaduzenja'] = stavka.find('MestoZaduzenja').text
                    podaci['IzvorInformacije'] = stavka.find('IzvorInformacije').text if stavka.find('IzvorInformacije') is not None else None
                    podaci['ModelPozivaZaduzenja'] = stavka.find('ModelPozivaZaduzenja').text
                    podaci['PozivZaduzenja'] = stavka.find('PozivZaduzenja').text
                    podaci['SifraPlacanja'] = stavka.find('SifraPlacanja').text
                    
                    izvor_informacije = podaci['IzvorInformacije']
                    iznos_text = stavka.find('Iznos').text
                    
                    if izvor_informacije in ['2', '20']:
                        # UPLATA - pozitivan iznos
                        podaci['Iznos'] = float(iznos_text)
                    elif izvor_informacije in ['1', '13']:
                        # ISPLATA - negativan iznos
                        podaci['Iznos'] = -float(iznos_text)
                    else:
                        # Nepoznat tip - default pozitivan
                        podaci['Iznos'] = float(iznos_text)
                    podaci['RacunOdobrenja'] = stavka.find('RacunOdobrenja').text #! onom kome se plaća
                    podaci['NazivOdobrenja'] = stavka.find('NazivOdobrenja').text
                    podaci['MestoOdobrenja'] = stavka.find('MestoOdobrenja').text
                    podaci['ModelPozivaOdobrenja'] = stavka.find('ModelPozivaOdobrenja').text
                    podaci['PozivOdobrenja'] = stavka.find('PozivOdobrenja').text if stavka.find('PozivOdobrenja').text else "-" #! ako nije None onda preuzmi vrednost iz xml, akoj je None onda mu dodeli "-"
                    podaci['SvrhaDoznake'] = stavka.find('SvrhaDoznake').text if stavka.find('SvrhaDoznake').text else "-" #! isti princip kao gornji red 
                    podaci['PozivNaBrojApp'] = izvuci_poziv_na_broj_iz_svrhe_uplate(podaci['SvrhaDoznake']) #! ovde dodati kod koji će da iz SVRHE UPLATE povlači POZIV NA BROJ za APP
                    # podaci['DatumValute'] = stavka.find('DatumValute').text
                    podaci['PodatakZaReklamaciju'] = stavka.find('PodatakZaReklamaciju').text
                    # podaci['VremeUnosa'] = stavka.find('VremeUnosa').text
                    # podaci['VremeIzvrsenja'] = stavka.find('VremeIzvrsenja').text
                    podaci['StatusNaloga'] = stavka.find('StatusNaloga').text
                    # podaci['TipSloga'] = stavka.find('TipSloga').text
                    podaci['TipPlacanja'] = stavka.find('TipPlacanja').text if stavka.find('TipPlacanja') else None
                    
                    logging.debug(f'testiranje: {podaci["PozivNaBrojApp"]=}')

                    #! provera da li je poziv na broj validan
                    provera_validnosti_poziva_na_broj(podaci, all_reference_numbers)
                    logging.debug(f'pre appenda: {podaci=}')
                    logging.debug(f'Iznos: {podaci["Iznos"]}, Tip: {izvor_informacije}, Validnost: {podaci.get("Validnost")}')
                    stavke.append(podaci)
                logging.debug(f'{stavke=}')
                
                flash('Uspešno je učitan XML fajl.', 'success')
                return render_template('posting_payment.html',
                                        title="Knjiženje uplata",
                                        legend="Knjiženje uplata",
                                        stavke=stavke,
                                        datum_izvoda_element=datum_izvoda_element,
                                        broj_izvoda_element=broj_izvoda_element,
                                        iznos_potrazuje_element=iznos_potrazuje_element,
                                        racun_izvoda_element=racun_izvoda_element,
                                        broj_pojavljivanja=broj_pojavljivanja,
                                        route_name=route_name)
            except ET.ParseError as e:
                logging.error(f'Greška pri parsiranju XML fajla: {str(e)}')
                db.session.rollback()
                flash(f'Greška pri parsiranju XML fajla: {str(e)}', 'danger')
                return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata", route_name=route_name)
            except Exception as e:
                logging.error(f'Došlo je do greške prilikom učitavanja XML fajla: {str(e)}')
                db.session.rollback()
                flash(f'Došlo je do greške prilikom učitavanja XML fajla: {str(e)}', 'danger')
                return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata", route_name=route_name)
        if request.method == 'POST' and ('submitBtnSaveData' in request.form):
            try:
                logging.debug(f'pritisnuto je dugme sačuvajte i rasknjićite uplate')
                # Dohvaćanje vrijednosti iz obrasca
                payment_date = datetime.strptime(request.form['payment_date'], '%d.%m.%Y')
                statment_nubmer = int(request.form['statment_nubmer'])
                total_payment_amount = float(request.form['total_payment_amount'].replace(',', '.'))
                number_of_items = int(request.form['number_of_items'])
                bank_account = request.form['bank_account'] #! obezbedi da bude string a ne int, mora i u db da se ispravi
                logging.debug(f'{payment_date=}')
                logging.debug(f'{statment_nubmer=}')
                logging.debug(f'{total_payment_amount=}')
                logging.debug(f'{number_of_items=}')
                existing_payments = StudentPayment.query.filter_by(
                                                        payment_date=payment_date,
                                                        statment_nubmer=statment_nubmer,
                                                        bank_account=bank_account).first()
                logging.debug(f'{existing_payments=}')
                if existing_payments:
                    error_mesage = f'Uplata za dati datum ({payment_date}) i broj računa ({statment_nubmer}) već postoji u bazi. Izaberite novi XML fajl i pokušajte ponovo.'
                    flash(error_mesage, 'danger')
                    return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata")
                else:
                    # čuvanje podataka u bazu
                    new_payment = StudentPayment(payment_date=payment_date,
                                                    bank_account=bank_account,
                                                    statment_nubmer=statment_nubmer,
                                                    total_payment_amount=total_payment_amount,
                                                    number_of_items=number_of_items,
                                                    number_of_errors=0
                                                )
                    db.session.add(new_payment)
                    db.session.commit()
                    
                    uplatioci = request.form.getlist('uplatilac')
                    iznosi = request.form.getlist('iznos')
                    pozivi_na_broj = request.form.getlist('poziv_na_broj')
                    svrha_uplate = request.form.getlist('svrha_uplate')
                    logging.debug(f'{iznosi=}')
                    logging.debug(f'{pozivi_na_broj=}')
                    logging.debug(f'{svrha_uplate=}')
                    records = []
                    for i in range(len(iznosi)):
                        records.append({
                                'uplatilac': uplatioci[i],
                                'iznos': iznosi[i],
                                'poziv_na_broj': pozivi_na_broj[i],
                                'svrha_uplate': svrha_uplate[i]
                            })
                    logging.debug(f'{records=}')
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
                        logging.debug(f'{student_ids=}')
                        logging.debug(f'{service_item_ids=}')
                        logging.debug(f'{student_id=}')
                        logging.debug(f'{service_item_id=}')
                        if (student_id not in student_ids) or (service_item_id not in service_item_ids):
                            logging.debug(f'nije u listi student_ids: {student_id=}')
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
                        logging.debug(f'{new_record.student_id=}')
                        logging.debug(f'{new_record.service_item_id=}')
                        logging.debug(f'{new_record.student_debt_total=}')
                        logging.debug(f'{new_record.purpose_of_payment=}')
                        logging.debug(f'{new_record.reference_number=}')
                        db.session.add(new_record)
                        db.session.commit()
                    new_payment.number_of_errors = number_of_errors
                    db.session.commit()
                    flash(f'Uspešno ste uvezli izvod broj: {new_payment.statment_nubmer} na podračunu {new_payment.bank_account}, od datuma {new_payment.payment_date.strftime("%d.%m.%Y.")}', 'success')
                    return redirect(url_for('transactions.payments_archive_list'))
            except ValueError as e:
                db.session.rollback()
                flash(f'Greška pri konverziji podataka: {str(e)}', 'danger')
                return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata", route_name=route_name)
            except Exception as e:
                db.session.rollback()
                flash(f'Došlo je do greške prilikom čuvanja podataka: {str(e)}', 'danger')
                return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata", route_name=route_name)
        return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata", route_name=route_name)
    except Exception as e:
        db.session.rollback()
        flash(f'Došlo je do neočekivane greške: {str(e)}', 'danger')
        return render_template('posting_payment.html', legend="Knjiženje uplata", title="Knjiženje uplata", route_name=route_name)


@transactions.route('/transfer_funds', methods=['GET'])
@transactions.route('/transfer_funds/<int:student_id>', methods=['GET'])
@login_required
def transfer_funds(student_id=None):
    """Prikaz stranice za preknjižavanje sredstava"""
    # Provera licence
    school = School.query.first()
    if school and school.license_expiry_date:
        days_left = school.days_until_license_expiry()
        if days_left is not None and days_left <= 0:
            flash('Licenca je istekla. Molimo obnovite licencu da biste nastavili sa korišćenjem aplikacije.', 'danger')
            return redirect(url_for('main.license_info'))

    students = Student.query.order_by(Student.student_surname, Student.student_name).all()
    
    selected_student = None
    services_data = []
    services_with_surplus = []
    services_with_debt = []
    
    if student_id:
        # Dobavljanje direktnih podataka o transakcijama za izabranog učnika
        student = Student.query.get_or_404(student_id)
        
        # Dobavljamo sve transakcije za učnika
        transaction_records = TransactionRecord.query.filter_by(student_id=student_id).all()
        
        # Grupisanje transakcija po uslugama
        services_data = {}
        for record in transaction_records:
            service_id = record.service_item_id
            if service_id not in services_data:
                services_data[service_id] = {
                    'service_id': service_id,
                    'service_item': record.transaction_record_service_item,
                    'debt_amount': 0,
                    'payment_amount': 0,
                    'saldo': 0
                }
            
            if record.student_debt_id:
                services_data[service_id]['debt_amount'] += record.student_debt_total
            elif record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id:
                services_data[service_id]['payment_amount'] += record.student_debt_total
        
        # Konverzija u listu i računanje salda
        services_list = []
        services_with_surplus = []
        services_with_debt = []
        
        for service_id, data in services_data.items():
            # Računanje salda
            data['saldo'] = data['debt_amount'] - data['payment_amount']
            
            # Preskakanje usluga sa nultim saldom
            if data['saldo'] == 0:
                continue
                
            services_list.append(data)
            
            # Identifikujemo usluge koje imaju višak sredstava (negativan saldo)
            if data['saldo'] < 0:
                services_with_surplus.append(data)
            # Identifikujemo usluge koje su u dugovanju (pozitivan saldo)
            elif data['saldo'] > 0:
                services_with_debt.append(data)
        
        selected_student = student
        services_data = services_list
    
    return render_template('transfer_funds.html',
                          students=students,
                          selected_student_id=student_id,
                          selected_student=selected_student,
                          services_data=services_data,
                          services_with_surplus=services_with_surplus,
                          services_with_debt=services_with_debt,
                          legend="Preknjižavanje sredstava", 
                          title="Preknjižavanje sredstava",
                          route_name="transfer_funds")


@transactions.route('/transfer_funds', methods=['POST'])
@login_required
def process_transfer_funds():
    """Obrada zahteva za preknjižavanje sredstava"""
    # Provera licence
    school = School.query.first()
    if school and school.license_expiry_date:
        days_left = school.days_until_license_expiry()
        if days_left is not None and days_left <= 0:
            flash('Licenca je istekla. Molimo obnovite licencu da biste nastavili sa korišćenjem aplikacije.', 'danger')
            return redirect(url_for('main.license_info'))

    student_id = request.form.get('student_id', type=int)
    source_service_id = request.form.get('source_service', type=int)
    target_service_id = request.form.get('target_service', type=int)
    amount = request.form.get('amount', type=float)
    amount = round(amount, 2)  # Zaokružite na 2 decimale
    transfer_note = request.form.get('transfer_note', '')
    
    if not all([student_id, source_service_id, target_service_id, amount]) or source_service_id == target_service_id:
        flash('Greška: Nedostaju potrebni podaci ili je izabrana ista usluga za izvor i cilj.', 'danger')
        return redirect(url_for('transactions.transfer_funds', student_id=student_id))
    
    # Provera da li je iznos validan i da li izvorna usluga ima dovoljno sredstava
    # Dobavljamo transakcije direktno za tačniji obračun
    transaction_records = TransactionRecord.query.filter_by(student_id=student_id, service_item_id=source_service_id).all()
    
    debt_amount = sum(record.student_debt_total for record in transaction_records if record.student_debt_id)
    payment_amount = sum(record.student_debt_total for record in transaction_records if record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id)
    
    saldo = debt_amount - payment_amount
    
    # Proveravamo da li usluga ima višak sredstava (negativan saldo)
    if saldo >= 0:
        flash('Greška: Izabrana izvorna usluga nema višak sredstava.', 'danger')
        return redirect(url_for('transactions.transfer_funds', student_id=student_id))
    
    if amount > round(abs(saldo), 2):
        flash(f'Greška: Iznos za preknjižavanje ne može biti veći od viška na izvornoj usluzi ({abs(saldo):.2f}).', 'danger')
        flash(f'debug: {amount=} | {abs(saldo)=}', 'danger')
        return redirect(url_for('transactions.transfer_funds', student_id=student_id))
    
    try:
        # Kreiranje zapisa o preknjižavanju
        fund_transfer = FundTransfer(
            student_id=student_id,
            source_service_id=source_service_id,
            target_service_id=target_service_id,
            amount=amount,
            note=transfer_note
        )
        db.session.add(fund_transfer)
        db.session.flush()  # Da bismo dobili ID pre commit-a
        
        # Kreiranje transakcije za smanjenje viška na izvornoj usluzi
        source_transaction = TransactionRecord(
            student_id=student_id,
            service_item_id=source_service_id,
            student_debt_total=-amount,  # Negativan iznos koji predstavlja "trošak" tj. smanjenje viška
            purpose_of_payment=f"Preknjižavanje na uslugu ID: {target_service_id}",
            fund_transfer_id=fund_transfer.id
        )
        db.session.add(source_transaction)
        
        # Kreiranje transakcije za umanjenje dugovanja na ciljnoj usluzi
        target_transaction = TransactionRecord(
            student_id=student_id,
            service_item_id=target_service_id,
            student_debt_total=amount,  # Pozitivan iznos koji predstavlja "uplatu" tj. umanjenje dugovanja
            purpose_of_payment=f"Preknjižavanje sa usluge ID: {source_service_id}",
            fund_transfer_id=fund_transfer.id
        )
        db.session.add(target_transaction)
        
        db.session.commit()
        flash('Preknjižavanje uspešno izvršeno.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Greška prilikom preknjižavanja: {str(e)}', 'danger')
    
    return redirect(url_for('transactions.transfer_funds', student_id=student_id))


@transactions.route('/transfers_list', methods=['GET'])
@login_required
def transfers_list():
    """Prikaz liste svih preknjižavanja i rasknjižavanja"""
    # Provera licence
    school = School.query.first()
    if school and school.license_expiry_date:
        days_left = school.days_until_license_expiry()
        if days_left is not None and days_left <= 0:
            flash('Licenca je istekla. Molimo obnovite licencu da biste nastavili sa korišćenjem aplikacije.', 'danger')
            return redirect(url_for('main.license_info'))

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    
    # Pretraga preknjižavanja
    transfer_query = FundTransfer.query
    writeoff_query = DebtWriteOff.query
    
    # Filtriranje po datumu ako je definisano
    if start_date and end_date:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        end_date_obj = end_date_obj.replace(hour=23, minute=59, second=59)
        transfer_query = transfer_query.filter(FundTransfer.transfer_date.between(start_date_obj, end_date_obj))
        writeoff_query = writeoff_query.filter(DebtWriteOff.writeoff_date.between(start_date_obj, end_date_obj))
    
    transfers = transfer_query.order_by(FundTransfer.transfer_date.desc()).all()
    writeoffs = writeoff_query.order_by(DebtWriteOff.writeoff_date.desc()).all()
    
    # Kombinovanje u jednu listu sa oznakom tipa
    combined_list = []
    for transfer in transfers:
        combined_list.append({
            'type': 'transfer',
            'id': transfer.id,
            'date': transfer.transfer_date,
            'student': transfer.student,
            'amount': transfer.amount,
            'note': transfer.note,
            'data': transfer
        })
    
    for writeoff in writeoffs:
        combined_list.append({
            'type': 'writeoff',
            'id': writeoff.id,
            'date': writeoff.writeoff_date,
            'student': writeoff.student,
            'amount': writeoff.amount,
            'note': writeoff.note,
            'data': writeoff
        })
    
    # Sortiranje po datumu
    combined_list.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('transfers_list.html',
                         combined_list=combined_list,
                         start_date=start_date,
                         end_date=end_date,
                         legend="Lista preknjižavanja i rasknjižavanja", 
                         title="Lista preknjižavanja i rasknjižavanja",
                         route_name="transfers_list")


@transactions.route('/view_transfer/<int:transfer_id>', methods=['GET'])
@login_required
def view_transfer(transfer_id):
    """Prikaz detalja preknjižavanja"""
    # Provera licence
    school = School.query.first()
    if school and school.license_expiry_date:
        days_left = school.days_until_license_expiry()
        if days_left is not None and days_left <= 0:
            flash('Licenca je istekla. Molimo obnovite licencu da biste nastavili sa korišćenjem aplikacije.', 'danger')
            return redirect(url_for('main.license_info'))

    transfer = FundTransfer.query.get_or_404(transfer_id)
    
    # Dobavljanje povezanih transakcija
    transactions = TransactionRecord.query.filter_by(fund_transfer_id=transfer_id).all()
    
    return render_template('view_transfer.html',
                          transfer=transfer,
                          transactions=transactions,
                          legend="Detalji preknjižavanja", 
                          title="Detalji preknjižavanja",
                          route_name="view_transfer")


@transactions.route('/write_off_debt', methods=['POST'])
@login_required
def write_off_debt():
    """Obrada zahteva za rasknjižavanje dugovanja"""
    # Provera licence
    school = School.query.first()
    if school and school.license_expiry_date:
        days_left = school.days_until_license_expiry()
        if days_left is not None and days_left <= 0:
            flash('Licenca je istekla. Molimo obnovite licencu da biste nastavili sa korišćenjem aplikacije.', 'danger')
            return redirect(url_for('main.license_info'))

    student_id = request.form.get('student_id', type=int)
    debt_service_id = request.form.get('debt_service', type=int)
    writeoff_amount = request.form.get('writeoff_amount', type=float)
    writeoff_amount = round(writeoff_amount, 2)
    writeoff_note = request.form.get('writeoff_note', '')
    password = request.form.get('password', '')
    
    # Validacija osnovnih podataka
    if not all([student_id, debt_service_id, writeoff_amount, password]):
        flash('Greška: Nedostaju potrebni podaci.', 'danger')
        return redirect(url_for('transactions.transfer_funds', student_id=student_id))
    
    # Provera lozinke
    if not bcrypt.check_password_hash(current_user.user_password, password):
        flash('Greška: Neispravna lozinka.', 'danger')
        return redirect(url_for('transactions.transfer_funds', student_id=student_id))
    
    # Provera da li usluga ima dugovanje i da li je iznos validan
    transaction_records = TransactionRecord.query.filter_by(
        student_id=student_id, 
        service_item_id=debt_service_id
    ).all()
    
    debt_amount = sum(record.student_debt_total for record in transaction_records if record.student_debt_id)
    payment_amount = sum(record.student_debt_total for record in transaction_records if record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id)
    
    saldo = debt_amount - payment_amount
    
    # Proveravamo da li usluga ima dugovanje (pozitivan saldo)
    if saldo <= 0:
        flash('Greška: Izabrana usluga nema dugovanje.', 'danger')
        return redirect(url_for('transactions.transfer_funds', student_id=student_id))
    
    if writeoff_amount > round(saldo, 2):
        flash(f'Greška: Iznos za rasknjižavanje ne može biti veći od trenutnog duga ({saldo:.2f}).', 'danger')
        return redirect(url_for('transactions.transfer_funds', student_id=student_id))
    
    try:
        # Kreiranje zapisa o rasknjižavanju
        debt_writeoff = DebtWriteOff(
            student_id=student_id,
            service_id=debt_service_id,
            amount=writeoff_amount,
            note=writeoff_note,
            user_id=current_user.id
        )
        db.session.add(debt_writeoff)
        db.session.flush()
        
        # Kreiranje transakcije za umanjenje dugovanja
        writeoff_transaction = TransactionRecord(
            student_id=student_id,
            service_item_id=debt_service_id,
            student_debt_total=writeoff_amount,
            purpose_of_payment=f"Rasknjižavanje dugovanja{': ' + writeoff_note if writeoff_note else ''}",
            debt_writeoff_id=debt_writeoff.id
        )
        db.session.add(writeoff_transaction)
        
        db.session.commit()
        flash('Rasknjižavanje dugovanja uspešno izvršeno.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logging.error(f'Greška prilikom rasknjižavanja: {str(e)}')
        flash(f'Greška prilikom rasknjižavanja: {str(e)}', 'danger')
    
    return redirect(url_for('transactions.transfer_funds', student_id=student_id))


@transactions.route('/view_writeoff/<int:writeoff_id>', methods=['GET'])
@login_required
def view_writeoff(writeoff_id):
    """Prikaz detalja rasknjižavanja dugovanja"""
    # Provera licence
    school = School.query.first()
    if school and school.license_expiry_date:
        days_left = school.days_until_license_expiry()
        if days_left is not None and days_left <= 0:
            flash('Licenca je istekla. Molimo obnovite licencu da biste nastavili sa korišćenjem aplikacije.', 'danger')
            return redirect(url_for('main.license_info'))

    writeoff = DebtWriteOff.query.get_or_404(writeoff_id)
    
    # Dobavljanje povezanih transakcija
    transactions = TransactionRecord.query.filter_by(debt_writeoff_id=writeoff_id).all()
    
    return render_template('view_writeoff.html',
                          writeoff=writeoff,
                          transactions=transactions,
                          legend="Detalji rasknjižavanja", 
                          title="Detalji rasknjižavanja",
                          route_name="view_writeoff")