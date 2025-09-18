import os, logging
from flask import Blueprint
from flask import  render_template, url_for, flash, redirect, request, abort
from onetouch import db, bcrypt, mail, app
from onetouch.users.forms import LoginForm, RequestResetForm, ResetPasswordForm
from onetouch.models import User, School
from flask_login import login_user, login_required, logout_user, current_user
from flask_mail import Message
from sqlalchemy.exc import SQLAlchemyError

users = Blueprint('users', __name__)

@users.route("/login", methods=['GET', 'POST'])
def login():
    try:
        route_name = request.endpoint
        if current_user.is_authenticated:
            return redirect(url_for('main.home'))
        
        form = LoginForm()
        if form.validate_on_submit():
            try:
                user = User.query.filter_by(user_mail=form.email.data).first()
                
                if user and bcrypt.check_password_hash(user.user_password, form.password.data):
                    try:
                        login_user(user, remember=form.remember.data)
                        next_page = request.args.get('next')
                        logging.info(f'Uspešna prijava korisnika: {user.user_name}')
                        flash(f'Dobro došli, {user.user_name}!', 'success')
                        return redirect(next_page) if next_page else redirect(url_for('main.home'))
                    except Exception as e:
                        logging.error(f'Greška prilikom prijave korisnika: {str(e)}')
                        flash('Došlo je do greške prilikom prijave. Pokušajte ponovo.', 'danger')
                else:
                    logging.warning(f'Neuspešan pokušaj prijave za email: {form.email.data}')
                    flash('Neispravni podaci za prijavu.', 'danger')
                    
            except SQLAlchemyError as e:
                logging.error(f'Greška pri pristupu bazi podataka: {str(e)}')
                flash('Trenutno nije moguće pristupiti sistemu. Pokušajte kasnije.', 'danger')
                
        return render_template('login.html', title='Login', form=form, route_name=route_name)
        
    except Exception as e:
        logging.error(f'Neočekivana greška u login ruti: {str(e)}')
        flash('Došlo je do greške. Pokušajte ponovo.', 'danger')
        return redirect(url_for('main.home'))

@users.route("/logout")
@login_required
def logout():
    try:
        current_username = current_user.user_name
        logout_user()
        logging.info(f'Korisnik {current_username} se uspešno odjavio')
        flash('Uspešno ste se odjavili.', 'success')
        return redirect(url_for('main.home'))
    except Exception as e:
        logging.error(f'Greška prilikom odjavljivanja: {str(e)}')
        flash('Došlo je do greške prilikom odjavljivanja.', 'danger')
        return redirect(url_for('main.home'))

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Zahtev za resetovanje lozinke',
                    sender='noreply@uplatnice.online',
                    recipients=[user.user_mail])
    reset_url = url_for('users.reset_token', token=token, _external=True)
    msg.body = f'''Da biste resetovali lozinku, kliknite na sledeći link:
{reset_url}

Ako Vi niste napavili ovaj zahtev, molim Vas ignorišite ovaj mejl i neće biti napravljene nikakve izmene na Vašem nalogu.
'''
    msg.html = f'''
    <p>Da biste resetovali lozinku, kliknite na sledeći link:</p>
    <p><a href="{reset_url}">Resetuj lozinku</a></p>
    <p>Ako Vi niste napavili ovaj zahtev, molim Vas ignorišite ovaj mejl i neće biti napravljene nikakve izmene na Vašem nalogu.</p>
    '''
    try:
        mail.send(msg)
    except Exception as e:
        logging.error(f'Greška pri slanju mejla: {str(e)}')
        raise

@users.route("/create_password", methods=['GET', 'POST'])
@users.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    try:
        route_name = request.endpoint
        is_create = 'create' in request.path

        if current_user.is_authenticated:
            return redirect(url_for('main.home'))
            
        form = RequestResetForm()
        if form.validate_on_submit():
            try:
                user = User.query.filter_by(user_mail=form.email.data).first()
                if user:
                    try:
                        send_reset_email(user)
                        action_type = "kreiranje" if is_create else "resetovanje"
                        logging.info(f'Zahtev za {action_type} lozinke poslat za korisnika: {user.user_mail}')
                        flash(f'Mejl je poslat na Vašu adresu sa instrukcijama za {action_type} lozinke.', 'info')
                        return redirect(url_for('users.login'))
                    except Exception as e:
                        logging.error(f'Greška pri slanju mejla za {"kreiranje" if is_create else "resetovanje"} lozinke: {str(e)}')
                        flash('Došlo je do greške pri slanju mejla. Pokušajte ponovo kasnije.', 'danger')
                else:
                    logging.warning(f'Pokušaj {"kreiranja" if is_create else "resetovanja"} lozinke za nepostojeći email: {form.email.data}')
                    flash('Ne postoji nalog sa ovom email adresom.', 'warning')
                    
            except SQLAlchemyError as e:
                logging.error(f'Greška pri pristupu bazi podataka: {str(e)}')
                flash('Trenutno nije moguće pristupiti sistemu. Pokušajte kasnije.', 'danger')
        
        title = 'Kreiranje lozinke' if is_create else 'Resetovanje lozinke'
        return render_template('reset_request.html', 
                                title=title, 
                                form=form, 
                                legend='', 
                                route_name=route_name, 
                                is_create=is_create)
        
    except Exception as e:
        action_type = "kreiranje" if is_create else "resetovanje"
        logging.error(f'Neočekivana greška u {action_type} lozinke: {str(e)}')
        flash('Došlo je do greške. Pokušajte ponovo.', 'danger')
        return redirect(url_for('main.home'))

@users.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    try:
        route_name = request.endpoint
        if current_user.is_authenticated:
            return redirect(url_for('main.home'))

        try:
            user = User.verify_reset_token(token)
            if user is None:
                logging.warning(f'Pokušaj resetovanja lozinke sa nevažećim tokenom: {token}')
                flash('Ovo je nevažeći ili istekli token.', 'warning')
                return redirect(url_for('users.reset_request'))

            form = ResetPasswordForm()
            if form.validate_on_submit():
                try:
                    hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
                    user.user_password = hashed_password
                    db.session.commit()
                    logging.info(f'Uspešno resetovana lozinka za korisnika: {user.user_mail}')
                    flash('Vaša lozinka je uspešno ažurirana!', 'success')
                    return redirect(url_for('users.login'))
                except bcrypt.BcryptError as e:
                    db.session.rollback()
                    logging.error(f'Greška pri heširanju lozinke: {str(e)}')
                    flash('Došlo je do greške pri promeni lozinke. Pokušajte ponovo.', 'danger')
                except SQLAlchemyError as e:
                    db.session.rollback()
                    logging.error(f'Greška pri čuvanju nove lozinke u bazi: {str(e)}')
                    flash('Došlo je do greške pri čuvanju nove lozinke. Pokušajte ponovo.', 'danger')

            return render_template('reset_token.html', title='Resetovanje lozinke', form=form, legend='Resetovanje lozinke', route_name=route_name)

        except Exception as e:
            logging.error(f'Greška pri verifikaciji tokena: {str(e)}')
            flash('Došlo je do greške pri verifikaciji tokena. Pokušajte ponovo.', 'danger')
            return redirect(url_for('users.reset_request'))

    except Exception as e:
        logging.error(f'Neočekivana greška u reset_token ruti: {str(e)}')
        flash('Došlo je do greške. Pokušajte ponovo.', 'danger')
        return redirect(url_for('main.home'))