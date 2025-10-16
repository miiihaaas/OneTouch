from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, SelectField
from wtforms.validators import DataRequired, Optional
from onetouch import db
from onetouch.models import Student, School


class RegisterStudentModalForm(FlaskForm):
    student_name = StringField('Ime', validators=[DataRequired()])
    student_surname = StringField('Prezime', validators=[DataRequired()])
    student_class = SelectField('Razred', coerce=str)
    student_section = SelectField('Odeljenje', coerce=int)
    parent_email = StringField('e-mail roditelja', validators={Optional()})
    send_mail = BooleanField('Slanje uplatnice roditelju na mejl', validators={Optional()})
    print_payment = BooleanField('Štampa uplatnice', validators={Optional()})
    submit_register = SubmitField('Registrujte učenika')
    
    def __init__(self, *args, **kwargs):
        super(RegisterStudentModalForm, self).__init__(*args, **kwargs)
        school = School.query.first()
        if school:
            # Generisanje choices za razrede
            self.student_class.choices = [("0", "Predškolsko")] + [(str(i), str(i)) for i in range(1, school.broj_razreda + 1)]
            # Generisanje choices za odeljenja
            self.student_section.choices = [(i, str(i)) for i in range(school.broj_odeljenja + 1)]
        else:
            # Podrazumevane vrednosti ako škola nije pronađena
            self.student_class.choices = [("0", "Predškolsko"), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")]
            self.student_section.choices = [(i, str(i)) for i in range(16)]


class EditStudentModalForm(FlaskForm):
    student_name = StringField('Ime', validators=[DataRequired()])
    student_surname = StringField('Prezime', validators=[DataRequired()])
    student_class = SelectField('Razred', coerce=str)
    student_section = SelectField('Odeljenje', coerce=int)
    parent_email = StringField('e-mail roditelja', validators={Optional()})
    send_mail = BooleanField('Slanje uplatnice roditelju na mejl', validators={Optional()})
    print_payment = BooleanField('Štampa uplatnice', validators={Optional()})
    submit_edit = SubmitField('Sačuvajte')
    
    def __init__(self, *args, **kwargs):
        super(EditStudentModalForm, self).__init__(*args, **kwargs)
        school = School.query.first()
        if school:
            # Generisanje choices za razrede
            self.student_class.choices = [("0", "Predškolsko")] + [(str(i), str(i)) for i in range(1, school.broj_razreda + 1)]
            # Generisanje choices za odeljenja
            self.student_section.choices = [(i, str(i)) for i in range(school.broj_odeljenja + 1)]
        else:
            # Podrazumevane vrednosti ako škola nije pronađena
            self.student_class.choices = [("0", "Predškolsko"), ("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("7", "7"), ("8", "8")]
            self.student_section.choices = [(i, str(i)) for i in range(16)]