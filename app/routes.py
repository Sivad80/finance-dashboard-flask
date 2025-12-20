from flask import Blueprint, render_template

main = Blueprint('main', __name__)

@main.route('/')
def dashboard():
    return render_template('dashboard.html')

