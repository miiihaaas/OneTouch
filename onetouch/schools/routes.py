from flask import Blueprint, render_template, redirect, url_for, flash, request
from onetouch import db, app
from onetouch.models import School, Student
from onetouch.schools.forms import EditSchoolForm
from flask_login import current_user

schools = Blueprint('schools', __name__)

@schools.route('/school', methods=['GET', 'POST'])
def school_profile():
    school = School.query.first()
    print(school.school_name)
    if not current_user.is_authenticated:
        flash('Morate da budete prijavljeni da biste pristupili ovoj stranici.', 'info')
        return redirect(url_for('users.login'))
        
    form = EditSchoolForm()
    if form.validate_on_submit():
        school.school_name = form.school_name.data
        school.school_address = form.school_address.data
        school.school_zip_code = form.school_zip_code.data
        school.school_city = form.school_city.data
        school.school_municipality = form.school_municipality.data
        school.school_bank_account = form.school_bank_account.data
        db.session.commit()
        flash('Podaci škole su ažurirani.', 'success')
        return redirect(url_for('main.home'))
    elif request.method == 'GET':
        form.school_name.data = school.school_name
        form.school_address.data = school.school_address
        form.school_zip_code.data = school.school_zip_code
        form.school_city.data = school.school_city
        form.school_municipality.data = school.school_municipality
        form.school_bank_account.data = school.school_bank_account
    
    return render_template('school.html', title='Podaci škole', legend="Podaci škole", form=form)
    
