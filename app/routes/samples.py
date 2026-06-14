import csv
import io
from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app.database import get_db, can_transition, status_to_text

samples_bp = Blueprint('samples', __name__)

def row_to_dict(row):
    return {
        'id': row['id'],
        'sample_id': row['sample_id'],
        'batch_no': row['batch_no'],
        'sample_type': row['sample_type'],
        'current_status': row['current_status'],
        'current_status_text': status_to_text(row['current_status']),
        'review_remark': row['review_remark'],
        'reviewed_by': row['reviewed_by'],
        'reviewed_at': row['reviewed_at'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at']
    }

def _analyze_samples(samples_data, existing_ids):
    input_sample_ids = set()
    result = {
        'importable': [],
        'duplicates_batch': [],
        'duplicates_system': [],
        'missing_fields': [],
        'invalid': []
    }
    
    for idx, item in enumerate(samples_data):
        sid = str(item.get('sample_id', '')).strip()
        sample_type = str(item.get('sample_type', '')).strip()
        
        if not sid:
            result['missing_fields'].append({
                'index': idx,
                'item': item,
                'reason': 'sample_id 不能为空'
            })
            continue
        
        if sid in input_sample_ids:
            result['duplicates_batch'].append({
                'index': idx,
                'sample_id': sid,
                'sample_type': sample_type,
                'reason': '本批次内重复'
            })
            continue
        input_sample_ids.add(sid)
        
        if sid in existing_ids:
            result['duplicates_system'].append({
                'index': idx,
                'sample_id': sid,
                'sample_type': sample_type,
                'reason': '系统中已存在'
            })
            continue
        
        result['importable'].append({
            'index': idx,
            'sample_id': sid,
            'sample_type': sample_type
        })
    
    return result

@samples_bp.route('', methods=['GET'])
@login_required
def list_samples():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status = request.args.get('status', '')
    batch_no = request.args.get('batch_no', '')
    search = request.args.get('search', '')
    
    conn = get_db()
    query = 'SELECT * FROM samples WHERE 1=1'
    params = []
    
    if status:
        query += ' AND current_status = ?'
        params.append(status)
    if batch_no:
        query += ' AND batch_no = ?'
        params.append(batch_no)
    if search:
        query += ' AND (sample_id LIKE ? OR batch_no LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])
    
    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'items': [row_to_dict(r) for r in rows]
    })

@samples_bp.route('/<int:sample_id>', methods=['GET'])
@login_required
def get_sample(sample_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    
    if not row:
        conn.close()
        return jsonify({'error': '样本不存在'}), 404
    
    sample = row_to_dict(row)
    
    logs = conn.execute(
        'SELECT * FROM status_logs WHERE sample_id = ? ORDER BY id ASC',
        (sample_id,)
    ).fetchall()
    sample['status_logs'] = [{
        'id': l['id'],
        'status': l['status'],
        'status_text': status_to_text(l['status']),
        'operator': l['operator'],
        'remark': l['remark'],
        'temperature': l['temperature'],
        'previous_status': l['previous_status'],
        'created_at': l['created_at']
    } for l in logs]
    
    evidences = conn.execute(
        'SELECT * FROM evidences WHERE sample_id = ? ORDER BY id DESC',
        (sample_id,)
    ).fetchall()
    sample['evidences'] = [{
        'id': e['id'],
        'type': e['type'],
        'description': e['description'],
        'file_path': e['file_path'],
        'uploaded_by': e['uploaded_by'],
        'created_at': e['created_at']
    } for e in evidences]
    
    conn.close()
    return jsonify(sample)

@samples_bp.route('/import/preview', methods=['POST'])
@login_required
def preview_import():
    data = request.get_json()
    samples_data = data.get('samples', [])
    batch_no = data.get('batch_no', '').strip()
    
    if not samples_data:
        return jsonify({'error': '导入数据不能为空'}), 400
    
    if not batch_no:
        return jsonify({'error': '批次号不能为空'}), 400
    
    conn = get_db()
    existing_ids = set()
    for r in conn.execute('SELECT sample_id FROM samples').fetchall():
        existing_ids.add(r['sample_id'])
    conn.close()
    
    analysis = _analyze_samples(samples_data, existing_ids)
    
    total = len(samples_data)
    importable_count = len(analysis['importable'])
    duplicate_batch_count = len(analysis['duplicates_batch'])
    duplicate_system_count = len(analysis['duplicates_system'])
    missing_count = len(analysis['missing_fields'])
    invalid_count = len(analysis['invalid'])
    
    return jsonify({
        'success': True,
        'batch_no': batch_no,
        'total_count': total,
        'importable_count': importable_count,
        'duplicate_batch_count': duplicate_batch_count,
        'duplicate_system_count': duplicate_system_count,
        'duplicate_total_count': duplicate_batch_count + duplicate_system_count,
        'missing_fields_count': missing_count,
        'invalid_count': invalid_count,
        'importable': analysis['importable'],
        'duplicates_batch': analysis['duplicates_batch'],
        'duplicates_system': analysis['duplicates_system'],
        'missing_fields': analysis['missing_fields'],
        'invalid': analysis['invalid']
    })

@samples_bp.route('/import', methods=['POST'])
@login_required
def import_samples():
    data = request.get_json()
    samples_data = data.get('samples', [])
    batch_no = data.get('batch_no', '').strip()
    
    if not samples_data:
        return jsonify({'error': '导入数据不能为空'}), 400
    
    if not batch_no:
        return jsonify({'error': '批次号不能为空'}), 400
    
    conn = get_db()
    
    existing_ids = set()
    for r in conn.execute('SELECT sample_id FROM samples').fetchall():
        existing_ids.add(r['sample_id'])
    
    analysis = _analyze_samples(samples_data, existing_ids)
    
    imported = []
    batch_items = []
    
    for item in analysis['importable']:
        sid = item['sample_id']
        sample_type = item['sample_type']
        try:
            conn.execute(
                'INSERT INTO samples (sample_id, batch_no, sample_type, current_status) VALUES (?, ?, ?, ?)',
                (sid, batch_no, sample_type, 'PENDING')
            )
            new_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            
            conn.execute(
                'INSERT INTO status_logs (sample_id, status, operator, remark, previous_status) VALUES (?, ?, ?, ?, ?)',
                (new_id, 'PENDING', current_user.username, '批次导入', None)
            )
            
            imported.append({'sample_id': sid, 'id': new_id})
            batch_items.append({
                'sample_id': sid,
                'sample_type': sample_type,
                'result': 'success',
                'reason': '',
                'sample_db_id': new_id
            })
        except Exception as e:
            batch_items.append({
                'sample_id': sid,
                'sample_type': sample_type,
                'result': 'invalid',
                'reason': str(e),
                'sample_db_id': None
            })
    
    for item in analysis['duplicates_batch']:
        batch_items.append({
            'sample_id': item['sample_id'],
            'sample_type': item['sample_type'],
            'result': 'duplicate_batch',
            'reason': item['reason'],
            'sample_db_id': None
        })
    
    for item in analysis['duplicates_system']:
        batch_items.append({
            'sample_id': item['sample_id'],
            'sample_type': item['sample_type'],
            'result': 'duplicate_system',
            'reason': item['reason'],
            'sample_db_id': None
        })
    
    for item in analysis['missing_fields']:
        batch_items.append({
            'sample_id': '',
            'sample_type': '',
            'result': 'missing_fields',
            'reason': item['reason'],
            'sample_db_id': None
        })
    
    success_count = len(imported)
    duplicate_batch_count = len(analysis['duplicates_batch'])
    duplicate_system_count = len(analysis['duplicates_system'])
    duplicate_total_count = duplicate_batch_count + duplicate_system_count
    missing_count = len(analysis['missing_fields'])
    invalid_count = len(analysis['invalid'])
    total_count = len(samples_data)
    
    conn.execute(
        '''INSERT INTO import_batches 
           (batch_no, operator, total_count, success_count, duplicate_count, invalid_count, status) 
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (batch_no, current_user.username, total_count, success_count, 
         duplicate_total_count, missing_count + invalid_count, 'completed')
    )
    batch_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    
    for bi in batch_items:
        conn.execute(
            '''INSERT INTO import_batch_items 
               (batch_id, sample_id, sample_type, result, reason, sample_db_id) 
               VALUES (?, ?, ?, ?, ?, ?)''',
            (batch_id, bi['sample_id'], bi['sample_type'], 
             bi['result'], bi['reason'], bi['sample_db_id'])
        )
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'batch_id': batch_id,
        'batch_no': batch_no,
        'total_count': total_count,
        'imported_count': success_count,
        'success_count': success_count,
        'duplicate_batch_count': duplicate_batch_count,
        'duplicate_system_count': duplicate_system_count,
        'duplicate_count': duplicate_total_count,
        'missing_fields_count': missing_count,
        'invalid_count': invalid_count,
        'imported': imported,
        'duplicates_batch': analysis['duplicates_batch'],
        'duplicates_system': analysis['duplicates_system'],
        'missing_fields': analysis['missing_fields'],
        'invalid': analysis['invalid']
    })

@samples_bp.route('/import/batches', methods=['GET'])
@login_required
def list_import_batches():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    batch_no = request.args.get('batch_no', '')
    operator = request.args.get('operator', '')
    
    conn = get_db()
    query = 'SELECT * FROM import_batches WHERE 1=1'
    params = []
    
    if not current_user.is_admin():
        query += ' AND operator = ?'
        params.append(current_user.username)
    elif operator:
        query += ' AND operator = ?'
        params.append(operator)
    
    if batch_no:
        query += ' AND batch_no LIKE ?'
        params.append(f'%{batch_no}%')
    
    count_query = query.replace('SELECT *', 'SELECT COUNT(*)')
    total = conn.execute(count_query, params).fetchone()[0]
    
    query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
    params.extend([per_page, (page - 1) * per_page])
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    items = []
    for r in rows:
        items.append({
            'id': r['id'],
            'batch_no': r['batch_no'],
            'operator': r['operator'],
            'total_count': r['total_count'],
            'success_count': r['success_count'],
            'duplicate_count': r['duplicate_count'],
            'invalid_count': r['invalid_count'],
            'status': r['status'],
            'created_at': r['created_at']
        })
    
    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'items': items
    })

@samples_bp.route('/import/batches/<int:batch_id>', methods=['GET'])
@login_required
def get_import_batch(batch_id):
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    result_filter = request.args.get('result', '')
    
    conn = get_db()
    batch_row = conn.execute(
        'SELECT * FROM import_batches WHERE id = ?', (batch_id,)
    ).fetchone()
    
    if not batch_row:
        conn.close()
        return jsonify({'error': '批次记录不存在'}), 404
    
    if not current_user.is_admin() and batch_row['operator'] != current_user.username:
        conn.close()
        return jsonify({'error': '无权查看此批次记录'}), 403
    
    batch = {
        'id': batch_row['id'],
        'batch_no': batch_row['batch_no'],
        'operator': batch_row['operator'],
        'total_count': batch_row['total_count'],
        'success_count': batch_row['success_count'],
        'duplicate_count': batch_row['duplicate_count'],
        'invalid_count': batch_row['invalid_count'],
        'status': batch_row['status'],
        'created_at': batch_row['created_at']
    }
    
    items_query = 'SELECT * FROM import_batch_items WHERE batch_id = ?'
    items_params = [batch_id]
    
    if result_filter:
        items_query += ' AND result = ?'
        items_params.append(result_filter)
    
    count_query = items_query.replace('SELECT *', 'SELECT COUNT(*)')
    items_total = conn.execute(count_query, items_params).fetchone()[0]
    
    items_query += ' ORDER BY id ASC LIMIT ? OFFSET ?'
    items_params.extend([per_page, (page - 1) * per_page])
    
    item_rows = conn.execute(items_query, items_params).fetchall()
    
    items = []
    for r in item_rows:
        items.append({
            'id': r['id'],
            'sample_id': r['sample_id'],
            'sample_type': r['sample_type'],
            'result': r['result'],
            'reason': r['reason'],
            'sample_db_id': r['sample_db_id'],
            'created_at': r['created_at']
        })
    
    conn.close()
    
    return jsonify({
        'batch': batch,
        'items_total': items_total,
        'page': page,
        'per_page': per_page,
        'items': items
    })

def _update_status(conn, sample_id, new_status, operator, remark=None, temperature=None):
    row = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    if not row:
        return None, '样本不存在'
    
    if not can_transition(row['current_status'], new_status):
        return None, f'无法从 {status_to_text(row["current_status"])} 变更为 {status_to_text(new_status)}'
    
    previous_status = row['current_status']
    
    conn.execute(
        'UPDATE samples SET current_status = ?, updated_at = ? WHERE id = ?',
        (new_status, datetime.now().isoformat(), sample_id)
    )
    
    conn.execute(
        'INSERT INTO status_logs (sample_id, status, operator, remark, temperature, previous_status) VALUES (?, ?, ?, ?, ?, ?)',
        (sample_id, new_status, operator, remark, temperature, previous_status)
    )
    
    return True, None

@samples_bp.route('/<int:sample_id>/status', methods=['POST'])
@login_required
def update_status(sample_id):
    data = request.get_json()
    new_status = data.get('status', '')
    remark = data.get('remark', '')
    temperature = data.get('temperature')
    
    valid_statuses = ['WAREHOUSED', 'PACKED', 'HANDED_OVER', 'ARRIVED']
    if new_status not in valid_statuses:
        return jsonify({'error': '无效的状态'}), 400
    
    conn = get_db()
    success, error = _update_status(conn, sample_id, new_status, current_user.username, remark, temperature)
    
    if not success:
        conn.close()
        return jsonify({'error': error}), 400
    
    conn.commit()
    
    row = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    conn.close()
    
    return jsonify({
        'success': True,
        'sample': row_to_dict(row)
    })

@samples_bp.route('/<int:sample_id>/exception', methods=['POST'])
@login_required
def record_exception(sample_id):
    data = request.get_json()
    exception_type = data.get('type', '')
    description = data.get('description', '')
    temperature = data.get('temperature')
    evidence_file = data.get('evidence_file', '')
    
    if exception_type not in ['overtemp', 'damage', 'other']:
        return jsonify({'error': '无效的异常类型'}), 400
    
    conn = get_db()
    row = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    
    if not row:
        conn.close()
        return jsonify({'error': '样本不存在'}), 404
    
    if row['current_status'] in ['REVIEW_CLOSED', 'FROZEN', 'PENDING']:
        conn.close()
        return jsonify({'error': '当前状态不允许录入异常'}), 400
    
    previous_status = row['current_status']
    remark_map = {
        'overtemp': '超温异常',
        'damage': '破损异常',
        'other': '其他异常'
    }
    
    conn.execute(
        'UPDATE samples SET current_status = ?, updated_at = ? WHERE id = ?',
        ('FROZEN', datetime.now().isoformat(), sample_id)
    )
    
    conn.execute(
        'INSERT INTO status_logs (sample_id, status, operator, remark, temperature, previous_status) VALUES (?, ?, ?, ?, ?, ?)',
        (sample_id, 'FROZEN', current_user.username, 
         f'{remark_map.get(exception_type, "异常")}: {description}', 
         temperature, previous_status)
    )
    
    evidence_type_map = {
        'overtemp': 'temperature',
        'damage': 'photo',
        'other': 'text'
    }
    
    conn.execute(
        'INSERT INTO evidences (sample_id, type, description, file_path, uploaded_by) VALUES (?, ?, ?, ?, ?)',
        (sample_id, evidence_type_map.get(exception_type, 'text'), 
         description, evidence_file, current_user.username)
    )
    
    conn.commit()
    
    row = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    conn.close()
    
    return jsonify({
        'success': True,
        'sample': row_to_dict(row)
    })

@samples_bp.route('/<int:sample_id>/review', methods=['POST'])
@login_required
def review_sample(sample_id):
    if not current_user.is_admin():
        return jsonify({'error': '只有管理员可以复核关闭异常'}), 403
    
    data = request.get_json()
    action = data.get('action', '')
    remark = data.get('remark', '')
    
    if action not in ['close', 'keep_frozen']:
        return jsonify({'error': '无效的操作'}), 400
    
    conn = get_db()
    row = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    
    if not row:
        conn.close()
        return jsonify({'error': '样本不存在'}), 404
    
    if row['current_status'] != 'FROZEN':
        conn.close()
        return jsonify({'error': '只有异常冻结状态的样本才能复核'}), 400
    
    if action == 'close':
        conn.execute(
            'UPDATE samples SET current_status = ?, review_remark = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ? WHERE id = ?',
            ('REVIEW_CLOSED', remark, current_user.username, datetime.now().isoformat(), 
             datetime.now().isoformat(), sample_id)
        )
        
        conn.execute(
            'INSERT INTO status_logs (sample_id, status, operator, remark, previous_status) VALUES (?, ?, ?, ?, ?)',
            (sample_id, 'REVIEW_CLOSED', current_user.username, 
             f'复核关闭: {remark}', 'FROZEN')
        )
    else:
        conn.execute(
            'UPDATE samples SET review_remark = ?, reviewed_by = ?, reviewed_at = ?, updated_at = ? WHERE id = ?',
            (remark, current_user.username, datetime.now().isoformat(), 
             datetime.now().isoformat(), sample_id)
        )
        
        conn.execute(
            'INSERT INTO status_logs (sample_id, status, operator, remark, previous_status) VALUES (?, ?, ?, ?, ?)',
            (sample_id, 'FROZEN', current_user.username, 
             f'复核维持冻结: {remark}', 'FROZEN')
        )
    
    conn.commit()
    
    row = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    conn.close()
    
    return jsonify({
        'success': True,
        'sample': row_to_dict(row)
    })

@samples_bp.route('/batch-status', methods=['POST'])
@login_required
def batch_update_status():
    data = request.get_json()
    sample_ids = data.get('sample_ids', [])
    new_status = data.get('status', '')
    remark = data.get('remark', '')
    
    valid_statuses = ['WAREHOUSED', 'PACKED', 'HANDED_OVER', 'ARRIVED']
    if new_status not in valid_statuses:
        return jsonify({'error': '无效的状态'}), 400
    
    if not sample_ids:
        return jsonify({'error': '请选择样本'}), 400
    
    conn = get_db()
    success_count = 0
    failed = []
    
    for sid in sample_ids:
        try:
            ok, err = _update_status(conn, sid, new_status, current_user.username, remark)
            if ok:
                success_count += 1
            else:
                failed.append({'sample_id': sid, 'error': err})
        except Exception as e:
            failed.append({'sample_id': sid, 'error': str(e)})
    
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'success_count': success_count,
        'failed_count': len(failed),
        'failed': failed
    })
