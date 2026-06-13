import csv
import io
from datetime import datetime
from flask import Blueprint, request, make_response, jsonify
from flask_login import login_required, current_user

from app.database import get_db, status_to_text

export_bp = Blueprint('export', __name__)

@export_bp.route('/handover', methods=['GET'])
@login_required
def export_handover():
    batch_no = request.args.get('batch_no', '')
    sample_ids = request.args.get('sample_ids', '')
    
    conn = get_db()
    
    query = 'SELECT * FROM samples WHERE 1=1'
    params = []
    
    if batch_no:
        query += ' AND batch_no = ?'
        params.append(batch_no)
    
    if sample_ids:
        id_list = [int(x) for x in sample_ids.split(',') if x.isdigit()]
        if id_list:
            placeholders = ','.join(['?'] * len(id_list))
            query += f' AND id IN ({placeholders})'
            params.extend(id_list)
    
    query += ' ORDER BY id ASC'
    samples = conn.execute(query, params).fetchall()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        '样本编号', '批次号', '样本类型', '当前状态', 
        '入库时间', '打包时间', '交接时间', '到达时间',
        '最新温度', '异常状态', '证据数量', '照片证据', '文字证据',
        '复核人', '复核时间', '复核备注'
    ])
    
    for s in samples:
        logs = conn.execute(
            'SELECT status, created_at, temperature FROM status_logs WHERE sample_id = ? ORDER BY id ASC',
            (s['id'],)
        ).fetchall()
        
        log_map = {}
        latest_temp = None
        for log in logs:
            log_map[log['status']] = log['created_at']
            if log['temperature'] is not None:
                latest_temp = log['temperature']
        
        evidences = conn.execute(
            'SELECT type, description, file_path FROM evidences WHERE sample_id = ? ORDER BY id ASC',
            (s['id'],)
        ).fetchall()
        
        photo_files = '; '.join([e['file_path'] for e in evidences if e['file_path']])
        text_descs = '; '.join([e['description'] for e in evidences if e['description']])
        
        is_frozen = s['current_status'] in ['FROZEN', 'REVIEW_CLOSED']
        
        writer.writerow([
            s['sample_id'],
            s['batch_no'],
            s['sample_type'] or '',
            status_to_text(s['current_status']),
            log_map.get('WAREHOUSED', ''),
            log_map.get('PACKED', ''),
            log_map.get('HANDED_OVER', ''),
            log_map.get('ARRIVED', ''),
            latest_temp if latest_temp is not None else '',
            '是' if is_frozen else '否',
            len(evidences),
            photo_files,
            text_descs,
            s['reviewed_by'] or '',
            s['reviewed_at'] or '',
            s['review_remark'] or ''
        ])
    
    conn.close()
    
    output.seek(0)
    filename = f'handover_{batch_no or "all"}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response

@export_bp.route('/sample-timeline/<int:sample_id>', methods=['GET'])
@login_required
def export_sample_timeline(sample_id):
    conn = get_db()
    
    sample = conn.execute('SELECT * FROM samples WHERE id = ?', (sample_id,)).fetchone()
    if not sample:
        conn.close()
        return jsonify({'error': '样本不存在'}), 404
    
    logs = conn.execute(
        'SELECT * FROM status_logs WHERE sample_id = ? ORDER BY id ASC',
        (sample_id,)
    ).fetchall()
    
    evidences = conn.execute(
        'SELECT * FROM evidences WHERE sample_id = ? ORDER BY id ASC',
        (sample_id,)
    ).fetchall()
    
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['样本编号', sample['sample_id']])
    writer.writerow(['批次号', sample['batch_no']])
    writer.writerow(['样本类型', sample['sample_type'] or ''])
    writer.writerow(['当前状态', status_to_text(sample['current_status'])])
    writer.writerow([])
    
    writer.writerow(['=== 状态时间线 ==='])
    writer.writerow(['序号', '状态', '操作人', '时间', '温度', '备注'])
    for i, log in enumerate(logs, 1):
        writer.writerow([
            i,
            status_to_text(log['status']),
            log['operator'],
            log['created_at'],
            log['temperature'] if log['temperature'] is not None else '',
            log['remark'] or ''
        ])
    
    writer.writerow([])
    writer.writerow(['=== 证据记录 ==='])
    writer.writerow(['序号', '类型', '描述', '文件', '上传人', '时间'])
    for i, ev in enumerate(evidences, 1):
        writer.writerow([
            i,
            ev['type'],
            ev['description'] or '',
            ev['file_path'] or '',
            ev['uploaded_by'],
            ev['created_at']
        ])
    
    if sample['reviewed_by']:
        writer.writerow([])
        writer.writerow(['=== 复核信息 ==='])
        writer.writerow(['复核人', sample['reviewed_by']])
        writer.writerow(['复核时间', sample['reviewed_at']])
        writer.writerow(['复核备注', sample['review_remark'] or ''])
    
    output.seek(0)
    filename = f'sample_{sample["sample_id"]}_timeline_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response
