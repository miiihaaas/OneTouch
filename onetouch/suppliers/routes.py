import builtins
import logging
from datetime import date
from flask import Blueprint, jsonify
from flask import render_template, url_for, flash, redirect, request, abort
from flask_login import login_required, current_user
from onetouch import db, bcrypt
from onetouch.models import Supplier, Service, ServiceItem, User, TransactionRecord, School
from onetouch.suppliers.forms import RegisterSupplierModalForm, EditSupplierModalForm, EditServiceModalForm, RegisterServiceModalForm, RegisterServiceProfileModalForm, EditServiceProfileModalForm
from onetouch.suppliers.functions import convert_to_latin


suppliers = Blueprint('suppliers', __name__)

def load_user(user_id):
    return User.query.get(int(user_id))


# Ova funkcija će proveriti da li je korisnik ulogovan pre nego što pristupi zaštićenoj ruti
@suppliers.before_request
def require_login():
    if request.endpoint and not current_user.is_authenticated:
        return redirect(url_for('users.login'))


@suppliers.route('/supplier_list', methods=['GET', 'POST'])
def supplier_list():
    route_name = request.endpoint
    suppliers = Supplier.query.filter(Supplier.id != 0).all()
    edit_form = EditSupplierModalForm()
    register_form = RegisterSupplierModalForm()
    if request.form.get('submit_edit'):
        if edit_form.validate_on_submit():
            supplier = Supplier.query.get(request.form.get('supplier_id'))
            logging.debug(f'{supplier.supplier_name=}; {supplier.archived=}')
            suppliers = Supplier.query.all()
            suppliers.remove(Supplier.query.get(supplier.id))
            
            supplier.supplier_name = convert_to_latin(edit_form.supplier_name.data)
            supplier.archived = edit_form.archived.data
            if supplier.supplier_name in [s.supplier_name for s in suppliers]:
                flash(f'Dobavljač sa nazivom "{supplier.supplier_name}" već postoji.', 'danger')
                return redirect(url_for('suppliers.supplier_list'))
            db.session.commit()
            flash(f'Izmene profila dobavljača "{supplier.supplier_name}" su sačuvane.', 'success')
            return redirect(url_for('suppliers.supplier_list'))
        elif request.method == 'GET': 
            supplier = Supplier.query.get(request.form.get('supplier_id'))
    if request.form.get('submit_register'):
        if register_form.validate_on_submit():
            existing_supplier = Supplier.query.filter_by(supplier_name=register_form.supplier_name.data).first()
            if existing_supplier:
                flash(f'Dobavljač sa nazivom "{existing_supplier.supplier_name}" već postoji.', 'danger')
                return redirect(url_for('suppliers.supplier_list'))
            supplier = Supplier(supplier_name=convert_to_latin(register_form.supplier_name.data),
                                archived=False)
            db.session.add(supplier)
            db.session.commit()
            flash(f'Registrovan je novi dobavljač "{supplier.supplier_name}".', 'success')
            return redirect(url_for('suppliers.supplier_list'))


    return render_template('supplier_list.html',
                            tite = 'Dobavljači',
                            legend = 'Dobavljači',
                            suppliers=suppliers,
                            edit_form=edit_form,
                            register_form=register_form,
                            route_name=route_name)


@suppliers.route('/service_list', methods=['GET', 'POST'])
def service_list():
    route_name = request.endpoint
    services=Service.query.filter(Service.id != 0).all()
    edit_form = EditServiceModalForm()
    edit_form.reset()
    suppliers_chices_not_archived = [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).all()]
    # suppliers_chices = [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).filter(Supplier.archived == False).all()]
    suppliers_chices = [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).filter(Supplier.archived == False, Supplier.id != 0).all()]
    edit_form.supplier_id.choices = suppliers_chices_not_archived
    register_form = RegisterServiceModalForm()
    register_form.reset()
    register_form.supplier_id.choices = suppliers_chices
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        service = Service.query.get(request.form.get('service_id'))
        logging.debug(request.form.get('service_id'))
        logging.debug(service)
        
        service.service_name = convert_to_latin(edit_form.service_name.data)
        service.payment_per_unit = edit_form.payment_per_unit.data
        service.supplier_id = edit_form.supplier_id.data
        service.archived = edit_form.archived.data
        
        db.session.commit()
        flash(f'Podaci usluge "{service.service_name}" su ažurirani.', 'success')
        return redirect(url_for('suppliers.service_list'))
    
    if register_form.validate_on_submit() and request.form.get('submit_register'):
        print('register form triggered.')
        service = Service(service_name=convert_to_latin(register_form.service_name.data), 
                            payment_per_unit=register_form.payment_per_unit.data,
                            supplier_id=register_form.supplier_id.data,
                            archived=False)
        db.session.add(service)
        db.session.commit()
        flash(f'Usluga "{service.service_name}" je registrovana.', 'success')
        return redirect(url_for('suppliers.service_list'))
    return render_template('service_list.html',
                            tite = 'Tip usluge',
                            legend = 'Tip usluge',
                            suppliers_chices=suppliers_chices,
                            services=services,
                            edit_form=edit_form,
                            register_form=register_form,
                            route_name=route_name)


@suppliers.route('/service_profile_list', methods=['POST', 'GET'])
@login_required
def service_profile_list():
    route_name = request.endpoint
    school = School.query.first()
    school_bank_accounts = school.school_bank_accounts.get('bank_accounts', [])
    school_reference_numbers_spiri = [bank_account['reference_number_spiri'][2:11] for bank_account in school_bank_accounts]
    logging.debug(f'{school_bank_accounts=}')
    
    def get_reference_number(school_bank_accounts, edit_bank_account):
        for bank_account in school_bank_accounts:
            if bank_account['reference_number_spiri'] == edit_bank_account:
                return bank_account['bank_account_number']
        return None
    
    
    
    # service_profiles = ServiceItem.query.all()
    service_profiles = ServiceItem.query.filter(ServiceItem.id != 0).all() #! svi koji nemaju id=0 koji je rezervisan za grešku

    register_form = RegisterServiceProfileModalForm()
    edit_form = EditServiceProfileModalForm()
    
    register_form.supplier_id.choices = [(0, "Selektujte dobavljača")] + [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).filter(Supplier.archived == False, Supplier.id != 0).all()]
    register_form.service_id.choices = [(0, "Selektujte uslugu")] + [(s.id, s.service_name) for s in db.session.query(Service.id, Service.service_name).filter(Service.archived == False, Service.id != 0).all()] # '/get_services' - ajax ažurira dinamičnu listu
    
        
    edit_form.supplier_id.choices = [(0, "Selektujte dobavljača")] + [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).filter(Supplier.archived == False).all()]
    edit_form.service_id.choices = [(0, "Selektujte uslugu")] + [(s.id, s.service_name) for s in Service.query.all() if s.id > 0] #todo: napraviti da bude dinamično na osnovu supplier_id
    
    if request.form.get('submit_edit'):
        print('porlazi submit edit dugme')
        
    if not edit_form.validate_on_submit():
        logging.debug('nije validna edit forma')
        for field, errors in edit_form.errors.items():
            for error in errors:
                logging.debug(f'{field}: {error}')
    
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        print(f'{request.form=}')
        service_profile = ServiceItem.query.get(request.form.get('get_service_profile'))
        logging.debug('validation, edit from, service profile')
        logging.debug(f"klasa je: classes-{service_profile.id}") #todo: probaj 'beautifulsoup4'
        class_list = request.form.getlist(f"service_item_class_")
        logging.debug(f'{class_list=}')
        class_list_string = ', '.join(class_list)
        logging.debug(f'classes string: {class_list_string}')
        logging.debug(f'validacija edit forme: {service_profile}')
        service_profile.service_item_name = convert_to_latin(edit_form.service_item_name.data)
        service_profile.service_item_date = date.today()
        service_profile.supplier_id = edit_form.supplier_id.data
        # service_profile.bank_account = edit_form.bank_account.data
        # service_profile.reference_number_spiri = get_reference_number(school_bank_accounts, edit_form.bank_account.data)
        service_profile.bank_account = get_reference_number(school_bank_accounts, edit_form.bank_account.data)
        service_profile.reference_number_spiri = edit_form.bank_account.data
        service_profile.service_id = edit_form.service_id.data
        service_profile.service_item_class = class_list_string
        service_profile.price = edit_form.price.data
        service_profile.installment_number = edit_form.installment_number.data
        service_profile.installment_1 = edit_form.installment_1.data
        service_profile.installment_2 = edit_form.installment_2.data
        service_profile.installment_3 = edit_form.installment_3.data
        service_profile.installment_4 = edit_form.installment_4.data
        service_profile.installment_5 = edit_form.installment_5.data
        service_profile.installment_6 = edit_form.installment_6.data
        service_profile.installment_7 = edit_form.installment_7.data
        service_profile.installment_8 = edit_form.installment_8.data
        service_profile.installment_9 = edit_form.installment_9.data
        service_profile.installment_10 = edit_form.installment_10.data
        service_profile.installment_11 = edit_form.installment_11.data
        service_profile.installment_12 = edit_form.installment_12.data
        service_profile.archived = edit_form.archived.data
        logging.debug(f'debug installment_number: {service_profile.installment_number=}; {type(service_profile.installment_number)=}')
        if service_profile.installment_number == "1":
            service_profile.installment_1 = service_profile.price
            logging.debug(f'dodeljena je ukupna cena u prvu vrednost polja prverate!')
        db.session.commit()
        flash(f'Uspesno ste izmenili podatke o usluzi: { service_profile.service_item_service.service_name } - { service_profile.service_item_name }', 'success')
        return redirect(url_for("suppliers.service_profile_list"))
        
    
    if register_form.validate_on_submit() and request.form.get('submit_register'):
        logging.debug('validation, register from, service profile')
        class_list = request.form.getlist("classes")
        class_list_string = ', '.join(class_list)
        logging.debug(f'classes string: {class_list_string}')
        
        if register_form.installment_number.data == '1':
            register_form.installment_1.data = register_form.price.data
        
        service_profile = ServiceItem(service_item_name=convert_to_latin(register_form.service_item_name.data),
                                        service_item_date=date.today(),
                                        supplier_id=register_form.supplier_id.data,
                                        service_id=register_form.service_id.data,
                                        # bank_account=register_form.bank_account.data,
                                        # reference_number_spiri=get_reference_number(school_bank_accounts, register_form.bank_account.data),
                                        bank_account=get_reference_number(school_bank_accounts, register_form.bank_account.data),
                                        reference_number_spiri=register_form.bank_account.data,
                                        service_item_class=class_list_string,
                                        price=register_form.price.data,
                                        installment_number=register_form.installment_number.data,
                                        installment_1=register_form.installment_1.data,
                                        installment_2=register_form.installment_2.data,
                                        installment_3=register_form.installment_3.data,
                                        installment_4=register_form.installment_4.data,
                                        installment_5=register_form.installment_5.data,
                                        installment_6=register_form.installment_6.data,
                                        installment_7=register_form.installment_7.data,
                                        installment_8=register_form.installment_8.data,
                                        installment_9=register_form.installment_9.data,
                                        installment_10=register_form.installment_10.data,
                                        installment_11=register_form.installment_11.data,
                                        installment_12=register_form.installment_12.data,
                                        archived=False)
        logging.debug(f'{service_profile.installment_number=}')
        if service_profile.installment_number == '1':
            service_profile.installment_1 = service_profile.price
        flash(f'Kreirana je usluga "{service_profile.service_item_name}"', 'success')
        db.session.add(service_profile)
        db.session.commit()
        return redirect(url_for("suppliers.service_profile_list"))
        
    
    return render_template('service_profile_list.html',
                            tite = 'Detalji usluge',
                            legend = 'Detalji usluge',
                            service_profiles= service_profiles,
                            register_form = register_form,
                            edit_form = edit_form, getattr=builtins.getattr,
                            route_name = route_name)

#! AJAX routes
@suppliers.route('/get_services', methods=['POST'])
def get_services():
    supplier_id = request.form.get('supplier_id', 0, type=int)
    services = Service.query.filter_by(supplier_id=supplier_id, archived=False).filter(Service.id != 0).all()
    logging.debug(f'services: {[s.archived for s in services]}')
    options = [(0, "Selektujte uslugu")] + [(s.id, s.service_name) for s in services]
    html = ''
    for option in options:
        html += '<option value="{0}">{1}</option>'.format(option[0], option[1])
    return html


@suppliers.route('/get_payment', methods=['POST'])
def get_payment():
    service_id = request.form.get('service_id', type=int)
    service = Service.query.get(service_id)
    return jsonify({'payment_per_unit': service.payment_per_unit})


@suppliers.route('/service_profile/<int:service_profile_id>/delete', methods=['POST'])
@login_required
def delete_service_profile(service_profile_id):
    logging.debug(f'delete profile section: {service_profile_id}')
    service_profile = ServiceItem.query.get_or_404(service_profile_id)
    transactions = TransactionRecord.query.filter_by(service_item_id=service_profile_id).all()
    if not current_user.is_authenticated:
        flash('Morate da budete ulogovani da biste pristupili ovoj stranici', 'danger')
        return redirect(url_for('users.login'))
    elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
        logging.debug ('nije dobar password')
        flash('Uneliste pogrešnu lozinku.', 'danger')
        return redirect(url_for('suppliers.service_profile_list'))
    elif transactions:
        flash(f'Usluga "{service_profile.service_item_name}" ima zaduženja i jedino što možete je da je arhivirate.', 'danger')
        return redirect(url_for('suppliers.service_profile_list'))
    else:
        flash(f'Uspešno je obrisana usluga "{service_profile.service_item_name}".', 'success')
        db.session.delete(service_profile)
        db.session.commit()
        return redirect(url_for("suppliers.service_profile_list"))