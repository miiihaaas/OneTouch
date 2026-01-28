from flask import Blueprint
from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user, login_required
from flask_mail import Message, Mail
from onetouch import mail, celery
from onetouch.main.functions import send_license_expiry_notification
from onetouch.users.routes import send_reset_email
import logging
from onetouch.models import User, School, SMTPErrorLog, TransactionRecord
from onetouch import db
from sqlalchemy import func
from datetime import datetime, timedelta

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


@main.route("/users", methods=['GET', 'POST'])
@login_required
def users():
    try:
        route_name = request.endpoint
        from flask_wtf.csrf import generate_csrf
        users = User.query.filter(User.id > 1).all()
        return render_template('users.html', 
                                title='Korisnici',
                                legend='Korisnici',
                                route_name=route_name,
                                csrf_token=generate_csrf,
                                users=users)
    except Exception as e:
        logging.error(f'Error in users route: {str(e)}')
        flash(f'Došlo je do greške prilikom učitavanja stranice. {str(e)}', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/school_license", methods=['GET', 'POST'])
@login_required
def school_license():
    try:
        school = School.query.first()
        route_name = request.endpoint
        if request.method == 'POST':
            # Ažuriranje osnovnih informacija o školi
            school.school_name = request.form.get('school_name', school.school_name)
            school.school_address = request.form.get('school_address', school.school_address)
            school.school_zip_code = request.form.get('school_zip_code', school.school_zip_code)
            school.school_city = request.form.get('school_city', school.school_city)
            school.school_municipality = request.form.get('school_municipality', school.school_municipality)
            school.broj_razreda = request.form.get('broj_razreda', school.broj_razreda)
            school.broj_odeljenja = request.form.get('broj_odeljenja', school.broj_odeljenja)
            school.has_preschool = 'has_preschool' in request.form
            school.supplier_billing_options = 'supplier_billing_options' in request.form
            school.sending_email = 'sending_email' in request.form

            # Ažuriranje finansijskih informacija
            if request.form.get('class_plus_one'):
                from datetime import datetime
                school.class_plus_one = datetime.strptime(request.form['class_plus_one'], '%Y-%m-%d').date()
            
            if request.form.get('license_expiry_date'):
                from datetime import datetime
                school.license_expiry_date = datetime.strptime(request.form['license_expiry_date'], '%Y-%m-%d').date()
            
            db.session.commit()
            flash('Podaci o školi su uspešno ažurirani.', 'success')
            return redirect(url_for('main.school_license'))
        else:
            from flask_wtf.csrf import generate_csrf
            return render_template('school_licence.html', 
                                    title='Škola',
                                    legend='Podaci o školi',
                                    route_name=route_name,
                                    csrf_token=generate_csrf,
                                    school=school)
    except Exception as e:
        logging.error(f'Error in school_license route: {str(e)}')
        flash(f'Došlo je do greške prilikom učitavanja stranice. {str(e)}', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/edit_user/<int:user_id>", methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    try:
        route_name = request.endpoint
        user = User.query.get_or_404(user_id)
        if request.method == 'POST':
            user.user_name = request.form['user_name'].title()
            user.user_surname = request.form['user_surname'].title()
            user.user_mail = request.form['user_mail']
            db.session.commit()
            flash('Korisnik je uspešno izmenjen.', 'success')
            return redirect(url_for('main.users'))
        return render_template('edit_user.html', title='Izmena korisnika', legend='Izmena korisnika', route_name=route_name, user=user)
    except Exception as e:
        logging.error(f'Error in edit_user route: {str(e)}')
        flash('Došlo je do greške prilikom učitavanja stranice.', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/register_user", methods=['GET', 'POST'])
@login_required
def register_user():
    try:
        route_name = request.endpoint
        if request.method == 'POST':
            from werkzeug.security import generate_password_hash
            # Postaviti privremenu lozinku koja će biti promenjena
            temporary_password = "test"  # Možete generisati slučajnu lozinku ako želite
            hashed_password = generate_password_hash(temporary_password)
            
            user = User(
                user_name=request.form['user_name'].title(),
                user_surname=request.form['user_surname'].title(),
                user_mail=request.form['user_mail'],
                user_role='user',
                user_password=hashed_password,
                school_id=1 #uvek je 1 jer je samo jedna škola
            )
            db.session.add(user)
            db.session.commit()
            flash('Korisnik je uspešno registrovan.', 'success')
            return redirect(url_for('main.users'))
        return render_template('register_user.html', title='Registracija korisnika', legend='Registracija korisnika', route_name=route_name)
    except Exception as e:
        logging.error(f'Error in register_user route: {str(e)}')
        flash('Došlo je do greške prilikom učitavanja stranice.', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/delete_user/<int:user_id>", methods=['POST'])
@login_required
def delete_user(user_id):
    try:
        if request.method == 'POST':
            from werkzeug.security import check_password_hash
            user = User.query.get_or_404(user_id)
            if check_password_hash(user.user_password, request.form['input_password']):
                db.session.delete(user)
                db.session.commit()
                flash('Korisnik je uspešno obrisan.', 'success')
                return redirect(url_for('main.users'))
            else:
                flash('Pogrešna lozinka.', 'danger')
                return redirect(url_for('main.users'))
    except Exception as e:
        logging.error(f'Error in delete_user route: {str(e)}')
        flash('Došlo je do greške prilikom brisanja korisnika.', 'danger')
        return render_template('errors/500.html'), 500


@main.route("/send_create_password_mail/<int:user_id>", methods=['POST'])
@login_required
def send_create_password_mail(user_id):
    try:
        if request.method == 'POST':
            user = User.query.get_or_404(user_id)
            send_reset_email(user)
            flash('Mejl za kreiranje lozinke je uspešno poslat.', 'success')
            return redirect(url_for('main.users'))
    except Exception as e:
        logging.error(f'Error in send_create_password_mail route: {str(e)}')
        flash('Došlo je do greške prilikom slanja mejla za kreiranje lozinke.', 'danger')
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


@main.route("/api/users_list", methods=['GET'])
@login_required
def users_list():
    try:
        from flask import jsonify
        # DataTables parametri za server-side procesiranje
        draw = request.args.get('draw', 1, type=int)
        start = request.args.get('start', 0, type=int)
        length = request.args.get('length', 10, type=int)
        search_value = request.args.get('search[value]', '')
        
        # Osnovna query
        query = User.query
        
        # Pretraga
        if search_value:
            search_value = f'%{search_value}%'
            query = query.filter((User.user_name.like(search_value)) |
                               (User.user_surname.like(search_value)) |
                               (User.user_mail.like(search_value)))
        
        # Ukupan broj zapisa pre filtriranja
        total_records = User.query.count()
        # Ukupan broj zapisa posle filtriranja
        total_filtered_records = query.count()
        
        # Sortiranje
        order_column_idx = request.args.get('order[0][column]', 2, type=int)
        order_direction = request.args.get('order[0][dir]', 'asc')
        
        columns = ['id', 'user_name', 'user_surname', 'user_mail', 'user_role']
        
        if order_column_idx < len(columns):
            order_column = columns[order_column_idx]
            if order_direction == 'asc':
                query = query.order_by(getattr(User, order_column).asc())
            else:
                query = query.order_by(getattr(User, order_column).desc())
        
        # Paginacija
        users = query.offset(start).limit(length).all()
        
        # Formiranje odgovora
        data = []
        for user in users:
            data.append({
                'id': user.id,
                'user_name': user.user_name,
                'user_surname': user.user_surname,
                'user_mail': user.user_mail,
                'user_role': user.user_role
            })
        
        return jsonify({
            'draw': draw,
            'recordsTotal': total_records,
            'recordsFiltered': total_filtered_records,
            'data': data
        })
        
    except Exception as e:
        logging.error(f'Error in users_list route: {str(e)}')
        return jsonify({
            'error': str(e),
            'draw': 1,
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'data': []
        }), 500


@main.route('/email_monitoring')
@login_required
def email_monitoring():
    """
    Dashboard za monitoring email slanja i grešaka.
    """
    try:
        from flask_wtf.csrf import generate_csrf
        route_name = request.endpoint

        # Statistika grešaka po tipu
        error_stats = (db.session.query(
            SMTPErrorLog.error_type,
            func.count(SMTPErrorLog.id).label('count')
        )
        .filter(SMTPErrorLog.resolved == False)
        .group_by(SMTPErrorLog.error_type)
        .all())

        # Poslednje greške (50)
        recent_errors = (SMTPErrorLog.query
                         .order_by(SMTPErrorLog.timestamp.desc())
                         .limit(50)
                         .all())

        # Greške u poslednjih 24h
        yesterday = datetime.utcnow() - timedelta(hours=24)
        errors_24h = SMTPErrorLog.query.filter(
            SMTPErrorLog.timestamp >= yesterday
        ).count()

        # Uspešno poslati mejlovi u poslednjih 24h
        # Pretpostavljamo da su mejlovi poslati u poslednjih 24h oni sa debt_sent=True
        sent_24h = TransactionRecord.query.filter(
            TransactionRecord.debt_sent == True
        ).count()

        # Celery queue status (ako je Redis dostupan)
        try:
            inspect = celery.control.inspect()

            active_tasks = inspect.active()
            scheduled_tasks = inspect.scheduled()

            # Broj aktivnih task-ova
            active_count = sum(len(tasks) for tasks in (active_tasks or {}).values())
            scheduled_count = sum(len(tasks) for tasks in (scheduled_tasks or {}).values())

            queue_status = {
                'active': active_count,
                'scheduled': scheduled_count,
                'workers': len(active_tasks or {})
            }
        except Exception as e:
            logging.error(f'Error fetching Celery status: {str(e)}')
            queue_status = None

        return render_template(
            'email_monitoring.html',
            title='Email Monitoring',
            legend='Email Monitoring Dashboard',
            route_name=route_name,
            csrf_token=generate_csrf(),
            error_stats=error_stats,
            recent_errors=recent_errors,
            errors_24h=errors_24h,
            sent_24h=sent_24h,
            queue_status=queue_status
        )
    except Exception as e:
        logging.error(f'Error in email_monitoring route: {str(e)}')
        flash('Došlo je do greške prilikom učitavanja email monitoring dashboarda.', 'danger')
        return render_template('errors/500.html'), 500


@main.route('/resolve_smtp_error/<int:error_id>', methods=['POST'])
@login_required
def resolve_smtp_error(error_id):
    """Označi SMTP grešku kao rešenu."""
    try:
        error = SMTPErrorLog.query.get_or_404(error_id)
        error.resolved = True
        db.session.commit()
        flash('Greška označena kao rešena.', 'success')
        return redirect(url_for('main.email_monitoring'))
    except Exception as e:
        logging.error(f'Error in resolve_smtp_error route: {str(e)}')
        flash('Došlo je do greške prilikom rešavanja greške.', 'danger')
        return redirect(url_for('main.email_monitoring'))


@main.route('/retry_failed_email/<int:record_id>', methods=['POST'])
@login_required
def retry_failed_email(record_id):
    """Ručno retry-uj neuspeo mejl."""
    try:
        record = TransactionRecord.query.get_or_404(record_id)

        # Reset debt_sent flag
        record.debt_sent = False
        db.session.commit()

        # Re-queue email task
        from onetouch.tasks.email_tasks import send_email_task
        from onetouch.transactions.functions import project_folder
        import os

        user_folder = os.path.join(project_folder, 'static', 'payment_slips', f'user_{current_user.id}')
        file_name = f'uplatnica_{record.id}.pdf'

        # Dobij database URI za ovu školu
        database_uri = os.getenv('SQLALCHEMY_DATABASE_URI')

        send_email_task.delay(record.id, user_folder, file_name, database_uri)

        flash(f'Mejl za učenika {record.transaction_record_student.student_name} je ponovo queue-ovan.', 'success')
        return redirect(url_for('main.email_monitoring'))
    except Exception as e:
        logging.error(f'Error in retry_failed_email route: {str(e)}')
        flash('Došlo je do greške prilikom retry-a mejla.', 'danger')
        return redirect(url_for('main.email_monitoring'))
