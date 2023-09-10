from flask import Blueprint
from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user
from flask_mail import Message, Mail
from onetouch import mail


main = Blueprint('main', __name__)


@main.route("/")
@main.route("/home")
def home():
    if current_user.is_authenticated:
        pass
    else:
        flash('Morate da budete prijavljeni da biste pristupili ovoj stranici.', 'info')
        return redirect(url_for('main.login'))
    return render_template('home.html', title="Početna", legend="Početna")


@main.route("/about")
def about():
    return render_template('about.html', title='O softveru')


@main.route('/send_mail', methods=['POST', 'GET'])
def send_mail():
    sender_email = 'noreply@uplatnice.online'
    recipient_email = 'miiihaaas@gmail.com'
    subject = 'Test slanja mejla klikom na link iz aplikacije'
    body = 'Ovo je poruka koja se salje klikom na link iz aplikacije'
    
    message = Message(subject, sender=sender_email, recipients=[recipient_email])
    message.body = body
    
    try:
        mail.send(message)
        flash('Mejl je poslat', 'success')
        return redirect(url_for('main.home'))
    except Exception as e:
        flash('Greska prilikom slanja mejla: ' + str(e), 'danger')
        return redirect(url_for('main.home'))