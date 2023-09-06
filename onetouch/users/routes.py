import os
from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt, mail, app
from onetouch.users.forms import LoginForm
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
    return render_template('login.html', title='Login', form=form)


@users.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main.home'))