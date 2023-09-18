from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, SelectField, DecimalField, DateField
from wtforms.validators import DataRequired, Optional, ValidationError
from onetouch import db
from onetouch.models import Supplier


class RegisterSupplierModalForm(FlaskForm):
    supplier_name = StringField('Naziv dobavljača', validators=[DataRequired()])
    submit_register = SubmitField('Registrujte dobavljača')


class EditSupplierModalForm(FlaskForm):
    supplier_name = StringField('Naziv dobavljača', validators=[DataRequired()])
    archived = BooleanField('Dobavljač arhiviran')
    submit_edit = SubmitField('Sačuvajte')


class RegisterServiceModalForm(FlaskForm):
    service_name = StringField('Naziv usluge', validators=[DataRequired()])
    supplier_id = SelectField('Naziv dobavljača', choices=[], coerce=int) #! nastavi kod za choices...
    payment_per_unit = SelectField('Tip plaćanja', choices=[('kom', 'Plaćanje po jedinici'), ('mes', 'Mesečno plaćanje'), ('god', 'Plaćanje po obračunskom periodu')])
    submit_register = SubmitField('Registrujte uslugu')
    
    def reset(self):
        self.__init__()


class EditServiceModalForm(FlaskForm):
    service_name = StringField('Naziv usluge', validators=[DataRequired()])
    supplier_id = SelectField('Naziv dobavljača', choices=[], coerce=int) #! nastavi kod za choices...
    payment_per_unit = SelectField('Tip plaćanja', choices=[('kom', 'Plaćanje po jedinici'), ('mes', 'Mesečno plaćanje'), ('god', 'Plaćanje po obračunskom periodu')])
    archived = BooleanField('Usluga arhivirana')
    submit_edit = SubmitField('Sačuvajte')
    
    def reset(self):
        self.__init__()


class RegisterServiceProfileModalForm(FlaskForm):
    service_item_name = StringField('Detalji usluge', validators=[DataRequired()])
    service_item_date = DateField('Datum: ', format='%Y-%m-%d', validators=[Optional()])
    supplier_id = SelectField('Dobavljač', choices=[])
    service_id = SelectField('Tip usluge', choices=[])
    service_item_class = StringField('Razred') #! morada bude strin koji će da čuva listu odabranih razleda
    price = DecimalField('Cena', validators=[DataRequired()])
    installment_number = SelectField('Broj rata', choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    installment_1 = DecimalField('Rata 1', validators=[Optional()])
    installment_2 = DecimalField('Rata 2', validators=[Optional()])
    installment_3 = DecimalField('Rata 3', validators=[Optional()])
    installment_4 = DecimalField('Rata 4', validators=[Optional()])
    installment_5 = DecimalField('Rata 5', validators=[Optional()])
    installment_6 = DecimalField('Rata 6', validators=[Optional()])
    installment_7 = DecimalField('Rata 7', validators=[Optional()])
    installment_8 = DecimalField('Rata 8', validators=[Optional()])
    installment_9 = DecimalField('Rata 9', validators=[Optional()])
    installment_10 = DecimalField('Rata 10', validators=[Optional()])
    installment_11 = DecimalField('Rata 11', validators=[Optional()])
    installment_12 = DecimalField('Rata 12', validators=[Optional()])
    # archived = BooleanField('Usluga arhivirana')
    submit_register = SubmitField('Kreirajte uslugu')


class EditServiceProfileModalForm(FlaskForm):
    service_item_name = StringField('Detalji usluge', validators=[DataRequired()])
    service_item_date = DateField('Datum: ', format='%Y-%m-%d', validators=[Optional()])
    supplier_id = SelectField('Dobavljač', choices=[])
    service_id = SelectField('Tip usluge', choices=[])
    service_item_class = StringField('Razred')
    price = DecimalField('Cena', validators=[DataRequired()])
    installment_number = SelectField('Broj rata', choices=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])
    installment_1 = DecimalField('Rata 1', validators=[Optional()])
    installment_2 = DecimalField('Rata 2', validators=[Optional()])
    installment_3 = DecimalField('Rata 3', validators=[Optional()])
    installment_4 = DecimalField('Rata 4', validators=[Optional()])
    installment_5 = DecimalField('Rata 5', validators=[Optional()])
    installment_6 = DecimalField('Rata 6', validators=[Optional()])
    installment_7 = DecimalField('Rata 7', validators=[Optional()])
    installment_8 = DecimalField('Rata 8', validators=[Optional()])
    installment_9 = DecimalField('Rata 9', validators=[Optional()])
    installment_10 = DecimalField('Rata 10', validators=[Optional()])
    installment_11 = DecimalField('Rata 11', validators=[Optional()])
    installment_12 = DecimalField('Rata 12', validators=[Optional()])
    archived = BooleanField('Usluga arhivirana')
    submit_edit = SubmitField('Sačuvajte')