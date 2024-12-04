import os, logging
from flask import Flask
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
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER') # https://www.youtube.com/watch?v=IolxqkL7cD8&ab_channel=CoreySchafer   ////// os.environ.get vs os.getenv
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASS') # https://www.youtube.com/watch?v=IolxqkL7cD8&ab_channel=CoreySchafer -- za 2 step verification: https://support.google.com/accounts/answer/185833
mail = Mail(app)


logging.basicConfig(filename='app.log', level=logging.DEBUG, format=f'%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
# logging.basicConfig(level=logging.DEBUG, format=f'%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
logging.debug('App started')
#! podsetnik za hijerarkiju
# logging.debug('This is a debug message')
# logging.info('This is an info message')
# logging.warning('This is a warning message')
# logging.error('This is an error message')
# logging.critical('This is a critical message')

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
