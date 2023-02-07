from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, SelectField
from wtforms.validators import DataRequired
from onetouch import db
from onetouch.models import Student


class RegisterStudentModalForm(FlaskForm):
    student_name = StringField('Ime', validators=[DataRequired()])
    student_surname = StringField('Prezime', validators=[DataRequired()])
    student_class = SelectField('Razred', choices = [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")])
    student_section = SelectField('Odeljenje', choices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
    submit_register = SubmitField('Registrujte učenika')


class EditStudentModalForm(FlaskForm):
    student_name = StringField('Ime', validators=[DataRequired()])
    student_surname = StringField('Prezime', validators=[DataRequired()])
    student_class = SelectField('Razred', choices = [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")])
    student_section = SelectField('Odeljenje', choices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15])
    submit_edit = SubmitField('Sačuvajte')