import csv
import io
from datetime import datetime
from flask import Blueprint, request, jsonify, make_response
from flask_login import login_required, current_user

from app.database import get_db, op_type_to_text

logs_bp = Blueprint('logs', __name__)


@logs_bp.route('', methods=['GET'])
@login_required
def list_operation_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    operator = request.args.get('operator', '')
    operation_type = request.args.get('operation_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conn = get_db()

    query = 'SELECT * FROM operation_logs WHERE 1=1'
    params = []

    if not current_user.is_admin():
        query += ' AND operator = ?'
        params.append(current_user.username)
    elif operator:
        query += ' AND operator = ?'
        params.append(operator)

    if operation_type:
        query += ' AND operation_type = ?'
        params.append(operation_type)

    if date_from:
        query += ' AND created_at >= ?'
        params.append(date_from)

    if date_to:
        query += ' AND created_at <= ?'
        params.append(date_to + ' 23:59:59')

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
            'operator': r['operator'],
            'operation_type': r['operation_type'],
            'operation_type_text': op_type_to_text(r['operation_type']),
            'target_type': r['target_type'],
            'target_id': r['target_id'],
            'detail': r['detail'],
            'sample_count': r['sample_count'],
            'related_batch_op_id': r['related_batch_op_id'],
            'created_at': r['created_at']
        })

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'items': items
    })


@logs_bp.route('/operators', methods=['GET'])
@login_required
def list_operators():
    conn = get_db()

    if current_user.is_admin():
        rows = conn.execute(
            'SELECT DISTINCT operator FROM operation_logs ORDER BY operator'
        ).fetchall()
    else:
        rows = [{'operator': current_user.username}]

    conn.close()

    return jsonify({
        'operators': [r['operator'] for r in rows]
    })


@logs_bp.route('/export', methods=['GET'])
@login_required
def export_operation_logs():
    operator = request.args.get('operator', '')
    operation_type = request.args.get('operation_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    conn = get_db()

    query = 'SELECT * FROM operation_logs WHERE 1=1'
    params = []

    if not current_user.is_admin():
        query += ' AND operator = ?'
        params.append(current_user.username)
    elif operator:
        query += ' AND operator = ?'
        params.append(operator)

    if operation_type:
        query += ' AND operation_type = ?'
        params.append(operation_type)

    if date_from:
        query += ' AND created_at >= ?'
        params.append(date_from)

    if date_to:
        query += ' AND created_at <= ?'
        params.append(date_to + ' 23:59:59')

    query += ' ORDER BY id DESC'
    rows = conn.execute(query, params).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        '序号', '操作时间', '操作人', '操作类型',
        '目标类型', '目标ID', '操作详情', '涉及样本数', '关联批量操作ID'
    ])

    for idx, r in enumerate(rows, 1):
        writer.writerow([
            idx,
            r['created_at'],
            r['operator'],
            op_type_to_text(r['operation_type']),
            r['target_type'] or '',
            r['target_id'] or '',
            r['detail'] or '',
            r['sample_count'] or 0,
            r['related_batch_op_id'] or ''
        ])

    output.seek(0)
    filename = f'operation_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response
