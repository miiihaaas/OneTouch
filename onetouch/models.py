from onetouch import app, db, login_manager
from flask_login import UserMixin
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class User(db.Model, UserMixin): #! ovo je samo administrator škole
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(255), nullable=False)
    user_surname = db.Column(db.String(255), nullable=False)
    user_mail = db.Column(db.String(255), nullable=False)
    user_password = db.Column(db.String(255), nullable=False)


class School(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_name = db.Column(db.String(255), nullable=False)
    school_address = db.Column(db.String(255), nullable=False)
    school_zip_code = db.Column(db.Integer, nullable=False)
    school_city = db.Column(db.String(255), nullable=False)
    school_municipality = db.Column(db.String(255), nullable=False)
    school_bank_account = db.Column(db.String(255), nullable=False)


class Supplier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    supplier_name = db.Column(db.String(255), nullable=False)
    archived = db.Column(db.Boolean, nullable=False, default=False) #! ovo treba da je checkbox, ako je true onda neće se prikazati u listi
    services = db.relationship('Service', backref='service_supplier', lazy=True)
    service_items = db.relationship('ServiceItem', backref='service_item_supplier', lazy=True)


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(255), nullable=False)
    payment_per_unit = db.Column(db.String(255), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False) # ovde treba da bude dropdown menu
    service_items = db.relationship('ServiceItem', backref='service_item_service', lazy=True)
    archived = db.Column(db.Boolean, nullable=False, default=False) #! ovo treba da je checkbox, ako je true onda neće se prikazati u listi


class ServiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_item_name = db.Column(db.String(255), nullable=False)
    service_item_date = db.Column(db.DateTime, nullable=False) #! neka ostane samo datum radi evidencije, ali ćemo dodati atribu arhivirano: true vs false
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=False)
    service_item_class = db.Column(db.Integer, nullable=True) #! ovo treba da je dropdown meni sa cekbox itemima koji kada se čekiraju imaju listu kao input
    price = db.Column(db.Float, nullable=False)
    # discount = db.Column(db.Float, nullable=False)
    installment_number = db.Column(db.Integer)
    installment_1 = db.Column(db.Float, nullable=True)
    installment_2 = db.Column(db.Float, nullable=True)
    installment_3 = db.Column(db.Float, nullable=True)
    installment_4 = db.Column(db.Float, nullable=True)
    installment_5 = db.Column(db.Float, nullable=True)
    installment_6 = db.Column(db.Float, nullable=True)
    installment_7 = db.Column(db.Float, nullable=True)
    installment_8 = db.Column(db.Float, nullable=True)
    installment_9 = db.Column(db.Float, nullable=True)
    installment_10 = db.Column(db.Float, nullable=True)
    installment_11 = db.Column(db.Float, nullable=True)
    installment_12 = db.Column(db.Float, nullable=True)
    archived = db.Column(db.Boolean, nullable=False, default=False) #! ovo treba da je checkbox, ako je true onda neće se prikazati u listi
    student_debts = db.relationship('StudentDebt', backref='student_debt_service_item', lazy=True ) #todo: dodaj u db
    transaction_records = db.relationship('TransactionRecord', backref='transaction_record_service_item', lazy=True)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(255), nullable=False)
    student_surname = db.Column(db.String(255), nullable=False)
    student_class = db.Column(db.Integer, nullable=False)
    student_section = db.Column(db.Integer, nullable=False) 
    # student_debts = db.relationship('StudentDebt', backref='student_debt_student', lazy=True) #todo: dodaj u db
    transaction_records = db.relationship('TransactionRecord', backref='transaction_record_student', lazy=True) #todo: dodaj u db


class Teacher(db.Model): #! ovo se odnosi na razrednog tj učitelja
    id = db.Column(db.Integer, primary_key=True)
    teacher_name = db.Column(db.String(255), nullable=False)
    teacher_surname = db.Column(db.String(255), nullable=False)
    teacher_class = db.Column(db.Integer, nullable=False)
    teacher_section = db.Column(db.Integer, nullable=False) 


class StudentDebt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_debt_date = db.Column(db.DateTime, nullable=False)
    service_item_id = db.Column(db.Integer, db.ForeignKey('service_item.id'), nullable=False)
    debt_class = db.Column(db.Integer, nullable=False)
    debt_section = db.Column(db.Integer, nullable=False)
    installment_number = db.Column(db.Integer)
    purpose_of_payment = db.Column(db.String(255), nullable=True)
    transaction_records = db.relationship('TransactionRecord', backref='transaction_record_student_debt', lazy=True)


class StudentPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_date = db.Column(db.DateTime, nullable=False) #! izvlači iz XML fajla (<DatumIzvoda>20.05.2021</DatumIzvoda>)
    statment_nubmer = db.Column(db.Integer, nullable=False) #! izvlači iz XML fajla (<BrojIzvoda>108</BrojIzvoda>)
    total_payment_amount = db.Column(db.Float, nullable=False) #! izvlači iz XML fajla (<IznosPotrazuje>40824,00</IznosPotrazuje>)
    number_of_items = db.Column(db.Integer, nullable=False) #! izvlači iz XML fajla (for loop bi trebalo da uradi routes.py)
    transaction_records = db.relationship('TransactionRecord', backref='transaction_record_student_payment', lazy=True)


class TransactionRecord(db.Model): #! ovde će da idu zapisi zaduženja i uplata po detetu 
    id = db.Column(db.Integer, primary_key=True)
    student_debt_id = db.Column(db.Integer, db.ForeignKey('student_debt.id'), nullable=False)
    student_payment_id = db.Column(db.Integer, db.ForeignKey('student_payment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    service_item_id = db.Column(db.Integer, db.ForeignKey('service_item.id'), nullable=False)
    student_debt_installment_number = db.Column(db.Integer, nullable=True)
    student_debt_amount = db.Column(db.Integer) #! ovde treba da bude vrednost ako je na komaad od 0 - 31 tj 0 ili 1 ako nije na komad
    studetn_debt_installment_value = db.Column(db.Float)
    student_debt_discount = db.Column(db.Float)
    student_debt_total = db.Column(db.Float) #! ovde će da bude proračun za zaduženje i podatak iz XML fala ako je upitanju uplatnica za razduženje
    payer = db.Column(db.String(255), nullable=True)
    reference_number = db.Column(db.String(100), nullable=True)

with app.app_context():
    db.create_all()
    db.session.commit()