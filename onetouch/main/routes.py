from flask import Blueprint
from flask import render_template, redirect, url_for, flash, request
from flask_login import current_user


main = Blueprint('main', __name__)


@main.route("/")
@main.route("/home")
def home():
    if current_user.is_authenticated:
        pass
    else:
        flash('Morate da budete prijavljeni da biste pristupili ovoj stranici.', 'info')
        return redirect(url_for('main.about'))
    return render_template('home.html', title="Početna")


@main.route("/about")
def about():
    return render_template('about.html', title='O softveru')


@main.route('/ajax', methods=['POST'])
def ajax():
    new_value = request.form.get('new_value')
    return new_value