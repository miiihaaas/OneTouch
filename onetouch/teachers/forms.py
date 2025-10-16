from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, SelectField
from wtforms.validators import DataRequired
from onetouch import db
from onetouch.models import Teacher, School

class RegisterTeacherModalForm(FlaskForm):
    teacher_name = StringField('Ime', validators=[DataRequired()])
    teacher_surname = StringField('Prezime', validators=[DataRequired()])
    teacher_class = SelectField('Razred', coerce=int)
    teacher_section = SelectField('Odeljenje', coerce=int)
    submit_register = SubmitField('Registrujte odeljenskog starešinu')
    
    def __init__(self, *args, **kwargs):
        super(RegisterTeacherModalForm, self).__init__(*args, **kwargs)
        school = School.query.first()
        if school:
            # Generisanje choices za razrede
            self.teacher_class.choices = [(i, str(i)) for i in range(school.broj_razreda + 1)]
            # Generisanje choices za odeljenja
            self.teacher_section.choices = [(i, str(i)) for i in range(school.broj_odeljenja + 1)]
        else:
            # Podrazumevane vrednosti ako škola nije pronađena
            self.teacher_class.choices = [(i, str(i)) for i in range(9)]
            self.teacher_section.choices = [(i, str(i)) for i in range(16)]

class EditTeacherModalForm(FlaskForm):
    teacher_name = StringField('Ime', validators=[DataRequired()])
    teacher_surname = StringField('Prezime', validators=[DataRequired()])
    teacher_class = SelectField('Razred', coerce=int)
    teacher_section = SelectField('Odeljenje', coerce=int)
    submit_edit = SubmitField('Sačuvajte')
    
    def __init__(self, *args, **kwargs):
        super(EditTeacherModalForm, self).__init__(*args, **kwargs)
        school = School.query.first()
        if school:
            # Generisanje choices za razrede
            self.teacher_class.choices = [(i, str(i)) for i in range(school.broj_razreda + 1)]
            # Generisanje choices za odeljenja
            self.teacher_section.choices = [(i, str(i)) for i in range(school.broj_odeljenja + 1)]
        else:
            # Podrazumevane vrednosti ako škola nije pronađena
            self.teacher_class.choices = [(i, str(i)) for i in range(9)]
            self.teacher_section.choices = [(i, str(i)) for i in range(16)]