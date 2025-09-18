from flask import Blueprint, render_template, redirect, url_for, flash, request
from onetouch import db, app
from onetouch.models import School
from onetouch.schools.forms import EditSchoolForm, BankAccountForm
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError
import logging

schools = Blueprint('schools', __name__)

logger = logging.getLogger(__name__)

@schools.route('/school', methods=['GET', 'POST'])
@login_required
def school_profile():
    try:
        route_name = request.endpoint
        school = School.query.first()
        if not school:
            logger.error("School record not found in database")
            flash('Greška: Podaci o školi nisu pronađeni.', 'danger')
            return redirect(url_for('main.home'))
            
        form = EditSchoolForm()
        if form.validate_on_submit():
            try:
                # Reset bank accounts list
                school.school_bank_accounts = {"bank_accounts": []}
                
                # Process bank account forms
                for bank_account_form in form.school_bank_accounts.entries:
                    account_number = bank_account_form.bank_account_number.data.strip()
                    reference_number = bank_account_form.reference_number_spiri.data.strip()
                    
                    # if account_number and reference_number:
                    if account_number:
                        try:
                            school.school_bank_accounts["bank_accounts"].append({
                                "bank_account_number": account_number,
                                "reference_number_spiri": reference_number
                            })
                        except SQLAlchemyError as e:
                            db.session.rollback()
                            logger.error(f"Database error while adding bank account: {str(e)}")
                            flash('Došlo je do greške pri čuvanju podataka. Pokušajte ponovo.', 'danger')
                            return redirect(url_for('schools.school_profile'))

                # Update school details
                school.school_name = form.school_name.data.strip()
                school.school_address = form.school_address.data.strip()
                school.school_zip_code = form.school_zip_code.data.strip()
                school.school_city = form.school_city.data.strip()
                school.school_municipality = form.school_municipality.data.strip()
                school.school_phone_number = form.school_phone_number.data.strip()
                school.school_email = form.school_email.data.strip()
                
                db.session.commit()
                logger.info(f"School profile updated successfully by user {current_user.id}")
                flash('Podaci škole su uspešno ažurirani.', 'success')
                
            except SQLAlchemyError as e:
                db.session.rollback()
                logger.error(f"Database error while updating school profile: {str(e)}")
                flash('Došlo je do greške pri čuvanju podataka. Pokušajte ponovo.', 'danger')
                return render_template('errors/500.html'), 500
                
        elif request.method == 'GET':
            # Populate form with existing data
            try:
                form.school_name.data = school.school_name
                form.school_address.data = school.school_address
                form.school_zip_code.data = school.school_zip_code
                form.school_city.data = school.school_city
                form.school_municipality.data = school.school_municipality
                form.school_phone_number.data = school.school_phone_number
                form.school_email.data = school.school_email
                
                # Populate bank accounts
                bank_accounts_json = school.school_bank_accounts.get('bank_accounts', [])
                for bank_account_data in bank_accounts_json:
                    form.school_bank_accounts[-1].bank_account_number.data = bank_account_data.get('bank_account_number', '')
                    form.school_bank_accounts[-1].reference_number_spiri.data = bank_account_data.get('reference_number_spiri', '')
                    form.school_bank_accounts.append_entry()
                
                # Add empty entry for new account
                form.school_bank_accounts[-1].bank_account_number.data = ''
                form.school_bank_accounts[-1].reference_number_spiri.data = ''
                
            except Exception as e:
                logger.error(f"Error populating school form: {str(e)}")
                flash('Greška pri učitavanju podataka škole.', 'danger')
                return render_template('errors/500.html'), 500
                
        else:
            # Show validation errors
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'Greška u polju {field}: {error}', 'danger')

        return render_template('school.html', 
                                title='Podaci škole', 
                                legend="Podaci škole", 
                                form=form, 
                                route_name=route_name)

    except Exception as e:
        logger.error(f"Unexpected error in school_profile route: {str(e)}")
        flash('Došlo je do neočekivane greške. Molimo pokušajte ponovo.', 'danger')
        return render_template('errors/500.html'), 500
