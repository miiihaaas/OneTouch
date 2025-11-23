from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from onetouch.supplier_invoices import supplier_invoices
from onetouch.supplier_invoices.forms import InvoiceForm, DeleteInvoiceForm
from onetouch.models import SupplierInvoice, Supplier, School
from onetouch import db

@supplier_invoices.route('/invoices_list', methods=['GET', 'POST'])
@login_required
def invoices_list():
    """Lista faktura sa CRUD operacijama kroz modale."""

    # Učitaj dobavljače - potrebni i za GET i za POST
    dobavljaci = Supplier.query.filter_by(archived=False).order_by(Supplier.supplier_name).all()

    # POST - Obrada forme
    if request.method == 'POST':
        if 'submit_register' in request.form:
            forma = InvoiceForm()
            forma.supplier_id.choices = [(d.id, d.supplier_name) for d in dobavljaci]
            if forma.validate_on_submit():
                faktura = SupplierInvoice(
                    invoice_number=forma.invoice_number.data,
                    invoice_date=forma.invoice_date.data,
                    traffic_date=forma.traffic_date.data,
                    supplier_id=forma.supplier_id.data,
                    total_amount=forma.total_amount.data
                )
                db.session.add(faktura)
                db.session.commit()
                flash('Faktura uspešno kreirana.', 'success')
            else:
                flash('Greška pri kreiranju fakture.', 'danger')

        elif 'submit_edit' in request.form:
            faktura_id = request.form.get('invoice_id')
            forma = InvoiceForm()
            forma.supplier_id.choices = [(d.id, d.supplier_name) for d in dobavljaci]
            if forma.validate_on_submit():
                faktura = SupplierInvoice.query.get_or_404(faktura_id)
                faktura.invoice_number = forma.invoice_number.data
                faktura.invoice_date = forma.invoice_date.data
                faktura.traffic_date = forma.traffic_date.data
                faktura.supplier_id = forma.supplier_id.data
                faktura.total_amount = forma.total_amount.data
                db.session.commit()
                flash('Faktura uspešno ažurirana.', 'success')

        elif 'submit_delete' in request.form:
            faktura_id = request.form.get('invoice_id')
            faktura = SupplierInvoice.query.get_or_404(faktura_id)
            db.session.delete(faktura)
            db.session.commit()
            flash('Faktura uspešno obrisana.', 'success')

        return redirect(url_for('supplier_invoices.invoices_list'))

    # GET - Prikaži listu
    skola = School.query.first()
    fakture = SupplierInvoice.query.order_by(SupplierInvoice.invoice_date.desc()).all()

    invoice_forma = InvoiceForm()
    invoice_forma.supplier_id.choices = [(d.id, d.supplier_name) for d in dobavljaci]

    return render_template('supplier_invoices/invoices_list.html',
                            title='Fakture dobavljača',
                            legend='Fakture dobavljača',
                            fakture=fakture,
                            dobavljaci=dobavljaci,
                            invoice_forma=invoice_forma,
                            skola=skola)
