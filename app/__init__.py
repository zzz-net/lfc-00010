import os
from flask import Flask
from flask_login import LoginManager, UserMixin

from app.database import init_db, get_db

login_manager = LoginManager()
login_manager.login_view = 'pages.login_page'

class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role
    
    def is_admin(self):
        return self.role == 'admin'

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row['id'], row['username'], row['role'])
    return None

def create_app():
    app = Flask(__name__, 
                static_folder='static', 
                template_folder='templates')
    app.config['SECRET_KEY'] = 'sample-tracker-secret-key-2024'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
    
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    app.config['UPLOAD_FOLDER'] = upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    
    login_manager.init_app(app)
    
    init_db()
    
    from app.routes.pages import pages_bp
    from app.routes.auth import auth_bp
    from app.routes.samples import samples_bp
    from app.routes.export import export_bp
    from app.routes.evidence import evidence_bp
    
    app.register_blueprint(pages_bp)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(samples_bp, url_prefix='/api/samples')
    app.register_blueprint(export_bp, url_prefix='/api/export')
    app.register_blueprint(evidence_bp, url_prefix='/api/evidence')
    
    return app
