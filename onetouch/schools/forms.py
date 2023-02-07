from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField
from wtforms.validators import DataRequired
from onetouch.models import School


class EditSchoolForm(FlaskForm):
    school_name = StringField('Naziv škole')
    school_address = StringField('Adresa')
    school_zip_code = StringField('Poštanski broj')
    school_city = StringField('Grad')
    school_municipality = StringField('Opština')
    school_bank_account = StringField('Broj bankovnog računa')
    submit = SubmitField('Sačuvajte')