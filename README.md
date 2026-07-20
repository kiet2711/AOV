# 🎮 AOV Load Tran - Công cụ thay ảnh tải trận AOV

> **Web:** https://aov-pamo.onrender.com

Công cụ web giúp bạn dễ dàng thay **ảnh tải trận** (Load Screen) và **Flowborn** trong game Liên Quân Mobile (AOV/KGVN) chỉ qua trình duyệt, không cần cài đặt phần mềm.

---

## 🚀 Tính năng

| Tính năng | Mô tả |
|---|---|
| 🖼️ Ảnh tải trận | Thay ảnh hiển thị khi đang vào trận |
| ⚔️ Flowborn (Xạ thủ) | Thay ảnh Flowborn nhân vật vai Xạ thủ |
| 🔮 Flowborn (Pháp sư) | Thay ảnh Flowborn nhân vật vai Pháp sư |
| ✂️ Crop ảnh trực tiếp | Cắt ảnh đúng tỷ lệ 1080×1701 ngay trên web, không cần phần mềm |
| 🌐 Quảng trường | Tùy chọn hiển thị ảnh ở khu vực Quảng trường (mọi người thấy) |
| 📊 Log tiến trình | Hiển thị từng bước xử lý theo thời gian thực |
| 🔒 Sign Bridge | Tự động ký xác thực động, tránh lỗi -5001 |

---

## 📋 Hướng dẫn sử dụng

### Bước 1 — Lấy Token từ game

Token là mã xác thực tài khoản của bạn. Cách lấy:

1. Mở **Liên Quân Mobile** trên điện thoại
2. Vào **Camp** (khu vực cộng đồng trong game)
3. Dùng công cụ chặn traffic (HTTP Toolkit, Fiddler, mitmproxy...) để bắt request
4. Tìm request đến `kgvn-api.mobagarena.com` và sao chép giá trị header **`msdk-itopencodeparam`**

> ⚠️ Token có thời hạn ngắn (thường vài giờ). Nếu gặp lỗi, hãy lấy token mới.

### Bước 2 — Chọn ảnh và cắt

1. Nhấn **"Chọn ảnh"** để tải ảnh lên
2. Dùng công cụ crop để chọn vùng muốn hiển thị (tỷ lệ tự động 1080×1701)
3. Kéo / thu phóng để căn chỉnh ảnh theo ý muốn

### Bước 3 — Cài đặt và tải lên

| Cài đặt | Tùy chọn |
|---|---|
| **Chế độ** | Ảnh tải trận / Flowborn Xạ thủ / Flowborn Pháp sư |
| **Hiển thị** | ☑️ Quảng trường = mọi người thấy ảnh của bạn |

4. Dán **Token** vào ô nhập
5. Nhấn **"Tải lên & Xử lý"**
6. Theo dõi tiến trình trong khung log bên dưới

---

## 📊 Các bước xử lý (Log tiến trình)

Khi nhấn tải lên, bạn sẽ thấy các bước sau trong log:

```
== BẮT ĐẦU XỬ LÝ ==
🔑 Đang xác thực token... (Chế độ: Ảnh tải trận)
✅ Xác thực thành công! Đã tìm thấy tài khoản.
🖼️  Đang chuẩn bị ảnh để tải lên...
📤 Bắt đầu tải lên... (Hiển thị: Chỉ mình tôi)
🔍 Đang lấy thông tin khung ảnh hiện tại của bạn...
✅ Lấy thông tin khung ảnh thành công!
🚀 Chuẩn bị tải lên 1 ảnh...
Ảnh #01 ⏳ Đang tạo slot poster trên server...
Ảnh #01 ✅ Tạo poster thành công (ID: 12345678)
Ảnh #01 ☁️  Đang tải ảnh lên server (245 KB)...
Ảnh #01 ✅ Tải ảnh lên thành công!
Ảnh #01 💾 Đang lưu thiết lập khung ảnh...
Ảnh #01 ✅ Lưu khung ảnh thành công!
Ảnh #01 🔄 Đang áp dụng ảnh tải trận vào tài khoản...
Ảnh #01 🎉 THÀNH CÔNG! Ảnh tải trận đã được cập nhật! [Ảnh tĩnh]
📊 Kết quả: 1 thành công / 0 thất bại
== HOÀN THÀNH ==
```

> ✅ Sau khi thấy **HOÀN THÀNH**, mở game và vào trận để xem ảnh mới!

---

## ❗ Các lỗi thường gặp và cách xử lý

### 🔴 Lỗi Token

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| `❌ Xác thực thất bại! Token không hợp lệ hoặc đã hết hạn.` | Token sai hoặc hết hạn | Lấy lại token mới từ game |
| `❌ Đã xảy ra lỗi không mong muốn: 403` | Token bị từ chối | Thử lấy token trong khoảng thời gian gần nhất |

> 💡 Token thường hết hạn sau **2–4 giờ**. Hãy lấy token khi vừa mở game xong.

---

### 🔴 Lỗi Upload ảnh

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| `❌ Không lấy được quyền upload. Server từ chối cấp phép.` | Server game lỗi tạm thời hoặc token yếu | Thử lại sau vài phút hoặc lấy token mới |
| `❌ Tải ảnh lên thất bại! Kiểm tra kết nối mạng.` | Mạng không ổn định hoặc server COS lỗi | Kiểm tra kết nối internet, thử lại |
| `❌ Tạo poster thất bại: frequency limited` | Gửi quá nhiều request liên tiếp | Đợi 30–60 giây rồi thử lại |
| `⚠️  GIF động thất bại, dùng ảnh tĩnh thay thế.` | GIF quá lớn hoặc server không nhận | Tool tự động dùng ảnh tĩnh thay thế (vẫn OK) |

---

### 🔴 Lỗi Áp dụng poster

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| `❌ Áp dụng thất bại: -1999` | Quá nhiều request, bị giới hạn tần suất | Đợi 1–2 phút rồi thử lại |
| `❌ Áp dụng thất bại: -5001` | Lỗi xác thực động (Sign Bridge chưa chạy) | Hệ thống tự xử lý; nếu vẫn lỗi, thử lấy token mới |
| `⚠️  Lưu khung ảnh không thuận lợi` | Lỗi nhỏ khi lưu cấu hình, không ảnh hưởng kết quả | Bỏ qua, ảnh vẫn được áp dụng bình thường |

---

### 🔴 Lỗi File ảnh

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| `❌ Lỗi xử lý ảnh! File ảnh bị hỏng hoặc định dạng không được hỗ trợ.` | File lỗi hoặc sai định dạng | Dùng file JPG, PNG, hoặc WEBP hợp lệ |
| Không thấy crop tool sau khi chọn ảnh | File quá lớn hoặc định dạng lạ | Chuyển sang JPG/PNG trước khi upload |

**Định dạng hỗ trợ:** `JPG` · `PNG` · `WEBP` · `GIF` · `MP4`

---

### 🔴 Lỗi khác

| Thông báo | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Lỗi kết nối server` | Server web bị ngắt hoặc quá tải | Thử lại sau vài giây |
| `❌ Đã xảy ra lỗi không mong muốn: ...` | Lỗi không xác định | Chụp màn hình log và gửi cho admin |
| Màn hình log trống, không có gì | Kết nối WebSocket bị ngắt | Tải lại trang và thử lại |

---

## 🛠️ Cài đặt & Chạy local (cho developer)

### Yêu cầu

- Python 3.8+
- Node.js (tùy chọn, dùng cho Sign Bridge)

### Cài đặt thư viện

```bash
pip install -r requirements.txt
```

### Chạy server

```bash
python app.py
```

Sau đó mở trình duyệt tại: **http://localhost:5000**

### Sign Bridge (tùy chọn, khuyến khích)

Sign Bridge giúp tự động tạo mã xác thực động, tránh lỗi `-5001`:

```bash
# Cách 1: Dùng Node.js
node sign_bridge.js

# Cách 2: Dùng Python
python sign_bridge_py.py
```

> Sign Bridge chạy nền ở port `19876`. Tool sẽ tự kết nối khi cần.

---

## 📁 Cấu trúc project

```
AOV/
├── app.py              # Flask web server chính
├── loadtran.py         # Logic xử lý upload ảnh
├── sign_bridge.js      # Sign Bridge (Node.js)
├── sign_bridge_py.py   # Sign Bridge (Python)
├── requirements.txt    # Thư viện Python cần thiết
├── static/
│   ├── script.js       # Frontend JavaScript
│   └── style.css       # Giao diện CSS
├── templates/
│   └── index.html      # Trang web chính
└── uploads/            # Thư mục lưu ảnh tạm (tự tạo)
```

---

## 💡 Mẹo sử dụng

- **Ảnh đẹp nhất:** Dùng ảnh dọc tỷ lệ 9:14 (ví dụ 1080×1680) để crop ít nhất
- **Token nhanh nhất:** Mở Camp trong game → bắt ngay request đầu tiên
- **Tránh lỗi -1999:** Không spam nhấn tải lên liên tục, đợi log hiển thị HOÀN THÀNH rồi mới thử lần tiếp theo
- **Sau khi thành công:** Cần khởi động lại game hoặc vào trận mới để thấy ảnh mới

---

*Tool được phát triển cho cộng đồng Liên Quân Mobile VN. Sử dụng có trách nhiệm.*
