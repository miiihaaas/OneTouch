from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt
from onetouch.models import Teacher
from onetouch.teachers.forms import RegisterTeacherModalForm, EditTeacherModalForm
from flask_login import login_required, current_user


teachers = Blueprint('teachers', __name__)


@teachers.route('/teacher_list', methods=['GET', 'POST'])
def teacher_list():
    teachers = Teacher.query.all()
    edit_form = EditTeacherModalForm()
    register_form = RegisterTeacherModalForm() 
    if register_form.validate_on_submit() and request.form.get('submit_register'):
        print('register form validation')
        teacher=Teacher(teacher_name=register_form.teacher_name.data.capitalize(),
                        teacher_surname=register_form.teacher_surname.data.capitalize(),
                        teacher_class=register_form.teacher_class.data,
                        teacher_section=register_form.teacher_section.data)
        db.session.add(teacher)
        db.session.commit()
        return redirect(url_for('teachers.teacher_list'))
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        print('edit form validation')
        teacher = Teacher.query.get(request.form.get('get_teacher'))
        
        teacher.teacher_name = edit_form.teacher_name.data.capitalize()
        teacher.teacher_surname = edit_form.teacher_surname.data.capitalize()
        teacher.teacher_class = edit_form.teacher_class.data
        teacher.teacher_section = edit_form.teacher_section.data
        db.session.commit()
        return redirect(url_for('teachers.teacher_list'))
    elif request.method == 'GET' and request.form.get('get_teacher') != None:
        print(f'get: {request.form.get("get_teacher")}')
        teacher = Teacher.query.get(request.form.get('get_teacher'))
        
        #edit_form.teacher_name.data = teacher.teacher_name
    return render_template('teacher_list.html', title='Razredne starešine', 
                            legend='Razredne starešine', 
                            teachers=teachers, 
                            edit_form=edit_form, 
                            register_form=register_form)


@teachers.route('/teacher/<int:teacher_id>/delete', methods=['POST'])
@login_required
def delete_teacher(teacher_id):
    teacher = Teacher.query.get(teacher_id)
    if not current_user.is_authenticated:
        flash('Morate da budete ulogovani da biste pristupili ovoj stranici', 'danger')
        return redirect(url_for('users.login'))
    elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
        print ('nije dobar password')
        abort(403)
    else:
        db.session.delete(teacher)
        db.session.commit()
        return redirect(url_for("teachers.teacher_list"))