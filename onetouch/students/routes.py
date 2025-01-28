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
from sqlalchemy.exc import SQLAlchemyError
import logging
logger = logging.getLogger(__name__)

students = Blueprint('students', __name__)


# Ova funkcija će proveriti da li je korisnik ulogovan pre nego što pristupi zaštićenoj ruti
@students.before_request
def require_login():
    if request.endpoint and not current_user.is_authenticated:
        return redirect(url_for('users.login'))


@students.route('/student_list', methods=['GET', 'POST'])
def student_list():
    try:
        route_name = request.endpoint
        school = School.query.first()
        danas = datetime.now()
        plus_one_button = check_if_plus_one(school)
        active_date_start = danas.replace(month=8, day=15)
        active_date_end = danas.replace(month=9, day=30)
        
        # Provera isteka licence
        license_expired = False
        if school and school.license_expiry_date:
            days_left = school.days_until_license_expiry()
            if days_left is not None and days_left <= 0:
                license_expired = True
        
        register_form = RegisterStudentModalForm()
        edit_form = EditStudentModalForm()
        
        if edit_form.validate_on_submit() and request.form.get('submit_edit'):
            try:
                student = Student.query.get(request.form.get('student_id'))
                logging.debug(f'debug- edit mode: {student.student_name=} {student.student_surname=}')
                logging.debug(f'{edit_form.student_name.data=} {edit_form.student_surname.data=} {edit_form.send_mail.data=}')
                logging.debug(f'{request.form.get("send_mail")=}')
                student.student_name = convert_to_latin(edit_form.student_name.data.strip().title())
                student.student_surname = convert_to_latin(" ".join(word.title() for word in edit_form.student_surname.data.strip().split()))
                student.student_class = edit_form.student_class.data
                student.student_section = edit_form.student_section.data
                student.parent_email = edit_form.parent_email.data
                student.send_mail = edit_form.send_mail.data
                student.print_payment = edit_form.print_payment.data
                db.session.commit()
                flash(f'Podaci o učeniku "{student.student_name} {student.student_surname}" su ažurirani.', 'success')
                return redirect(url_for('students.student_list'))
            except SQLAlchemyError as e:
                db.session.rollback()
                logger.error(f"Greška pri ažuriranju učenika: {str(e)}")
                flash('Došlo je do greške pri ažuriranju podataka o učeniku.', 'danger')
                return render_template('errors/500.html'), 500
                
        if register_form.validate_on_submit() and request.form.get('submit_register'):
            try:
                student = Student(
                                student_name=convert_to_latin(register_form.student_name.data.strip().title()),
                                student_surname=convert_to_latin(" ".join(word.title() for word in register_form.student_surname.data.strip().split())),
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
            except SQLAlchemyError as e:
                db.session.rollback()
                logger.error(f"Greška pri registraciji učenika: {str(e)}")
                flash('Došlo je do greške pri registraciji učenika.', 'danger')
                return render_template('errors/500.html'), 500
                
        return render_template('student_list.html', 
                                title='Učenici', 
                                legend="Učenici",
                                register_form=register_form, 
                                edit_form=edit_form,
                                plus_one_button=plus_one_button,
                                active_date_start=active_date_start,
                                active_date_end=active_date_end,
                                danas=danas,
                                route_name=route_name,
                                license_expired=license_expired)
    except Exception as e:
        logger.error(f"Neočekivana greška u student_list: {str(e)}")
        flash('Došlo je do neočekivane greške.', 'danger')
        return render_template('errors/500.html'), 500


@students.route('/api/students_list')
def api_students_list():
    try:
        students_query = Student.query.filter(Student.student_class < 9)
        
        # search filter
        search = request.args.get('search[value]')
        student_class = request.args.get('searchRazred')
        student_section = request.args.get('searchOdeljenje')
        logging.debug(f'debug: {search=} {student_class=} {student_section=}')
        
        try:
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
        except SQLAlchemyError as e:
            logger.error(f"Greška pri filtriranju učenika: {str(e)}")
            return jsonify({
                'error': 'Došlo je do greške pri pretraživanju učenika',
                'data': [],
                'recordsFiltered': 0,
                'recordsTotal': 0,
                'draw': request.args.get('draw', type=int)
            }), 500
        
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
        
        try:
            students_query = students_query.offset(start).limit(length)
            students_list = []
            for student in students_query:
                new_dict = {
                    'id': str(student.id).zfill(4),
                    'student_name': student.student_name,
                    'student_surname': student.student_surname,
                    'student_class': student.student_class,
                    'student_section': student.student_section,
                    'parent_email': student.parent_email if student.parent_email else "",
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
        except SQLAlchemyError as e:
            logger.error(f"Greška pri učitavanju učenika: {str(e)}")
            return jsonify({
                'error': 'Došlo je do greške pri učitavanju učenika',
                'data': [],
                'recordsFiltered': 0,
                'recordsTotal': 0,
                'draw': request.args.get('draw', type=int)
            }), 500
            
    except Exception as e:
        logger.error(f"Neočekivana greška u api_students_list: {str(e)}")
        return jsonify({
            'error': 'Došlo je do neočekivane greške',
            'data': [],
            'recordsFiltered': 0,
            'recordsTotal': 0,
            'draw': request.args.get('draw', type=int)
        }), 500



@students.route('/class_plus_one', methods=['GET', 'POST'])
def class_plus_one():
    try:
        # Dohvatanje podataka iz baze
        try:
            students = Student.query.filter(Student.student_class < 100).all()
            school = School.query.first()
            class_plus_one = school.class_plus_one
        except SQLAlchemyError as e:
            logger.error(f"Greška pri dohvatanju podataka iz baze: {str(e)}")
            flash('Došlo je do greške pri učitavanju podataka.', 'danger')
            return redirect(url_for('students.student_list'))

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
            logger.info('Ove godine, razred svih učenika je već promenjen putem masovne promene.')
            flash('Ove godine, razred svih učenika je već promenjen putem masovne promene.', 'info')
        elif class_plus_one < start_of_school_year:
            logger.info('Prebacivanje učenika u sledeći razred...')
            try:
                for student in students:
                    student.student_class = int(student.student_class) + 1
                school.class_plus_one = now
                db.session.commit()
                flash('Razred je uspešno promenjen za sve učenike. Za učenike koji su ponavljali razred, potrebno je ručno ažurirati njihove podatke.', 'success')
            except SQLAlchemyError as e:
                db.session.rollback()
                logger.error(f"Greška pri ažuriranju razreda: {str(e)}")
                flash('Došlo je do greške pri promeni razreda. Promene nisu sačuvane.', 'danger')
        else:
            logger.warning('Pokušaj promene razreda van dozvoljenog perioda.')
            flash('Došlo je do greške. Nisu promenjeni razredi kod učenika.', 'danger')

        return redirect(url_for('students.student_list'))
        
    except Exception as e:
        logger.error(f"Neočekivana greška u class_plus_one: {str(e)}")
        flash('Došlo je do neočekivane greške.', 'danger')
        return redirect(url_for('students.student_list'))

@students.route('/student/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    try:
        # Provera da li student postoji
        try:
            student = Student.query.get(student_id)
            if not student:
                flash('Učenik nije pronađen.', 'danger')
                return redirect(url_for('students.student_list'))
        except SQLAlchemyError as e:
            logger.error(f"Greška pri dohvatanju učenika: {str(e)}")
            flash('Došlo je do greške pri pristupu podacima učenika.', 'danger')
            return redirect(url_for('students.student_list'))

        # Provera autentifikacije i lozinke
        if not current_user.is_authenticated:
            flash('Morate biti prijavljeni da biste pristupili ovoj stranici', 'danger')
            return redirect(url_for('users.login'))
        elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
            logger.warning(f'Pogrešna lozinka pri pokušaju brisanja učenika: {student.student_name} {student.student_surname}')
            flash(f'Pogrešna lozinka! nije obrisan profil učenika: {student.student_name} {student.student_surname}', 'danger')
            return redirect(url_for('students.student_list'))
        
        # Provera zaduženja i brisanje/arhiviranje
        try:
            list_of_students_with_debts = TransactionRecord.query.filter_by(student_id=student.id).all()
            logger.debug(f'{list_of_students_with_debts=}')
            
            if list_of_students_with_debts:
                logger.info(f'Učenik {student.student_name} {student.student_surname} ima zaduženje, prebacuje se u arhivu (razred+100)')
                student.student_class += 100
            else:
                logger.info(f'Učenik {student.student_name} {student.student_surname} nema zaduženje, briše se iz baze')
                db.session.delete(student)
                
            db.session.commit()
            flash(f'Profil učenika "{student.student_name} {student.student_surname}" je obrisan.', 'success')
            
        except SQLAlchemyError as e:
            db.session.rollback()
            logger.error(f"Greška pri brisanju/arhiviranju učenika: {str(e)}")
            flash('Došlo je do greške pri brisanju učenika. Promene nisu sačuvane.', 'danger')
            
        return redirect(url_for("students.student_list"))
        
    except Exception as e:
        logger.error(f"Neočekivana greška u delete_student: {str(e)}")
        flash('Došlo je do neočekivane greške.', 'danger')
        return redirect(url_for('students.student_list'))
