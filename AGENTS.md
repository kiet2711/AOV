# Repository Guidelines & AI Context

## Overview
Dự án này là công cụ đổi ảnh tải trận (Loadtran / Playerimage Poster & Flowborn Poster) cho game **Liên Quân Mobile (Arena of Valor - Garena VN)**.

## Tài Liệu Tham Khảo Nhanh Cho AI (Crucial Knowledge)
- **Tài liệu toàn diện về API & giao thức**: Đọc file [API_REFERENCE.md](file:///d:/AOV/API_REFERENCE.md).
- **Core backend**: [loadtran.py](file:///d:/AOV/loadtran.py) (CLI & logic xử lý API).
- **Web backend**: [app.py](file:///d:/AOV/app.py) (Flask web interface & API).
- **Sign Bridge**: [sign_bridge.js](file:///d:/AOV/sign_bridge.js) & [camp_security.js](file:///d:/AOV/camp_security.js) (Chạy máy ảo Tencent Chaos VM trên cổng 19876 để sinh chữ ký `Encodeparam`).

## Các Quy Tắc Quan Trọng Cần Ghi Nhớ
1. Mọi request tới `kgvn-api.mobagarena.com` (ngoại trừ `/api/user/game/getcredential`) **bắt buộc** phải có 2 headers xác thực:
   - `Msdk-Itopencodeparam`: Token tĩnh 256 ký tự lấy từ HAR/URL.
   - `Encodeparam`: Chữ ký động sinh từ `sign_bridge.js` (Tencent Chaos VM `__TCSJ__.getEncodeParam()`).
2. Nếu gặp lỗi `-1991: empty repeat check param` $\rightarrow$ Thiếu header `Encodeparam`.
3. Nếu gặp lỗi `-5001: auth failed` $\rightarrow$ `Encodeparam` hết hạn/sai hoặc token không hợp lệ.
4. Đảm bảo Sign Bridge được khởi động (`node sign_bridge.js 19876`) trước khi thực hiện các lệnh gọi API.
