import os
import threading
from flask import Flask, render_template, request, jsonify
import loadtran
from pathlib import Path

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

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
            loadtran.tprint("== BAT DAU XU LY ==")
            # 1. Start sign bridge if needed
            loadtran._start_sign_bridge()
            
            # 2. Get user_path
            loadtran.tprint(f"Dang lay user_path (mode={mode})...")
            user_path = loadtran.get_user_path(token, mode=mode)
            if not user_path:
                loadtran.tprint("Khong lay duoc user_path tu server (403/Loi token).")
                return

            loadtran.tprint(f"user_path: {user_path}")

            # 3. Prepare media
            loadtran.tprint(f"Xu ly media: {file_path}")
            media_info = loadtran.prepare_media(Path(file_path), auto_resize=False) # Already cropped frontend
            if not media_info:
                loadtran.tprint("Loi xu ly media")
                return

            # 4. Run worker
            acc = {
                "label": "Web-Account",
                "token": token,
                "user_path": user_path
            }
            results = {}
            loadtran.tprint(f"Bat dau upload (Quang truong: {is_share})...")
            loadtran.acc_worker(acc, [media_info], is_share, results, dry_run=False, mode=mode)
            
            loadtran.tprint("== HOAN THANH ==")
        except Exception as e:
            loadtran.tprint(f"Loi Exception: {e}")

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
