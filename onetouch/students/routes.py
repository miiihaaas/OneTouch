from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt
from onetouch.models import Student, ServiceItem
from onetouch.students.forms import EditStudentModalForm, RegisterStudentModalForm
from flask_login import login_required, current_user


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


@students.route('/student_debts', methods=['POST', 'GET'])
@login_required
def student_debts():
    students = Student.query.all()
    service_items = ServiceItem.query.all()
    print(f'{service_items=}')
    return render_template('student_debts.html', students=students, service_items=service_items)

#! Ajax
@students.route('/get_service_items', methods=['POST'])
def get_service_items():
    service_item_class = request.form.get('classes', 0, type=int)
    print(f'from AJAX service items: {service_item_class=}')
    options = [(0, "Selektujte uslugu")]
    service_items = ServiceItem.query.all()
    for service_item in service_items:
        if str(service_item_class) in service_item.service_item_class:
            options.append((service_item.id, service_item.service_item_service.service_name + " - " + service_item.service_item_name))
            print(options)
    html = ''
    for option in options:
        html += '<option value="{0}">{1}</option>'.format(option[0], option[1])
    return html


@students.route('/get_installments', methods=['POST'])
def get_installments():
    print(request.form)
    service_item_id = int(request.form.get('installments'))
    print(f'from AJAX installments: {service_item_id=}')
    options = [(0, "Selektujte ratu")]
    service_item = ServiceItem.query.get_or_404(service_item_id)
    
    for i in range(1, service_item.installment_number + 1):
        options.append((i, f'Rata {i}'))
        installment_attr = f'installment_{i}'
        installment_option = getattr(service_item, installment_attr)
        print(f'{installment_option=}')
    
    html = ''
    for option in options:
        html += '<option value="{0}">{1}</option>'.format(option[0], option[1])
    return html


@students.route('/get_installment_values', methods=['POST'])
def get_installment_values():
    print(request.form)
    service_item_id = int(request.form.get('installments'))
    installment_number = int(request.form.get('installment_values'))
    print(f'{service_item_id=} {installment_number=}')
    service_item = ServiceItem.query.get_or_404(service_item_id)
    print(service_item)
    installment_attr = f'installment_{installment_number}'
    installment_value_result = {"result" : getattr(service_item,installment_attr)} 
    print(f'{installment_value_result=}')
    return installment_value_result