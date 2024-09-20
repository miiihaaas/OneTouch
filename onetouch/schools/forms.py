from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FieldList, FormField
from wtforms.validators import DataRequired
from onetouch.models import School


class BankAccountForm(FlaskForm):
    bank_account_number = StringField('Broj bankovnog računa', validators=[])
    reference_number_spiri = StringField('Poziv na broj', validators=[])


class EditSchoolForm(FlaskForm):
    school_name = StringField('Naziv škole', validators = [DataRequired()])
    school_address = StringField('Adresa', validators = [DataRequired()])
    school_zip_code = StringField('Poštanski broj', validators = [DataRequired()])
    school_city = StringField('Grad', validators = [DataRequired()])
    school_municipality = StringField('Opština', validators = [DataRequired()])
    # school_bank_account = StringField('Broj bankovnog računa', validators = [DataRequired()])
    # school_bank_accounts = FieldList(StringField('Broj bankovnog računa'), min_entries=1)
    school_bank_accounts = FieldList(FormField(BankAccountForm), min_entries=1)

    submit = SubmitField('Sačuvajte', validators = [DataRequired()])