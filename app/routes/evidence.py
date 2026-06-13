import os
import uuid
from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.database import get_db

evidence_bp = Blueprint('evidence', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'pdf', 'txt', 'csv'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@evidence_bp.route('/upload', methods=['POST'])
@login_required
def upload_evidence():
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400
    
    file = request.files['file']
    sample_id = request.form.get('sample_id')
    description = request.form.get('description', '')
    
    if file.filename == '':
        return jsonify({'error': '未选择文件'}), 400
    
    if not sample_id:
        return jsonify({'error': '缺少样本ID'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件类型'}), 400
    
    conn = get_db()
    sample = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    if not sample:
        conn.close()
        return jsonify({'error': '样本不存在'}), 404
    
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
    file.save(filepath)
    
    evidence_type = 'photo' if ext in {'png', 'jpg', 'jpeg', 'gif', 'bmp'} else 'document'
    
    conn.execute(
        'INSERT INTO evidences (sample_id, type, description, file_path, uploaded_by) VALUES (?, ?, ?, ?, ?)',
        (sample_id, evidence_type, description, unique_name, current_user.username)
    )
    
    conn.commit()
    evidence_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    row = conn.execute('SELECT * FROM evidences WHERE id = ?', (evidence_id,)).fetchone()
    conn.close()
    
    return jsonify({
        'success': True,
        'evidence': {
            'id': row['id'],
            'type': row['type'],
            'description': row['description'],
            'file_path': row['file_path'],
            'uploaded_by': row['uploaded_by'],
            'created_at': row['created_at']
        }
    })

@evidence_bp.route('/files/<filename>')
@login_required
def get_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)
