import itertools
import json
import logging
import os
from datetime import datetime, date
from flask import Blueprint, render_template, url_for, flash, redirect, request, abort, current_app
from flask_login import login_required, current_user
from onetouch.models import Student, ServiceItem, Teacher, User, TransactionRecord, School
from onetouch.transactions.functions import gen_report_student, gen_report_school, gen_report_student_list, send_mail, add_fonts
from onetouch.overviews.functions import get_filtered_transactions_data, add_filter_info_to_pdf
from flask_mail import Message
from onetouch import mail, app
from sqlalchemy.exc import SQLAlchemyError

overviews = Blueprint('overviews', __name__)


@overviews.route("/overview_students", methods=['GET', 'POST'])
@login_required
def overview_students():
    try:
        route_name = request.endpoint
        danas = date.today()
        
        # Dobavljanje parametara iz URL-a
        try:
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            service_id = request.args.get('service_id')
            razred = request.args.get('razred')
            odeljenje = request.args.get('odeljenje')
            dugovanje = request.args.get('debts')
            preplata = request.args.get('overpayments')
            
            logging.debug(f'debug: {start_date=} {end_date=} {service_id=} {razred=} {odeljenje=} {dugovanje=} {preplata=}')
            
            # Postavljanje podrazumevanih vrednosti
            service_id = '0' if not service_id else service_id
            razred = '' if not razred else razred
            odeljenje = '' if not odeljenje else odeljenje
            dugovanje = True if dugovanje == 'true' else False
            preplata = True if preplata == 'true' else False
            
            logging.debug(f'nakon prilagođavanja: {razred=} {odeljenje=}')
            logging.debug(f'{start_date=} {end_date=} {service_id=}')
            
            # Postavljanje datuma
            current_year = request.args.get('current_year')
            use_school_year = current_year == 'true'
            
            # Provera da li je current_year promenjen iz true u false (switch isključen)
            current_year_changed = request.args.get('current_year') is not None
            
            if start_date is None or end_date is None or use_school_year or (current_year_changed and not use_school_year):
                # Ako je zahtevana tekuća školska godina, postavi odgovarajuće datume
                if use_school_year:
                    if danas.month >= 9:  # Septembar ili kasnije
                        start_date = danas.replace(month=9, day=1)
                        end_date = danas.replace(month=8, day=31, year=danas.year+1)
                    else:  # Pre septembra
                        start_date = danas.replace(month=9, day=1, year=danas.year-1)
                        end_date = danas.replace(month=8, day=31)
                # Ako je switch isključen, vrati na podrazumevane vrednosti
                elif current_year_changed and not use_school_year:
                    start_date = danas.replace(month=9, day=1, year=2020)
                    if danas.month < 9:
                        end_date = danas.replace(month=8, day=31)
                    else:
                        end_date = danas.replace(month=8, day=31, year=danas.year+1)
                # Podrazumevane vrednosti ako nije ništa od gore navedenog
                else:
                    start_date = danas.replace(month=9, day=1, year=2020)
                    if danas.month < 9:
                        end_date = danas.replace(month=8, day=31)
                    else:
                        end_date = danas.replace(month=8, day=31, year=danas.year+1)
            
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                
        except ValueError as e:
            logging.error(f'Greška pri obradi datuma: {str(e)}')
            flash('Neispravan format datuma.', 'danger')
            return redirect(url_for('main.home'))
            
        try:
            # Dobavljanje transakcija iz baze
            records = TransactionRecord.query.join(Student).filter(Student.student_class < 9).all()
            logging.info(f'sve transakcije: {len(records)=}')
            
            filtered_records = []
            
            # Filtriranje po razredu i odeljenju
            if razred == '' and odeljenje == '':
                for record in records:
                    if record.student_debt_id:
                        if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                            filtered_records.append(record)
                    elif record.student_payment_id:
                        if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                            filtered_records.append(record)
            elif razred != '' and odeljenje == '':
                for record in records:
                    current_class = record.transaction_record_student.student_class
                    if current_class == int(razred):
                        if record.student_debt_id:
                            if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                                filtered_records.append(record)
                        elif record.student_payment_id:
                            if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                                filtered_records.append(record)
            elif odeljenje != '' and razred == '':
                for record in records:
                    current_section = record.transaction_record_student.student_section
                    if current_section == int(odeljenje):
                        if record.student_debt_id:
                            if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                                filtered_records.append(record)
                        elif record.student_payment_id:
                            if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                                filtered_records.append(record)
            else:
                for record in records:
                    current_class = record.transaction_record_student.student_class
                    current_section = record.transaction_record_student.student_section
                    if current_class == int(razred) and current_section == int(odeljenje):
                        if record.student_debt_id:
                            if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                                filtered_records.append(record)
                        elif record.student_payment_id:
                            if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                                filtered_records.append(record)
                                
            options = []
            for record in filtered_records:
                if record.service_item_id not in [option['value'] for option in options]:
                    options.append({
                        'value': record.service_item_id,
                        'label': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
                    })
            logging.debug(f'{options=}')
            
            export_data = []
            for record in filtered_records:
                if service_id == '0' or int(service_id) == record.service_item_id:
                    if record.student_id in [student['student_id'] for student in export_data]:
                        existing_record = next((item for item in export_data if item["student_id"] == record.student_id), None)
                        existing_record['student_debt'] += record.student_debt_total if record.student_debt_id else 0
                        existing_record['student_payment'] += record.student_debt_total if record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id else 0
                        existing_record['saldo'] = existing_record['student_debt'] - existing_record['student_payment']

                    else:
                        logging.debug(f'{record=}')
                        new_record = {
                            'student_id': record.student_id,
                            'student_name': record.transaction_record_student.student_name,
                            'student_surname': record.transaction_record_student.student_surname,
                            'student_class': record.transaction_record_student.student_class,
                            'student_section': record.transaction_record_student.student_section,
                            'student_debt': record.student_debt_total if record.student_debt_id else 0,
                            'student_payment': record.student_debt_total if record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id else 0,
                        }
                        new_record['saldo'] = new_record['student_debt'] - new_record['student_payment']
                        logging.debug(f'{new_record=}')
                        if int(new_record['student_id']) > 1:
                            export_data.append(new_record)
            # export_data = [dict(t) for t in {tuple(d.items()) for d in export_data}]
            
            logging.info(f'{export_data=}')
            
            filtered_export_data = []
            for record in export_data:
                if dugovanje:
                    if record['saldo'] > 0:
                        filtered_export_data.append(record)
                elif preplata:
                    if record['saldo'] < 0:
                        filtered_export_data.append(record)
            if len(filtered_export_data) > 0:
                export_data = filtered_export_data
            
            students = Student.query.filter(Student.student_class < 9).all()
            teachers = Teacher.query.all()
            
            report_students = gen_report_student_list(export_data, start_date, end_date, filtered_records, service_id, razred, odeljenje, dugovanje, preplata)
            
            school = School.query.first()
            return render_template('overview_students.html', 
                                    title='Pregled po učeniku', 
                                    legend="Pregled po učeniku", 
                                    export_data=export_data,
                                    students=students,
                                    teachers=teachers,
                                    start_date=start_date,
                                    end_date=end_date,
                                    service_id=service_id,
                                    options=options,
                                    razred=razred,
                                    odeljenje=odeljenje,
                                    dugovanje=dugovanje,
                                    preplata=preplata,
                                    route_name=route_name,
                                    use_school_year=use_school_year,
                                    school=school)
            
        except SQLAlchemyError as e:
            logging.error(f'Greška pri pristupu bazi podataka: {str(e)}')
            flash('Došlo je do greške pri učitavanju podataka.', 'danger')
            return redirect(url_for('main.home'))
            
    except Exception as e:
        logging.error(f'Neočekivana greška u overview_students: {str(e)}')
        flash('Došlo je do neočekivane greške.', 'danger')
        return redirect(url_for('main.home'))


@overviews.route("/overview_student/<int:student_id>", methods=['GET', 'POST'])
@login_required
def overview_student(student_id):
    try:
        route_name = request.endpoint
        danas = date.today()
        
        # Dohvatanje i provera studenta
        try:
            student = Student.query.get_or_404(student_id)
        except SQLAlchemyError as e:
            logging.error(f'Greška pri dohvatanju učenika (ID: {student_id}): {str(e)}')
            flash('Učenik nije pronađen.', 'danger')
            return redirect(url_for('main.home'))
            
        # Obrada datuma
        try:
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            current_year = request.args.get('current_year')
            
            # Provera da li je zahtevana tekuća školska godina
            use_school_year = current_year == 'true'
            
            # Provera da li je current_year promenjen iz true u false (switch isključen)
            current_year_changed = request.args.get('current_year') is not None
            
            if start_date is None or end_date is None or use_school_year or (current_year_changed and not use_school_year):
                # Ako je zahtevana tekuća školska godina, postavi odgovarajuće datume
                if use_school_year:
                    if danas.month >= 9:  # Septembar ili kasnije
                        start_date = danas.replace(month=9, day=1)
                        end_date = danas.replace(month=8, day=31, year=danas.year+1)
                    else:  # Pre septembra
                        start_date = danas.replace(month=9, day=1, year=danas.year-1)
                        end_date = danas.replace(month=8, day=31)
                # Ako je switch isključen, vrati na podrazumevane vrednosti
                elif current_year_changed and not use_school_year:
                    start_date = danas.replace(month=9, day=1, year=2020)
                    if danas.month < 9:
                        end_date = danas.replace(month=8, day=31)
                    else:
                        end_date = danas.replace(month=8, day=31, year=danas.year+1)
                # Podrazumevane vrednosti ako nije ništa od gore navedenog
                else:
                    start_date = danas.replace(month=9, day=1, year=2020)
                    if danas.month < 9:
                        end_date = danas.replace(month=8, day=31)
                    else:
                        end_date = danas.replace(month=8, day=31, year=danas.year+1)
            
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                
            logging.debug(f'Datumi: {start_date=} {end_date=} {use_school_year=}')
            
        except ValueError as e:
            logging.error(f'Greška pri obradi datuma: {str(e)}')
            flash('Neispravan format datuma.', 'danger')
            return redirect(url_for('main.home'))
            
        try:
            # Dohvatanje transakcija
            transaction_records = TransactionRecord.query.filter_by(student_id=student_id).all()
            
            data = []
            unique_services_list = []
            
            # Obrada transakcija
            for record in transaction_records:
                # Dodavanje usluge u listu bez obzira na to da li je zaduženje pozitivno ili negativno
                if (record.service_item_id not in [item['id'] for item in unique_services_list]) and record.student_debt_total != 0:
                    try:
                        # Određivanje datuma na osnovu tipa transakcije
                        if record.student_debt_id:
                            transaction_date = record.transaction_record_student_debt.student_debt_date
                        elif record.student_payment_id:
                            transaction_date = record.transaction_record_student_payment.payment_date
                        elif record.fund_transfer_id:
                            transaction_date = record.transfer_record.transfer_date
                        elif record.debt_writeoff_id:
                            transaction_date = record.writeoff_record.writeoff_date
                        else:
                            continue  # Preskoči ako nije nijedan od očekivanih tipova
                        
                        service_data = {
                            'id': record.service_item_id,
                            'service_debt_id': record.student_debt_id if record.student_debt_id else ServiceItem.query.get_or_404(int(record.service_item_id)).id,
                            'service_item_date': record.transaction_record_service_item.service_item_date,
                            'service_name': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name,
                            'date': transaction_date,
                        }
                        
                        if service_data['date'].date() >= start_date and service_data['date'].date() <= end_date:
                            unique_services_list.append(service_data)
                            
                    except SQLAlchemyError as e:
                        logging.error(f'Greška pri dohvatanju podataka o usluzi: {str(e)}')
                        continue
                
                try:
                    if record.student_debt_id:
                        rata = sum(1 for item in data if item["service_item_id"] == record.service_item_id) + 1
                        description = f'{record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name} / Rata {rata}'
                        date_ = record.transaction_record_student_debt.student_debt_date
                    elif record.student_payment_id:
                        description = f'{record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                        date_ = record.transaction_record_student_payment.payment_date
                    elif record.fund_transfer_id:
                        # Preknjižavanje
                        logging.debug(f"Fund transfer record: {record.id}, amount: {record.student_debt_total}")
                        if record.student_debt_total > 0:  # Pozitivan iznos (smanjenje viška)
                            description = f'Preknjižavanje na: {record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                        else:  # Negativan iznos (povećanje sredstava)
                            description = f'Preknjižavanje sa: {record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                        date_ = record.transfer_record.transfer_date
                    elif record.debt_writeoff_id:
                        # Rasknjižavanje dugovanja
                        description = f'Rasknjižavanje: {record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                        date_ = record.writeoff_record.writeoff_date
                        
                    if record.student_debt_total:
                        # Određivanje tipa transakcije i pravilno postavljanje debt_amount i payment_amount
                        debt_amount = 0
                        payment_amount = 0
                        
                        if record.student_debt_id:
                            # Ovo je zaduženje - može biti pozitivno (dug) ili negativno (kredit/preplata)
                            debt_amount = record.student_debt_total
                            logging.debug(f"ZADUŽENJE: {record.id}, {debt_amount}, {date_}, {description}")
                        elif record.student_payment_id:
                            # Ovo je uplata - koristi apsolutnu vrednost
                            payment_amount = abs(record.student_debt_total)
                            logging.debug(f"UPLATA: {record.id}, {payment_amount}, {date_}, {description}")
                        elif record.fund_transfer_id:
                            # Preknjižavanje - posebna logika zavisno od smera
                            if record.student_debt_total != None:
                                # Preknjižavanje NA ovu uslugu - povećava dug
                                debt_amount = 0
                                payment_amount = record.student_debt_total
                        elif record.debt_writeoff_id:
                            # Rasknjižavanje dugovanja - smanjuje dug
                            payment_amount = abs(record.student_debt_total)
                            logging.debug(f"RASKNJIŽAVANJE: {record.id}, {payment_amount}, {date_}, {description}")
                        
                        # Kreiramo objekt za transakciju sa precizno definisanim vrednostima
                        test_data = {
                            'id': record.id,
                            'service_item_id': record.service_item_id,
                            'student_payment_id': record.student_payment_id,
                            'fund_transfer_id': record.fund_transfer_id,
                            'debt_writeoff_id': record.debt_writeoff_id,
                            'write_off_id': record.debt_writeoff_id,  # Alias za template
                            'date': date_,
                            'description': description,
                            'debt_amount': debt_amount,
                            'payment_amount': payment_amount,
                        }
                        
                        # Izračunavanje salda na osnovu svih prethodnih transakcija iste usluge
                        previous_items = [item for item in data if item['service_item_id'] == test_data['service_item_id']]
                        
                        if previous_items:
                            # Ako već postoje transakcije za ovu uslugu, uzimamo poslednji saldo
                            previous_saldo = previous_items[-1]['saldo']
                            # Novi saldo je prethodni saldo plus zaduženje minus uplata
                            test_data['saldo'] = previous_saldo + debt_amount - payment_amount
                            logging.debug(f"Saldo RAČUNANJE (postojeća usluga): {test_data['id']}, prev={previous_saldo}, debt={debt_amount}, payment={payment_amount}, new={test_data['saldo']}")
                        else:
                            # Prva transakcija za ovu uslugu
                            test_data['saldo'] = debt_amount - payment_amount
                            logging.debug(f"Saldo RAČUNANJE (prva transakcija): {test_data['id']}, debt={debt_amount}, payment={payment_amount}, new={test_data['saldo']}")
                        
                        # Dodatna provera da li je saldo ispravno izračunat
                        total_debt = sum(item['debt_amount'] for item in previous_items) + debt_amount
                        total_payment = sum(item['payment_amount'] for item in previous_items) + payment_amount
                        expected_saldo = total_debt - total_payment
                        
                        # Ako postoji razlika, koristimo očekivani saldo
                        if abs(test_data['saldo'] - expected_saldo) > 0.001:  # Tolerancija za float razlike
                            logging.warning(f"Korekcija salda: {test_data['saldo']} -> {expected_saldo}")
                            test_data['saldo'] = expected_saldo
                            
                        data.append(test_data)
                        
                except Exception as e:
                    logging.error(f'Greška pri obradi transakcije (ID: {record.id}): {str(e)}')
                    continue
            
            # Sortiranje podataka po usluzi i datumu
            data.sort(key=lambda x: (x['service_item_id'], x['date']))
            
            # Nakon sortiranja, izvrši ponovno izračunavanje salda za svaku uslugu
            # kako bi osigurao pravilno prikazan saldo u svakom redu
            service_saldo = {}
            for i, item in enumerate(data):
                service_id = item['service_item_id']
                
                # Inicijalizacija salda za novu uslugu
                if service_id not in service_saldo:
                    service_saldo[service_id] = 0
                
                # Izračunavanje salda nakon svake transakcije
                old_saldo = service_saldo[service_id]
                
                # Zaduženje povećava saldo
                service_saldo[service_id] += item['debt_amount']
                # Uplata smanjuje saldo
                service_saldo[service_id] -= item['payment_amount']
                
                logging.debug(f"Transakcija {item['id']}: {old_saldo:.2f} + {item['debt_amount']:.2f} - {item['payment_amount']:.2f} = {service_saldo[service_id]:.2f}")
                
                # Postavlja saldo za trenutni red
                data[i]['saldo'] = service_saldo[service_id]
                logging.debug(f"Finalni saldo za red {item['id']}: {data[i]['saldo']:.2f}")
            
            # Sortiranje liste usluga
            unique_services_list.sort(key=lambda x: x['id'], reverse=True)
            
            report_student = gen_report_student(data, unique_services_list, student, start_date, end_date)
            
            return render_template('overview_student.html',
                                title='Pregled učenika',
                                legend=f'Pregled učenika: {student.student_name} {student.student_surname} ({student.student_class}/{student.student_section})',
                                student=student,
                                data=data,
                                unique_services_list=unique_services_list,
                                start_date=start_date,
                                end_date=end_date,
                                route_name=route_name,
                                use_school_year=use_school_year)
                                
        except SQLAlchemyError as e:
            logging.error(f'Greška pri pristupu bazi podataka: {str(e)}')
            flash('Došlo je do greške pri učitavanju podataka.', 'danger')
            return redirect(url_for('main.home'))
            
    except Exception as e:
        logging.error(f'Neočekivana greška u overview_student: {str(e)}')
        flash('Došlo je do neočekivane greške.', 'danger')
        return redirect(url_for('overviews.overview_students'))


@overviews.route("/overview_sections", methods=['GET', 'POST']) # odeljenja #! dodati try-except blok za ovu rutu
def overview_sections():
    route_name = request.endpoint
    danas = date.today()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    service_id = request.args.get('service_id')
    razred = request.args.get('razred')
    odeljenje = request.args.get('odeljenje')
    logging.debug(f'pri uvoženju podataka: {razred=} {odeljenje=}')
    if not service_id:
        service_id = '0' # ako nije definisana promenjiva na početku, dodeli joj '0' što predstavlja sve usluge
    if not razred:
        razred = '' # ako nije definisana promenjiva na početku, dodeli joj '' što predstavlja sve razrede
    if not odeljenje:
        odeljenje = '' # ako nije definisana promenjiva na početku, dodeli joj '' što predstavlja sve odeljenja
    logging.debug(f'nakon prilagođavanja: {razred=} {odeljenje=}')
    logging.debug(f'{start_date=} {end_date=} {service_id=}')
    current_year = request.args.get('current_year')
    use_school_year = current_year == 'true'
    
    # Provera da li je current_year promenjen iz true u false (switch isključen)
    current_year_changed = request.args.get('current_year') is not None
            
    if start_date is None or end_date is None or use_school_year or (current_year_changed and not use_school_year):
        # Ako je zahtevana tekuća školska godina, postavi odgovarajuće datume
        if use_school_year:
            if danas.month >= 9:  # Septembar ili kasnije
                start_date = danas.replace(month=9, day=1)
                end_date = danas.replace(month=8, day=31, year=danas.year+1)
            else:  # Pre septembra
                start_date = danas.replace(month=9, day=1, year=danas.year-1)
                end_date = danas.replace(month=8, day=31)
        # Ako je switch isključen, vrati na podrazumevane vrednosti
        elif current_year_changed and not use_school_year:
            start_date = danas.replace(month=9, day=1, year=2020)
            if danas.month < 9:
                end_date = danas.replace(month=8, day=31)
            else:
                end_date = danas.replace(month=8, day=31, year=danas.year+1)
        # Podrazumevane vrednosti ako nije ništa od gore navedenog
        else:
            start_date = danas.replace(month=9, day=1, year=2020)
            if danas.month < 9:
                end_date = danas.replace(month=8, day=31)
            else:
                end_date = danas.replace(month=8, day=31, year=danas.year+1)
    
    logging.debug(f'posle if bloka: {start_date=} {end_date=} {use_school_year=}')
    if type(start_date) is str:
        # Konvertuj start_date i end_date u datetime.date objekte
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    logging.debug(f'posle if ako je string: {start_date=} {end_date=}')
    records = TransactionRecord.query.all()
    logging.debug(f'sve transakcije: {len(records)=}')
    
    filtered_records = []
    if razred == '' and odeljenje == '': #! ako nisu definisani raztrd i odeljenje, izlistaj sve razrede i odeljenja
        for record in records:
            if record.student_debt_id:
                if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                    filtered_records.append(record)
            elif record.student_payment_id:
                if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                    filtered_records.append(record)
    elif razred != '' and odeljenje == '': #! ako je definisan razred, izlistaj sva odeljenja tog razreda
        for record in records:
            current_class = record.transaction_record_student.student_class
            if current_class == int(razred):
                if record.student_debt_id:
                    if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                        filtered_records.append(record)
                elif record.student_payment_id:
                    if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                        filtered_records.append(record)
    elif odeljenje != '' and razred == '': #! ako je definisana odeljenja, izlistaj sve studente tog odeljenja
        for record in records:
            current_section = record.transaction_record_student.student_section
            if current_section == int(odeljenje):
                if record.student_debt_id:
                    if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                        filtered_records.append(record)
                elif record.student_payment_id:
                    if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                        filtered_records.append(record)
    else:
        for record in records:
            current_class = record.transaction_record_student.student_class
            current_section = record.transaction_record_student.student_section
            logging.debug(f'{current_class=} {current_section=}')
            logging.debug(f'{razred=} {odeljenje=}')
            if current_class == int(razred) and current_section == int(odeljenje):
                if record.student_debt_id:
                    if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                        filtered_records.append(record)
                elif record.student_payment_id:
                    if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                        filtered_records.append(record)
    logging.debug(f'nakon filtriranja: {len(filtered_records)=}')
    
    students = Student.query.filter(Student.student_class < 9).all()
    teachers = Teacher.query.all()
    teacher_clasroom_list = []
    for teacher in teachers:
        new_teacher = {
            'class': teacher.teacher_class,
            'section': teacher.teacher_section,
            'name': teacher.teacher_name,
            'surname': teacher.teacher_surname,
        }
        teacher_clasroom_list.append(new_teacher)
    logging.debug(f'{teacher_clasroom_list=}')
    
    unique_sections = []
    for student in students:
        if str(student.student_class) + '/' + str(student.student_section) not in [(section['section']) for section in unique_sections]:
            unique_sections.append({'section': str(student.student_class) + '/' + str(student.student_section)})
    unique_sections.sort(key=lambda x: x['section'])
    logging.debug(f'{unique_sections=}')
    options = []
    for record in filtered_records:
        if record.service_item_id not in [option['value'] for option in options]:
            options.append({
                'value': record.service_item_id,
                'label': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
            })
    
    data = []
    for section in unique_sections:
        for record in filtered_records:
            section_key = f"{record.transaction_record_student.student_class}/{record.transaction_record_student.student_section}" #odeljenje (npr: 1/1)
            if section['section'] == section_key:
                if service_id == '0' or int(service_id) == record.service_item_id:
                    if section_key in [(f"{existing_record['class']}/{existing_record['section']}") for existing_record in data]:
                        existing_record = next((item for item in data if item['class'] == record.transaction_record_student.student_class and item['section'] == record.transaction_record_student.student_section), None)
                        if existing_record:
                            existing_record['student_debt'] += record.student_debt_total if record.student_debt_id else 0
                            existing_record['student_payment'] += record.student_debt_total if record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id else 0
                            existing_record['saldo'] = existing_record['student_debt'] - existing_record['student_payment']
                    else:
                        new_record = {
                            'service_item_id': record.service_item_id,
                            'class': record.transaction_record_student.student_class,
                            'section': record.transaction_record_student.student_section,
                            'student_debt': record.student_debt_total if record.student_debt_id else 0,
                            'student_payment': record.student_debt_total if record.student_payment_id or record.fund_transfer_id or record.debt_writeoff_id else 0,
                        }
                        new_record['saldo'] = new_record['student_debt'] - new_record['student_payment']
                        new_record['teacher'] = next((item['name'] + ' ' + item['surname'] for item in teacher_clasroom_list if item['class'] == new_record['class'] and item['section'] == new_record['section']), None)
                        data.append(new_record)
    logging.info(f'{data=}')

    report_school = gen_report_school(data, start_date, end_date, filtered_records, service_id, razred, odeljenje)
    
    school = School.query.first()
    return render_template('overview_sections.html',
                            title='Pregled škole po uslugama', 
                            legend="Pregled škole po uslugama",
                            unique_sections=unique_sections,
                            data=data,
                            start_date=start_date,
                            end_date=end_date,
                            service_id=service_id,
                            options=options,
                            razred=razred,
                            odeljenje=odeljenje,
                            route_name=route_name,
                            use_school_year=use_school_year,
                            school=school)


@overviews.route("/overview_debts", methods=['GET', 'POST'])
def overview_debts():
    try:
        route_name = request.endpoint
        # Dobavljanje liste svih usluga za multiselect
        services = []
        try:
            service_items = ServiceItem.query.order_by(ServiceItem.service_item_date.desc()).all()
            
            for item in service_items:
                service = {
                    'id': item.id,
                    'name': f"{item.service_item_service.service_name} - {item.service_item_name}"
                }
                if service not in services:
                    services.append(service)
        except SQLAlchemyError as e:
            logging.error(f'Greška pri dobavljanju usluga: {str(e)}')
            flash('Došlo je do greške pri učitavanju usluga.', 'danger')
            
        # Podrazumevane vrednosti
        min_debt_amount = 0
        selected_services = []
        export_data = []
        
        # Obrada POST zahteva
        if request.method == 'POST':
            # Bezbedno konvertovanje vrednosti iz forme u float, sa proverom za prazan string
            min_debt_amount_str = request.form.get('minDebtAmount', '')
            min_debt_amount = round(float(min_debt_amount_str) if min_debt_amount_str.strip() else 0, 2)
            selected_services = request.form.getlist('selectedServices')
            print(f'{min_debt_amount=}')
            print(f'{selected_services=}')
            
            # Filtriranje transakcija po izabranim uslugama i minimalnom dugovanju
            try:
                records = TransactionRecord.query.join(Student).filter(Student.student_class < 9)
                
                # Filtriranje po izabranim uslugama ako su izabrane
                if selected_services:
                    records = records.filter(TransactionRecord.service_item_id.in_([int(s) for s in selected_services]))
                
                records = records.all()
                
                # Grupisanje po učeniku (sumiranje svih dugovanja po učeniku)
                student_data = {}
                services_by_student = {}  # Praćenje usluga po učeniku za detalje PDF-a
                
                for record in records:
                    student_id = record.student_id
                    
                    # Inicijalizacija podataka za učenika ako ne postoje
                    if student_id not in student_data:
                        student_data[student_id] = {
                            'student_id': student_id,
                            'student_name': record.transaction_record_student.student_name,
                            'student_surname': record.transaction_record_student.student_surname,
                            'student_class': record.transaction_record_student.student_class,
                            'student_section': record.transaction_record_student.student_section,
                            'student_debt': 0,
                            'student_payment': 0,
                            'saldo': 0
                        }
                        services_by_student[student_id] = {}
                    
                    # Inicijalizacija podataka po usluzi za detalje
                    service_id = record.service_item_id
                    if service_id not in services_by_student[student_id]:
                        services_by_student[student_id][service_id] = {
                            'service_item_id': service_id,
                            'service_name': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name,
                            'student_debt': 0,
                            'student_payment': 0,
                            'saldo': 0
                        }
                    
                    # Sabiranje zaduženja i uplata
                    if record.student_debt_id:
                        student_data[student_id]['student_debt'] += record.student_debt_total
                        services_by_student[student_id][service_id]['student_debt'] += record.student_debt_total
                    elif record.student_payment_id:
                        student_data[student_id]['student_payment'] += record.student_debt_total
                        services_by_student[student_id][service_id]['student_payment'] += record.student_debt_total
                    
                    # Ažuriranje salda po učeniku
                    student_data[student_id]['saldo'] = round(student_data[student_id]['student_debt'] - student_data[student_id]['student_payment'], 2)
                    
                    # Ažuriranje salda po usluzi
                    services_by_student[student_id][service_id]['saldo'] = round(services_by_student[student_id][service_id]['student_debt'] - services_by_student[student_id][service_id]['student_payment'], 2)
                
                # Filtriranje po minimalnom dugovanju i pretvaranje u listu
                for student_id, data in student_data.items():
                    if round(data['saldo'], 2) > min_debt_amount:
                        # Provera da li učenik ima i dugovanja i preplate po uslugama
                        has_debts = False
                        has_overpayments = False
                        
                        # Dodaj listu usluga za PDF izveštaj
                        data['services'] = list(services_by_student[student_id].values())
                        
                        # Proveri da li ima bar jednu uslugu sa preplatom i bar jednu sa dugovanjem
                        for service in data['services']:
                            rounded_saldo = round(service['saldo'], 2)
                            if abs(rounded_saldo) < 0.01:
                                continue
                            else:
                                if rounded_saldo > 0:  # Dugovanje
                                    has_debts = True
                                elif rounded_saldo < 0:  # Preplata
                                    has_overpayments = True
                        
                        # Dodaj indikatore o stanju za kasnije korišćenje u šablonu
                        data['has_debts'] = has_debts
                        data['has_overpayments'] = has_overpayments
                        
                        export_data.append(data)
                
                # Sortiranje po saldu (dugovanje) od najvećeg ka najmanjem
                export_data.sort(key=lambda x: x['saldo'], reverse=True)
                
                if not export_data:
                    flash('Nema učenika koji odgovaraju zadatim kriterijumima.', 'info')
                    
            except SQLAlchemyError as e:
                logging.error(f'Greška pri filtriranju dugovanja: {str(e)}')
                flash('Došlo je do greške pri filtriranju podataka.', 'danger')
        
        # Konvertujemo selected_services iz stringova u cele brojeve za pravilno poređenje u šablonu
        selected_services_int = [int(s) for s in selected_services] if selected_services else []
        
        return render_template('overview_debts.html',
                        title='Pregled dugovanja učenika',
                        legend='Pregled dugovanja učenika',
                        route_name=route_name,
                        services=services,
                        min_debt_amount=min_debt_amount,
                        selected_services=selected_services_int,
                        export_data=export_data)
    
    except Exception as e:
        logging.error(f'Greška pri pregledu dugovanja učenika: {str(e)}')
        flash('Greška pri pregledu dugovanja učenika.', 'danger')
        return redirect(url_for('main.home'))



@overviews.route("/send_student_report_email/<int:student_id>")
@login_required
def send_student_report_email(student_id):
    try:
        # Dobavljanje podataka o učeniku
        student = Student.query.get_or_404(student_id)
        
        # Provera da li učenik ima definisan mejl roditelja
        if not student.parent_email:
            flash('Učenik nema definisan mejl roditelja.', 'danger')
            return redirect(url_for('overviews.overview_student', student_id=student_id))
            
        # Dobavljanje perioda iz URL parametara
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        danas = date.today()
        
        # Postavljanje podrazumevanih vrednosti za datume ako nisu specifikovani
        if start_date is None or end_date is None:
            start_date = danas.replace(month=9, day=1, year=2020)
            if danas.month < 9:
                end_date = danas.replace(month=8, day=31)
            else:
                end_date = danas.replace(month=8, day=31, year=danas.year+1)
                
        # Konverzija datuma ako su stringovi
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            
        # Dobavljanje transakcija za učenika
        transaction_records = TransactionRecord.query.filter_by(student_id=student_id).all()
        
        data = []
        unique_services_list = []
        
        # Obrada transakcija - isti kod kao u overview_student
        for record in transaction_records:
            # Dodavanje usluge u listu bez obzira na to da li je zaduženje pozitivno ili negativno
            if (record.service_item_id not in [item['id'] for item in unique_services_list]) and record.student_debt_total != 0:
                try:
                    # Određivanje datuma na osnovu tipa transakcije
                    if record.student_debt_id:
                        transaction_date = record.transaction_record_student_debt.student_debt_date
                    elif record.student_payment_id:
                        transaction_date = record.transaction_record_student_payment.payment_date
                    elif record.fund_transfer_id:
                        transaction_date = record.transfer_record.transfer_date
                    elif record.debt_writeoff_id:
                        transaction_date = record.writeoff_record.writeoff_date
                    else:
                        continue  # Preskoči ako nije nijedan od očekivanih tipova
                    
                    service_data = {
                        'id': record.service_item_id,
                        'service_debt_id': record.student_debt_id if record.student_debt_id else ServiceItem.query.get_or_404(int(record.service_item_id)).id,
                        'service_item_date': record.transaction_record_service_item.service_item_date,
                        'service_name': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name,
                        'date': transaction_date,
                    }
                    
                    if service_data['date'].date() >= start_date and service_data['date'].date() <= end_date:
                        unique_services_list.append(service_data)
                        
                except SQLAlchemyError as e:
                    logging.error(f'Greška pri dohvatanju podataka o usluzi: {str(e)}')
                    continue
            
            try:
                if record.student_debt_id:
                    rata = sum(1 for item in data if item["service_item_id"] == record.service_item_id) + 1
                    description = f'{record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name} / Rata {rata}'
                    date_ = record.transaction_record_student_debt.student_debt_date
                elif record.student_payment_id:
                    description = f'{record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                    date_ = record.transaction_record_student_payment.payment_date
                elif record.fund_transfer_id:
                    # Preknjižavanje
                    if record.student_debt_total > 0:
                        description = f'Preknjižavanje na: {record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                    else:
                        description = f'Preknjižavanje sa: {record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                    date_ = record.transfer_record.transfer_date
                elif record.debt_writeoff_id:
                    description = f'Rasknjižavanje: {record.transaction_record_service_item.service_item_service.service_name} - {record.transaction_record_service_item.service_item_name}'
                    date_ = record.writeoff_record.writeoff_date
                    
                if record.student_debt_total:
                    # Određivanje tipa transakcije i pravilno postavljanje debt_amount i payment_amount
                    debt_amount = 0
                    payment_amount = 0
                    
                    if record.student_debt_id:
                        # Ovo je zaduženje - može biti pozitivno (dug) ili negativno (kredit/preplata)
                        debt_amount = record.student_debt_total
                    elif record.student_payment_id:
                        # Ovo je uplata - koristi apsolutnu vrednost
                        payment_amount = abs(record.student_debt_total)
                    elif record.fund_transfer_id:
                        # Preknjižavanje - posebna logika zavisno od smera
                        if record.student_debt_total != None:
                            debt_amount = 0
                            payment_amount = record.student_debt_total
                    elif record.debt_writeoff_id:
                        # Rasknjižavanje dugovanja - smanjuje dug
                        payment_amount = abs(record.student_debt_total)
                    
                    test_data = {
                        'id': record.id,
                        'service_item_id': record.service_item_id,
                        'student_payment_id': record.student_payment_id,
                        'fund_transfer_id': record.fund_transfer_id,
                        'debt_writeoff_id': record.debt_writeoff_id,
                        'date': date_,
                        'description': description,
                        'debt_amount': debt_amount,
                        'payment_amount': payment_amount,
                    }
                    
                    if test_data['service_item_id'] in [item['service_item_id'] for item in data]:
                        saldo_sum = [item['saldo'] for item in data if item['service_item_id'] == test_data['service_item_id']]
                        test_data['saldo'] = saldo_sum[-1] + test_data['debt_amount'] - test_data['payment_amount']
                    else:
                        test_data['saldo'] = test_data['debt_amount'] - test_data['payment_amount']
                        
                    data.append(test_data)
                    
            except Exception as e:
                logging.error(f'Greška pri obradi transakcije (ID: {record.id}): {str(e)}')
                continue
        
        data.sort(key=lambda x: (x['service_item_id'], x['date']))
        unique_services_list.sort(key=lambda x: x['id'], reverse=True)
        
        # Generisanje izveštaja
        gen_report_student(data, unique_services_list, student, start_date, end_date)
        
        # Putanja do generisanog izveštaja
        project_folder = os.path.dirname(os.path.dirname((os.path.abspath(__file__))))
        user_folder = f'{project_folder}/static/reports/user_{current_user.id}'
        file_path = f'{user_folder}/report_student.pdf'
        file_name = 'report_student.pdf'
        
        # Slanje mejla
        school = School.query.first()
        student_name = f'{student.student_name} {student.student_surname}'
        parent_email = student.parent_email
        
        try:
            sender = (f'{school.school_name}', f'{current_app.config["MAIL_USERNAME"]}')
            subject = f"{school.school_name} | Izveštaj za učenika: {student_name} ({student.student_class}/{student.student_section})" 
            
            message = Message(subject, 
                            sender=sender,
                            recipients=[parent_email])
            
            # Telo mejla
            message.html = render_template(
                'message_html_send_report.html',
                student=student,
                school=school,
                start_date=start_date,
                end_date=end_date
            )
            
            # Prilaganje PDF izveštaja
            with app.open_resource(file_path) as attachment:
                message.attach(file_name, 'application/pdf', attachment.read())
                
            mail.send(message)
            flash('Izveštaj je uspešno poslat na mejl roditelja.', 'success')
            logging.info(f'Izveštaj poslat na mejl: {parent_email} za učenika: {student_name}')
            
        except Exception as e:
            flash(f'Došlo je do greške prilikom slanja izveštaja: {str(e)}', 'danger')
            logging.error(f'Greška pri slanju izveštaja na mejl: {str(e)}')
            
        return redirect(url_for('overviews.overview_student', student_id=student_id))
        
    except Exception as e:
        flash(f'Došlo je do neočekivane greške: {str(e)}', 'danger')
        logging.error(f'Neočekivana greška u send_student_report_email: {str(e)}')
        return redirect(url_for('overviews.overview_student', student_id=student_id))


@overviews.route("/generate_pdf_reports/<int:student_id>")
@login_required
def generate_pdf_reports(student_id):
    """
    Generiše dva PDF izveštaja za učenika:
    1. Listu usluga sa pozitivnim saldom
    2. Uplatnice za usluge sa pozitivnim saldom
    """
    try:
        # Kreiranje PDF-a sa listom usluga
        project_folder = os.path.dirname(os.path.dirname((os.path.abspath(__file__))))
        user_folder = f'{project_folder}/static/reports/user_{current_user.id}'
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
            
        # Dobavljanje parametara iz URL-a
        min_debt_amount_str = request.args.get('min_debt_amount', '0')
        min_debt_amount = float(min_debt_amount_str) if min_debt_amount_str.strip() else 0
        
        selected_services_param = request.args.get('selected_services', '')
        selected_services = selected_services_param.split(',') if selected_services_param else []
        
        # Dobavljanje filtriranih podataka o transakcijama korišćenjem pomoćne funkcije
        services_with_positive_saldo, selected_service_names, student = get_filtered_transactions_data(
            student_id, selected_services, min_debt_amount)
        
        if not services_with_positive_saldo:
            flash('Učenik nema dugovanja ni za jednu uslugu.', 'info')
            return redirect(url_for('overviews.overview_debts'))
        
        # Generisanje PDF-a sa listom usluga koje imaju pozitivan saldo
        from fpdf import FPDF
        from onetouch.transactions.functions import add_fonts
        
        pdf = FPDF()
        add_fonts(pdf)
        pdf.add_page()
        
        # Dodavanje informacija o filtriranju korišćenjem pomoćne funkcije
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
        
        # Drugi PDF - uplatnice za sve usluge sa pozitivnim saldom
        from onetouch.transactions.functions import prepare_qr_data, generate_qr_code, add_payment_slip_content, PDF, cleanup_qr_codes, setup_pdf_page
        
        # Generisanje podataka o školi
        school = School.query.first()
        
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
            
            # Koordinate su već postavljene kroz setup_pdf_page funkciju
            
            # Generisanje QR koda
            qr_data = prepare_qr_data(payment_data, payment_data['primalac'])
            qr_code_filename = generate_qr_code(qr_data, payment_data['student_id'], project_folder, current_user.id)
            
            # Dodavanje sadržaja uplatnice
            add_payment_slip_content(payment_slips_pdf, payment_data, y, y_qr, project_folder, current_user)
        
        # Čišćenje privremenih QR kodova
        cleanup_qr_codes(project_folder, current_user.id)
        
        # Čuvanje drugog PDF-a (uplatnice)
        payment_slips_path = os.path.join(user_folder, f'payment_slips_{student_id}.pdf')
        payment_slips_pdf.output(payment_slips_path)
        
        # Priprema linkova za PDF fajlove za prikazivanje u HTML šablonu
        pdf_links = [
            {
                'name': 'Lista dugovanja',
                'url': url_for('static', filename=f'reports/user_{current_user.id}/services_list_{student_id}.pdf')
            },
            {
                'name': 'Uplatnice',
                'url': url_for('static', filename=f'reports/user_{current_user.id}/payment_slips_{student_id}.pdf')
            }
        ]
        
        # Prikazivanje HTML stranice sa porukom o uspešno generisanim PDF-ovima
        return render_template('operation_success.html',
                            title='PDF izveštaji su uspešno generisani',
                            message='PDF izveštaji su uspešno generisani i otvoreni u novim tabovima.',
                            pdf_links=pdf_links,
                            auto_close=True)
        
    except Exception as e:
        logging.error(f'Greška pri generisanju PDF izveštaja: {str(e)}')
        flash(f'Došlo je do greške pri generisanju PDF-a: {str(e)}', 'danger')
        return redirect(url_for('overviews.overview_debts'))


@overviews.route("/send_debt_emails/<int:student_id>")
@login_required
def send_debt_emails(student_id):
    """
    Šalje e-mail sa izveštajem o dugovanjima za sve usluge sa pozitivnim saldom.
    """
    try:
        # Dobavljanje parametara iz URL-a
        min_debt_amount_str = request.args.get('min_debt_amount', '0')
        min_debt_amount = float(min_debt_amount_str) if min_debt_amount_str.strip() else 0
        
        selected_services_param = request.args.get('selected_services', '')
        selected_services = selected_services_param.split(',') if selected_services_param else []
        
        # Dobavljanje filtriranih podataka o transakcijama korišćenjem pomoćne funkcije
        services_with_positive_saldo, selected_service_names, student = get_filtered_transactions_data(
            student_id, selected_services, min_debt_amount)
            
        # Provera da li učenik ima definisan mejl roditelja
        if not student.parent_email:
            flash('Učenik nema definisan mejl roditelja.', 'danger')
            return redirect(url_for('overviews.overview_debts'))
        
        if not services_with_positive_saldo:
            flash('Učenik nema dugovanja ni za jednu uslugu.', 'info')
            return redirect(url_for('overviews.overview_debts'))
        
        # Generisanje HTML sadržaja e-maila
        template_data = {
            'student': student,
            'services': services_with_positive_saldo,
            'total_debt': sum(service['debt_amount'] for service in services_with_positive_saldo),
            'total_payment': sum(service['payment_amount'] for service in services_with_positive_saldo),
            'total_saldo': sum(service['saldo'] for service in services_with_positive_saldo),
            'school': School.query.first(),
            'now': datetime.now(),
            'min_debt_amount': min_debt_amount,
            'selected_services': selected_services,
            'selected_service_names': selected_service_names
        }
        
        html_content = render_template('message_html_debt_report.html', **template_data)
        
        # Podaci škole
        school = School.query.first()
        
        # Generisanje PDF-a sa listom usluga koje imaju pozitivan saldo
        from fpdf import FPDF
        from onetouch.transactions.functions import add_fonts
        
        # Kreiranje PDF-a sa listom usluga
        project_folder = os.path.dirname(os.path.dirname((os.path.abspath(__file__))))
        user_folder = f'{project_folder}/static/reports/user_{current_user.id}'
        if not os.path.exists(user_folder):
            os.makedirs(user_folder)
            
        # --- Generisanje prvog PDF-a - lista usluga ---
        pdf = FPDF()
        add_fonts(pdf)
        pdf.add_page()
        
        # Dodavanje informacija o filtriranju korišćenjem pomoćne funkcije
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
        
        # --- Generisanje drugog PDF-a - uplatnice ---
        from onetouch.transactions.functions import prepare_qr_data, generate_qr_code, add_payment_slip_content, PDF, cleanup_qr_codes, setup_pdf_page
        
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
                'iznos': saldo,
                'racun_primaoca': bank_account_number,
                'model': '97' if service_item.reference_number_spiri else '',
                'poziv_na_broj': service_item.reference_number_spiri if service_item.reference_number_spiri else '',
            }
            
            # Koordinate su već postavljene kroz setup_pdf_page funkciju
            
            # Generisanje QR koda
            qr_data = prepare_qr_data(payment_data, payment_data['primalac'])
            qr_code_filename = generate_qr_code(qr_data, payment_data['student_id'], project_folder, current_user.id)
            
            # Dodavanje sadržaja uplatnice
            add_payment_slip_content(payment_slips_pdf, payment_data, y, y_qr, project_folder, current_user)
        
        # Čišćenje privremenih QR kodova
        cleanup_qr_codes(project_folder, current_user.id)
        
        # Čuvanje drugog PDF-a (uplatnice)
        payment_slips_path = os.path.join(user_folder, f'payment_slips_{student_id}.pdf')
        payment_slips_pdf.output(payment_slips_path)
        
        # Slanje mejla sa prilozima
        subject = f'{school.school_name} | Izveštaj o dugovanju za učenika {student.student_name} {student.student_surname}'
        sender = (f'{school.school_name}', f'{current_app.config["MAIL_USERNAME"]}')
        recipients = [student.parent_email]
        
        msg = Message(subject=subject, sender=sender, recipients=recipients)
        msg.html = html_content
        
        # Dodavanje PDF priloga
        with app.open_resource(services_list_path) as attachment:
            msg.attach('lista_dugovanja.pdf', 'application/pdf', attachment.read())
            
        with app.open_resource(payment_slips_path) as attachment:
            msg.attach('uplatnice.pdf', 'application/pdf', attachment.read())
        
        # Slanje mejla
        mail.send(msg)
        
        # Evidencija slanja mejla
        flash(f'Uspešno poslat e-mail na adresu {student.parent_email}.', 'success')
        
        # Prikazivanje HTML stranice sa porukom o uspešno poslatom e-mailu
        pdf_links = [
            {
                'name': 'Lista dugovanja',
                'url': url_for('static', filename=f'reports/user_{current_user.id}/services_list_{student_id}.pdf')
            },
            {
                'name': 'Uplatnice',
                'url': url_for('static', filename=f'reports/user_{current_user.id}/payment_slips_{student_id}.pdf')
            }
        ]
        
        return render_template('operation_success.html',
                            title='E-mail uspešno poslat',
                            message=f'E-mail je uspešno poslat na adresu {student.parent_email}.',
                            pdf_links=pdf_links,
                            auto_close=False)
        
    except Exception as e:
        logging.error(f'Greška pri slanju e-maila: {str(e)}')
        flash(f'Došlo je do greške pri slanju e-maila: {str(e)}', 'danger')
        return redirect(url_for('overviews.overview_debts'))
