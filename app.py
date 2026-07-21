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

ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts.json')
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.json')

MAX_ACCOUNTS = 5
TOKEN_EXPIRE_SECONDS = 5 * 3600   # 5 tieng

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
# Helpers (JSON Fallback)
# =============================================================================

def _load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('users', [])
    except Exception:
        return []

def _save_users(users):
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': users}, f, ensure_ascii=False, indent=2)

def _load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    try:
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('accounts', [])
    except Exception:
        return []

def _save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'accounts': accounts}, f, ensure_ascii=False, indent=2)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session['username'] != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def _get_token_status(saved_at):
    age = time.time() - saved_at
    if age < 3600:        # < 1 tieng
        return 'new'
    elif age < 7200:      # 1-2 tieng
        return 'old'
    else:                 # > 2 tieng
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
        
        user_info = None
        try:
            user = User.query.filter_by(username=username).first()
            if user:
                user_info = {'username': user.username, 'password_hash': user.password_hash}
        except Exception as e:
            print(f"[Fallback] DB Error on login: {e}")
            users = _load_users()
            user_info = next((u for u in users if u['username'] == username), None)
        
        if user_info and check_password_hash(user_info['password_hash'], password):
            session['username'] = username
            if username == 'admin':
                return redirect(url_for('admin_dashboard'))
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

            
        if not username or not password:
            return render_template('register.html', error='Vui lòng nhập đầy đủ thông tin.')
            
        password_hash = generate_password_hash(password)
        try:
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                return render_template('register.html', error='Tên đăng nhập đã tồn tại.')
                
            new_user = User(username=username, password_hash=password_hash)
            db.session.add(new_user)
            db.session.commit()
        except Exception as e:
            print(f"[Fallback] DB Error on register: {e}")
            users = _load_users()
            if any(u['username'] == username for u in users):
                return render_template('register.html', error='Tên đăng nhập đã tồn tại.')
                
            users.append({'username': username, 'password_hash': password_hash})
            _save_users(users)
        
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
    current_user = session['username']
    
    try:
        Account.query.filter(Account.saved_at < now - TOKEN_EXPIRE_SECONDS).delete()
        db.session.commit()
        
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
    except Exception as e:
        print(f"[Fallback] DB Error on get_accounts: {e}")
        accounts = _load_accounts()
        accounts = [a for a in accounts if (now - a.get('saved_at', 0)) < TOKEN_EXPIRE_SECONDS]
        _save_accounts(accounts)
        
        user_accounts = [a for a in accounts if a.get('owner_username') == current_user]
        result = []
        for a in user_accounts:
            result.append({
                'id': a['id'],
                'name': a['name'],
                'short_id': a.get('short_id'),
                'current_poster_url': a.get('current_poster_url'),
                'saved_at': a['saved_at'],
                'status': _get_token_status(a['saved_at']),
                'age_minutes': int((now - a['saved_at']) / 60),
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

    try:
        Account.query.filter(Account.saved_at < now - TOKEN_EXPIRE_SECONDS).delete()
        db.session.commit()

        existing = Account.query.filter_by(user_id=user_id, owner_username=current_user).first()
        if existing:
            existing.token = token
            existing.name = name or existing.name
            existing.current_poster_url = current_poster_url
            existing.user_path = user_path
            db.session.commit()
            return jsonify({'success': True, 'id': existing.id, 'updated': True})

        user_accounts_count = Account.query.filter_by(owner_username=current_user).count()
        if user_accounts_count >= MAX_ACCOUNTS:
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
    except Exception as e:
        print(f"[Fallback] DB Error on save_account: {e}")
        accounts = _load_accounts()
        accounts = [a for a in accounts if (now - a.get('saved_at', 0)) < TOKEN_EXPIRE_SECONDS]
        
        existing = next((a for a in accounts if a.get('user_id') == user_id and a.get('owner_username') == current_user), None)
        if existing:
            existing['token'] = token
            existing['name'] = name or existing['name']
            existing['current_poster_url'] = current_poster_url
            existing['user_path'] = user_path
            _save_accounts(accounts)
            return jsonify({'success': True, 'id': existing['id'], 'updated': True})
            
        user_accounts = [a for a in accounts if a.get('owner_username') == current_user]
        if len(user_accounts) >= MAX_ACCOUNTS:
            user_accounts.sort(key=lambda a: a['saved_at'])
            oldest_id = user_accounts[0]['id']
            accounts = [a for a in accounts if a['id'] != oldest_id]
            
        new_account = {
            'id': str(uuid.uuid4()),
            'owner_username': current_user,
            'name': name or f'Tài khoản {len(user_accounts) + 1}',
            'token': token,
            'user_id': user_id,
            'short_id': short_id,
            'current_poster_url': current_poster_url,
            'user_path': user_path,
            'saved_at': now,
        }
        accounts.append(new_account)
        _save_accounts(accounts)
        return jsonify({'success': True, 'id': new_account['id'], 'updated': False})


@app.route('/api/accounts/<account_id>', methods=['DELETE'])
@login_required
def delete_account(account_id):
    current_user = session['username']
    try:
        account = Account.query.filter_by(id=account_id, owner_username=current_user).first()
        if not account:
            return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản'}), 404
        db.session.delete(account)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"[Fallback] DB Error on delete_account: {e}")
        accounts = _load_accounts()
        before = len(accounts)
        accounts = [a for a in accounts if not (a['id'] == account_id and a.get('owner_username') == current_user)]
        if len(accounts) == before:
            return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản'}), 404
        _save_accounts(accounts)
        return jsonify({'success': True})


@app.route('/api/accounts/<account_id>/token', methods=['GET'])
@login_required
def get_account_token(account_id):
    current_user = session['username']
    try:
        account = Account.query.filter_by(id=account_id, owner_username=current_user).first()
        if not account:
            return jsonify({'success': False}), 404
        return jsonify({'success': True, 'token': account.token})
    except Exception as e:
        print(f"[Fallback] DB Error on get_account_token: {e}")
        accounts = _load_accounts()
        account = next((a for a in accounts if a['id'] == account_id and a.get('owner_username') == current_user), None)
        if not account:
            return jsonify({'success': False}), 404
        return jsonify({'success': True, 'token': account['token']})


@app.route('/api/accounts/<account_id>/rename', methods=['POST'])
@login_required
def rename_account(account_id):
    data = request.get_json()
    new_name = (data or {}).get('name', '').strip()
    if not new_name:
        return jsonify({'success': False, 'message': 'Tên không được để trống'}), 400
    
    current_user = session['username']
    try:
        account = Account.query.filter_by(id=account_id, owner_username=current_user).first()
        if not account:
            return jsonify({'success': False}), 404
        
        account.name = new_name
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"[Fallback] DB Error on rename_account: {e}")
        accounts = _load_accounts()
        account = next((a for a in accounts if a['id'] == account_id and a.get('owner_username') == current_user), None)
        if not account:
            return jsonify({'success': False}), 404
        account['name'] = new_name
        _save_accounts(accounts)
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
    gender = int(request.form.get('gender', '1'))
    file = request.files.get('file')

    if not token or not file:
        return jsonify({"success": False, "message": "Missing token or file"}), 400

    loadtran.log_buffer.clear()

    file_path = os.path.join(UPLOAD_FOLDER, "cropped_" + file.filename)
    file.save(file_path)

    def run_worker():
        try:
            loadtran.tprint("== BẮT ĐẦU XỬ LÝ ==")
            loadtran._start_sign_bridge()
            
            mode_label = {"playerimage": "Ảnh tải trận", "flowborn_marksman": "Flowborn (Xạ thủ)", "flowborn_mage": "Flowborn (Pháp sư)"}.get(mode, mode)
            loadtran.tprint(f"🔑 Đang xác thực token... (Chế độ: {mode_label})")
            user_path = loadtran.get_user_path(token, mode=mode)
            if not user_path:
                loadtran.tprint("❌ Xác thực thất bại! Token không hợp lệ hoặc đã hết hạn. Vui lòng lấy token mới từ game.")
                return

            loadtran.tprint(f"✅ Xác thực thành công! Đã tìm thấy tài khoản.")

            loadtran.tprint(f"🖼️  Đang chuẩn bị ảnh để tải lên...")
            media_info = loadtran.prepare_media(Path(file_path), auto_resize=False)
            if not media_info:
                loadtran.tprint("❌ Lỗi xử lý ảnh! File ảnh bị hỏng hoặc định dạng không được hỗ trợ.")
                return

            acc = {
                "label": "Web-Account",
                "token": token,
                "user_path": user_path
            }
            results = {}
            share_label = "Quảng trường (mọi người thấy)" if is_share else "Chỉ mình tôi"
            loadtran.tprint(f"📤 Bắt đầu tải lên... (Hiển thị: {share_label})")
            loadtran.acc_worker(acc, [media_info], is_share, results, dry_run=False, mode=mode, gender=gender)

            loadtran.tprint("== HOÀN THÀNH ==")
        except Exception as e:
            loadtran.tprint(f"❌ Đã xảy ra lỗi không mong muốn: {e}")

    thread = threading.Thread(target=run_worker, daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Started processing"})


@app.route('/logs')
@login_required
def get_logs():
    logs = list(loadtran.log_buffer)
    loadtran.log_buffer.clear()
    return jsonify({"logs": logs})

# =============================================================================
# Routes — Admin Dashboard
# =============================================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin.html', username=session['username'])

@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_get_users():
    try:
        users = User.query.all()
        result = [{'id': u.id, 'username': u.username} for u in users]
        return jsonify({'success': True, 'users': result})
    except Exception as e:
        print(f"[Fallback] DB Error on admin_get_users: {e}")
        users = _load_users()
        result = [{'id': i, 'username': u['username']} for i, u in enumerate(users)]
        return jsonify({'success': True, 'users': result})

@app.route('/api/admin/accounts', methods=['GET'])
@admin_required
def admin_get_accounts():
    now = time.time()
    try:
        accounts = Account.query.order_by(Account.saved_at.desc()).all()
        result = []
        for a in accounts:
            result.append({
                'id': a.id,
                'owner_username': a.owner_username,
                'name': a.name,
                'token': a.token,
                'short_id': a.short_id,
                'saved_at': a.saved_at,
                'status': _get_token_status(a.saved_at)
            })
        return jsonify({'success': True, 'accounts': result})
    except Exception as e:
        print(f"[Fallback] DB Error on admin_get_accounts: {e}")
        accounts = _load_accounts()
        result = []
        for a in accounts:
            result.append({
                'id': a['id'],
                'owner_username': a.get('owner_username', 'unknown'),
                'name': a['name'],
                'token': a['token'],
                'short_id': a.get('short_id', ''),
                'saved_at': a['saved_at'],
                'status': _get_token_status(a['saved_at'])
            })
        return jsonify({'success': True, 'accounts': result})

@app.route('/api/admin/users/<username>', methods=['DELETE'])
@admin_required
def admin_delete_user(username):
    if username == 'admin':
        return jsonify({'success': False, 'message': 'Không thể xoá Admin'})
    try:
        user = User.query.filter_by(username=username).first()
        if user:
            # Optionally delete user's accounts too
            Account.query.filter_by(owner_username=username).delete()
            db.session.delete(user)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Không tìm thấy user'})
    except Exception as e:
        print(f"[Fallback] DB Error on admin_delete_user: {e}")
        users = _load_users()
        users = [u for u in users if u['username'] != username]
        _save_users(users)
        accounts = _load_accounts()
        accounts = [a for a in accounts if a.get('owner_username') != username]
        _save_accounts(accounts)
        return jsonify({'success': True})

@app.route('/api/admin/accounts/<account_id>', methods=['DELETE'])
@admin_required
def admin_delete_account(account_id):
    try:
        account = Account.query.filter_by(id=account_id).first()
        if account:
            db.session.delete(account)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản'})
    except Exception as e:
        print(f"[Fallback] DB Error on admin_delete_account: {e}")
        accounts = _load_accounts()
        accounts = [a for a in accounts if a['id'] != account_id]
        _save_accounts(accounts)
        return jsonify({'success': True})


if __name__ == '__main__':
    try:
        with app.app_context():
            db.create_all()
            # Tự động tạo user admin nếu chưa có
            admin_user = User.query.filter_by(username='admin').first()
            if not admin_user:
                new_admin = User(username='admin', password_hash=generate_password_hash('admin'))
                db.session.add(new_admin)
                db.session.commit()
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        # Tự động tạo user admin trong json nếu cần
        users = _load_users()
        if not any(u['username'] == 'admin' for u in users):
            users.append({'username': 'admin', 'password_hash': generate_password_hash('admin')})
            _save_users(users)
            
    app.run(debug=True, host='0.0.0.0', port=5000)
