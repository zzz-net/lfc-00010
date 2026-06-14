from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required

pages_bp = Blueprint('pages', __name__)

@pages_bp.route('/')
@login_required
def index():
    return redirect(url_for('pages.samples_page'))

@pages_bp.route('/login')
def login_page():
    return render_template('login.html')

@pages_bp.route('/samples')
@login_required
def samples_page():
    return render_template('samples.html')

@pages_bp.route('/samples/<int:sample_id>')
@login_required
def sample_detail_page(sample_id):
    return render_template('sample_detail.html', sample_id=sample_id)

@pages_bp.route('/import-records')
@login_required
def import_records_page():
    return render_template('import_records.html')


@pages_bp.route('/operation-logs')
@login_required
def operation_logs_page():
    return render_template('operation_logs.html')
