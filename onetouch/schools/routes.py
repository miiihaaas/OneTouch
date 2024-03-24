from flask import Blueprint, render_template, redirect, url_for, flash, request
from onetouch import db, app
from onetouch.models import School
from onetouch.schools.forms import EditSchoolForm, BankAccountForm
from flask_login import current_user

schools = Blueprint('schools', __name__)


@schools.route('/school', methods=['GET', 'POST'])
def school_profile():
    school = School.query.first()
    if not current_user.is_authenticated:
        flash('Morate da budete prijavljeni da biste pristupili ovoj stranici.', 'info')
        return redirect(url_for('users.login'))
        
    form = EditSchoolForm()
    if form.validate_on_submit():
        print('validna forma!!!')
        school.school_bank_accounts = {"bank_accounts": []}
        for bank_account_form in form.school_bank_accounts.entries:
            if bank_account_form.bank_account_number.data.strip() and bank_account_form.reference_number_spiri.data.strip():
                school.school_bank_accounts["bank_accounts"].append({
                    "bank_account_number": bank_account_form.bank_account_number.data,
                    "reference_number_spiri": bank_account_form.reference_number_spiri.data
                })

        school.school_name = form.school_name.data
        school.school_address = form.school_address.data
        school.school_zip_code = form.school_zip_code.data
        school.school_city = form.school_city.data
        school.school_municipality = form.school_municipality.data
        db.session.commit()
        flash('Podaci škole su ažurirani.', 'success')
        return redirect(url_for('main.home'))
    elif request.method == 'GET':
        form.school_name.data = school.school_name
        form.school_address.data = school.school_address
        form.school_zip_code.data = school.school_zip_code
        form.school_city.data = school.school_city
        form.school_municipality.data = school.school_municipality
        bank_accounts_json = school.school_bank_accounts.get('bank_accounts', [])
        for bank_account_data in bank_accounts_json:
            form.school_bank_accounts[-1].bank_account_number.data = bank_account_data.get('bank_account_number', '')
            form.school_bank_accounts[-1].reference_number_spiri.data = bank_account_data.get('reference_number_spiri', '')
            form.school_bank_accounts.append_entry()
        
        form.school_bank_accounts[-1].bank_account_number.data = ''
        form.school_bank_accounts[-1].reference_number_spiri.data = ''
    else:
        # Prikazujemo greške validacije
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')

    return render_template('school.html', title='Podaci škole', legend="Podaci škole", form=form)

