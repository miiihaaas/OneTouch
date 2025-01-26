from onetouch import logger, db, app, mail
from flask_mail import Message
from flask import render_template

def send_license_expiry_notification(school):
    try:
        days_left = school.days_until_license_expiry()
        logger.debug(f'Provera licence za školu {school.school_name}, preostalo dana: {days_left}')
        if days_left not in app.config['LICENSE_NOTIFICATION_DAYS']:
            return False
            
        # Proveri da li je mejl već poslat danas
        from datetime import datetime
        today = datetime.now().date()
        if school.last_license_email_date == today:
            return False
            
        # Pripremi i pošalji mejl
        subject = f'Obaveštenje o isteku licence - {school.school_name} - {days_left} dana'
        html_body = render_template('message_html_license_expiry_notification.html', 
                                    school=school,
                                    days_left=days_left)
        body = f'''Poštovani,

Obaveštavamo vas da će licenca za korišćenje OneTouch softvera za školu {school.school_name} isteći za {days_left} dana.

Datum isteka licence: {school.license_expiry_date.strftime('%d.%m.%Y.')}

Molimo vas da kontaktirate školu radi produženja licence.
{school.school_name}
{school.school_address}
{school.school_zip_code} {school.school_city}


Srdačan pozdrav,
OneTouch Tim'''
        
        msg = Message(subject,
                        sender=app.config['MAIL_USERNAME'],
                        recipients=app.config['LICENSE_NOTIFICATION_EMAILS'])
        msg.body = body
        msg.html = html_body
        
        try:
            mail.send(msg)
            logger.info(f'Uspešno poslat mejl za školu {school.school_name}')
            
            # Ažuriraj datum poslednjeg slanja
            school.last_license_email_date = today
            db.session.commit()
            logger.debug(f'Ažuriran datum poslednjeg slanja za školu {school.school_name}')
            
            return True
            
        except ConnectionRefusedError:
            logger.error(f'Nije moguće povezati se sa mail serverom {app.config["MAIL_SERVER"]}:{app.config["MAIL_PORT"]}')
            raise
        except TimeoutError:
            logger.error(f'Isteklo vreme za povezivanje sa mail serverom {app.config["MAIL_SERVER"]}')
            raise
        except Exception as e:
            logger.error(f'Greška pri slanju mejla: {str(e)}')
            raise
        
    except Exception as e:
        logger.error(f'Greška u send_license_expiry_notification: {str(e)}')
        return False