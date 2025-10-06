# ai_agent/tools.py

from onetouch.models import Student, TransactionRecord
from onetouch import db
from onetouch.overviews.functions import get_filtered_transactions_data

# Definicija tools za Claude API
TOOLS = [
    {
        "name": "get_student_balance",
        "description": "Dobavi stanje učenika - zaduženja, uplate i saldo. Koristi kada te pitaju o finansijskom stanju učenika.",
        "input_schema": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "ID učenika"
                }
            },
            "required": ["student_id"]
        }
    },
    {
        "name": "search_students",
        "description": "Pretraži učenike po imenu, prezimenu ili kombinaciji. Koristi kada ne znaš ID učenika ali znaš ime. Vraća listu pronađenih učenika sa njihovim ID-evima.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Ime, prezime ili kombinacija za pretragu (npr. 'Marko', 'Petrović', 'Ana Jovanović')"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_section_overview",
        "description": "Dobavi finansijski pregled celog razreda/odeljenja - ukupno zaduženje, uplate i dugovanja. Koristi kada te pitaju o finansijskom stanju odeljenja ili razreda.",
        "input_schema": {
            "type": "object",
            "properties": {
                "student_class": {
                    "type": "integer",
                    "description": "Broj razreda (0-8)"
                },
                "student_section": {
                    "type": "integer",
                    "description": "Broj odeljenja (0-15). Opciono - ako nije navedeno, prikazuje sve sekcije u razredu."
                }
            },
            "required": ["student_class"]
        }
    }
]


def get_section_overview(student_class: int, student_section: int = None):
    """Dobavi pregled finansijskog stanja odeljenja ili celog razreda"""
    try:
        # Osnovni filter za razred
        query = Student.query.filter(
            Student.student_class == student_class,
            Student.student_class < 9  # Samo aktivni učenici
        )
        
        # Dodatni filter za odeljenje ako je naveden
        if student_section is not None:
            query = query.filter(Student.student_section == student_section)
        
        students = query.all()
        
        if not students:
            return {
                "found": False,
                "message": f"Nije pronađeno nijedno odeljenje za razred {student_class}" + 
                          (f"/{student_section}" if student_section is not None else "")
            }
        
        # Prikupljanje finansijskih podataka za sve učenike
        total_debt = 0
        total_payment = 0
        total_saldo = 0
        students_with_debt = 0
        student_details = []
        
        for student in students:
            # Dobavi sve transakcije za učenika
            transactions = TransactionRecord.query.filter_by(
                student_id=student.id
            ).all()
            
            student_debt = 0
            student_payment = 0
            
            for trans in transactions:
                if trans.student_debt_id:
                    student_debt += trans.student_debt_total or 0
                elif trans.student_payment_id:
                    student_payment += trans.student_debt_total or 0
            
            student_saldo = student_debt - student_payment
            
            total_debt += student_debt
            total_payment += student_payment
            total_saldo += student_saldo
            
            if student_saldo > 0:
                students_with_debt += 1
                student_details.append({
                    "name": f"{student.student_name} {student.student_surname}",
                    "saldo": student_saldo
                })
        
        # Sortiranje učenika sa dugom po visini duga (opadajuće)
        student_details.sort(key=lambda x: x['saldo'], reverse=True)
        
        return {
            "found": True,
            "class": student_class,
            "section": student_section,
            "total_students": len(students),
            "total_debt": total_debt,
            "total_payment": total_payment,
            "total_saldo": total_saldo,
            "students_with_debt": students_with_debt,
            "top_debtors": student_details[:5] if student_details else []  # Top 5 dužnika
        }
        
    except Exception as e:
        return {"error": str(e)}

def search_students(query: str):
    """Pretraži učenike po imenu ili prezimenu"""
    try:
        query_lower = query.lower().strip()
        parts = query_lower.split()

        # Ako korisnik unese jedno ime (npr. "Jovan"), tražimo bilo gde to ime
        if len(parts) == 1:
            students = Student.query.filter(
                db.or_(
                    Student.student_name.ilike(f"%{parts[0]}%"),
                    Student.student_surname.ilike(f"%{parts[0]}%")
                ),
                Student.student_class < 9  # Samo aktivni učenici
            ).all()

        # Ako korisnik unese dva dela (npr. "Jovan Petrović" ili "Petrović Jovan")
        elif len(parts) >= 2:
            first, second = parts[0], parts[1]

            students = Student.query.filter(
                db.and_(
                    Student.student_class < 9,
                    db.or_(
                        db.and_(
                            Student.student_name.ilike(f"%{first}%"),
                            Student.student_surname.ilike(f"%{second}%")
                        ),
                        db.and_(
                            Student.student_name.ilike(f"%{second}%"),
                            Student.student_surname.ilike(f"%{first}%")
                        )
                    )
                )
            ).all()

        else:
            students = []
        
        if not students:
            return {
                "found": False,
                "message": f"Nije pronađen nijedan učenik sa pretragom '{query}'"
            }
        
        return {
            "found": True,
            "count": len(students),
            "students": [
                {
                    "id": student.id,
                    "name": f"{student.student_name} {student.student_surname}",
                    "class": f"{student.student_class}/{student.student_section}"
                }
                for student in students
            ]
        }
    except Exception as e:
        return {"error": str(e)}

def get_student_balance(student_id: int):
    """Tool koji direktno koristi postojeće funkcije"""
    try:
        services, _, student = get_filtered_transactions_data(
            student_id=student_id
        )
        
        return {
            "student": f"{student.student_name} {student.student_surname}",
            "class": f"{student.student_class}/{student.student_section}",
            "services": [
                {
                    "name": s['service_item'].service_item_name,
                    "debt": s['debt_amount'],
                    "payment": s['payment_amount'],
                    "saldo": s['saldo']
                }
                for s in services
            ]
        }
    except Exception as e:
        return {"error": str(e)}

def process_tool_call(tool_name: str, tool_input: dict, user):
    """Poziva odgovarajuću tool funkciju"""
    
    if tool_name == "get_student_balance":
        return get_student_balance(tool_input["student_id"])
    
    if tool_name == "search_students":
        return search_students(tool_input["query"])
    
    if tool_name == "get_section_overview":
        return get_section_overview(tool_input["student_class"], tool_input.get("student_section"))
    
    #! Dodaj druge tools ovde kad ih budeš pravio
    
    return {"error": f"Nepoznat tool: {tool_name}"}