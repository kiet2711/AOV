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
   - `Msdk-Itopencodeparam`: Token tĩnh 256 ký tự lấy từ HAR/URL (luôn chạy qua hàm `clean_token` để lọc URL/query rác).
   - `Encodeparam`: Chữ ký động sinh từ `sign_bridge.js` (Tencent Chaos VM `__TCSJ__.getEncodeParam()`).
2. Nếu gặp lỗi `-1991: empty repeat check param` $\rightarrow$ Thiếu header `Encodeparam` (chưa bật hoặc không kết nối được Sign Bridge ở cổng 19876).
3. Nếu gặp lỗi `-5001: auth failed` $\rightarrow$ `Encodeparam` hết hạn/sai hoặc token không hợp lệ / hết hạn trên Garena.
4. Đảm bảo Sign Bridge được khởi động (`node sign_bridge.js 19876` hoặc qua hàm `_start_sign_bridge()`). Trên cloud (Render/Linux), `nodejs-bin` trong `requirements.txt` đảm bảo Node.js luôn có sẵn.

---

## Cẩm Nang & Lưu Ý Đặc Biệt Khi Đổi Ảnh Flowborn (Cực Kỳ Quan Trọng)

### 1. Khác Biệt Giữa Playerimage Và Flowborn
- **Playerimage (Ảnh tải trận thường)**:
  - File prefix: `0/1/{posterId}.png`
  - COS Path Partition: `/1/704/<hash>/`
  - Scene COS: `PlayerimagePoster`
  - Save URL: `/api/game/poster/playerimage/saveposter`
- **Flowborn (Tướng 2D / Nguyên Tố)**:
  - Xạ thủ (Marksman): `mainJob: 5`, File prefix: `5/1/{posterId}.png`
  - Pháp sư (Mage): `mainJob: 4`, File prefix: `4/1/{posterId}.png`
  - COS Path Partition: `/2/704/<hash>/` (Lưu ý partition là `/2/`, không phải `/1/`)
  - Scene COS: `FlowbornPoster`
  - Save URL: `/api/game/poster/flowborn/saveposter`

### 2. Bảng Tham Số BaseInfo & Background Chuẩn Cho Flowborn
- **Nền mặc định (`bg`)**:
  - `id: "22"`, `picUrl: "https://kg-camp.mobagarena.com/manage/flowborn_official/IDqWId2J.png"` *(TUYỆT ĐỐI KHÔNG dùng ID cũ `"30"` vì server sẽ từ chối).*
- **Nhân vật Xạ thủ (`mainJob: 5`)**:
  - Nam (`gender: 1`): `id: "31"`, `picUrl: ".../QQD3ebSX.png"`
  - Nữ (`gender: 2`): `id: "32"`, `picUrl: ".../Pd7zTH2f.png"`
- **Nhân vật Pháp sư (`mainJob: 4`)**:
  - Nam (`gender: 1`): `id: "61"`, `picUrl: ".../epf8os8a.png"`
  - Nữ (`gender: 2`): `id: "62"`, `picUrl: ".../5fXAjyuq.png"`

### 3. Các Lỗi Thường Gặp Của Flowborn & Cách Khắc Phục (Tra Cứu Nhanh)
- **Lỗi `-1993: player game data not ready`**:
  - *Nguyên nhân:* Tài khoản in-game của người dùng chưa tạo/chọn nhân vật giới tính đó (ví dụ tài khoản chỉ mới tạo Xạ thủ Nam trong game nhưng web lại gửi yêu cầu áp dụng Xạ thủ Nữ).
  - *Giải pháp triệt để:* Trước khi save, gọi `POST /api/game/poster/flowborn/geteditorconfig` với `{"mainJob": mainJob}` để lấy danh sách `baseList` tài khoản đang có. Nếu không khớp giới tính yêu cầu, tự động fallback về `baseList[0]` của tài khoản.
- **Lỗi `-1997: invalid main job`**:
  - *Nguyên nhân:* Gửi sai tên trường body API (ví dụ gửi `heroJob` thay vì `mainJob`).
- **Lỗi `51: invalid GetEditorResourceReq.Page`**:
  - *Nguyên nhân:* Khi gọi `geteditorresource`, thiếu các trường phân trang `{"mainJob": 5, "page": 1, "pageSize": 50, "type": 1}`.
- **Lỗi `unavailableResources`**:
  - *Nguyên nhân:* Dùng `bg_id` hoặc `baseInfo.id` cũ đã bị game đóng/thay thế. Luôn cập nhật theo danh sách ở mục 2.

