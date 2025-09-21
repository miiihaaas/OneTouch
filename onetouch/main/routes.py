from flask import Blueprint
from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from flask_mail import Message, Mail
from onetouch import mail
from onetouch.main.functions import send_license_expiry_notification
import logging

main = Blueprint('main', __name__)

@main.route("/")
@main.route("/home")
@login_required
def home():
    try:
        route_name = request.endpoint
        return render_template('home.html', title="Početna", legend="Početna", route_name=route_name)
    except Exception as e:
        logging.error(f'Error in home route: {str(e)}')
        flash('Došlo je do greške prilikom učitavanja početne stranice.', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/about")
def about():
    try:
        route_name = request.endpoint
        return render_template('about.html', title='O softveru', route_name=route_name)
    except Exception as e:
        logging.error(f'Error in about route: {str(e)}')
        flash('Došlo je do greške prilikom učitavanja stranice.', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/instructions", methods=['GET'])
@login_required
def instructions():
    try:
        route_name = request.endpoint
        return render_template('instructions.html', title='Upustva', legend='Upustva', route_name=route_name)
    except Exception as e:
        logging.error(f'Error in instructions route: {str(e)}')
        flash('Došlo je do greške prilikom učitavanja upustava.', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/check_licenses")
@login_required
def check_licenses():
    try:
        from onetouch.models import School
        school = School.query.first()  # Pošto imamo samo jednu školu
        if send_license_expiry_notification(school):
            flash('Mejl o isteku licence je uspešno poslat.', 'success')
            print('Mejl o isteku licence je uspešno poslat.')
        else:
            flash('Mejl o isteku licence nije uspešno poslat.', 'danger')
            print('Mejl o isteku licence nije uspešno poslat.')
        return redirect(url_for('main.home'))
    except Exception as e:
        logging.error(f'Error in check_licenses route: {str(e)}')
        flash('Došlo je do greške prilikom provere licence.', 'danger')
        print('Došlo je do greške prilikom provere licence.')
        return redirect(url_for('main.home'))


@main.route("/news", methods=['GET'])
def news():
    try:
        route_name = request.endpoint
        return render_template('news.html', title='Novosti', legend='Novosti', route_name=route_name)
    except Exception as e:
        logging.error(f'Error in news route: {str(e)}')
        flash('Došlo je do greške prilikom učitavanja stranice.', 'danger')
        return render_template('errors/500.html'), 500