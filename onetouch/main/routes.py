from flask import Blueprint
from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_mail import Message, Mail
from onetouch import mail


main = Blueprint('main', __name__)


@main.route("/")
@main.route("/home")
def home():
    route_name = request.endpoint
    if current_user.is_authenticated:
        pass
    else:
        flash('Morate biti prijavljeni da biste pristupili ovoj stranici.', 'info')
        return redirect(url_for('users.login'))
    return render_template('home.html', title="Početna", legend="Početna", route_name=route_name)


@main.route("/about")
def about():
    route_name = request.endpoint
    return render_template('about.html', title='O softveru', route_name=route_name)


@main.route("/instructions", methods=['GET'])
def instructions():
    route_name = request.endpoint
    return render_template('instructions.html', title='Upustva', route_name=route_name)
