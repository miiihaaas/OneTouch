from bs4 import BeautifulSoup
from datetime import date
from flask import Blueprint, jsonify
from flask import render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt
from onetouch.models import Supplier, Service, ServiceItem, User
from onetouch.suppliers.forms import RegisterSupplierModalForm, EditSupplierModalForm, EditServiceModalForm, RegisterServiceModalForm, RegisterServiceProfileModalForm, EditServiceProfileModalForm
from flask_login import login_required, current_user


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
    suppliers = Supplier.query.all()
    edit_form = EditSupplierModalForm()
    register_form = RegisterSupplierModalForm()
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        supplier = Supplier.query.get(request.form.get('supplier_id'))
        
        supplier.supplier_name = edit_form.supplier_name.data
        supplier.archived = edit_form.archived.data
        db.session.commit()
        flash(f'Izmene profila dobavljača "{supplier.supplier_name}" su sačuvane.', 'success')
        return redirect(url_for('suppliers.supplier_list'))
    elif request.method == 'GET': 
        supplier = Supplier.query.get(request.form.get('supplier_id'))
        #
    
    if register_form.validate_on_submit() and request.form.get('submit_register'):
        supplier = Supplier(supplier_name=register_form.supplier_name.data,
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
                            register_form=register_form)


@suppliers.route('/service_list', methods=['GET', 'POST'])
def service_list():
    services=Service.query.all()
    edit_form = EditServiceModalForm()
    edit_form.reset()
    suppliers_chices_not_archived = [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).all()]
    suppliers_chices = [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).filter(Supplier.archived == False).all()]
    edit_form.supplier_id.choices = suppliers_chices_not_archived
    register_form = RegisterServiceModalForm()
    register_form.reset()
    register_form.supplier_id.choices = suppliers_chices
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        print('edit form triggered.')
        service = Service.query.get(request.form.get('service_id'))
        print(request.form.get('service_id'))
        print(service)
        
        service.service_name = edit_form.service_name.data
        service.payment_per_unit = edit_form.payment_per_unit.data
        service.supplier_id = edit_form.supplier_id.data
        service.archived = edit_form.archived.data
        
        db.session.commit()
        flash(f'Podaci usluge "{service.service_name}" su ažurirani.', 'success')
        return redirect(url_for('suppliers.service_list'))
    
    if register_form.validate_on_submit() and request.form.get('submit_register'):
        print('register form triggered.')
        service = Service(service_name=register_form.service_name.data, 
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
                            register_form=register_form)
    


# @suppliers.route('/service/<int:service_id>/delete', methods=['POST'])
# @login_required
# def delete_service(service_id):
#     service = Service.query.get(service_id)
#     if not current_user.is_authenticated:
#         flash('Morate da budete ulogovani da biste pristupili ovoj stranici', 'danger')
#         return redirect(url_for('users.login'))
#     elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
#         print ('nije dobar password')
#         abort(403)
#     else:
#         flash(f'Uspešno je obrisana usluga "{service.service_name}"', 'success')
#         db.session.delete(service)
#         db.session.commit()
#         return redirect(url_for("suppliers.service_list"))
    

@suppliers.route('/service_profile_list', methods=['POST', 'GET'])
@login_required
def service_profile_list():
    service_profiles = ServiceItem.query.all()
    register_form = RegisterServiceProfileModalForm()
    edit_form = EditServiceProfileModalForm()
    
    register_form.supplier_id.choices = [(0, "Selektujte dobavljača")] + [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).filter(Supplier.archived == False).all()]
    register_form.service_id.choices = [(0, "Selektujte uslugu")] + [(s.id, s.service_name) for s in db.session.query(Service.id, Service.service_name).filter(Service.archived == False).all()] # '/get_services' - ajax ažurira dinamičnu listu
    
        
    edit_form.supplier_id.choices = [(0, "Selektujte dobavljača")] + [(s.id, s.supplier_name) for s in db.session.query(Supplier.id, Supplier.supplier_name).filter(Supplier.archived == False).all()]
    edit_form.service_id.choices = [(0, "Selektujte uslugu")] + [(s.id, s.service_name) for s in Service.query.all()] #todo: napraviti da bude dinamično na osnovu supplier_id
    
    if request.form.get('submit_edit'):
        print('porlazi submit edit dugme')
        
    if not edit_form.validate_on_submit():
        print('nije validna edit forma')
        for field, errors in edit_form.errors.items():
            for error in errors:
                print(f'{field}: {error}')
    
    if edit_form.validate_on_submit() and request.form.get('submit_edit'):
        service_profile = ServiceItem.query.get(request.form.get('get_service_profile'))
        print('validation, edit from, service profile')
        print(f"klasa je: classes-{service_profile.id}") #todo: probaj 'beautifulsoup4'
        class_list = request.form.getlist(f"classes-{service_profile.id}")
        print(f'{class_list=}')
        class_list_string = ', '.join(class_list)
        print(f'classes string: {class_list_string}')
        print(f'validacija edit forme: {service_profile}')
        service_profile.service_item_name = edit_form.service_item_name.data
        service_profile.service_item_date = date.today()
        service_profile.supplier_id = edit_form.supplier_id.data
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
        if service_profile.installment_number == 1:
            service_profile.installment_1 = service_profile.price
        db.session.commit()
        return redirect(url_for("suppliers.service_profile_list"))
        
    
    if register_form.validate_on_submit() and request.form.get('submit_register'):
        print('validation, register from, service profile')
        class_list = request.form.getlist("classes")
        class_list_string = ', '.join(class_list)
        print(f'classes string: {class_list_string}')
        
        if register_form.installment_number.data == '1':
            register_form.installment_1.data = register_form.price.data
        
        service_profile = ServiceItem(service_item_name=register_form.service_item_name.data,
                                        service_item_date=date.today(),
                                        supplier_id=register_form.supplier_id.data,
                                        service_id=register_form.service_id.data,
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
        print(f'{service_profile.installment_number=}')
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
                            edit_form = edit_form)

#! AJAX routes
@suppliers.route('/get_services', methods=['POST'])
def get_services():
    supplier_id = request.form.get('supplier_id', 0, type=int)
    services = Service.query.filter_by(supplier_id=supplier_id, archived=False).all()
    print(f'services: {[s.archived for s in services]}')
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
    print(f'delete profile section: {service_profile_id}')
    service_profile = ServiceItem.query.get_or_404(service_profile_id)
    if not current_user.is_authenticated:
        flash('Morate da budete ulogovani da biste pristupili ovoj stranici', 'danger')
        return redirect(url_for('users.login'))
    elif not bcrypt.check_password_hash(current_user.user_password, request.form.get("input_password")):
        print ('nije dobar password')
        flash('Niste dobro uneli lozinku.', 'danger')
        return redirect(url_for('suppliers.service_profile_list'))
    else:
        flash(f'Uspešno je obrisana usluga "{service_profile.service_item_name}".', 'success')
        db.session.delete(service_profile)
        db.session.commit()
        return redirect(url_for("suppliers.service_profile_list"))