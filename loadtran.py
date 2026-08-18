#!/usr/bin/env python3
"""
KGVN Load Tran v3.2  --  by hienmods & Antigravity
Mod anh load tran (playerimage) -- Multi-account, Sign Bridge, Auto Resize
Ho tro: JPG . PNG . WEBP . GIF . MP4
"""

import argparse
import hashlib
import hmac as hmac_lib
import http.client
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path


try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("\033[91m[!] Thieu: pip install requests\033[0m")
    sys.exit(1)

try:
    from PIL import Image as _PIL_Image
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

# =============================================================================
# ANSI COLORS
# =============================================================================

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    PURPLE = "\033[95m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    GRAY   = "\033[90m"

def ok(msg):   return "{}OK   {}{}".format(C.GREEN,  msg, C.RESET)
def err(msg):  return "{}ERR  {}{}".format(C.RED,    msg, C.RESET)
def warn(msg): return "{}WRN  {}{}".format(C.YELLOW, msg, C.RESET)
def info(msg): return "{}  >  {}{}".format(C.CYAN,   msg, C.RESET)
def dim(msg):  return "{}{}{}".format(C.GRAY, msg, C.RESET)
def bold(msg): return "{}{}{}".format(C.BOLD, msg, C.RESET)

def sep(width=62, char="-", color=C.GRAY):
    return "{}{}{}".format(color, char*width, C.RESET)

# =============================================================================
# CAU HINH
# =============================================================================

COS_BUCKET   = "aovcamp-h5-ugc-1254801811"
COS_REGION   = "ap-singapore"
COS_HOST     = "{}.cos.{}.myqcloud.com".format(COS_BUCKET, COS_REGION)
CDN_BASE     = "https://kg-camp.mobagarena.com"
UGC_CDN_BASE = "https://kg-camp-ugc.mobagarena.com"
API_BASE     = "https://kgvn-api.mobagarena.com"
IMAGE_EXTS   = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4"}
MAX_MEDIA_PER_ACC = 6

# Kich thuoc poster chuan
POSTER_W = 1080
POSTER_H = 1701

# Playerimage constants
PI_BG_ID      = "21"
PI_BG_PICURL  = CDN_BASE + "/manage/playerimage_official/iDzT817p.png"
PI_BG_W       = 320
PI_BG_H       = 503.98877550239234

# Timing
POSTER_STAGGER = 3.6
ROUND_DELAY    = 3.0
ACC_STAGGER    = 2.0

# Sign Bridge
SIGN_BRIDGE_PORT    = 19876
SIGN_BRIDGE_JS      = "sign_bridge.js"
SIGN_BRIDGE_TIMEOUT = 8.0

FIXED_HEADERS = {
    "Camp-Source":        "AOV-CAMP",
    "Msdk-Gameid":        "1137",
    "Camp-Authtype":      "msdk",
    "areaid":             "1",
    "Msdk-Os":            "2",
    "logicworldid":       "1011",
    "Aov-Language":       "VN",
    "Msdk-Channelid":     "10",
    "Aov-Region":         "1137",
    "Origin":             "https://kgvn-camp.mobagarena.com",
    "Referer":            "https://kgvn-camp.mobagarena.com/",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Mobile/15E148 MSDK/5.36.000.9136 mQQAppId/1105779914 "
        "mWXAppId/wx7a814e3ceeda8320 mGameId/1137 MSDKDeviceModel/955BC6E3-8E62-467E-8422-329F8582B09A"
    ),
    "Accept":             "application/json, text/plain, */*",
    "Accept-Language":    "vi-VN,vi;q=0.9",
    "Accept-Encoding":    "gzip, deflate, br",
}

log_buffer = []

def strip_ansi(text):
    return re.sub(r'\033\[[0-9;]*m', '', text)

_print_lock = threading.Lock()
def tprint(msg):
    with _print_lock:
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            try:
                print(msg.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding), flush=True)
            except Exception:
                print(msg.encode('ascii', errors='replace').decode('ascii'), flush=True)
        log_buffer.append(strip_ansi(msg))

# =============================================================================
# SIGN BRIDGE -- Dynamic encodeparam (Tencent Chaos VM)
# =============================================================================

_sign_bridge_proc  = None
_sign_bridge_ok    = None
_sign_bridge_lock  = threading.Lock()

def _find_sign_bridge():
    candidates = [
        Path(SIGN_BRIDGE_JS),
        Path(__file__).parent / SIGN_BRIDGE_JS,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None

def clean_token(raw):
    """
    Tu dong trich xuat token 256 hex chuan tu moi loai input:
    - Raw token hex (256 ky tu)
    - URL in-game (chua itopencodeparam=...)
    - Chuoi key-value (itopencodeparam: ..., msdk-itopencodeparam: ...)
    - JSON / HAR snippet
    """
    if not raw:
        return ""
    raw = str(raw).strip()
    # 1. Parse URL / query string
    if "itopencodeparam=" in raw or "access_token=" in raw or "http://" in raw or "https://" in raw:
        unquoted = urllib.parse.unquote(raw)
        m = re.search(r'itopencodeparam=([0-9a-fA-F]{50,800})', unquoted, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m2 = re.search(r'msdk-itopencodeparam[:=]\s*([0-9a-fA-F]{50,800})', unquoted, re.IGNORECASE)
        if m2:
            return m2.group(1).strip()
        m3 = re.search(r'access_token=([0-9a-fA-F]{50,800})', unquoted, re.IGNORECASE)
        if m3:
            return m3.group(1).strip()

    # 2. Tim chuoi hex dai nhat (token MSDK thuong dai 256 ky tu hex)
    matches = re.findall(r'[0-9a-fA-F]{64,800}', raw)
    if matches:
        return max(matches, key=len).strip()

    return raw.strip().strip('"').strip("'")

def _start_sign_bridge():
    global _sign_bridge_proc
    with _sign_bridge_lock:
        if _sign_bridge_proc and _sign_bridge_proc.poll() is None:
            return
        # Kiem tra neu cong da co service chay san
        try:
            conn = http.client.HTTPConnection("127.0.0.1", SIGN_BRIDGE_PORT, timeout=1.0)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            if resp.status == 200:
                return
        except Exception:
            pass

        bridge = _find_sign_bridge()
        if not bridge:
            return
        try:
            node_bin = shutil.which("node") or shutil.which("nodejs") or "node"
            _sign_bridge_proc = subprocess.Popen(
                [node_bin, bridge, str(SIGN_BRIDGE_PORT)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
        except Exception:
            pass

def _request_bridge(endpoint, payload_dict, timeout=SIGN_BRIDGE_TIMEOUT):
    try:
        conn = http.client.HTTPConnection("127.0.0.1", SIGN_BRIDGE_PORT, timeout=timeout)
        body = json.dumps(payload_dict).encode()
        conn.request("POST", endpoint, body=body,
                     headers={"Content-Type": "application/json",
                              "Content-Length": str(len(body))})
        resp = conn.getresponse()
        if resp.status == 200:
            return json.loads(resp.read().decode())
    except Exception:
        pass
    return None

def get_dynamic_encodeparam(auth_token, role_id=None):
    auth_token = clean_token(auth_token)
    _start_sign_bridge()
    res = _request_bridge("/get_encodeparam", {"token": auth_token, "roleId": role_id})
    if res and res.get("code") == 0:
        return res.get("encodeparam")
    return None


def test_sign_bridge():
    global _sign_bridge_ok
    _start_sign_bridge()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", SIGN_BRIDGE_PORT, timeout=2.0)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        _sign_bridge_ok = (resp.status == 200)
        return _sign_bridge_ok
    except Exception:
        _sign_bridge_ok = False
        return False

# =============================================================================
# UTILS
# =============================================================================

def gen_traceparent():
    return "00-{}-{}-01".format(os.urandom(16).hex(), os.urandom(8).hex())

def check_connectivity():
    for host in ["kgvn-api.mobagarena.com", "8.8.8.8"]:
        try:
            socket.setdefaulttimeout(5)
            socket.getaddrinfo(host, 443)
            return True
        except socket.gaierror:
            continue
    return False

def make_session():
    s = requests.Session()
    r = Retry(total=3, backoff_factor=1.5,
              status_forcelist=[500,502,503,504],
              allowed_methods=["POST","PUT","GET"])
    a = HTTPAdapter(max_retries=r)
    s.mount("https://", a); s.mount("http://", a)
    return s

def ask_choice(prompt, options):
    print("\n" + "{}{}{}".format(C.CYAN, prompt, C.RESET))
    for k, v in options.items():
        print("    {}[{}]{}  {}".format(C.YELLOW+C.BOLD, k, C.RESET, v))
    while True:
        try:
            c = input("    {}Chon: {}".format(C.PURPLE, C.RESET)).strip()
            if c in options: return c
            print(warn("Nhap: " + " / ".join(options.keys())))
        except KeyboardInterrupt:
            print("\n" + err("Huy")); sys.exit(0)

def cinput(prompt):
    try:
        return input("{}{}{}".format(C.PURPLE, prompt, C.RESET)).strip()
    except KeyboardInterrupt:
        print("\n" + err("Huy")); sys.exit(0)

def has_ffmpeg():
    try:
        subprocess.run(["ffmpeg","-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

# =============================================================================
# AUTO RESIZE ANH
# =============================================================================

def resize_to_poster(raw_bytes, ext):
    if not PILLOW_OK:
        return raw_bytes
    try:
        img = _PIL_Image.open(io.BytesIO(raw_bytes))
        src_w, src_h = img.size
        ratio = max(POSTER_W/src_w, POSTER_H/src_h)
        new_w, new_h = int(src_w*ratio), int(src_h*ratio)
        img = img.resize((new_w, new_h), _PIL_Image.LANCZOS)
        left = (new_w - POSTER_W) // 2
        top  = (new_h - POSTER_H) // 2
        img = img.crop((left, top, left+POSTER_W, top+POSTER_H))
        buf = io.BytesIO()
        img.convert("RGBA").save(buf, format="PNG", optimize=False)
        return buf.getvalue()
    except Exception:
        return raw_bytes

# =============================================================================
# COS SIGNING
# =============================================================================

def _hmac_sha1(key, msg):
    return hmac_lib.new(key, msg.encode(), hashlib.sha1).hexdigest()

def build_cos_auth(sid, skey, method, pathname, clen):
    now  = int(time.time())
    end  = now + 86400
    kt   = "{};{}".format(now, end)
    sk   = _hmac_sha1(skey.encode(), kt)
    hh   = "content-length={}&host={}".format(clen, COS_HOST)
    hs   = "{}\n{}\n\n{}\n".format(method.lower(), pathname, hh)
    hhttp= hashlib.sha1(hs.encode()).hexdigest()
    s2s  = "sha1\n{}\n{}\n".format(kt, hhttp)
    sig  = _hmac_sha1(sk.encode(), s2s)
    return ("q-sign-algorithm=sha1&q-ak={}"
            "&q-sign-time={}&q-key-time={}"
            "&q-header-list=content-length;host&q-url-param-list="
            "&q-signature={}").format(sid, kt, kt, sig)

# =============================================================================
# MEDIA PROCESSING
# =============================================================================

def prepare_media(file_path, auto_resize=True):
    file_path = Path(file_path)
    ext       = file_path.suffix.lower()
    raw       = file_path.read_bytes()

    if ext in (".jpg",".jpeg",".png",".webp"):
        if auto_resize and PILLOW_OK:
            png_b = resize_to_poster(raw, ext)
            label = "{} {:,}B -> resize {:,}B".format(ext.upper().lstrip("."), len(raw), len(png_b))
        else:
            png_b = raw
            label = "{} {:,}B".format(ext.upper().lstrip("."), len(raw))
        return {"png_bytes": png_b, "anim_bytes": None, "anim_ext": None,
                "label": label, "name": file_path.name}

    if ext == ".gif":
        if not PILLOW_OK:
            print(err("GIF can Pillow: pip install Pillow")); sys.exit(1)
        try:
            gif = _PIL_Image.open(io.BytesIO(raw))
            gif.seek(0)
            buf = io.BytesIO()
            gif.convert("RGBA").save(buf, format="PNG")
            png_b = buf.getvalue()
            if auto_resize: png_b = resize_to_poster(png_b, ".png")
            print(info("    GIF: frame1->PNG {:,}B  +  GIF goc {:,}B".format(len(png_b), len(raw))))
            return {"png_bytes": png_b, "anim_bytes": raw, "anim_ext": "gif",
                    "label": "GIF {:,}B anim".format(len(raw)), "name": file_path.name}
        except Exception as e:
            print(err("Loi GIF: " + str(e))); sys.exit(1)

    if ext == ".mp4":
        if not has_ffmpeg():
            print(err("MP4 can ffmpeg: pkg install ffmpeg")); sys.exit(1)
        tmp_mp4 = tempfile.mktemp(suffix=".mp4")
        tmp_gif = tempfile.mktemp(suffix=".gif")
        tmp_png = tempfile.mktemp(suffix=".png")
        try:
            with open(tmp_mp4,"wb") as f: f.write(raw)
            print(info("    MP4 -> GIF (fps=10 scale=320)..."))
            subprocess.run(["ffmpeg","-i",tmp_mp4,"-vf","fps=10,scale=320:-1:flags=lanczos",
                            "-loop","0",tmp_gif,"-y"], capture_output=True, check=True)
            with open(tmp_gif,"rb") as f: gif_b = f.read()
            subprocess.run(["ffmpeg","-i",tmp_gif,"-vframes","1","-f","image2",tmp_png,"-y"],
                           capture_output=True, check=True)
            with open(tmp_png,"rb") as f: png_b = f.read()
            for fp in [tmp_mp4,tmp_gif,tmp_png]:
                try: os.unlink(fp)
                except: pass
            if auto_resize: png_b = resize_to_poster(png_b, ".png")
            print(info("    PNG render {:,}B  GIF anim {:,}B".format(len(png_b), len(gif_b))))
            return {"png_bytes": png_b, "anim_bytes": gif_b, "anim_ext": "gif",
                    "label": "MP4->GIF {:,}B anim".format(len(gif_b)), "name": file_path.name}
        except subprocess.CalledProcessError as e:
            print(err("ffmpeg that bai: " + str(e))); sys.exit(1)
        except Exception as e:
            print(err("Loi MP4: " + str(e))); sys.exit(1)

    print(err("Dinh dang khong ho tro: " + ext)); sys.exit(1)

def scan_media(directory):
    files = sorted([p for p in Path(directory).iterdir()
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTS])
    if not files:
        print(err("Khong tim thay media trong: " + directory)); sys.exit(1)
    return files

# =============================================================================
# API HELPERS
# =============================================================================

def api_post(session, endpoint, payload, auth_token,
             retry_on_code1=False, max_retries=3, delay=3.0,
             fallback_token=None):
    auth_token = clean_token(auth_token)
    hdrs = dict(FIXED_HEADERS)
    hdrs["Content-Type"]         = "application/json"
    hdrs["traceparent"]          = gen_traceparent()
    hdrs["priority"]             = "u=1, i"
    hdrs["Msdk-Itopencodeparam"] = auth_token

    # Lay dynamic encodeparam tu Sign Bridge
    enc = get_dynamic_encodeparam(auth_token)
    if enc:
        hdrs["Encodeparam"] = enc

    data = {}
    for attempt in range(max_retries):
        try:
            r = session.post(API_BASE + endpoint, json=payload, headers=hdrs, timeout=25)
            r.raise_for_status()
            data = r.json()
            if retry_on_code1 and data.get("code") == 1:
                wait = delay * (attempt + 1)
                tprint(warn("  code=1 thu lai {}s [{}/{}]".format(int(wait), attempt+1, max_retries)))
                time.sleep(wait); continue
            return data
        except requests.exceptions.ConnectionError as e:
            tprint(err("Loi ket noi: " + str(e))); return {"code":-1, "msg": str(e)}
        except requests.exceptions.HTTPError as e:
            try:
                err_json = r.json()
                return err_json
            except Exception:
                return {"code": -1, "msg": str(e)}
        except requests.exceptions.Timeout:
            if attempt < max_retries-1:
                tprint(warn("  Timeout [{}/{}] thu lai...".format(attempt+1, max_retries)))
                time.sleep(delay)
            else:
                return {"code":-1, "msg": "timeout"}
    return data

def cos_put(session, url, data, headers, label=""):
    for attempt in range(3):
        try:
            resp = session.put(url, data=data, headers=headers, timeout=60)
            if resp.status_code == 200: return resp
            tprint(warn("  COS {} [{}]: {}".format(label, resp.status_code, resp.text[:120])))
            if attempt < 2: time.sleep(2)
        except requests.exceptions.ConnectionError as e:
            tprint(err("COS loi: " + str(e))); return None
    return resp

def get_user_path(auth_token, mode="playerimage"):
    auth_token = clean_token(auth_token)
    sess = make_session()
    if mode == "flowborn_marksman":
        payload = {"scene": "FlowbornPoster", "fileName": "5/1/test.png"}
    elif mode == "flowborn_mage":
        payload = {"scene": "FlowbornPoster", "fileName": "4/1/test.png"}
    else:
        payload = {"scene": "PlayerimagePoster", "fileName": "0/1/test.png"}
    rc = api_post(sess, "/api/game/poster/getcoscredential", payload, auth_token)
    if rc.get("code") == 0 and rc.get("data"):
        val = rc["data"].get("path", "")
        if val:
            parts = val.strip("/").split("/")
            if len(parts) >= 3:
                return "/" + "/".join(parts[:3]) + "/"
    return None

def get_account_info(auth_token):
    """
    Xac thuc token va lay thong tin tai khoan:
    Tra ve: { token_valid, clean_token, user_id, short_id, current_poster_url, user_path, charac_name, role_job_name, head_url, rank_grade_star }
    """
    auth_token = clean_token(auth_token)
    _start_sign_bridge()
    sess = make_session()

    # 1. Khoi tao phien va lay thong tin user tu bridge
    bridge_res = _request_bridge("/init_session", {"token": auth_token})
    charac_name = None
    role_job_name = None
    head_url = None
    rank_grade_star = None

    if bridge_res and bridge_res.get("code") == 0 and bridge_res.get("data"):
        b_data = bridge_res["data"]
        charac_name = b_data.get("characName")
        role_job_name = b_data.get("roleJobName")
        head_url = b_data.get("headUrl")
        rank_grade_star = b_data.get("rankGradeStar")

    # 2. Xac thuc token qua getcoscredential (lay user_id tu path)
    payload = {"scene": "PlayerimagePoster", "fileName": "0/1/test.png"}
    rc = api_post(sess, "/api/game/poster/getcoscredential", payload, auth_token)

    if rc.get("code") != 0 or not rc.get("data"):
        return {
            "token_valid": False, "clean_token": auth_token, "user_id": None, "short_id": None,
            "current_poster_url": None, "user_path": None,
            "charac_name": None, "role_job_name": None,
            "head_url": None, "rank_grade_star": None
        }

    # Trich xuat user_id va user_path tu path
    val = rc["data"].get("path", "")
    user_id = None
    user_path = None
    if val:
        parts = val.strip("/").split("/")
        if len(parts) >= 3:
            user_id = parts[2]
            user_path = "/" + "/".join(parts[:3]) + "/"

    # 3. Lay anh poster hien tai (neu co)
    current_poster_url = None
    try:
        endpoint_getposter = "/api/game/poster/playerimage/getposter"
        r_gp = api_post(sess, endpoint_getposter, {}, auth_token)
        if r_gp.get("code") == 0 and r_gp.get("data"):
            data_gp = r_gp["data"]
            if data_gp.get("picUrl") and data_gp.get("posterId"):
                # Anh poster hien tai thuong o dang <picUrl>0/1/<posterId>.png
                p_url = data_gp["picUrl"].rstrip("/") + "/0/1/" + str(data_gp["posterId"]) + ".png"
                current_poster_url = p_url
            elif data_gp.get("picInfo"):
                pi_gp = data_gp["picInfo"]
                sl_gp = pi_gp.get("stickerList", [])
                if sl_gp:
                    current_poster_url = sl_gp[-1].get("picUrl")
                elif pi_gp.get("bg") and pi_gp["bg"].get("picUrl"):
                    current_poster_url = pi_gp["bg"].get("picUrl")
    except Exception:
        pass

    return {
        "token_valid": True,
        "clean_token": auth_token,
        "user_id": user_id,
        "short_id": user_id[:8] if user_id else None,
        "current_poster_url": current_poster_url,
        "user_path": user_path,
        "charac_name": charac_name,
        "role_job_name": role_job_name,
        "head_url": head_url,
        "rank_grade_star": rank_grade_star
    }


# =============================================================================
# POSTER WORKER
# =============================================================================

def poster_worker(idx, acc_lbl, auth_token, user_path,
                  media, pic_info_raw, is_share, results, dry_run=False, mode="playerimage", gender=1):
    session = make_session()
    png_b    = media["png_bytes"]
    anim_b   = media["anim_bytes"]
    anim_ext = media["anim_ext"]
    fname    = media.get("name", "?")
    step_tag = "Ảnh #{:02d}".format(idx)

    is_flowborn = mode.startswith("flowborn_")
    create_url = "/api/game/poster/flowborn/createposter" if is_flowborn else "/api/game/poster/playerimage/createposter"
    save_url = "/api/game/poster/flowborn/saveposter" if is_flowborn else "/api/game/poster/playerimage/saveposter"
    scene_name = "FlowbornPoster" if is_flowborn else "PlayerimagePoster"

    if mode == "flowborn_marksman":
        file_prefix = "5/1/"
        mainJob = 5
        bg_id = "22"
        bg_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/IDqWId2J.png"
        skinColor = 1
        if gender == 1:
            baseInfo_id = "31"
            baseInfo_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/QQD3ebSX.png"
        else:
            baseInfo_id = "32"
            baseInfo_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/Pd7zTH2f.png"
    elif mode == "flowborn_mage":
        file_prefix = "4/1/"
        mainJob = 4
        bg_id = "22"
        bg_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/IDqWId2J.png"
        skinColor = 1
        if gender == 1:
            baseInfo_id = "61"
            baseInfo_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/epf8os8a.png"
        else:
            baseInfo_id = "62"
            baseInfo_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/5fXAjyuq.png"
    else:
        file_prefix = "0/1/"
        mainJob = 0
        bg_id = "21"
        bg_picUrl = CDN_BASE + "/manage/playerimage_official/iDzT817p.png"
        baseInfo_id = ""
        baseInfo_picUrl = ""
        skinColor = 1


    if dry_run:
        tprint("{} [DRY RUN] Kiểm tra xong - không thực hiện tải lên ({:,}B)".format(step_tag, len(png_b)))
        results[idx-1] = (True, "DRY-RUN", "", "IMG"); return

    try:
        # A. Tạo poster mới trên server
        tprint("{} ⏳ Đang tạo slot poster trên server...".format(step_tag))
        r = api_post(session, create_url, {}, auth_token)
        if r.get("code") != 0 or not r.get("data"):
            err_msg = r.get("msg", "Lỗi không rõ")
            tprint("{} ❌ Tạo poster thất bại: {}".format(step_tag, err_msg[:60]))
            results[idx-1] = (False, "Tạo poster: " + err_msg[:40]); return
        pid = r["data"]["posterId"]
        tprint("{} ✅ Tạo poster thành công (ID: {})".format(step_tag, pid))
        time.sleep(0.5)

        # B. Lấy quyền upload lên Cloud
        def get_creds(filename):
            rc = api_post(session, "/api/game/poster/getcoscredential",
                         {"scene": scene_name, "fileName": filename},
                         auth_token)
            return rc["data"] if rc.get("code") == 0 else None

        creds1 = get_creds("{}{}.png".format(file_prefix, pid))
        if not creds1:
            tprint("{} ❌ Không lấy được quyền upload. Server từ chối cấp phép.".format(step_tag))
            results[idx-1] = (False, "Không có quyền upload"); return
        creds2 = get_creds("{}{}_large.png".format(file_prefix, pid)) or creds1
        time.sleep(0.3)

        # C. Upload ảnh lên Cloud
        ck_path = creds1.get("path", "")
        suffix = "{}{}.png".format(file_prefix, pid)
        if ck_path and ck_path.endswith(suffix):
            actual_user_path = ck_path[:-len(suffix)]
        else:
            actual_user_path = user_path

        ck   = "{}{}{}.png".format(actual_user_path, file_prefix, pid)
        ck_l = "{}{}{}_large.png".format(actual_user_path, file_prefix, pid)

        def mkhdr(key, buf, creds_in):
            return {
                "Authorization":        build_cos_auth(
                    creds_in["tmpSecretId"], creds_in["tmpSecretKey"], "PUT", key, len(buf)),
                "Content-Type":         "image/png",
                "Content-Length":       str(len(buf)),
                "Host":                 COS_HOST,
                "x-cos-security-token": creds_in["token"],
                "Origin":               "https://kgvn-camp.mobagarena.com",
                "Referer":              "https://kgvn-camp.mobagarena.com/",
            }

        tprint("{} ☁️  Đang tải ảnh lên server ({:,} KB)...".format(step_tag, len(png_b)//1024))
        r2 = cos_put(session, "https://"+COS_HOST+ck, png_b, mkhdr(ck, png_b, creds1), ".png")
        if r2 is None or r2.status_code != 200:
            tprint("{} ❌ Tải ảnh lên thất bại! Kiểm tra kết nối mạng.".format(step_tag))
            results[idx-1] = (False, "Upload ảnh thất bại"); return
        tprint("{} ✅ Tải ảnh lên thành công!".format(step_tag))
        cos_put(session, "https://"+COS_HOST+ck_l, png_b, mkhdr(ck_l, png_b, creds2), "_large")
        sticker_url = UGC_CDN_BASE + ck

        if anim_b is not None and anim_ext:
            ck_a = "{}{}{}.{}".format(actual_user_path, file_prefix, pid, anim_ext)
            creds3 = get_creds("{}{}.{}".format(file_prefix, pid, anim_ext)) or creds1
            tprint("{} ☁️  Đang tải GIF động lên server ({:,} KB)...".format(step_tag, len(anim_b)//1024))
            r_a  = cos_put(session, "https://"+COS_HOST+ck_a,
                           anim_b, mkhdr(ck_a, anim_b, creds3), "."+anim_ext)
            if r_a is not None and r_a.status_code == 200:
                sticker_url = UGC_CDN_BASE + ck_a
                tprint("{} ✅ Tải GIF động lên thành công!".format(step_tag))
            else:
                tprint("{} ⚠️  GIF động thất bại, dùng ảnh tĩnh thay thế.".format(step_tag))

        time.sleep(0.5)

        # D. Áp dụng poster
        tprint("{} 🔄 Đang áp dụng ảnh tải trận vào tài khoản...".format(step_tag))
        if is_flowborn:
            # Tự động lấy cấu hình nhân vật hợp lệ từ server cho tài khoản này
            try:
                cfg_r = api_post(session, "/api/game/poster/flowborn/geteditorconfig", {"mainJob": mainJob}, auth_token)
                if cfg_r.get("code") == 0 and cfg_r.get("data") and cfg_r["data"].get("baseList"):
                    bl = cfg_r["data"]["baseList"]
                    matched_base = next((b for b in bl if b.get("gender") == gender), bl[0])
                    baseInfo_id = matched_base.get("id", baseInfo_id)
                    baseInfo_picUrl = matched_base.get("picUrl", baseInfo_picUrl)
                    gender = matched_base.get("gender", gender)
                    skinColor = matched_base.get("skinColor", skinColor)
            except Exception:
                pass

            payload = {
                "posterId": pid,
                "isApply": True,
                "isShare": is_share,
                "mainJob": mainJob,
                "picInfo": {
                    "bg": {
                        "id": bg_id,
                        "picUrl": bg_picUrl
                    },
                    "baseInfo": {
                        "id": baseInfo_id,
                        "gender": gender,
                        "mainJob": mainJob,
                        "picUrl": baseInfo_picUrl,
                        "skinColor": skinColor
                    },
                    "stickerList": []
                },
                "picUrl": UGC_CDN_BASE + actual_user_path
            }
        else:
            payload = {
                "posterId": pid,
                "isApply": True,
                "isShare": is_share,
                "picUrl": UGC_CDN_BASE + actual_user_path,
                "picInfo": {
                    "bg": {
                        "id": PI_BG_ID,
                        "picUrl": PI_BG_PICURL,
                        "source": 1,
                        "width": PI_BG_W,
                        "height": PI_BG_H,
                        "posX": 0,
                        "posY": 0
                    },
                    "stickerList": []
                }
            }

        rp = api_post(session, save_url,
                      payload,
                      auth_token, retry_on_code1=True, max_retries=4, delay=4.0)

        unavail = (rp.get("data") or {}).get("unavailableResources", [])
        kind    = "GIF động" if anim_b else "Ảnh tĩnh"

        if rp.get("code") == 0:
            tprint("{} 🎉 THÀNH CÔNG! Ảnh tải trận đã được cập nhật! [{}]".format(step_tag, kind))
            results[idx-1] = (True, pid, sticker_url, kind)
        else:
            err_msg = rp.get("msg", "Lỗi không rõ")
            if "-1993" in err_msg:
                err_msg = "Tài khoản chưa tạo hoặc chưa chọn tướng này trong game (hoặc sai giới tính)"
            tprint("{} ❌ Áp dụng thất bại: {}".format(step_tag, err_msg[:80]))
            results[idx-1] = (False, "Áp dụng: " + err_msg[:50])


    except Exception as e:
        tprint("{} ❌ Lỗi hệ thống: {}".format(step_tag, str(e)[:80]))
        results[idx-1] = (False, "Lỗi: " + str(e)[:40])

# =============================================================================
# ACC WORKER
# =============================================================================

def acc_worker(acc, media_list, is_share, acc_results, dry_run=False, mode="playerimage", gender=1):
    lbl = acc["label"]
    tprint("\n" + sep(62, "=", C.CYAN))
    tprint("{}  BẮT ĐẦU  {}{}".format(C.CYAN+C.BOLD, lbl, C.RESET))
    tprint(sep(62, "=", C.CYAN))

    auth_token = acc.get("token")
    user_path = acc.get("user_path")
    if not auth_token or not user_path:
        tprint(err("  [{}] Thiếu token hoặc đường dẫn tài khoản -- bỏ qua".format(lbl)))
        acc_results[lbl] = {"ok":0,"fail":0,"rounds":[]}; return

    _start_sign_bridge()

    n_media    = len(media_list)
    total_ok   = total_fail = 0
    round_logs = []

    tprint("")
    tprint("🚀 Chuẩn bị tải lên {} ảnh...".format(n_media))

    results = [None]*n_media
    threads = []
    for i, m in enumerate(media_list, 1):
        t = threading.Thread(
            target=poster_worker,
            args=(i, lbl, auth_token, user_path, m, {}, is_share, results),
            kwargs={"dry_run": dry_run, "mode": mode, "gender": gender},
            daemon=True,
        )
        threads.append(t)

    for t in threads:
        t.start()
        time.sleep(POSTER_STAGGER)

    for t in threads:
        t.join()

    ok_n   = sum(1 for res in results if res and res[0])
    fail_n = n_media - ok_n
    total_ok   += ok_n
    total_fail += fail_n
    round_logs.append((1, results))

    tprint("")
    tprint("📊 Kết quả: {} thành công / {} thất bại".format(ok_n, fail_n))
    for i, res in enumerate(results, 1):
        if res and res[0]:
            kind = "GIF động" if (len(res) > 3 and res[3] != "IMG") else "Ảnh tĩnh"
            tprint("✅ Ảnh #{:02d}: Tải lên thành công! [{}]".format(i, kind))
        else:
            msg = str(res[1])[:50] if res else "Lỗi không xác định"
            tprint("❌ Ảnh #{:02d}: Thất bại - {}".format(i, msg))

    acc_results[lbl] = {"ok":total_ok,"fail":total_fail,"rounds":round_logs}

# =============================================================================
# CLI MAIN
# =============================================================================

def run(image_dir, dry_run=False):
    print("")
    print("{}{}".format(C.CYAN, "="*62))
    print("{}  KGVN  Mod Anh Load Tran  .  Multi-Account  v3.2     ".format(C.WHITE+C.BOLD))
    print("{}  JPG . PNG . WEBP . GIF . MP4  |  Chaos VM Bridge      ".format(C.CYAN))
    print("{}  Auto Resize 1080x1701   |  COS per-poster creds       ".format(C.CYAN))
    print("{}{}".format(C.CYAN, "="*62) + C.RESET)

    if dry_run:
        print("\n" + "{}  [DRY RUN MODE - KHONG THUC HIEN]{}".format(C.YELLOW+C.BOLD, C.RESET))

    print("\n" + info("Kiem tra ket noi..."))
    if not check_connectivity():
        print(err("Khong co ket noi internet!")); sys.exit(1)
    print(ok("Mang OK"))

    print(info("Kiem tra Sign Bridge..."))
    _start_sign_bridge()
    sb_ok = test_sign_bridge()
    if sb_ok:
        print(ok("Sign Bridge (Chaos VM) HOAT DONG"))
    else:
        print(warn("Sign Bridge chua san sang -> dang khoi dong lai..."))

    print("\n" + bold("--- Nhap Thong Tin ---"))
    auth_token = cinput("  Nhap Token (msdk-itopencodeparam hoac copy tu HAR): ")
    if not auth_token:
        print(err("  Token khong duoc de trong!")); sys.exit(1)

    print(info("  Dang lay thong tin account..."))
    acc_info = get_account_info(auth_token)
    if not acc_info.get("token_valid"):
        print(err("  Token khong hop le hoac da het han!")); sys.exit(1)

    user_path = acc_info.get("user_path")
    charac_name = acc_info.get("charac_name") or "Khong ro"
    print(ok("  Token hop le!"))
    print(dim("  Ten nhan vat: {}".format(charac_name)))
    print(dim("  user_path: {}".format(user_path)))

    selected = [{"token": auth_token, "user_path": user_path, "label": charac_name, "har": ""}]
    n_acc = 1

    print("\n" + info("Quet media trong: " + image_dir))
    all_files = scan_media(image_dir)
    print("  Tim thay {} file:".format(len(all_files)))
    for i, p in enumerate(all_files, 1):
        print("  {}[{}]{}  {}  {:.1f} KB".format(C.YELLOW, i, C.RESET, p.name, p.stat().st_size/1024))

    shared_media = [prepare_media(p, auto_resize=PILLOW_OK) for p in all_files[:MAX_MEDIA_PER_ACC]]
    acc_media_map = {selected[0]["label"]: shared_media}

    save_mode = ask_choice("Che do LUU:",
        {"1": "{}Luu rieng{}  (chi minh toi dung)".format(C.CYAN, C.RESET),
         "2": "{}Quang truong{}  (moi nguoi thay)".format(C.YELLOW, C.RESET)})
    is_share = (save_mode == "2")

    acc_results = {}
    print("\n" + bold("Bat dau tai len..."))
    acc_worker(selected[0], acc_media_map[selected[0]["label"]], is_share, acc_results, dry_run=dry_run)

    print("\n  {}Mo game -> Anh load tran de thay!{}\n".format(C.CYAN, C.RESET))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KGVN Mod Anh Load Tran - Multi-Account Tool v3.2")
    ap.add_argument("--dir",       default=".")
    ap.add_argument("--test-sign", action="store_true", help="Test sign bridge roi thoat")
    ap.add_argument("--dry-run",   action="store_true", help="Kiem tra config, khong thuc hien upload")
    args = ap.parse_args()

    if args.test_sign:
        print(info("Dang test Sign Bridge..."))
        _start_sign_bridge()
        time.sleep(1)
        ok_sb = test_sign_bridge()
        print(ok("Sign Bridge HOAT DONG!") if ok_sb else err("Sign Bridge KHONG HOAT DONG"))
        sys.exit(0 if ok_sb else 1)

    run(args.dir, dry_run=args.dry_run)
