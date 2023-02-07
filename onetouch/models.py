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
    services = db.relationship('Service', backref='service_supplier', lazy=True)


class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(255), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('supplier.id'), nullable=False) # ovde treba da bude dropdown menu


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(255), nullable=False)
    student_surname = db.Column(db.String(255), nullable=False)
    student_class = db.Column(db.Integer, nullable=False)
    student_section = db.Column(db.Integer, nullable=False) #todo: naći bolji prevod za odeljenje


class Teacher(db.Model): #! ovo se odnosi na razrednog tj učitelja
    id = db.Column(db.Integer, primary_key=True)
    teacher_name = db.Column(db.String(255), nullable=False)
    teacher_surname = db.Column(db.String(255), nullable=False)
    teacher_class = db.Column(db.Integer, nullable=False)
    teacher_section = db.Column(db.Integer, nullable=False) #todo: naći bolji prevod za odeljenje
    

with app.app_context():
    db.create_all()
    db.session.commit()