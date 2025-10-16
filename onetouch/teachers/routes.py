import logging
from datetime import datetime
from flask import Blueprint, render_template, url_for, flash, redirect, request, abort
from flask_login import login_required, current_user
from onetouch import db, bcrypt
from onetouch.models import Teacher, School
from onetouch.teachers.forms import RegisterTeacherModalForm, EditTeacherModalForm
from sqlalchemy.exc import SQLAlchemyError


teachers = Blueprint('teachers', __name__)

@teachers.route('/teacher_list', methods=['GET', 'POST'])
@login_required
def teacher_list():
    try:
        # Dohvatanje podataka
        try:
            teachers = Teacher.query.all()
            danas = datetime.now()
            active_date_start = danas.replace(month=4, day=15)
            active_date_end = danas.replace(month=9, day=15)
            school = School.query.first()
            license_expired = False
            try:
                if school and school.license_expiry_date:
                    days_left = school.days_until_license_expiry()
                    if days_left is not None and days_left <= 0:
                        license_expired = True
            except Exception as e:
                logging.error(f"Greška pri izračunavanju dana do isteka licence: {str(e)}")
                license_expired = False
            
            edit_form = EditTeacherModalForm()
            register_form = RegisterTeacherModalForm()
        except SQLAlchemyError as e:
            logging.error(f"Greška pri dohvatanju podataka: {str(e)}")
            flash('Došlo je do greške pri učitavanju podataka.', 'danger')
            return render_template('teacher_list.html', title='Odeljenske starešine', legend='Odeljenske starešine')
        
        # Registracija novog nastavnika
        if register_form.validate_on_submit() and request.form.get('submit_register'):
            try:
                teacher = Teacher(
                    teacher_name=register_form.teacher_name.data.title(),
                    teacher_surname=register_form.teacher_surname.data.title(),
                    teacher_class=register_form.teacher_class.data,
                    teacher_section=register_form.teacher_section.data
                )
                db.session.add(teacher)
                db.session.commit()
                flash(f'Dodat novi profil odeljanskog starešine: {teacher.teacher_name} {teacher.teacher_surname}', 'success')
                return redirect(url_for('teachers.teacher_list'))
            except SQLAlchemyError as e:
                db.session.rollback()
                logging.error(f"Greška pri registraciji nastavnika: {str(e)}")
                flash('Došlo je do greške pri dodavanju novog nastavnika.', 'danger')
                return redirect(url_for('teachers.teacher_list'))
        
        # Izmena postojećeg nastavnika
        if edit_form.validate_on_submit() and request.form.get('submit_edit'):
            try:
                logging.debug(f'edit form validation: {request.form.get("teacher_id")=}')
                teacher = Teacher.query.get(request.form.get('teacher_id'))
                if not teacher:
                    flash('Nastavnik nije pronađen.', 'danger')
                    return redirect(url_for('teachers.teacher_list'))
                
                teacher.teacher_name = edit_form.teacher_name.data.title()
                teacher.teacher_surname = edit_form.teacher_surname.data.title()
                teacher.teacher_class = edit_form.teacher_class.data
                teacher.teacher_section = edit_form.teacher_section.data
                db.session.commit()
                flash(f'Izmenjen je profil odeljanskog starešine: {teacher.teacher_name} {teacher.teacher_surname}', 'success')
                return redirect(url_for('teachers.teacher_list'))
            except SQLAlchemyError as e:
                db.session.rollback()
                logging.error(f"Greška pri izmeni nastavnika: {str(e)}")
                flash('Došlo je do greške pri izmeni podataka nastavnika.', 'danger')
                return redirect(url_for('teachers.teacher_list'))
                
        elif request.method == 'GET' and request.form.get('teacher_id') != None:
            logging.debug(f'get: {request.form.get("teacher_id")}')
            try:
                teacher = Teacher.query.get(request.form.get('teacher_id'))
                if not teacher:
                    flash('Nastavnik nije pronađen.', 'danger')
                    return redirect(url_for('teachers.teacher_list'))
            except SQLAlchemyError as e:
                logging.error(f"Greška pri dohvatanju nastavnika: {str(e)}")
                flash('Došlo je do greške pri pristupu podacima nastavnika.', 'danger')
                return redirect(url_for('teachers.teacher_list'))
        
        return render_template('teacher_list.html', 
                            title='Odeljenske starešine', 
                            legend='Odeljenske starešine', 
                            teachers=teachers, 
                            edit_form=edit_form, 
                            register_form=register_form,
                            active_date_start=active_date_start,
                            active_date_end=active_date_end,
                            danas=danas,
                            license_expired=license_expired,
                            school=school)
                            
    except Exception as e:
        logging.error(f"Neočekivana greška u teacher_list: {str(e)}")
        flash('Došlo je do neočekivane greške.', 'danger')
        return render_template('teacher_list.html', title='Odeljenske starešine', legend='Odeljenske starešine')


@teachers.route('/teacher/<int:teacher_id>/delete', methods=['POST'])
@login_required
def delete_teacher(teacher_id):
    try:
        # Provera da li nastavnik postoji
        try:
            teacher = Teacher.query.get(teacher_id)
            if not teacher:
                flash('Nastavnik nije pronađen.', 'danger')
                return redirect(url_for('teachers.teacher_list'))
        except SQLAlchemyError as e:
            logging.error(f"Greška pri dohvatanju nastavnika: {str(e)}")
            flash('Došlo je do greške pri pristupu podacima nastavnika.', 'danger')
            return redirect(url_for('teachers.teacher_list'))

        # Provera autentifikacije i lozinke
        if not current_user.is_authenticated:
            flash('Morate biti ulogovani da biste pristupili ovoj stranici', 'danger')
            return redirect(url_for('users.login'))
        elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
            logging.warning(f'Pogrešna lozinka pri pokušaju brisanja nastavnika: {teacher.teacher_name} {teacher.teacher_surname}')
            flash(f'Pogrešna lozinka! Nije obrisan profil odeljenskog starešine: {teacher.teacher_name} {teacher.teacher_surname}', 'danger')
            return redirect(url_for('teachers.teacher_list'))
        
        # Brisanje nastavnika
        try:
            db.session.delete(teacher)
            db.session.commit()
            flash(f'Obrisan je profil odeljenskog starešine: {teacher.teacher_name} {teacher.teacher_surname}', 'success')
        except SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Greška pri brisanju nastavnika: {str(e)}")
            flash('Došlo je do greške pri brisanju nastavnika.', 'danger')
            
        return redirect(url_for("teachers.teacher_list"))
        
    except Exception as e:
        logging.error(f"Neočekivana greška u delete_teacher: {str(e)}")
        flash('Došlo je do neočekivane greške.', 'danger')
        return redirect(url_for('teachers.teacher_list'))