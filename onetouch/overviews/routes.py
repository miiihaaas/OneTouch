import itertools, json
from datetime import datetime, date
from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch.models import Student, ServiceItem, Teacher, School, TransactionRecord


overviews = Blueprint('overviews', __name__)

@overviews.route("/overview_students", methods=['GET', 'POST'])
def overview_students():
    danas = date.today()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    service_id = request.args.get('service_id')
    if not service_id:
        service_id = '0' # ako nije definisana promenjiva na početku, dodeli joj '0' što predstavlja sve usluge
    print(f'{start_date=} {end_date=} {service_id=}')
    if start_date is None or end_date is None:
        if danas.month < 9:
            start_date = danas.replace(month=9, day=1, year=danas.year-1)
            end_date = danas.replace(month=8, day=31)
        else:
            start_date = danas.replace(month=9, day=1)
            end_date = danas.replace(month=8, day=31, year=danas.year+1)
    print(f'posle if bloka: {start_date=} {end_date=}')
    if type(start_date) is str:
        # Konvertuj start_date i end_date u datetime.date objekte
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    print(f'posle if ako je string: {start_date=} {end_date=}')
    records = TransactionRecord.query.all()
    print(f'sve transakcije: {len(records)=}')
    
    filtered_records = []
    for record in records:
        # print(f'{start_date=} {end_date=}')
        if record.student_debt_id:
            # print(f'{record.transaction_record_student_debt.student_debt_date=}')
            if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                filtered_records.append(record)
        elif record.student_payment_id:
            # print(f'{record.transaction_record_student_payment.payment_date=}')
            if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                filtered_records.append(record)
    print(f'nakon filtriranja: {len(filtered_records)=}')
    
    options = []
    for record in filtered_records:
        if record.service_item_id not in [option['value'] for option in options]:
            options.append({
                'value': record.service_item_id,
                'label': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
            })
    print(f'{options=}')
    
    export_data = []
    for record in filtered_records:
        if service_id == '0' or int(service_id) == record.service_item_id:
            if record.student_id in [student['student_id'] for student in export_data]:
                existing_record = next((item for item in export_data if item["student_id"] == record.student_id), None)
                # print(f'{existing_record=}')
                existing_record['student_debt'] += record.student_debt_total if record.student_debt_id else 0
                existing_record['student_payment'] += record.student_debt_total if record.student_payment_id else 0
                existing_record['saldo'] = existing_record['student_debt'] - existing_record['student_payment']

            else:
                new_record = {
                    'student_id': record.student_id,
                    'student_name': record.transaction_record_student.student_name,
                    'student_surname': record.transaction_record_student.student_surname,
                    'student_class': record.transaction_record_student.student_class,
                    'student_section': record.transaction_record_student.student_section,
                    'student_debt': record.student_debt_total if record.student_debt_id else 0,
                    'student_payment': record.student_debt_total if record.student_payment_id else 0,
                }
                new_record['saldo'] = new_record['student_debt'] - new_record['student_payment']
                # print(f'{new_record}')
                export_data.append(new_record)
    # export_data = [dict(t) for t in {tuple(d.items()) for d in export_data}]

    print(f'{export_data=}')
    
    students = Student.query.filter(Student.student_class < 9).all()
    teachers = Teacher.query.all()
    return render_template('overview_students.html', 
                            title='Pregled po učeniku', 
                            legend="Pregled po učeniku", 
                            export_data=export_data,
                            students=students,
                            teachers=teachers,
                            start_date=start_date,
                            end_date=end_date,
                            service_id=service_id,
                            options=options,)


@overviews.route("/overview_student/<int:student_id>", methods=['GET', 'POST'])
def overview_student(student_id):
    student = Student.query.get_or_404(student_id)
    danas = date.today()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    if start_date is None or end_date is None:
        if danas.month < 9:
            start_date = danas.replace(month=9, day=1, year=danas.year-1)
            end_date = danas.replace(month=8, day=31)
        else:
            start_date = danas.replace(month=9, day=1)
            end_date = danas.replace(month=8, day=31, year=danas.year+1)
    print(f'posle if bloka: {start_date=} {end_date=}')
    if type(start_date) is str:
        # Konvertuj start_date i end_date u datetime.date objekte
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    print(f'posle if ako je string: {start_date=} {end_date=}')
    # Prvo morate dohvatiti sve transakcije (zaduženja i uplate) za odabranog učenika
    transaction_records = TransactionRecord.query.filter_by(student_id=student_id).all()

    # Inicijalizirajte prazne liste za zaduženja i uplate
    data = []
    unique_services_list = []
    # Prolazite kroz sve transakcije i grupirate ih prema vrsti (zaduženje ili uplata)
    for record in transaction_records:
        if record.service_item_id not in [item['id'] for item in unique_services_list]:
            service_data = {
                'id': record.service_item_id,
                'service_item_date': record.transaction_record_service_item.service_item_date,
                'service_name': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name,
                'date': record.transaction_record_student_debt.student_debt_date if record.student_debt_id else record.transaction_record_student_payment.payment_date,
            }
            print(f'{start_date=} {end_date=} {service_data["date"].date()=}')
            if service_data['date'].date() >= start_date and service_data['date'].date() <= end_date:
                unique_services_list.append(service_data)
        if record.student_debt_id:
            description = record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name + ' / Rata ' + str(record.transaction_record_service_item.installment_number)
            date_ = record.transaction_record_student_debt.student_debt_date
        elif record.student_payment_id:
            description = record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
            date_ = record.transaction_record_student_payment.payment_date
        test_data = {
            'id': record.id,
            'service_item_id': record.service_item_id, #! ovo je za filtriranje po uslugama
            'student_payment_id': record.student_payment_id,
            'date': date_,
            'description': description,
            'debt_amount': record.student_debt_total if record.student_debt_id else 0,
            'payment_amount': record.student_debt_total if record.student_payment_id else 0,
        }
        if test_data['service_item_id'] in [item['service_item_id'] for item in data]:
            print(f'postoji zapis sa service_item_id: {test_data["service_item_id"]}, napravi sumu svih ključeva "saldo"')
            saldo_sum = [item['saldo'] for item in data if item['service_item_id'] == test_data['service_item_id']]
            print(f'saldo_sum: {saldo_sum=}')
            test_data['saldo'] = saldo_sum[-1] + test_data['debt_amount'] - test_data['payment_amount'] #! iz liste 'saldo' uzima poslenju vrednost i na to dodaje razliku zaduženja i uplata
        else:
            print(f'ovo je prvi zapis sa service_item_id: {test_data["service_item_id"]}, ključ "saldo" je "debt_amount" - "payment_amount')
            test_data['saldo'] = test_data['debt_amount'] - test_data['payment_amount']
        data.append(test_data)
    # unique_services_list.sort()
    
    print(f'{data=}')
    data.sort(key=lambda x: x['service_item_id'])
    print(f'{data=}')
    print(f'{len(data)=}')
    # Sortiranje rečnika po ključu 'id'
    unique_services_list = sorted(unique_services_list, key=lambda x: x['id'])
    print(f'{unique_services_list=}')

        
    return render_template('overview_student.html', 
                            title=f'Pregled stanja učenika: {student.student_name} {student.student_surname}', 
                            legend=f"Pregled stanja učenika: {student.student_name} {student.student_surname}", 
                            student=student,
                            start_date=start_date,
                            end_date=end_date,
                            transaction_records=transaction_records,
                            data=data,
                            unique_services_list=unique_services_list,
                            danas=danas)


@overviews.route("/overview_sections", methods=['GET', 'POST']) # odeljenja
def overview_sections():
    danas = date.today()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    service_id = request.args.get('service_id')
    if not service_id:
        service_id = '0' # ako nije definisana promenjiva na početku, dodeli joj '0' što predstavlja sve usluge
    print(f'{start_date=} {end_date=} {service_id=}')
    if start_date is None or end_date is None:
        if danas.month < 9:
            start_date = danas.replace(month=9, day=1, year=danas.year-1)
            end_date = danas.replace(month=8, day=31)
        else:
            start_date = danas.replace(month=9, day=1)
            end_date = danas.replace(month=8, day=31, year=danas.year+1)
    print(f'posle if bloka: {start_date=} {end_date=}')
    if type(start_date) is str:
        # Konvertuj start_date i end_date u datetime.date objekte
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
    print(f'posle if ako je string: {start_date=} {end_date=}')
    records = TransactionRecord.query.all()
    print(f'sve transakcije: {len(records)=}')
    
    filtered_records = []
    for record in records:
        # print(f'{start_date=} {end_date=}')
        if record.student_debt_id:
            # print(f'{record.transaction_record_student_debt.student_debt_date=}')
            if (start_date <= record.transaction_record_student_debt.student_debt_date.date() <= end_date):
                filtered_records.append(record)
        elif record.student_payment_id:
            # print(f'{record.transaction_record_student_payment.payment_date=}')
            if (start_date <= record.transaction_record_student_payment.payment_date.date() <= end_date):
                filtered_records.append(record)
    print(f'nakon filtriranja: {len(filtered_records)=}')
    # for filtered_record in filtered_records:
    #     print(f'{filtered_record.id=}')
    
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
    print(f'{teacher_clasroom_list=}')
    
    unique_sections = []
    for student in students:
        if str(student.student_class) + '/' + str(student.student_section) not in [(section['section']) for section in unique_sections]:
            unique_sections.append({'section': str(student.student_class) + '/' + str(student.student_section)})
    unique_sections.sort(key=lambda x: x['section'])
    print(f'{unique_sections=}')
    options = []
    for record in filtered_records:
        if record.service_item_id not in [option['value'] for option in options]:
            options.append({
                'value': record.service_item_id,
                'label': record.transaction_record_service_item.service_item_service.service_name + ' - ' + record.transaction_record_service_item.service_item_name
            })
    print(f'{options=}')
    
    data = []
    for section in unique_sections:
        for record in filtered_records:
            section_key = f"{record.transaction_record_student.student_class}/{record.transaction_record_student.student_section}" #odeljenje (npr: 1/1)
            if section['section'] == section_key:
                if service_id == '0' or int(service_id) == record.service_item_id:
                    if section_key in [(f"{existing_record['class']}/{existing_record['section']}") for existing_record in data]:
                        # print(f"Postoji zapis sa ključem 'class' i 'section': {record.transaction_record_student.student_class}/{record.transaction_record_student.student_section}. Treba sumirati zaduženja, uplate i saldo.")
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
    print(f'{data=}')

    
    return render_template('overview_sections.html',
                            title='Pregled škole po uslugama', 
                            legend="Pregled škole po uslugama",
                            unique_sections=unique_sections,
                            data=data,
                            start_date=start_date,
                            end_date=end_date,
                            options=options,
                            service_id=service_id,)

@overviews.route("/overview_services", methods=['GET', 'POST'])
def overview_services():
    danas = datetime.now()
    active_date_start = danas.replace(month=4, day=15)
    active_date_end = danas.replace(month=9, day=15)
    services = ServiceItem.query.all()
    return render_template('overview_services.html', #! napraviti html fajl, revidirati funkciju
                            title='Pregled po usluzi', 
                            legend="Pregled po usluzi", 
                            services=services,
                            active_date_start=active_date_start,
                            active_date_end=active_date_end,
                            danas=danas)
