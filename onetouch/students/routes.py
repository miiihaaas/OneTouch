from datetime import datetime
from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt
from onetouch.models import Student, ServiceItem, StudentDebt, School, TransactionRecord
from onetouch.students.forms import EditStudentModalForm, RegisterStudentModalForm
from flask_login import login_required, current_user
import xml.etree.ElementTree as ET
from flask import jsonify


students = Blueprint('students', __name__)


@students.route('/student_list', methods=['GET', 'POST'])
def student_list():
    danas = datetime.now()
    active_date_start = danas.replace(month=4, day=15)
    active_date_end = danas.replace(month=9, day=15)
    students = Student.query.filter(Student.student_class < 9).all()
    edit_form = EditStudentModalForm()
    register_form = RegisterStudentModalForm()
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        student = Student.query.get(request.form.get('get_student'))
        
        student.student_name = edit_form.student_name.data.capitalize()
        student.student_surname = edit_form.student_surname.data.capitalize()
        student.student_class = edit_form.student_class.data
        student.student_section = edit_form.student_section.data
        student.parent_email = edit_form.parent_email.data
        db.session.commit()
        return redirect(url_for('students.student_list'))
    elif request.method == 'GET': # and request.form.get('get_student') != None:
        print(f'get: {request.form.get("get_student")}')
        student = Student.query.get(request.form.get('get_student'))
        # print(student.student_name, student.student_surname, student.student_class)
        
    #     edit_form.student_name = edit_form.student_name.data
    #     edit_form.student_surname = edit_form.student_surname.data
    #     edit_form.student_class = str(edit_form.student_class.data)
    #     edit_form.student_section = edit_form.student_section.data

    if register_form.validate_on_submit() and request.form.get('submit_register'):
        student = Student(student_name=register_form.student_name.data.capitalize(),
                        student_surname=register_form.student_surname.data.capitalize(),
                        student_class=str(register_form.student_class.data),
                        student_section=register_form.student_section.data,
                        parent_email=register_form.parent_email.data)
        print(student.student_name, student.student_surname, student.student_class)
        db.session.add(student)
        db.session.commit()
        print("inputi su validni")
        return redirect(url_for('students.student_list'))
    return render_template('student_list.html', 
                            title='Učenici', 
                            legend="Učenici", 
                            students=students, 
                            edit_form=edit_form, 
                            register_form=register_form,
                            active_date_start=active_date_start,
                            active_date_end=active_date_end,
                            danas=danas)


@students.route('/class_plus_one', methods=['GET', 'POST'])
def class_plus_one():
    students = Student.query.filter(Student.student_class < 9).all()
    for student in students:
        student.student_class = int(student.student_class) + 1
        db.session.commit()
    return redirect(url_for('students.student_list'))


@students.route('/student/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get(student_id)
    if not current_user.is_authenticated:
        flash('Morate da budete prijavljeni da biste pristupili ovoj stranici', 'danger')
        return redirect(url_for('users.login'))
    elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
        print ('nije dobar password')
        abort(403)
    else:
        # proveri da li je studeent zadužen nekom uslugom
        list_of_students_with_debts = TransactionRecord.query.filter_by(student_id=student.id).all()
        print(f'{list_of_students_with_debts=}')
        if list_of_students_with_debts:
            print('student ima zaduzenje, prebacujem ga u 9. razred')
            student.student_class = 9
        else:
            print('student nema zaduženje, brišem ga iz baze')
            db.session.delete(student)
        db.session.commit()
        return redirect(url_for("students.student_list"))





