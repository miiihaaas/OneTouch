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
    students = Student.query.all()
    edit_form = EditStudentModalForm()
    register_form = RegisterStudentModalForm()
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        student = Student.query.get(request.form.get('get_student'))
        
        student.student_name = edit_form.student_name.data.capitalize()
        student.student_surname = edit_form.student_surname.data.capitalize()
        student.student_class = edit_form.student_class.data
        student.student_section = edit_form.student_section.data
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
                        student_section=register_form.student_section.data)
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
                            register_form=register_form)


@students.route('/student/<int:student_id>/delete', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get(student_id)
    if not current_user.is_authenticated:
        flash('Morate da budete ulogovani da biste pristupili ovoj stranici', 'danger')
        return redirect(url_for('users.login'))
    elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
        print ('nije dobar password')
        abort(403)
    else:
        db.session.delete(student)
        db.session.commit()
        return redirect(url_for("students.student_list"))





