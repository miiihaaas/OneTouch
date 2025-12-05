from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, DateField, SelectField
from wtforms.validators import DataRequired, NumberRange

class InvoiceForm(FlaskForm):
    """Forma za kreiranje i izmenu faktura."""
    invoice_number = StringField('Broj fakture', validators=[DataRequired()])
    invoice_date = DateField('Datum fakture', validators=[DataRequired()])
    traffic_date = DateField('Datum prometa', validators=[DataRequired()])
    supplier_id = SelectField('Dobavljač', coerce=int, validators=[DataRequired()])
    total_amount = FloatField('Ukupan iznos (sa PDV)', validators=[DataRequired(), NumberRange(min=0)])

class DeleteInvoiceForm(FlaskForm):
    pass  # Samo za CSRF zaštitu
