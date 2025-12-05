from flask import Blueprint, redirect, url_for, flash
from flask_login import current_user
from onetouch.models import School

supplier_invoices = Blueprint('supplier_invoices', __name__)

@supplier_invoices.before_request
def check_supplier_billing_access():
    """Blokira pristup ako škola nema aktiviranu opciju."""
    if not current_user.is_authenticated:
        return redirect(url_for('users.login'))

    school = School.query.first()
    if not school or not school.supplier_billing_options:
        flash('Modul fakturisanja dobavljača nije dostupan.', 'warning')
        return redirect(url_for('main.home'))

from onetouch.supplier_invoices import routes
