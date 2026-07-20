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
