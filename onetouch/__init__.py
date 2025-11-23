import os, logging
from logging.handlers import RotatingFileHandler
from flask import Flask, flash, session, request
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, current_user
from flask_mail import Mail
from dotenv import load_dotenv
from flask_migrate import Migrate
# from flask_apscheduler import APScheduler

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
migrate = Migrate(app, db, compare_type=True, render_as_batch=True) #da primeti izmene npr u dužini stringova
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
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME') 
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD') 
app.config['LICENSE_NOTIFICATION_DAYS'] = [int(x) for x in os.getenv('LICENSE_NOTIFICATION_DAYS').split(',')]
app.config['LICENSE_NOTIFICATION_EMAILS'] = os.getenv('LICENSE_NOTIFICATION_EMAILS').split(',')
mail = Mail(app)



logger.info('Aplikacija je pokrenuta')



# def check_license_job():
#     try:
#         with app.app_context():
#             logger.info('Započinjem proveru isteka licence')
#             from onetouch.models import School
#             from onetouch.main.functions import send_license_expiry_notification

#             school = School.query.first()
#             if not school:
#                 logger.warning('Nijedna škola nije pronađena u bazi')
#                 return

#             if not school.license_expiry_date:
#                 logger.warning(f'Škola {school.school_name} nema definisan datum isteka licence')
#                 return

#             days_left = school.days_until_license_expiry()
#             if days_left is None:
#                 logger.error(f'Greška pri računanju preostalog vremena licence za školu {school.school_name}')
#                 return

#             logger.info(f'Škola: {school.school_name}, preostalo dana: {days_left}')
            
#             try:
#                 notification_sent = send_license_expiry_notification(school)
#                 if notification_sent:
#                     logger.info(f'Uspešno poslato obaveštenje za školu {school.school_name}')
#                 else:
#                     logger.info(f'Nije potrebno slati obaveštenje za školu {school.school_name} u ovom trenutku')
#             except Exception as e:
#                 logger.error(f'Greška pri slanju email obaveštenja: {str(e)}')
                
#     except Exception as e:
#         logger.error(f'Neočekivana greška u check_license_job: {str(e)}')


# Inicijalizacija scheduler-a samo u glavnom procesu
scheduler = None
# if (os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug) and not app.config.get('SCHEDULER_STARTED', False):
#     try:
#         scheduler = APScheduler()
#         scheduler.init_app(app)
#         scheduler.start()
#         scheduler.add_job(id='check_license', func=check_license_job, 
#                         trigger='cron', hour=9, minute=0)
#         app.config['SCHEDULER_STARTED'] = True
#         logger.info('Startovan scheduler za proveru isteka licence.')
#     except Exception as e:
#         logger.error(f'Greška pri inicijalizaciji scheduler-a: {str(e)}')


@app.context_processor
def check_license_expiry():
    warning_shown = {}
    school = None
    if current_user.is_authenticated:
        school = current_user.user_school
        if school and school.license_expiry_date:
            days_left = school.days_until_license_expiry()
            if days_left is not None:
                if 2 <= days_left <= 30:
                    flash(f'Upozorenje: Preostalo je još {days_left} dana do isteka licence za korišćenje softvera. Kako bismo osigurali nesmetano korićenje usluga, molimo Vas da nas kontaktirate radi produženja licence.', 'warning')
                elif days_left == 1:
                    flash(f'Upozorenje: Preostalo je još 1 dan do isteka licence za korišćenje softvera. Kako bismo osigurali nesmetano korićenje usluga, molimo Vas da nas kontaktirate radi produženja licence.', 'danger')
                elif days_left <= 0:
                    flash(f'Upozorenje: Licenca za korišćenje softvera je istekla. Kako bismo osigurali nesmetano korićenje usluga, molimo Vas da nas kontaktirate radi produženja licence. Do tada ćete moći da koristite funkcionalnosti vezane za preglede.', 'danger')
                warning_shown['shown'] = True
    return {'warning_shown': warning_shown, 'school': school}


from onetouch.errors.routes import errors
from onetouch.ai_agent.routes import ai_agent
from onetouch.main.routes import main
from onetouch.overviews.routes import overviews
from onetouch.schools.routes import schools
from onetouch.students.routes import students
from onetouch.suppliers.routes import suppliers
from onetouch.supplier_invoices import supplier_invoices
from onetouch.teachers.routes import teachers
from onetouch.transactions.routes import transactions
from onetouch.users.routes import users


app.register_blueprint(errors)
app.register_blueprint(ai_agent)
app.register_blueprint(main)
app.register_blueprint(overviews)
app.register_blueprint(schools)
app.register_blueprint(students)
app.register_blueprint(suppliers)
app.register_blueprint(supplier_invoices, url_prefix='/supplier_invoices')
app.register_blueprint(teachers)
app.register_blueprint(transactions)
app.register_blueprint(users)
