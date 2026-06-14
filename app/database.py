import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sample_tracker.db')

STATUS_MAP = {
    'PENDING': '待入库',
    'WAREHOUSED': '已入库',
    'PACKED': '已打包',
    'HANDED_OVER': '已交接',
    'ARRIVED': '已到达',
    'FROZEN': '异常冻结',
    'REVIEW_CLOSED': '已复核关闭'
}

STATUS_ORDER = ['PENDING', 'WAREHOUSED', 'PACKED', 'HANDED_OVER', 'ARRIVED']

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'operator',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id VARCHAR(100) UNIQUE NOT NULL,
            batch_no VARCHAR(100) NOT NULL,
            sample_type VARCHAR(100),
            current_status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            review_remark TEXT,
            reviewed_by VARCHAR(50),
            reviewed_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS status_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id INTEGER NOT NULL,
            status VARCHAR(50) NOT NULL,
            operator VARCHAR(50) NOT NULL,
            remark TEXT,
            temperature REAL,
            previous_status VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sample_id) REFERENCES samples(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS evidences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sample_id INTEGER NOT NULL,
            type VARCHAR(20) NOT NULL,
            description TEXT,
            file_path VARCHAR(500),
            uploaded_by VARCHAR(50) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sample_id) REFERENCES samples(id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS import_batches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_no VARCHAR(100) NOT NULL,
            operator VARCHAR(50) NOT NULL,
            total_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            invalid_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'completed',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS import_batch_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL,
            sample_id VARCHAR(100),
            sample_type VARCHAR(100),
            result VARCHAR(20) NOT NULL,
            reason TEXT,
            sample_db_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (batch_id) REFERENCES import_batches(id)
        )
    ''')

    c.execute('CREATE INDEX IF NOT EXISTS idx_samples_batch ON samples(batch_no)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_samples_status ON samples(current_status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_status_logs_sample ON status_logs(sample_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_evidences_sample ON evidences(sample_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_import_batches_operator ON import_batches(operator)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_import_batches_batch_no ON import_batches(batch_no)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_import_batch_items_batch ON import_batch_items(batch_id)')
    
    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ('admin', generate_password_hash('admin123'), 'admin')
        )
        c.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ('operator', generate_password_hash('op123456'), 'operator')
        )
    
    conn.commit()
    conn.close()

def status_to_text(status_code):
    return STATUS_MAP.get(status_code, status_code)

def can_transition(from_status, to_status):
    if from_status == to_status:
        return False
    
    if from_status == 'FROZEN':
        return to_status == 'REVIEW_CLOSED'
    
    if from_status == 'REVIEW_CLOSED':
        return False
    
    if to_status == 'FROZEN':
        return from_status in ['WAREHOUSED', 'PACKED', 'HANDED_OVER', 'ARRIVED']
    
    if from_status == 'ARRIVED':
        return False
    
    if from_status in STATUS_ORDER and to_status in STATUS_ORDER:
        return STATUS_ORDER.index(to_status) == STATUS_ORDER.index(from_status) + 1
    
    return False
