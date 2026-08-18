# AOV H5 Camp — Tài Liệu Kỹ Thuật & Cấu Trúc Giao Thức (API Protocol Reference)

> Tài liệu này lưu trữ toàn bộ cơ chế hoạt động, các header bắt buộc, endpoint API, cấu trúc payload và các điểm nhạy cảm hay bị thay đổi khi game Liên Quân Mobile (Garena/Tencent) cập nhật. Dành cho các phiên làm việc và AI tiếp theo đọc để nắm bắt ngay lập tức.

---

## 1. Cơ Chế Xác Thực & Chữ Ký Bảo Mật (Authentication Architecture)

Hệ thống H5 Camp của Liên Quân (`kgvn-api.mobagarena.com`) sử dụng cơ chế bảo mật 2 lớp:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Token tĩnh: Msdk-Itopencodeparam (256 hex chars từ HAR) │
└──────────────────────────────┬──────────────────────────────┘
                               │
            POST /api/user/game/getcredential
                               ▼
        Nhận { encryption, roleId } từ Server
                               │
      Nạp vào __TCSJ__.setLoginRes(encryption, roleId)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Chữ ký động: Encodeparam = __TCSJ__.getEncodeParam(role) │
└─────────────────────────────────────────────────────────────┘
```

### Các Headers Bắt Buộc Trong Mọi Request API

| Header | Giá trị / Ý nghĩa | Ghi chú |
| :--- | :--- | :--- |
| `Camp-Source` | `AOV-CAMP` | Cố định |
| `Camp-Authtype`| `msdk` | Cố định |
| `Msdk-Gameid` | `1137` | Mã game Liên Quân VN |
| `Aov-Region` | `1137` | Khu vực VN |
| `Aov-Language` | `VN` | Ngôn ngữ |
| `Msdk-Channelid`| `10` | Kênh đăng nhập |
| `Msdk-Os` | `2` (iOS) hoặc `1` (Android) | Hệ điều hành client |
| `logicworldid` | `1011` | Server ID |
| `areaid` | `1` | Area ID |
| `Origin` | `https://kgvn-camp.mobagarena.com` | Bắt buộc CORS |
| `Referer` | `https://kgvn-camp.mobagarena.com/` | Bắt buộc CORS |
| `Msdk-Itopencodeparam` | Chuỗi 256 ký tự Hex (Token tài khoản) | **Bắt buộc** |
| `Encodeparam` | Base64 sinh động qua `__TCSJ__.getEncodeParam()` | **Bắt buộc** (bỏ qua ở bước `getcredential`) |

---

## 2. Bảng Mã Lỗi Thường Gặp (Error Codes & Troubleshooting)

| Mã lỗi | Thông báo từ Server | Nguyên nhân | Cách xử lý |
| :--- | :--- | :--- | :--- |
| `-1991` | `empty repeat check param` | Thiếu header `Encodeparam` trong request | Đảm bảo Sign Bridge đang chạy và gắn header `Encodeparam` |
| `-5001` | `auth failed` | `Encodeparam` bị cũ, sai hoặc token hết hạn | Khởi tạo lại phiên qua `/api/user/game/getcredential` |
| `1` | Lỗi chung / Rate limit | Gửi request quá nhanh | Đặt độ trễ (delay 3.6s) và retry lại |
| `403 Forbidden` | Server từ chối | Thiếu header hoặc chữ ký không khớp | Kiểm tra lại toàn bộ header bắt buộc và token |

---

## 3. Danh Sách Endpoint Quan Trọng

### A. Handshake & Thông Tin Người Dùng
1. **Lấy khóa mã hóa (Handshake):**
   - **URL:** `POST https://kgvn-api.mobagarena.com/api/user/game/getcredential`
   - **Headers:** Chỉ cần `Msdk-Itopencodeparam` (không cần `Encodeparam`).
   - **Payload:** `{}`
   - **Response:** `{"code":0, "data": {"encryption": "...", "roleId": "..."}}`

2. **Lấy thông tin nhân vật in-game:**
   - **URL:** `POST https://kgvn-api.mobagarena.com/api/user/game/getselfuserinfo`
   - **Payload:** `{}`
   - **Response:** `data.role` chứa `characName`, `headUrl`, `campRoleid`, `userGameInfo.roleJobName`, `rankGradeStar`.

---

### B. Quy Trình Đổi Ảnh Tải Trận (Poster Lifecycle)

1. **Bước 1: Tạo slot poster trên server**
   - **Playerimage (Ảnh tải trận thường):** `POST /api/game/poster/playerimage/createposter`
   - **Flowborn (Xạ thủ / Pháp sư):** `POST /api/game/poster/flowborn/createposter`
   - **Payload:** `{}`
   - **Response:** `{"code":0, "data": {"posterId": "8804815"}}`

2. **Bước 2: Lấy quyền upload Tencent COS Cloud (COS Credentials)**
   - **URL:** `POST /api/game/poster/getcoscredential`
   - **Payload:**
     - Playerimage: `{"scene": "PlayerimagePoster", "fileName": "0/1/<posterId>.png"}`
     - Large image: `{"scene": "PlayerimagePoster", "fileName": "0/1/<posterId>_large.png"}`
     - Flowborn Xạ thủ: `{"scene": "FlowbornPoster", "fileName": "5/1/<posterId>.png"}`
     - Flowborn Pháp sư: `{"scene": "FlowbornPoster", "fileName": "4/1/<posterId>.png"}`
   - **Response:** Cung cấp `tmpSecretId`, `tmpSecretKey`, `token`, `path` (dạng `/1/704/<hash>/0/1/<posterId>.png`).

3. **Bước 3: Upload ảnh trực tiếp lên COS Bucket**
   - **Host:** `aovcamp-h5-ugc-1254801811.cos.ap-singapore.myqcloud.com`
   - **Method:** `PUT https://{Host}{path}`
   - **Headers:** `Authorization` (HMAC-SHA1 Q-Sign), `x-cos-security-token: creds.token`, `Content-Type: image/png`.

4. **Bước 4: Áp dụng Poster vào tài khoản (`saveposter`)**
   - **Playerimage:**
     - **URL:** `POST /api/game/poster/playerimage/saveposter`
     - **Payload:**
       ```json
       {
         "posterId": "<posterId>",
         "isApply": true,
         "isShare": true,
         "picUrl": "https://kg-camp-ugc.mobagarena.com/1/704/<hash>/",
         "picInfo": {
           "bg": {
             "id": "21",
             "picUrl": "https://kg-camp.mobagarena.com/manage/playerimage_official/iDzT817p.png",
             "source": 1,
             "width": 320,
             "height": 503.98877550239234,
             "posX": 0,
             "posY": 0
           },
           "stickerList": []
         }
       }
       ```
   - **Flowborn:**
     - **URL:** `POST /api/game/poster/flowborn/saveposter`
     - **Payload:**
       ```json
       {
         "posterId": "<posterId>",
         "isApply": true,
         "isShare": true,
         "mainJob": 5,
         "picInfo": {
           "bg": {
             "id": "22",
             "picUrl": "https://kg-camp.mobagarena.com/manage/flowborn_official/IDqWId2J.png"
           },
           "baseInfo": {
             "id": "31",
             "gender": 1,
             "mainJob": 5,
             "picUrl": "https://kg-camp.mobagarena.com/manage/flowborn_official/QQD3ebSX.png",
             "skinColor": 1
           },
           "stickerList": []
         },
         "picUrl": "https://kg-camp-ugc.mobagarena.com/2/704/<hash>/"
       }
       ```
     - **Bảng tham số Base & BG Flowborn chuẩn**:
       - **BG mặc định**: `id: "22"`, URL: `https://kg-camp.mobagarena.com/manage/flowborn_official/IDqWId2J.png`
       - **Xạ thủ Nam (`mainJob: 5, gender: 1`)**: `baseInfo.id: "31"`, URL: `.../QQD3ebSX.png`
       - **Xạ thủ Nữ (`mainJob: 5, gender: 2`)**: `baseInfo.id: "32"`, URL: `.../Pd7zTH2f.png`
       - **Pháp sư Nam (`mainJob: 4, gender: 1`)**: `baseInfo.id: "61"`, URL: `.../epf8os8a.png`
       - **Pháp sư Nữ (`mainJob: 4, gender: 2`)**: `baseInfo.id: "62"`, URL: `.../5fXAjyuq.png`
       - *(Tool tự động gọi `/api/game/poster/flowborn/geteditorconfig` để lấy `baseList` hợp lệ theo tài khoản, tránh lỗi `-1993: player game data not ready`)*


---

## 4. Cấu Trúc Sign Bridge (`sign_bridge.js` + `camp_security.js`)

- **Vị trí:** `sign_bridge.js` và `camp_security.js` nằm cùng thư mục gốc của project.
- **Port:** `127.0.0.1:19876` (tự động khởi động nếu chưa chạy).
- **Cơ chế:** Node.js nạp máy ảo bảo mật **Tencent Chaos VM** (`__TENCENT_CHAOS_VM`), cung cấp đối tượng `global.__TCSJ__` với các hàm:
  - `setLoginRes(encryption, roleId)`: Nạp thông tin đăng nhập từ `getcredential`.
  - `getEncodeParam(roleId)`: Sinh chuỗi chữ ký `Encodeparam` động theo thời gian thực.
- **Các API của Bridge:**
  - `GET /health` $\rightarrow$ Kiểm tra trạng thái bridge (`200 OK`).
  - `POST /init_session` $\rightarrow$ Input `{ token }`, tự động handshake và cache session.
  - `POST /get_encodeparam` $\rightarrow$ Input `{ token, roleId }`, trả về `{ encodeparam }`.

---

## 5. Khi Game Có Bản Cập Nhật Mới Thì Cần Kiểm Tra Gì?

Nếu một ngày game tiếp tục cập nhật và tool bị lỗi:
1. **Kiểm tra bản H5 mới:**
   - Truy cập URL gốc: `https://kgvn-camp.mobagarena.com/app/player-poster`.
   - Tìm các thẻ `<script src="...">`.
   - Kiểm tra xem file bảo mật `camp-security-oversea.x.x.x.js` có đổi sang phiên bản mới hơn không.
   - Nếu có file mới, tải về và cập nhật nội dung vào `camp_security.js`.
2. **Kiểm tra file HAR mới từ người dùng:**
   - Tìm request `POST /api/game/poster/playerimage/saveposter` hoặc `createposter`.
   - Đối chiếu danh sách headers và body JSON xem có thêm trường/field nào mới không.
