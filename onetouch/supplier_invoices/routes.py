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

@supplier_invoices.route('/supplier_saldo_list', methods=['GET', 'POST'])
@login_required
def supplier_saldo_list():
    """Lista dobavljača u kojoj se prikazuju saldo dobavljača."""
    from onetouch.models import SupplierInvoice, SupplierTransaction
    from sqlalchemy import func

    suppliers = Supplier.query.filter_by(archived=False).all()
    supplier_data = []

    for supplier in suppliers:
        # Zaduženje (fakture)
        total_invoiced = db.session.query(
            func.sum(SupplierInvoice.total_amount)
        ).filter(
            SupplierInvoice.supplier_id == supplier.id
        ).scalar() or 0.0

        # Isplate (transakcije)
        total_paid = db.session.query(
            func.sum(SupplierTransaction.amount)
        ).filter(
            SupplierTransaction.supplier_id == supplier.id
        ).scalar() or 0.0

        total_paid = abs(total_paid)  # Pretvori u pozitivan
        balance = total_invoiced - total_paid

        supplier_data.append({
            'supplier': supplier,
            'total_invoiced': total_invoiced,
            'total_paid': total_paid,
            'balance': balance
        })

    # Sortiraj po saldu (najveće dugovanje prvo)
    supplier_data.sort(key=lambda x: x['balance'], reverse=True)

    school = School.query.first()

    return render_template('supplier_invoices/supplier_saldo_list.html',
                            title='Pregled po dobavljačima',
                            legend='Pregled po dobavljačima',
                            supplier_data=supplier_data,
                            school=school)


@supplier_invoices.route('/supplier_saldo_detail/<int:supplier_id>', methods=['GET', 'POST'])
@login_required
def supplier_saldo_detail(supplier_id):
    """Detaljan pregled svih faktura i isplata za jednog dobavljača."""
    from onetouch.models import SupplierInvoice, SupplierTransaction

    supplier = Supplier.query.get_or_404(supplier_id)

    # Fakture
    invoices = SupplierInvoice.query.filter_by(supplier_id=supplier_id).all()

    # Isplate
    transactions = SupplierTransaction.query.filter_by(supplier_id=supplier_id).all()

    # Kombinuj sve stavke
    all_entries = []

    for invoice in invoices:
        # Normalizuj datum u date objekat (ako je datetime, konvertuj u date)
        invoice_date = invoice.invoice_date.date() if hasattr(invoice.invoice_date, 'date') else invoice.invoice_date
        all_entries.append({
            'date': invoice_date,
            'type': 'invoice',
            'description': f"Faktura {invoice.invoice_number}",
            'amount': invoice.total_amount,
            'reference': invoice.invoice_number,
            'id': invoice.id
        })

    for tx in transactions:
        payment_date = tx.supplier_payment.payment_date if tx.supplier_payment else tx.created_date.date()
        # Normalizuj datum u date objekat (ako je datetime, konvertuj u date)
        payment_date = payment_date.date() if hasattr(payment_date, 'date') else payment_date
        all_entries.append({
            'date': payment_date,
            'type': 'payment',
            'description': tx.purpose_of_payment or "Isplata",
            'amount': tx.amount,
            'reference': tx.reference_number,
            'id': tx.id
        })

    # Sortiraj po datumu, pa po ID-u (za konzistentan redosled kada su datumi isti)
    all_entries.sort(key=lambda x: (x['date'], x['id']))

    # Računaj running balance
    running_balance = 0.0
    for entry in all_entries:
        running_balance += entry['amount']
        entry['balance'] = running_balance

    # Ukupni iznosi
    total_invoiced = sum(e['amount'] for e in all_entries if e['type'] == 'invoice')
    total_paid = abs(sum(e['amount'] for e in all_entries if e['type'] == 'payment'))
    final_balance = running_balance

    school = School.query.first()

    return render_template('supplier_invoices/supplier_saldo_detail.html',
                            title=f'Pregled po dobavljaču: {supplier.supplier_name}',
                            legend=f'Pregled po dobavljaču: {supplier.supplier_name}',
                            supplier=supplier,
                            entries=all_entries,
                            total_invoiced=total_invoiced,
                            total_paid=total_paid,
                            final_balance=final_balance,
                            school=school)


@supplier_invoices.route('/posting_supplier_payment', methods=['GET', 'POST'])
@login_required
def posting_supplier_payment():
    """Učitavanje bankovnih izvoda - SAMO za dobavljačke isplate."""
    from onetouch.models import SupplierPayment, SupplierTransaction
    from onetouch.transactions.functions import parse_supplier_reference_number
    from datetime import datetime
    import xml.etree.ElementTree as ET

    if request.method == 'POST' and 'submitBtnImportData' in request.form:
        try:
            file = request.files['fileInput']

            if file.filename == '':
                flash('Niste izabrali XML fajl', 'danger')
                return redirect(url_for('supplier_invoices.posting_supplier_payment'))

            # Parsiranje XML-a
            xml_content = file.read()
            root = ET.fromstring(xml_content)

            # Ekstrakcija osnovnih podataka izvoda
            izvod_broj = root.find('.//BrojIzvoda').text if root.find('.//BrojIzvoda') is not None else 'N/A'
            izvod_datum_text = root.find('.//DatumIzvoda').text if root.find('.//DatumIzvoda') is not None else None
            racun_izvoda = root.find('.//RacunIzvoda').text if root.find('.//RacunIzvoda') is not None else None
            iznos_duguje_text = root.find('.//IznosDuguje').text if root.find('.//IznosDuguje') is not None else '0'
            iznos_duguje = float(iznos_duguje_text.replace(',', '.'))

            if izvod_datum_text:
                izvod_datum = datetime.strptime(izvod_datum_text, '%d.%m.%Y').date()
            else:
                flash('XML fajl ne sadrži datum izvoda', 'danger')
                return redirect(url_for('supplier_invoices.posting_supplier_payment'))

            # Provera da li izvod već postoji
            postojeci_izvod = SupplierPayment.query.filter_by(
                statment_nubmer=izvod_broj,
                payment_date=izvod_datum
            ).first()

            if postojeci_izvod:
                flash(f'Izvod {izvod_broj} od {izvod_datum.strftime("%d.%m.%Y.")} već je učitan za dobavljače!', 'warning')
                return redirect(url_for('supplier_invoices.posting_supplier_payment'))

            # Parsiranje stavki
            stavke = []
            for stavka_elem in root.findall('.//Stavka'):
                # Ekstrakcija podataka
                izvor_informacije = stavka_elem.find('IzvorInformacije').text if stavka_elem.find('IzvorInformacije') is not None else ''

                # SAMO isplate (IzvorInformacije = '1')
                if izvor_informacije != '1':
                    continue

                iznos_text = stavka_elem.find('Iznos').text if stavka_elem.find('Iznos') is not None else '0'
                iznos = float(iznos_text.replace(',', '.'))

                # U XML-u su isplate pozitivne, ali čuvamo kao negativne u bazi radi razlikovanja
                iznos = -abs(iznos)

                poziv_odobrenja = stavka_elem.find('PozivNaBrojOdobrenja').text if stavka_elem.find('PozivNaBrojOdobrenja') is not None else ''
                svrha_doznake = stavka_elem.find('SvrhaDoznake').text if stavka_elem.find('SvrhaDoznake') is not None else ''
                naziv_odobrenja = stavka_elem.find('NazivOdobrenja').text if stavka_elem.find('NazivOdobrenja') is not None else ''

                # Parsiranje poziva na broj - traži D#### u svrsi isplate
                parsed = parse_supplier_reference_number(svrha_doznake)

                # Priprema podataka za prikaz
                supplier_obj = None
                supplier_id = None
                supplier_name = 'NEDODELJENO'
                is_valid = False
                error_message = 'Dobavljač nije automatski prepoznat - dodeli ručno'

                # Ako je validna dobavljačka transakcija, automatski dodeli dobavljača
                if parsed['is_supplier'] and parsed['is_valid']:
                    supplier_id = parsed['supplier_id']
                    supplier_obj = Supplier.query.get(supplier_id)
                    if supplier_obj:
                        supplier_name = supplier_obj.supplier_name
                        is_valid = True
                        error_message = None
                elif parsed['is_supplier'] and not parsed['is_valid']:
                    # Poziv je D####, ali dobavljač ne postoji
                    supplier_id = parsed['supplier_id']
                    error_message = parsed['error_message']

                podaci = {
                    'iznos': iznos,
                    'poziv_odobrenja': poziv_odobrenja,
                    'svrha_doznake': svrha_doznake,
                    'naziv_odobrenja': naziv_odobrenja,
                    'supplier_id': supplier_id,
                    'supplier_name': supplier_name,
                    'is_valid': is_valid,
                    'error_message': error_message
                }

                stavke.append(podaci)

            if not stavke:
                flash('XML fajl ne sadrži isplate (IzvorInformacije=1). Proverite da li ste izabrali ispravan izvod.', 'warning')
                return redirect(url_for('supplier_invoices.posting_supplier_payment'))

            # Prikaz stavki za pregled
            suppliers = Supplier.query.filter_by(archived=False).order_by(Supplier.supplier_name).all()
            return render_template('supplier_invoices/posting_supplier_payment.html',
                                    legend=f'Učitavanje isplata dobavljačima',
                                    title=f'Učitavanje isplata dobavljačima',
                                    stavke=stavke,
                                    izvod_broj=izvod_broj,
                                    izvod_datum=izvod_datum,
                                    racun_izvoda=racun_izvoda,
                                    iznos_duguje=iznos_duguje,
                                    suppliers=suppliers,
                                    show_preview=True)

        except Exception as e:
            flash(f'Greška prilikom parsiranja XML fajla: {str(e)}', 'danger')
            return redirect(url_for('supplier_invoices.posting_supplier_payment'))

    if request.method == 'POST' and 'submitBtnSaveData' in request.form:
        try:
            # Kreiranje ili pronalaženje StudentPayment zapisa
            izvod_broj = request.form.get('izvod_broj')
            izvod_datum_str = request.form.get('izvod_datum')
            izvod_datum = datetime.strptime(izvod_datum_str, '%Y-%m-%d').date()
            racun_izvoda = request.form.get('racun_izvoda')
            iznos_duguje = float(request.form.get('iznos_duguje', 0))
            broj_stavki = int(request.form.get('broj_stavki', 0))

            # Pronađi ili kreiraj SupplierPayment
            existing_payment = SupplierPayment.query.filter_by(
                statment_nubmer=izvod_broj,
                payment_date=izvod_datum
            ).first()

            if existing_payment:
                payment_id = existing_payment.id
            else:
                # Izračunaj broj grešaka (stavki gde dobavljač nije izabran)
                supplier_ids_form = request.form.getlist('supplier_id[]')
                broj_gresaka = sum(1 for sid in supplier_ids_form if not sid)

                new_payment = SupplierPayment(
                    payment_date=izvod_datum,
                    bank_account=racun_izvoda,
                    statment_nubmer=izvod_broj,
                    total_payment_amount=iznos_duguje,
                    number_of_items=broj_stavki,
                    number_of_errors=broj_gresaka
                )
                db.session.add(new_payment)
                db.session.flush()
                payment_id = new_payment.id

            # Čuvanje dobavljačkih transakcija
            # Izvuci podatke iz forme (skrivena polja)
            supplier_ids = request.form.getlist('supplier_id[]')
            amounts = request.form.getlist('amount[]')
            references = request.form.getlist('reference[]')
            purposes = request.form.getlist('purpose[]')
            payee_names = request.form.getlist('payee_name[]')

            for i in range(len(amounts)):
                # Sačuvaj SVE transakcije, čak i one gde dobavljač nije izabran
                supplier_id_value = supplier_ids[i] if i < len(supplier_ids) and supplier_ids[i] else None

                supplier_tx = SupplierTransaction(
                    supplier_payment_id=payment_id,
                    supplier_id=int(supplier_id_value) if supplier_id_value else None,
                    amount=float(amounts[i]),
                    reference_number=references[i],
                    purpose_of_payment=purposes[i],
                    payee_name=payee_names[i] if i < len(payee_names) else None,
                    payment_error=(supplier_id_value is None)  # Greška ako nije izabran dobavljač
                )
                db.session.add(supplier_tx)

            db.session.commit()
            flash(f'Izvod dobavljača uspešno sačuvan! Ukupno {len(amounts)} transakcija.', 'success')
            return redirect(url_for('supplier_invoices.posting_supplier_payment'))

        except Exception as e:
            db.session.rollback()
            flash(f'Greška prilikom čuvanja: {str(e)}', 'danger')
            return redirect(url_for('supplier_invoices.posting_supplier_payment'))

    # GET zahtev - prikaži formu
    school = School.query.first()
    return render_template('supplier_invoices/posting_supplier_payment.html',
                            title='Učitavanje isplata dobavljačima',
                            legend='Učitavanje isplata dobavljačima',
                            show_preview=False,
                            school=school)


@supplier_invoices.route('/supplier_payments_archive_list', methods=['GET'])
@login_required
def supplier_payments_archive_list():
    """Lista svih bankovnih izvoda sa dobavljačkim isplatama."""
    from onetouch.models import SupplierPayment, SupplierTransaction
    from sqlalchemy import func

    # Učitaj sve SupplierPayment zapise (samostalna tabela, potpuna separacija)
    payments = SupplierPayment.query.order_by(SupplierPayment.payment_date.desc()).all()

    # Agregacija po izvodu
    payment_data = []
    for payment in payments:
        supplier_count = SupplierTransaction.query.filter_by(
            supplier_payment_id=payment.id
        ).count()

        total_amount = db.session.query(
            func.sum(SupplierTransaction.amount)
        ).filter(
            SupplierTransaction.supplier_payment_id == payment.id
        ).scalar() or 0.0

        payment_data.append({
            'payment': payment,
            'supplier_count': supplier_count,
            'total_amount': abs(total_amount)  # Pozitivan iznos za prikaz
        })

    school = School.query.first()

    return render_template('supplier_invoices/supplier_payments_archive_list.html',
                         title='Arhiva isplata dobavljačima',
                         legend='Arhiva isplata dobavljačima',
                         payment_data=payment_data,
                         school=school)


@supplier_invoices.route('/supplier_payment_archive/<int:payment_id>', methods=['GET', 'POST'])
@login_required
def supplier_payment_archive(payment_id):
    """Pregled svih dobavljačkih transakcija sa jednog bankovnog izvoda."""
    from onetouch.models import SupplierPayment, SupplierTransaction

    payment = SupplierPayment.query.get_or_404(payment_id)

    # POST - Čuvanje izmena (AJAX)
    if request.method == 'POST':
        try:
            data = request.get_json()
            changes = data.get('changes', [])

            for change in changes:
                tx_id = change.get('tx_id')
                supplier_id = change.get('supplier_id')
                reference_number = change.get('reference_number')

                if tx_id:
                    tx = SupplierTransaction.query.get(tx_id)
                    if tx and tx.supplier_payment_id == payment_id:
                        # Ažuriraj supplier_id ako je poslat
                        if supplier_id:
                            tx.supplier_id = int(supplier_id)
                            tx.payment_error = False  # Nije više greška

                        # Ažuriraj reference_number ako je poslat
                        if reference_number is not None:
                            tx.reference_number = reference_number

            # Ažuriraj broj grešaka u izvodu
            broj_gresaka = SupplierTransaction.query.filter_by(
                supplier_payment_id=payment_id,
                payment_error=True
            ).count()
            payment.number_of_errors = broj_gresaka

            db.session.commit()
            return jsonify({'success': True, 'message': 'Izmene uspešno sačuvane'})

        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 400

    # GET - Prikaz izvoda
    # Učitaj sve dobavljačke transakcije za ovaj izvod
    transactions = SupplierTransaction.query.filter_by(
        supplier_payment_id=payment_id
    ).all()

    # Učitaj sve dobavljače za dropdown (za buduće editovanje)
    suppliers = Supplier.query.filter_by(archived=False).order_by(Supplier.supplier_name).all()

    school = School.query.first()

    return render_template('supplier_invoices/supplier_payment_archive.html',
                         title=f'Izvod dobavljača #{payment.statment_nubmer}',
                         legend=f'Izvod dobavljača #{payment.statment_nubmer} - {payment.payment_date.strftime("%d.%m.%Y.")}',
                         transactions=transactions,
                         payment=payment,
                         suppliers=suppliers,
                         school=school)

