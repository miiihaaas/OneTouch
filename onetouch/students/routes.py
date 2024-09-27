import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt
from onetouch.models import Student, User, StudentDebt, School, TransactionRecord
from onetouch.students.forms import EditStudentModalForm, RegisterStudentModalForm
from flask_login import login_required, current_user
from flask import jsonify

from onetouch.students.functons import check_if_plus_one
from onetouch.suppliers.functions import convert_to_latin


students = Blueprint('students', __name__)


def load_user(user_id):
    return User.query.get(int(user_id))


# Ova funkcija će proveriti da li je korisnik ulogovan pre nego što pristupi zaštićenoj ruti
@students.before_request
def require_login():
    if request.endpoint and not current_user.is_authenticated:
        return redirect(url_for('users.login'))


@students.route('/student_list', methods=['GET', 'POST'])
def student_list():
    route_name = request.endpoint
    school = School.query.first()
    danas = datetime.now()
    plus_one_button = check_if_plus_one(school)
    active_date_start = danas.replace(month=8, day=15)
    active_date_end = danas.replace(month=9, day=30)
    
    register_form = RegisterStudentModalForm()
    edit_form = EditStudentModalForm()
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        student = Student.query.get(request.form.get('student_id'))
        logging.debug(f'debug- edit mode: {student.student_name=} {student.student_surname=}')
        logging.debug(f'{edit_form.student_name.data=} {edit_form.student_surname.data=} {edit_form.send_mail.data=}')
        logging.debug(f'{request.form.get("send_mail")=}')
        student.student_name = convert_to_latin(edit_form.student_name.data.strip().capitalize())
        student.student_surname = convert_to_latin(" ".join(word.capitalize() for word in edit_form.student_surname.data.strip().split()))
        student.student_class = edit_form.student_class.data
        student.student_section = edit_form.student_section.data
        student.parent_email = edit_form.parent_email.data
        student.send_mail = edit_form.send_mail.data
        student.print_payment = edit_form.print_payment.data
        db.session.commit()
        flash(f'Podaci o učeniku "{student.student_name} {student.student_surname}" su ažurirani.', 'success')
        return redirect(url_for('students.student_list'))
    if register_form.validate_on_submit() and request.form.get('submit_register'):
        student = Student(
                            student_name=convert_to_latin(register_form.student_name.data.strip().capitalize()),
                            student_surname=convert_to_latin(" ".join(word.capitalize() for word in register_form.student_surname.data.strip().split())),
                            student_class=str(register_form.student_class.data),
                            student_section=register_form.student_section.data,
                            parent_email=register_form.parent_email.data,
                            send_mail=0,
                            print_payment=0
                        )

        logging.debug(student.student_name, student.student_surname, student.student_class)
        db.session.add(student)
        db.session.commit()
        logging.debug("inputi su validni")
        flash(f'Učenik "{student.student_name} {student.student_surname}" je registrovan.', 'success')
        return redirect(url_for('students.student_list'))
    return render_template('student_list.html', 
                            title='Učenici', 
                            legend="Učenici",
                            register_form=register_form, 
                            edit_form=edit_form,
                            plus_one_button=plus_one_button,
                            active_date_start=active_date_start,
                            active_date_end=active_date_end,
                            danas=danas,
                            route_name=route_name)


@students.route('/api/students_list')
def api_students_list():
    students_query = Student.query.filter(Student.student_class < 9)
    
    # search filter
    search = request.args.get('search[value]')
    student_class = request.args.get('searchRazred')
    student_section = request.args.get('searchOdeljenje')
    logging.debug(f'debug: {search=} {student_class=} {student_section=}')
    if search:
        students_query = students_query.filter(db.or_(
            Student.student_name.like(f'%{search}%'),
            Student.student_surname.like(f'%{search}%'),
            Student.id.like(f'%{search}%'))
        )
    if student_class:
        students_query = students_query.filter(Student.student_class == student_class)
    if student_section:
        students_query = students_query.filter(Student.student_section == student_section)
    total_filtered = students_query.count()
    
    # sorting
    order = []
    i = 0
    while True:
        col_index = request.args.get(f'order[{i}][column]')
        if col_index is None:
            break
        col_name = request.args.get(f'columns[{col_index}][data]')
        if col_name not in ['id', 'student_name', 'student_surname', 'student_class', 'student_section', 'parent_email']:
            col_name = 'parent_email'
        descending = request.args.get(f'order[{i}][dir]') == 'desc'
        col = getattr(Student, col_name)
        if descending:
            col = col.desc()
        order.append(col)
        i += 1
    if order:
        students_query = students_query.order_by(*order)
    
    # pagination
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    students_query = students_query.offset(start).limit(length)
    
    students_list = []
    for student in students_query:
        new_dict = {
            'id': str(student.id).zfill(4),
            'student_name': student.student_name,
            'student_surname': student.student_surname,
            'student_class': student.student_class,
            'student_section': student.student_section,
            'parent_email': student.parent_email,
            'send_mail': student.send_mail,
            'print_payment': student.print_payment
        }
        students_list.append(new_dict)
    logging.debug(f'{students_list=}')
    return {
        'data': students_list,
        'recordsFiltered': total_filtered,
        'recordsTotal': total_filtered,
        'draw': request.args.get('draw', type=int),
        }



@students.route('/testingg')
def testingg():
    students_query = Student.query.filter(Student.student_class < 9)
    
    # search filter
    search = request.args.get('search[value]')
    student_class = request.args.get('searchRazred')
    student_section = request.args.get('searchOdeljenje')
    logging.debug(f'debug: {search=} {student_class=} {student_section=}')
    if search:
        students_query = students_query.filter(db.or_(
            Student.student_name.like(f'%{search}%'),
            Student.student_surname.like(f'%{search}%'),
            Student.id.like(f'%{search}%'))
        )
    if student_class:
        students_query = students_query.filter(Student.student_class == student_class)
    if student_section:
        students_query = students_query.filter(Student.student_section == student_section)
    total_filtered = students_query.count()
    
    # sorting
    order = []
    i = 0
    while True:
        col_index = request.args.get(f'order[{i}][column]')
        if col_index is None:
            break
        col_name = request.args.get(f'columns[{col_index}][data]')
        if col_name not in ['id', 'student_name', 'student_surname', 'student_class', 'student_section', 'parent_email']:
            col_name = 'parent_email'
        descending = request.args.get(f'order[{i}][dir]') == 'desc'
        col = getattr(Student, col_name)
        if descending:
            col = col.desc()
        order.append(col)
        i += 1
    if order:
        students_query = students_query.order_by(*order)
    
    # pagination
    start = request.args.get('start', type=int)
    length = request.args.get('length', type=int)
    students_query = students_query.offset(start).limit(length)
    
    students_list = []
    for student in students_query:
        new_dict = {
            'id': str(student.id).zfill(4),
            'student_name': student.student_name,
            'student_surname': student.student_surname,
            'student_class': student.student_class,
            'student_section': student.student_section,
            'parent_email': student.parent_email,
            'send_mail': student.send_mail,
            'print_payment': student.print_payment
        }
        students_list.append(new_dict)
    logging.debug(f'{students_list=}')
    return {
        'data': students_list,
        'recordsFiltered': total_filtered,
        'recordsTotal': total_filtered,
        'draw': request.args.get('draw', type=int),
        }


@students.route('/class_plus_one', methods=['GET', 'POST'])
def class_plus_one():
    students = Student.query.filter(Student.student_class < 100).all() # da bi 9 razred sledeće godine posta 10 i tako se razlikovao od 8 koji je postao 9. U suprotnom bi svi bili 9 razred i ne bi smo razlikovali generacije
    school = School.query.first()
    
    # primer promenljive koja dolazi iz baze podataka
    class_plus_one = school.class_plus_one

    # trenutni datum
    now = datetime.now()
    
    if now.month >= 9:
        # ako smo nakon septembra, tekuća školska godina je od septembra ove godine do septembra sledeće
        start_of_school_year = datetime(now.year, 9, 1).date()
        end_of_school_year = datetime(now.year + 1, 8, 31).date()
    else:
        # ako smo pre septembra, tekuća školska godina je od septembra prošle godine do septembra ove godine
        start_of_school_year = datetime(now.year - 1, 9, 1).date()
        end_of_school_year = datetime(now.year, 8, 31).date()
    
    # Proveravamo da li datum class_plus_one spada u tekuću školsku godinu
    if start_of_school_year <= class_plus_one <= end_of_school_year:
        print('Ove godine, razred svih učenika je već promenjen putem masovne promene.')  # Unutar tekuće školske godine
        flash('Ove godine, razred svih učenika je već promenjen putem masovne promene.', 'info')
    elif class_plus_one < start_of_school_year:
        print('Nisu prebačeni đaci u sledeći razred. treba uraditi +1 razred')  # Pre tekuće školske godine
        for student in students:
            student.student_class = int(student.student_class) + 1
        school.class_plus_one = now
        db.session.commit()
        flash('Razred je uspešno promenjen za sve učenike. Za učenike koji su ponavljali razred, potrebno je ručno ažurirati njihove podatke.', 'success')
    else:
        print('Ovo je nemoguća opcija, neće se ništa uraditi.')  # Nakon tekuće školske godine
        flash('Došlo je do greške. Nisu promenjeni razredi kod učenka.', 'danger')

    return redirect(url_for('students.student_list'))


@students.route('/student/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get(student_id)
    if not current_user.is_authenticated:
        flash('Morate da budete prijavljeni da biste pristupili ovoj stranici', 'danger')
        return redirect(url_for('users.login'))
    elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
        logging.debug ('nije dobar password')
        flash(f'Pogrešna lozinka! nije obrisan profil učenika: {student.student_name} {student.student_surname}', 'danger')
        return redirect(url_for('students.student_list'))
    else:
        # proveri da li je studeent zadužen nekom uslugom
        list_of_students_with_debts = TransactionRecord.query.filter_by(student_id=student.id).all()
        logging.debug(f'{list_of_students_with_debts=}')
        if list_of_students_with_debts:
            logging.debug('student ima zaduzenje, prebacujem ga u razred koji je za 100 veći od njegovog trenutnog razreda')
            student.student_class += 100
        else:
            logging.debug('student nema zaduženje, brišem ga iz baze')
            db.session.delete(student)
        db.session.commit()
        flash(f'Profil učenika "{student.student_name} {student.student_surname}" je obrisan.', 'success')
        return redirect(url_for("students.student_list"))





