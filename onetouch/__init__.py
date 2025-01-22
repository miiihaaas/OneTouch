import os, logging
from logging.handlers import RotatingFileHandler
from flask import Flask, flash, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, current_user
from flask_mail import Mail
from dotenv import load_dotenv
from flask_migrate import Migrate

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
#kod ispod treba da reši problem Internal Server Error - komunikacija sa serverom
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['FLASK_APP'] = 'run.py'


db = SQLAlchemy(app)
# migrate = Migrate(app, db, compare_type=True, render_as_batch=True) #da primeti izmene npr u dužini stringova
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'users.login'
login_manager.login_message = 'Morate biti prijavljeni da biste pristupili ovoj stranici.'
login_manager.login_message_category = 'info'
app.config['JSON_AS_ASCII'] = False #! da ne bude ascii već utf8
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER') # dodati u .env: 'mail.uplatnice.online'
app.config['MAIL_PORT'] = os.getenv('MAIL_PORT') # dodati u .env: 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER') 
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS') 
mail = Mail(app)

@app.context_processor
def check_license_expiry():
    warning_shown = {}
    if current_user.is_authenticated:
        school = current_user.user_school
        if school and school.license_expiry_date:
            days_left = school.days_until_license_expiry()
            if days_left is not None:
                if 2 <= days_left <= 30:
                    flash(f'Upozorenje: Preostalo je još {days_left} dana do isteka licence. Kako bismo osigurali nesmetano korićenje usluga, molimo Vas da nas kontaktirate radi njenog produženja.', 'warning')
                elif days_left == 1:
                    flash(f'Upozorenje: Preostalo je još 1 dan do isteka licence. Kako bismo osigurali nesmetano korićenje usluga, molimo Vas da nas kontaktirate radi njenog produženja.', 'danger')
                elif days_left <= 0:
                    flash(f'Upozorenje: Vreme licence je isteklo. Kako bismo osigurali nesmetano korićenje usluga, molimo Vas da nas kontaktirate radi njenog produženja. Do tad ćete moći samo da koristite funkcionalnosti vezane za preglede.', 'danger')
                warning_shown['shown'] = True
    return warning_shown

# Podešavanje logovanja
log_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
if not os.path.exists(log_folder):
    os.makedirs(log_folder)

log_file = os.path.join(log_folder, 'onetouch.log')
handler = RotatingFileHandler(
    filename=log_file,
    maxBytes=5*1024*1024,  # 5MB po fajlu
    backupCount=10,        # čuva poslednjih 10 fajlova
    encoding='utf-8'
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(threadName)s : %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S'
))

logger = logging.getLogger('onetouch')
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)

logger.info('Aplikacija je pokrenuta')

from onetouch.main.routes import main
from onetouch.schools.routes import schools
from onetouch.students.routes import students
from onetouch.suppliers.routes import suppliers
from onetouch.teachers.routes import teachers
from onetouch.transactions.routes import transactions
from onetouch.overviews.routes import overviews
from onetouch.users.routes import users
from onetouch.errors.routes import errors


app.register_blueprint(main)
app.register_blueprint(schools)
app.register_blueprint(students)
app.register_blueprint(suppliers)
app.register_blueprint(teachers)
app.register_blueprint(transactions)
app.register_blueprint(overviews)
app.register_blueprint(users)
app.register_blueprint(errors)
