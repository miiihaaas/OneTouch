from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField
from wtforms.validators import DataRequired
from onetouch.models import School


class EditSchoolForm(FlaskForm):
    school_name = StringField('Naziv škole', validators = [DataRequired()])
    school_address = StringField('Adresa', validators = [DataRequired()])
    school_zip_code = StringField('Poštanski broj', validators = [DataRequired()])
    school_city = StringField('Grad', validators = [DataRequired()])
    school_municipality = StringField('Opština', validators = [DataRequired()])
    school_bank_account = StringField('Broj bankovnog računa', validators = [DataRequired()])
    submit = SubmitField('Sačuvajte', validators = [DataRequired()])