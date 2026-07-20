import os
import json
import time
import uuid
import threading
from flask import Flask, render_template, request, jsonify
import loadtran
from pathlib import Path

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts.json')
MAX_ACCOUNTS = 5
TOKEN_EXPIRE_SECONDS = 4 * 3600   # 4 tieng


# =============================================================================
# Account storage helpers
# =============================================================================

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

def _cleanup_expired(accounts):
    now = time.time()
    return [a for a in accounts if (now - a.get('saved_at', 0)) < TOKEN_EXPIRE_SECONDS]

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
def index():
    return render_template('index.html')


# =============================================================================
# Routes — Account Management API
# =============================================================================

@app.route('/api/verify_token', methods=['POST'])
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
def get_accounts():
    accounts = _load_accounts()
    accounts = _cleanup_expired(accounts)
    _save_accounts(accounts)

    now = time.time()
    result = []
    for a in accounts:
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

    accounts = _load_accounts()
    accounts = _cleanup_expired(accounts)

    # Neu da co account voi cung user_id -> cap nhat
    existing = next((a for a in accounts if a.get('user_id') == user_id), None)
    if existing:
        existing['token'] = token
        existing['name'] = name or existing['name']
        existing['current_poster_url'] = current_poster_url
        existing['user_path'] = user_path
        existing['saved_at'] = time.time()
        _save_accounts(accounts)
        return jsonify({'success': True, 'id': existing['id'], 'updated': True})

    # Kiem tra gioi han
    if len(accounts) >= MAX_ACCOUNTS:
        # Xoa account cu nhat
        accounts.sort(key=lambda a: a['saved_at'])
        accounts.pop(0)

    new_account = {
        'id': str(uuid.uuid4()),
        'name': name or f'Tài khoản {len(accounts) + 1}',
        'token': token,
        'user_id': user_id,
        'short_id': short_id,
        'current_poster_url': current_poster_url,
        'user_path': user_path,
        'saved_at': time.time(),
    }
    accounts.append(new_account)
    _save_accounts(accounts)
    return jsonify({'success': True, 'id': new_account['id'], 'updated': False})


@app.route('/api/accounts/<account_id>', methods=['DELETE'])
def delete_account(account_id):
    accounts = _load_accounts()
    before = len(accounts)
    accounts = [a for a in accounts if a['id'] != account_id]
    if len(accounts) == before:
        return jsonify({'success': False, 'message': 'Không tìm thấy tài khoản'}), 404
    _save_accounts(accounts)
    return jsonify({'success': True})


@app.route('/api/accounts/<account_id>/token', methods=['GET'])
def get_account_token(account_id):
    """Tra ve token de dien vao o nhap (khong lo thong tin toan bo)"""
    accounts = _load_accounts()
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False}), 404
    return jsonify({'success': True, 'token': account['token']})


@app.route('/api/accounts/<account_id>/rename', methods=['POST'])
def rename_account(account_id):
    data = request.get_json()
    new_name = (data or {}).get('name', '').strip()
    if not new_name:
        return jsonify({'success': False, 'message': 'Tên không được để trống'}), 400
    accounts = _load_accounts()
    account = next((a for a in accounts if a['id'] == account_id), None)
    if not account:
        return jsonify({'success': False}), 404
    account['name'] = new_name
    _save_accounts(accounts)
    return jsonify({'success': True})


# =============================================================================
# Routes — Upload & Logs
# =============================================================================

@app.route('/upload', methods=['POST'])
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
def get_logs():
    logs = list(loadtran.log_buffer)
    loadtran.log_buffer.clear()
    return jsonify({"logs": logs})


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
