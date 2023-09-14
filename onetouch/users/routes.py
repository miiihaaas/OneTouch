import os
from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt, mail, app
from onetouch.users.forms import LoginForm, RequestResetForm, ResetPasswordForm
from onetouch.models import User, School
from flask_login import login_user, login_required, logout_user, current_user
from flask_mail import Message
# from wtforms.validators import ValidationError


users = Blueprint('users', __name__)


@users.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(user_mail=form.email.data).first()
        if user and bcrypt.check_password_hash(user.user_password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            print(user.user_name)
            flash(f'Dobro došli, {user.user_name}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('main.home'))
        else:
            flash('Neispravni podaci za prijavu.', 'danger')
    return render_template('login.html', title='Login', form=form)


@users.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main.home'))


def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Zahtev za resetovanje lozinke', sender='noreply@uplatnice.online', recipients=[user.user_mail])
    msg.body = f'''Da biste resetovali lozinku, kliknite na sledeći link:
{url_for('users.reset_token', token=token, _external=True)}

Ako Vi niste napavili ovaj zahtev, molim Vas ignorišite ovaj mejl i neće biti napravljene nikakve izmene na Vašem nalogu.
    '''
    mail.send(msg)


@users.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
        if current_user.is_authenticated:
            return redirect(url_for('main.home'))
        form = RequestResetForm()
        if form.validate_on_submit():
            user  = User.query.filter_by(user_mail=form.email.data).first()
            send_reset_email(user)
            flash('Mejl je poslat na Vašu adresu sa instrukcijama za resetovanje lozinke. ', 'info')
            return redirect(url_for('users.login'))
        return render_template('reset_request.html', title='Resetovanje lozinke', form=form, legend='Resetovanje lozinke')


@users.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
        if current_user.is_authenticated:
            return redirect(url_for('main.home'))
        user = User.verify_reset_token(token)
        if user is None:
            flash('Ovo je nevažeći ili istekli token.', 'warning')
            return redirect(url_for('users.reset_request'))
        form = ResetPasswordForm()
        if form.validate_on_submit():
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            user.user_password = hashed_password
            db.session.commit()
            flash(f'Vaša lozinka je ažurirana!', 'success')
            return redirect(url_for('users.login'))

        return render_template('reset_token.html', title='Resetovanje lozinke', form=form)