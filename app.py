import os
import json
import time
import uuid
import threading
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_sqlalchemy import SQLAlchemy
import loadtran
from pathlib import Path

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'a_very_secret_key_12345')

# Configure Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://neondb_owner:npg_7bcWRKl4ETtF@ep-restless-salad-azv3963j-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MAX_ACCOUNTS = 5
TOKEN_EXPIRE_SECONDS = 4 * 3600   # 4 tieng

# =============================================================================
# Database Models
# =============================================================================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

class Account(db.Model):
    __tablename__ = 'accounts'
    id = db.Column(db.String(36), primary_key=True)
    owner_username = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    token = db.Column(db.String(2000), nullable=False)
    user_id = db.Column(db.String(100))
    short_id = db.Column(db.String(100))
    current_poster_url = db.Column(db.String(1000))
    user_path = db.Column(db.String(1000))
    saved_at = db.Column(db.Float, nullable=False)

# =============================================================================
# Helpers
# =============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def _get_token_status(saved_at):
    """Tra ve: 'new' | 'old' | 'expired'"""
    age = time.time() - saved_at
    if age < 3600:        # < 1 tieng
        return 'new'
    elif age < 7200:      # 1-2 tieng
        return 'old'
    else:                 # > 2 tieng (nhung chua bi xoa)
        return 'expired'


# =============================================================================
# Routes — Pages
# =============================================================================

@app.route('/')
@login_required
def index():
    return render_template('index.html', username=session['username'])

# =============================================================================
# Routes — Authentication
# =============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Tên đăng nhập hoặc mật khẩu không đúng.')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        reg_key = request.form.get('reg_key', '').strip()
        
        if reg_key != '405536':
            return render_template('register.html', error='Mã đăng ký không chính xác.')
            
        if not username or not password:
            return render_template('register.html', error='Vui lòng nhập đầy đủ thông tin.')
            
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error='Tên đăng nhập đã tồn tại.')
            
        new_user = User(
            username=username,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_user)
        db.session.commit()
        
        return render_template('register.html', success=f'Đã tạo tài khoản "{username}" thành công. Bạn có thể sử dụng tài khoản này để đăng nhập.')
        
    return render_template('register.html')

# =============================================================================
# Routes — Account Management API
# =============================================================================

@app.route('/api/verify_token', methods=['POST'])
@login_required
def verify_token():
    data = request.get_json()
    token = (data or {}).get('token', '').strip()
    if not token:
        return jsonify({'success': False, 'message': 'Token không được để trống'}), 400

    try:
        info = loadtran.get_account_info(token)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Lỗi xác thực: {e}'}), 500

    if not info.get('token_valid'):
        return jsonify({'success': False, 'message': 'Token không hợp lệ hoặc đã hết hạn'}), 401

    return jsonify({
        'success': True,
        'user_id': info['user_id'],
        'short_id': info['short_id'],
        'current_poster_url': info['current_poster_url'],
        'user_path': info['user_path'],
    })


@app.route('/api/accounts', methods=['GET'])
@login_required
def get_accounts():
    now = time.time()
    
    # Cleanup expired accounts
    Account.query.filter(Account.saved_at < now - TOKEN_EXPIRE_SECONDS).delete()
    db.session.commit()
    
    current_user = session['username']
    user_accounts = Account.query.filter_by(owner_username=current_user).order_by(Account.saved_at).all()

    result = []
    for a in user_accounts:
        result.append({
            'id': a.id,
            'name': a.name,
            'short_id': a.short_id,
            'current_poster_url': a.current_poster_url,
            'saved_at': a.saved_at,
            'status': _get_token_status(a.saved_at),
            'age_minutes': int((now - a.saved_at) / 60),
        })
    return jsonify({'accounts': result})


@app.route('/api/accounts', methods=['POST'])
@login_required
def save_account():
    data = request.get_json()
    token = (data or {}).get('token', '').strip()
    name = (data or {}).get('name', '').strip()
    user_id = (data or {}).get('user_id', '').strip()
    short_id = (data or {}).get('short_id', '').strip()
    current_poster_url = (data or {}).get('current_poster_url', '')
    user_path = (data or {}).get('user_path', '')

    if not token:
        return jsonify({'success': False, 'message': 'Token không được để trống'}), 400

    now = time.time()
    current_user = session['username']

    # Cleanup expired accounts
    Account.query.filter(Account.saved_at < now - TOKEN_EXPIRE_SECONDS).delete()
    db.session.commit()

    # Neu da co account voi cung user_id cua user nay -> cap nhat
    existing = Account.query.filter_by(user_id=user_id, owner_username=current_user).first()
    if existing:
        existing.token = token
        existing.name = name or existing.name
        existing.current_poster_url = current_poster_url
        existing.user_path = user_path
        existing.saved_at = now
        db.session.commit()
        return jsonify({'success': True, 'id': existing.id, 'updated': True})

    # Kiem tra gioi han cho user nay
    user_accounts_count = Account.query.filter_by(owner_username=current_user).count()
    if user_accounts_count >= MAX_ACCOUNTS:
        # Xoa account cu nhat cua user nay
        oldest_account = Account.query.filter_by(owner_username=current_user).order_by(Account.saved_at).first()
        if oldest_account:
            db.session.delete(oldest_account)
            db.session.commit()

    new_account = Account(
        id=str(uuid.uuid4()),
        owner_username=current_user,
        name=name or f'Tài khoản {user_accounts_count + 1}',
        token=token,
        user_id=user_id,
        short_id=short_id,
        current_poster_url=current_poster_url,
        user_path=user_path,
        saved_at=now
    )
    db.session.add(new_account)
    db.session.commit()
    return jsonify({'success': True, 'id': new_account.id, 'updated': False})


@app.route('/api/accounts/<account_id>', methods=['DELETE'])
@login_required
def delete_account(account_id):
    current_user = session['username']
    account = Account.query.filter_by(id=account_id, owner_username=current_user).first()
    if not account:
        return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản'}), 404
    db.session.delete(account)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/accounts/<account_id>/token', methods=['GET'])
@login_required
def get_account_token(account_id):
    """Tra ve token de dien vao o nhap (khong lo thong tin toan bo)"""
    current_user = session['username']
    account = Account.query.filter_by(id=account_id, owner_username=current_user).first()
    if not account:
        return jsonify({'success': False}), 404
    return jsonify({'success': True, 'token': account.token})


@app.route('/api/accounts/<account_id>/rename', methods=['POST'])
@login_required
def rename_account(account_id):
    data = request.get_json()
    new_name = (data or {}).get('name', '').strip()
    if not new_name:
        return jsonify({'success': False, 'message': 'Tên không được để trống'}), 400
    
    current_user = session['username']
    account = Account.query.filter_by(id=account_id, owner_username=current_user).first()
    if not account:
        return jsonify({'success': False}), 404
    
    account.name = new_name
    db.session.commit()
    return jsonify({'success': True})


# =============================================================================
# Routes — Upload & Logs
# =============================================================================

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    token = request.form.get('token')
    is_share = request.form.get('is_share') == 'true'
    mode = request.form.get('mode', 'playerimage')
    file = request.files.get('file')

    if not token or not file:
        return jsonify({"success": False, "message": "Missing token or file"}), 400

    # Reset logs
    loadtran.log_buffer.clear()

    # Save file
    file_path = os.path.join(UPLOAD_FOLDER, "cropped_" + file.filename)
    file.save(file_path)

    def run_worker():
        try:
            loadtran.tprint("== BẮT ĐẦU XỬ LÝ ==")

            # 1. Khởi động Sign Bridge nếu chưa chạy
            loadtran._start_sign_bridge()

            # 2. Xác thực token và lấy thông tin tài khoản
            mode_label = {"playerimage": "Ảnh tải trận", "flowborn_marksman": "Flowborn (Xạ thủ)", "flowborn_mage": "Flowborn (Pháp sư)"}.get(mode, mode)
            loadtran.tprint(f"🔑 Đang xác thực token... (Chế độ: {mode_label})")
            user_path = loadtran.get_user_path(token, mode=mode)
            if not user_path:
                loadtran.tprint("❌ Xác thực thất bại! Token không hợp lệ hoặc đã hết hạn. Vui lòng lấy token mới từ game.")
                return

            loadtran.tprint(f"✅ Xác thực thành công! Đã tìm thấy tài khoản.")

            # 3. Chuẩn bị ảnh
            loadtran.tprint(f"🖼️  Đang chuẩn bị ảnh để tải lên...")
            media_info = loadtran.prepare_media(Path(file_path), auto_resize=False)
            if not media_info:
                loadtran.tprint("❌ Lỗi xử lý ảnh! File ảnh bị hỏng hoặc định dạng không được hỗ trợ.")
                return

            # 4. Tiến hành tải lên
            acc = {
                "label": "Web-Account",
                "token": token,
                "user_path": user_path
            }
            results = {}
            share_label = "Quảng trường (mọi người thấy)" if is_share else "Chỉ mình tôi"
            loadtran.tprint(f"📤 Bắt đầu tải lên... (Hiển thị: {share_label})")
            loadtran.acc_worker(acc, [media_info], is_share, results, dry_run=False, mode=mode)

            loadtran.tprint("== HOÀN THÀNH ==")
        except Exception as e:
            loadtran.tprint(f"❌ Đã xảy ra lỗi không mong muốn: {e}")

    # Run in background
    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Started processing"})


@app.route('/logs')
@login_required
def get_logs():
    logs = list(loadtran.log_buffer)
    loadtran.log_buffer.clear()
    return jsonify({"logs": logs})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
