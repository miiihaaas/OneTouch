import itertools
import json
import logging
from datetime import datetime, date
from flask import Blueprint, render_template, url_for, flash, redirect, request, abort
from flask_login import login_required, current_user
from onetouch.models import Student, ServiceItem, Teacher, User, TransactionRecord
from onetouch.transactions.functions import gen_report_student, gen_report_school, gen_report_student_list
from sqlalchemy.exc import SQLAlchemyError
from onetouch import db, cache

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
            if start_date is None or end_date is None:
                start_date = danas.replace(month=9, day=1, year=2020)
                end_date = danas.replace(month=8, day=31, year=danas.year)
                # if danas.month < 9:
                #     start_date = danas.replace(month=9, day=1, year=danas.year-1)
                #     end_date = danas.replace(month=8, day=31)
                # else:
                #     start_date = danas.replace(month=9, day=1)
                #     end_date = danas.replace(month=8, day=31, year=danas.year+1)
            
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                
        except ValueError as e:
            logging.error(f'Greška pri obradi datuma: {str(e)}')
            flash('Neispravan format datuma.', 'danger')
            return redirect(url_for('main.home'))
        
        # Proverava da li je zahtev za DataTables Ajax serverside procesiranje
        if request.args.get('draw'):
            try:
                return get_students_data(request, start_date, end_date, service_id, razred, odeljenje, dugovanje, preplata)
            except Exception as e:
                logging.error(f'Greška pri generisanju podataka za DataTables: {str(e)}')
                return json.dumps({
                    'draw': int(request.args.get('draw')),
                    'recordsTotal': 0,
                    'recordsFiltered': 0,
                    'data': []
                }), 500, {'ContentType': 'application/json'}
            
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
            
            # Podaci će biti učitani preko Ajax-a, samo šaljemo inicijalne podatke za prikaz
            export_data = []
            students = Student.query.filter(Student.student_class < 9).all()
            teachers = Teacher.query.all()
            
            return render_template('overview_students.html', 
                                    title='Pregled po učeniku', 
                                    legend="Pregled po učeniku", 
                                    export_data=export_data,  # prazan niz, podaci će biti učitani preko Ajax-a
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
                                    route_name=route_name,)
            
        except SQLAlchemyError as e:
            logging.error(f'Greška pri pristupu bazi podataka: {str(e)}')
            flash('Došlo je do greške pri učitavanju podataka.', 'danger')
            return redirect(url_for('main.home'))
            
    except Exception as e:
        logging.error(f'Neočekivana greška u overview_students: {str(e)}')
        flash('Došlo je do neočekivane greške.', 'danger')
        return redirect(url_for('main.home'))


@cache.memoize(timeout=60)  # Keširaj rezultate na 1 minut
def get_students_data(request, start_date, end_date, service_id, razred, odeljenje, dugovanje, preplata):
    """
    Funkcija za serverside procesiranje DataTables za pregled učenika - optimizovana za performanse sa keširanjem
    """
    import time
    import traceback
    start_time = time.time()
    
    # Važni parametri za DataTables paginaciju
    draw = int(request.args.get('draw', 1))
    start_row = int(request.args.get('start', 0))
    length = int(request.args.get('length', 10))
    search_value = request.args.get('search[value]', '')
    order_column_index = int(request.args.get('order[0][column]', 0))
    order_dir = request.args.get('order[0][dir]', 'asc')
    
    # Kreiraj jedinstveni ključ za keš
    cache_key = f"students_data:{start_date}:{end_date}:{service_id}:{razred}:{odeljenje}:{dugovanje}:{preplata}:{search_value}:{order_column_index}:{order_dir}:{start_row}:{length}"
    
    # Proveri da li postoji keširani rezultat
    cached_result = cache.get(cache_key)
    if cached_result:
        logging.info(f'Koristi se keširani rezultat za ključ: {cache_key}')
        return cached_result
    
    try:
        
        # Import potrebnih modula
        from sqlalchemy import func, case, text, and_, or_
        from onetouch.models import StudentDebt, StudentPayment, Student, TransactionRecord
        
        # Direktno koristimo SQLAlchemy Core za agregaciju - mnogo brže od ORM-a
        # Kreiramo subupite za dugovanja i uplate
        db_session = db.session
        
        logging.info(f'Početak izvršavanja get_students_data - vreme: {time.time() - start_time:.2f}s')
        
        # Pripremamo uslove filtriranja koji će biti isti za oba subupita
        filter_conditions = []
        
        # Filter za razred i odeljenje
        if razred != '':
            filter_conditions.append(Student.student_class == int(razred))
        if odeljenje != '':
            filter_conditions.append(Student.student_section == int(odeljenje))
            
        # Filter za uslugu
        if service_id != '0':
            filter_conditions.append(TransactionRecord.service_item_id == int(service_id))
            
        # Filter za ID učenika > 1 (ignorisanje tehničkih stavki)
        filter_conditions.append(Student.id > 1)
        filter_conditions.append(Student.student_class < 9)
        
        logging.info(f'Priprema filtera - vreme: {time.time() - start_time:.2f}s')
        
        # Priprema filtera pre konstrukcije SQL upita
        razred_filter = f"AND s.student_class = {int(razred)}" if razred != '' else ""
        odeljenje_filter = f"AND s.student_section = {int(odeljenje)}" if odeljenje != '' else ""
        service_filter = f"AND tr.service_item_id = {int(service_id)}" if service_id != '0' else ""
        
        # Filter za dugovanje/preplatu
        if dugovanje:
            dugovanje_filter = "(total_debt - total_payment) > 0"
        elif preplata:
            dugovanje_filter = "(total_debt - total_payment) < 0"
        else:
            dugovanje_filter = "1=1"  # Uvek tačan uslov
            
        # Pretraga
        if search_value:
            search_term = search_value.lower()
            search_condition = f"WHERE CAST(student_id AS CHAR) LIKE '%{search_term}%' OR LOWER(student_name) LIKE '%{search_term}%' OR LOWER(student_surname) LIKE '%{search_term}%' OR CAST(student_class AS CHAR) LIKE '%{search_term}%' OR CAST(student_section AS CHAR) LIKE '%{search_term}%'"
        else:
            search_condition = ""
        
        # Postavka za sortiranje
        if order_column_index == 0:
            order_column = 'student_id'
        elif order_column_index == 1:
            order_column = 'student_name'  # Sortiranje po imenu
        elif order_column_index == 2:
            order_column = 'student_class'
        elif order_column_index == 3:
            order_column = 'student_section'
        elif order_column_index == 4:
            order_column = 'total_debt'
        elif order_column_index == 5:
            order_column = 'total_payment'
        elif order_column_index == 6:
            order_column = '(total_debt - total_payment)'  # Saldo
        else:
            order_column = 'student_id'  # Default vrednost
            
        # Direktan SQL upit za brzu agregaciju podataka po učeniku
        query_str = f"""
            WITH student_totals AS (
                -- Agregacija dugovanja po studentu
                SELECT 
                    s.id as student_id,
                    s.student_name,
                    s.student_surname,
                    s.student_class,
                    s.student_section,
                    COALESCE(SUM(CASE WHEN tr.student_debt_id IS NOT NULL THEN tr.student_debt_total ELSE 0 END), 0) as total_debt,
                    COALESCE(SUM(CASE WHEN tr.student_payment_id IS NOT NULL THEN tr.student_debt_total ELSE 0 END), 0) as total_payment
                FROM 
                    student s
                LEFT JOIN 
                    transaction_record tr ON s.id = tr.student_id
                LEFT JOIN 
                    student_debt sd ON tr.student_debt_id = sd.id
                LEFT JOIN 
                    student_payment sp ON tr.student_payment_id = sp.id
                WHERE 
                    s.id > 1 AND s.student_class < 9
                    AND (sd.student_debt_date BETWEEN :start_date AND :end_date OR sd.student_debt_date IS NULL)
                    AND (sp.payment_date BETWEEN :start_date AND :end_date OR sp.payment_date IS NULL)
                    -- Dodatni filteri za razred, odeljenje i uslugu
                    {razred_filter}
                    {odeljenje_filter}
                    {service_filter}
                    -- Jedan od njih mora biti popunjen da bi zapis bio validan
                    AND (tr.student_debt_id IS NOT NULL OR tr.student_payment_id IS NOT NULL)
                GROUP BY 
                    s.id, s.student_name, s.student_surname, s.student_class, s.student_section
                HAVING
                    -- Filter za dugovanje/preplatu
                    {dugovanje_filter}
            )
            SELECT * FROM student_totals
            {search_condition}
            ORDER BY {order_column} {order_dir}
            LIMIT :limit OFFSET :offset
        """
        
        query = text(query_str)
        
        # Pripremamo parametre za SQL upit - samo vrednosti, ne SQL delovi
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'limit': length,
            'offset': start_row
        }
        
        logging.info(f'SQL upit pripremljen - vreme: {time.time() - start_time:.2f}s')
            
        # Izvršavanje upita
        result = db_session.execute(query, params)
        rows = result.fetchall()
        
        logging.info(f'SQL upit izvršen - vreme: {time.time() - start_time:.2f}s')
        
        # Optimizovani upit za brojanje ukupnih zapisa (mnogo brži)
        # Koristimo samo ID polja bez nepotrebnih JOIN-ova kad je to moguće
        count_query_str = f"""
            SELECT COUNT(DISTINCT s.id) as total_count
            FROM 
                student s
            JOIN 
                transaction_record tr ON s.id = tr.student_id
            LEFT JOIN 
                student_debt sd ON tr.student_debt_id = sd.id
            LEFT JOIN 
                student_payment sp ON tr.student_payment_id = sp.id
            WHERE 
                s.id > 1 AND s.student_class < 9
                AND (sd.student_debt_date BETWEEN :start_date AND :end_date OR sd.student_debt_date IS NULL)
                AND (sp.payment_date BETWEEN :start_date AND :end_date OR sp.payment_date IS NULL)
                -- Dodatni filteri za razred, odeljenje i uslugu
                {razred_filter}
                {odeljenje_filter}
                {service_filter}
                -- Jedan od njih mora biti popunjen da bi zapis bio validan
                AND (tr.student_debt_id IS NOT NULL OR tr.student_payment_id IS NOT NULL)
        """
        
        # Dodajemo HAVING uslov samo ako je potreban za dugovanje/preplatu
        if dugovanje or preplata:
            count_query_str = f"""
                SELECT COUNT(*) FROM (
                    SELECT 
                        s.id as student_id,
                        COALESCE(SUM(CASE WHEN tr.student_debt_id IS NOT NULL THEN tr.student_debt_total ELSE 0 END), 0) as total_debt,
                        COALESCE(SUM(CASE WHEN tr.student_payment_id IS NOT NULL THEN tr.student_debt_total ELSE 0 END), 0) as total_payment
                    FROM 
                        student s
                    JOIN 
                        transaction_record tr ON s.id = tr.student_id
                    LEFT JOIN 
                        student_debt sd ON tr.student_debt_id = sd.id
                    LEFT JOIN 
                        student_payment sp ON tr.student_payment_id = sp.id
                    WHERE 
                        s.id > 1 AND s.student_class < 9
                        AND (sd.student_debt_date BETWEEN :start_date AND :end_date OR sd.student_debt_date IS NULL)
                        AND (sp.payment_date BETWEEN :start_date AND :end_date OR sp.payment_date IS NULL)
                        -- Dodatni filteri za razred, odeljenje i uslugu
                        {razred_filter}
                        {odeljenje_filter}
                        {service_filter}
                        -- Jedan od njih mora biti popunjen da bi zapis bio validan
                        AND (tr.student_debt_id IS NOT NULL OR tr.student_payment_id IS NOT NULL)
                    GROUP BY 
                        s.id
                    HAVING
                        -- Filter za dugovanje/preplatu
                        {dugovanje_filter}
                ) as count_subq
                {search_condition}
            """
        elif search_value:
            count_query_str += f" {search_condition}"
        count_query = text(count_query_str)
        
        count_result = db_session.execute(count_query, {
            'start_date': start_date,
            'end_date': end_date
        })
        total_records = count_result.scalar()
        
        logging.info(f'Ukupan broj zapisa izbrojan - vreme: {time.time() - start_time:.2f}s')
        
        # Koristimo podatke iz prve stranice za procenu suma ako je inicijalno učitavanje
        # Ovaj pristup će biti brz za prvo učitavanje, a kasnije ćemo imati tačne sume
        if start_row == 0 and request.args.get('initial_load', '0') == '1':
            # Za inicijalno učitavanje procenjujemo sume samo iz podataka prve stranice
            sums_query_str = None
            # Vrednosti ćemo izračunati iz već učitanih podataka za prvu stranicu
            logging.info(f'Korišćenje procenjenih suma za prvo učitavanje - vreme: {time.time() - start_time:.2f}s')
        else:
            # Standardno računanje suma za sve podatke
            sums_query_str = f"""
                SELECT 
                    COALESCE(SUM(total_debt), 0) as sum_debt,
                    COALESCE(SUM(total_payment), 0) as sum_payment,
                    COALESCE(SUM(total_debt - total_payment), 0) as sum_saldo
                FROM (
                    SELECT 
                        s.id as student_id,
                        COALESCE(SUM(CASE WHEN tr.student_debt_id IS NOT NULL THEN tr.student_debt_total ELSE 0 END), 0) as total_debt,
                        COALESCE(SUM(CASE WHEN tr.student_payment_id IS NOT NULL THEN tr.student_debt_total ELSE 0 END), 0) as total_payment
                    FROM 
                        student s
                    JOIN 
                        transaction_record tr ON s.id = tr.student_id
                    LEFT JOIN 
                        student_debt sd ON tr.student_debt_id = sd.id
                    LEFT JOIN 
                        student_payment sp ON tr.student_payment_id = sp.id
                    WHERE 
                        s.id > 1 AND s.student_class < 9
                        AND (sd.student_debt_date BETWEEN :start_date AND :end_date OR sd.student_debt_date IS NULL)
                        AND (sp.payment_date BETWEEN :start_date AND :end_date OR sp.payment_date IS NULL)
                        -- Dodatni filteri za razred, odeljenje i uslugu
                        {razred_filter}
                        {odeljenje_filter}
                        {service_filter}
                        -- Jedan od njih mora biti popunjen da bi zapis bio validan
                        AND (tr.student_debt_id IS NOT NULL OR tr.student_payment_id IS NOT NULL)
                    GROUP BY 
                        s.id
                    HAVING
                        -- Filter za dugovanje/preplatu
                        {dugovanje_filter}
                ) as sums_subq
                {search_condition}
            """
            sums_query = text(sums_query_str)
        
        # Računanje suma - optimizovano za brzo inicijalno učitavanje
        if sums_query_str is None:
            # Koristimo podatke iz prve stranice za aproksimaciju suma
            # Kasnije će biti ažurirano tačnim vrednostima kroz sledeće pozive
            if rows:
                # Računamo sume iz dobijenih redova podataka
                sum_zaduzenje = sum(float(row[5]) if row[5] is not None else 0 for row in rows)
                sum_uplate = sum(float(row[6]) if row[6] is not None else 0 for row in rows)
                sum_saldo = sum_zaduzenje - sum_uplate
                
                # Procena ukupnih suma (množimo sa faktorom na osnovu broja ukupnih zapisa)
                if total_records > 0 and length > 0:
                    factor = float(total_records) / min(length, len(rows))
                    sum_zaduzenje *= factor
                    sum_uplate *= factor
                    sum_saldo *= factor
            else:
                sum_zaduzenje = 0.0
                sum_uplate = 0.0
                sum_saldo = 0.0
        else:
            # Standardni pristup za računanje suma
            sums_result = db_session.execute(sums_query, {
                'start_date': start_date,
                'end_date': end_date
            })
            sums = sums_result.fetchone()
            sum_zaduzenje = float(sums[0]) if sums[0] is not None else 0
            sum_uplate = float(sums[1]) if sums[1] is not None else 0
            sum_saldo = float(sums[2]) if sums[2] is not None else 0
        
        logging.info(f'Sume izračunate - vreme: {time.time() - start_time:.2f}s')
        
        # Formatiranje rezultata za DataTables
        data_for_table = []
        for row in rows:
            student_id = row[0]
            student_name = row[1]
            student_surname = row[2]
            student_class = row[3]
            student_section = row[4]
            student_debt = float(row[5]) if row[5] is not None else 0
            student_payment = float(row[6]) if row[6] is not None else 0
            saldo = student_debt - student_payment
            
            student_id_formatted = "{:04d}".format(student_id)
            student_name_formatted = f"{student_name} {student_surname}"
            student_debt_formatted = "{:.2f}".format(student_debt)
            student_payment_formatted = "{:.2f}".format(student_payment)
            saldo_formatted = "{:.2f}".format(saldo)
            
            # Link za pregled kartice stanja
            action_button = f'<a href="{url_for("overviews.overview_student", student_id=student_id)}" class="btn-x btn-primary-x loading" title="Pregled kartice stanja"><i class="fa fa-magnifying-glass awesomeedit"></i></a>'
            
            data_for_table.append([
                student_id_formatted,
                student_name_formatted,
                student_class,
                student_section,
                student_debt_formatted,
                student_payment_formatted,
                saldo_formatted,
                action_button
            ])

        end_time = time.time()
        logging.info(f'Ukupno vreme izvršavanja get_students_data: {end_time - start_time:.2f}s')
        
        # Formiranje odgovora za DataTables
        response = {
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': total_records,
            'data': data_for_table,
            'sums': {
                'zaduzenje': "{:.2f}".format(sum_zaduzenje),
                'uplate': "{:.2f}".format(sum_uplate),
                'saldo': "{:.2f}".format(sum_saldo)
            },
            'performance': {
                'execution_time': "{:.2f}".format(time.time() - start_time),
                'cached': False,
                'estimated_sums': (sums_query_str is None)
            }
        }
        
        result = (json.dumps(response), 200, {'ContentType': 'application/json'})
        
        # Sačuvaj rezultat u keš
        cache.set(cache_key, result, timeout=60)
        
        return result
        
    except Exception as e:
        end_time = time.time()
        logging.error(f'Greška u get_students_data: {str(e)}. Vreme izvršavanja: {end_time - start_time:.2f}s')
        traceback_info = traceback.format_exc()
        logging.error(f'Traceback: {traceback_info}')
        return json.dumps({
            'draw': int(request.args.get('draw')),
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': [],
            'error': str(e)
        }), 500, {'ContentType': 'application/json'}


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
            
            if start_date is None or end_date is None:
                start_date = danas.replace(month=9, day=1, year=2020)
                end_date = danas.replace(month=8, day=31, year=danas.year)
                # if danas.month < 9:
                #     start_date = danas.replace(month=9, day=1, year=danas.year-1)
                #     end_date = danas.replace(month=8, day=31)
                # else:
                #     start_date = danas.replace(month=9, day=1)
                #     end_date = danas.replace(month=8, day=31, year=danas.year+1)
                    
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
                
            logging.debug(f'Datumi: {start_date=} {end_date=}')
            
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
                if (record.service_item_id not in [item['id'] for item in unique_services_list]) and record.student_debt_total > 0:
                    try:
                        service_data = {
                            'id': record.service_item_id,
                            'service_debt_id': record.student_debt_id if record.student_debt_id else ServiceItem.query.get_or_404(int(record.service_item_id)).id,
                            'service_item_date': record.transaction_record_service_item.service_item_date,
                            'service_name': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name,
                            'date': record.transaction_record_student_debt.student_debt_date if record.student_debt_id else record.transaction_record_student_payment.payment_date,
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
                        
                    if record.student_debt_total:
                        test_data = {
                            'id': record.id,
                            'service_item_id': record.service_item_id,
                            'student_payment_id': record.student_payment_id,
                            'date': date_,
                            'description': description,
                            'debt_amount': record.student_debt_total if record.student_debt_id else 0,
                            'payment_amount': record.student_debt_total if record.student_payment_id else 0,
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
            # unique_services_list.sort(key=lambda x: x['service_item_date'])
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
                                route_name=route_name)
                                
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
    if start_date is None or end_date is None:
        start_date = danas.replace(month=9, day=1, year=2020)
        end_date = danas.replace(month=8, day=31, year=danas.year)
        # if danas.month < 9:
        #     start_date = danas.replace(month=9, day=1, year=danas.year-1)
        #     end_date = danas.replace(month=8, day=31)
        # else:
        #     start_date = danas.replace(month=9, day=1)
        #     end_date = danas.replace(month=8, day=31, year=danas.year+1)
    logging.debug(f'posle if bloka: {start_date=} {end_date=}')
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
    logging.debug(f'{options=}')
    
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
                            existing_record['student_payment'] += record.student_debt_total if record.student_payment_id else 0
                            existing_record['saldo'] = existing_record['student_debt'] - existing_record['student_payment']
                    else:
                        new_record = {
                            'service_item_id': record.service_item_id,
                            'class': record.transaction_record_student.student_class,
                            'section': record.transaction_record_student.student_section,
                            'student_debt': record.student_debt_total if record.student_debt_id else 0,
                            'student_payment': record.student_debt_total if record.student_payment_id else 0,
                        }
                        new_record['saldo'] = new_record['student_debt'] - new_record['student_payment']
                        new_record['teacher'] = next((item['name'] + ' ' + item['surname'] for item in teacher_clasroom_list if item['class'] == new_record['class'] and item['section'] == new_record['section']), None)
                        data.append(new_record)
    logging.info(f'{data=}')

    report_school = gen_report_school(data, start_date, end_date, filtered_records, service_id, razred, odeljenje)
    
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
                            route_name=route_name,)

