from onetouch.models import Student, ServiceItem, TransactionRecord
from datetime import datetime


def get_filtered_transactions_data(student_id, selected_services=None, min_debt_amount=0):
    """
    Dobavlja i filtrira podatke o transakcijama za učenika.
    
    Args:
        student_id (int): ID učenika
        selected_services (list): Lista ID-eva usluga za filtriranje
        min_debt_amount (float): Minimalni iznos dugovanja
        
    Returns:
        tuple: (services_with_positive_saldo, selected_service_names, student)
            - services_with_positive_saldo: Lista usluga sa pozitivnim saldom
            - selected_service_names: Lista naziva selektovanih usluga
            - student: Objekat učenika
    """
    # Dobavljanje podataka o učeniku
    student = Student.query.get_or_404(student_id)
    
    # Filter za transakcije - osnovna pretraga po učeniku
    query = TransactionRecord.query.filter_by(student_id=student_id)
    
    # Dodatni filter po izabranim uslugama
    selected_service_names = []
    if selected_services and selected_services[0]:  # Provera da nije prazan string u prvom elementu
        service_ids = [int(s) for s in selected_services if s.strip()]
        if service_ids:  # Ako postoje validni ID-evi
            query = query.filter(TransactionRecord.service_item_id.in_(service_ids))
            
            # Prikupljanje naziva izabranih usluga za prikaz
            service_items = ServiceItem.query.filter(ServiceItem.id.in_(service_ids)).all()
            selected_service_names = [f"{item.service_item_service.service_name} - {item.service_item_name}" for item in service_items]
    
    # Izvršavanje upita
    transaction_records = query.all()
    
    # Grupisanje transakcija po uslugama
    services_data = {}
    for record in transaction_records:
        service_id = record.service_item_id
        if service_id not in services_data:
            services_data[service_id] = {
                'service_item': record.transaction_record_service_item,
                'debt_amount': 0,
                'payment_amount': 0,
                'saldo': 0
            }
        
        if record.student_debt_id:
            services_data[service_id]['debt_amount'] += record.student_debt_total
        elif record.student_payment_id:
            services_data[service_id]['payment_amount'] += record.student_debt_total
    
    # Računanje salda za svaku uslugu
    services_with_positive_saldo = []
    for service_id, data in services_data.items():
        data['saldo'] = data['debt_amount'] - data['payment_amount']
        if data['saldo'] > 0:
            services_with_positive_saldo.append({
                'service_id': service_id,
                'service_item': data['service_item'],
                'debt_amount': data['debt_amount'],
                'payment_amount': data['payment_amount'],
                'saldo': data['saldo']
            })
    
    return services_with_positive_saldo, selected_service_names, student


def add_filter_info_to_pdf(pdf, student, min_debt_amount, selected_service_names):
    """
    Dodaje informacije o filtriranju i osnovne podatke o učeniku na PDF.
    
    Args:
        pdf: FPDF objekat
        student: Objekat učenika
        min_debt_amount (float): Minimalni iznos dugovanja
        selected_service_names (list): Lista naziva selektovanih usluga
    """
    # Naslov
    pdf.set_font('DejaVuSansCondensed', 'B', 16)
    pdf.cell(0, 10, f"Lista dugovanja - {student.student_name} {student.student_surname}", new_x="LMARGIN", new_y="NEXT")
    
    # Informacije o učeniku i kriterijumima
    pdf.set_font('DejaVuSansCondensed', '', 12)
    pdf.cell(0, 10, f"Razred/odeljenje: {student.student_class}/{student.student_section}", new_x="LMARGIN", new_y="NEXT")
    
    # Datum generisanja
    current_date = datetime.now().strftime('%d.%m.%Y.')
    pdf.cell(0, 10, f"Datum generisanja: {current_date}", new_x="LMARGIN", new_y="NEXT")
    
    # Kriterijumi filtriranja
    # pdf.cell(0, 10, f"Minimalni iznos dugovanja: {min_debt_amount:.2f}", new_x="LMARGIN", new_y="NEXT")
    
    # Informacija o filtriranim uslugama
    if selected_service_names:
        pdf.cell(0, 10, "Filtrirano po sledećim uslugama:", new_x="LMARGIN", new_y="NEXT")
        for i, service_name in enumerate(selected_service_names):
            pdf.cell(0, 8, f"  {i+1}. {service_name}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 10, "Prikazane sve usluge sa dugovanjima.", new_x="LMARGIN", new_y="NEXT")
        
    pdf.ln(5)