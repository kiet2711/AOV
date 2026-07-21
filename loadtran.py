#!/usr/bin/env python3
"""
KGVN Load Tran v3.0  --  by hienmods
Mod anh load tran (playerimage) -- Multi-account, Sign Bridge, Auto Resize
Ho tro: JPG . PNG . WEBP . GIF . MP4

TINH NANG MOI so v1.0:
  * Sign Bridge: tu dong lay dynamic encodeparam (fix loi -5001 auth failed)
  * Auto Resize: tu dong resize anh ve 1080x1701 (khi co Pillow)
  * COS credentials rieng cho moi poster (thay vi dung chung)
  * savepostereditinfo bat buoc truoc saveposter
  * --test-sign: test sign bridge doc lap
  * --dry-run: kiem tra config khong thuc hien upload
"""

import argparse
import hashlib
import hmac as hmac_lib
import http.client
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
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
    BG_CYAN   = "\033[46m"
    BG_GREEN  = "\033[42m"
    BG_RED    = "\033[41m"
    BG_PURPLE = "\033[45m"

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
DEFAULT_HAR  = "0919.har"
MAX_MEDIA_PER_ACC = 6

# Kich thuoc poster chuan
POSTER_W = 1080
POSTER_H = 1701

# Playerimage constants
PI_STICKER_ID = "182"
PI_STICKER_W  = 690.9890109890109
PI_STICKER_H  = 690.9890109890109
PI_STICKER_X  = -194.8712087912088
PI_STICKER_Y  = -85.4572357633227
PI_BG_ID      = "21"
PI_BG_PICURL  = CDN_BASE + "/manage/playerimage_official/iDzT817p.png"
PI_BG_W       = 320
PI_BG_H       = 503.99824175824176

# Timing
POSTER_STAGGER = 3.6
ROUND_DELAY    = 3.0
ACC_STAGGER    = 2.0

# Sign Bridge
SIGN_BRIDGE_PORT    = 19876
SIGN_BRIDGE_JS      = "sign_bridge.js"
SIGN_BRIDGE_PY      = "sign_bridge_py.py"
SIGN_BRIDGE_TIMEOUT = 8.0

FIXED_HEADERS = {
    "camp-source":        "AOV-CAMP",
    "msdk-gameid":        "1137",
    "camp-authtype":      "msdk",
    "areaid":             "1",
    "msdk-os":            "1",
    "logicworldid":       "1011",
    "aov-language":       "VN",
    "msdk-channelid":     "10",
    "aov-region":         "1137",
    "origin":             "https://kgvn-camp.mobagarena.com",
    "x-requested-with":   "com.garena.game.kgvn",
    "referer":            "https://kgvn-camp.mobagarena.com/",
    "sec-ch-ua":          '"Chromium";v="146", "Not-A.Brand";v="24", "Android WebView";v="146"',
    "sec-ch-ua-mobile":   "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-site":     "same-site",
    "sec-fetch-mode":     "cors",
    "sec-fetch-dest":     "empty",
    "accept":             "*/*",
    "accept-language":    "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "accept-encoding":    "gzip, deflate, br, zstd",
    "user-agent": (
        "Mozilla/5.0 (Linux; Android 15; SM-A165F Build/AP3A.240905.015.A2; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/146.0.7680.177 "
        "Mobile Safari/537.36 MSDK/5.36.000 mQQAppId/1105779914 "
        "mWXAppId/wx7a814e3ceeda8320 mGameId/1137 MSDKdeviceId/disable"
    ),
}

log_buffer = []
import re

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
# SIGN BRIDGE -- Dynamic encodeparam
# =============================================================================

_sign_bridge_proc  = None
_sign_bridge_ok    = None
_sign_bridge_lock  = threading.Lock()

def _find_sign_bridge():
    candidates = [
        Path(SIGN_BRIDGE_JS),
        Path(SIGN_BRIDGE_PY),
        Path(__file__).parent / SIGN_BRIDGE_JS,
        Path(__file__).parent / SIGN_BRIDGE_PY,
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None

def _start_sign_bridge():
    global _sign_bridge_proc
    with _sign_bridge_lock:
        if _sign_bridge_proc and _sign_bridge_proc.poll() is None:
            return
        bridge = _find_sign_bridge()
        if not bridge:
            return
        try:
            if bridge.endswith(".js"):
                _sign_bridge_proc = subprocess.Popen(
                    ["node", bridge, str(SIGN_BRIDGE_PORT)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                _sign_bridge_proc = subprocess.Popen(
                    [sys.executable, bridge, str(SIGN_BRIDGE_PORT)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.5)
        except FileNotFoundError:
            pass

def _request_sign(payload_json, timeout=SIGN_BRIDGE_TIMEOUT):
    try:
        conn = http.client.HTTPConnection("127.0.0.1", SIGN_BRIDGE_PORT, timeout=timeout)
        body = payload_json.encode()
        conn.request("POST", "/sign", body=body,
                     headers={"Content-Type": "application/json",
                               "Content-Length": str(len(body))})
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            return data.get("encodeparam") or data.get("result")
    except Exception:
        pass
    return None

def get_dynamic_encodeparam(endpoint, payload, fallback_token):
    global _sign_bridge_ok
    if _sign_bridge_ok is False:
        return fallback_token
    _start_sign_bridge()
    sign_payload = json.dumps({"url": API_BASE + endpoint, "method": "POST", "body": payload})
    result = _request_sign(sign_payload)
    if result:
        _sign_bridge_ok = True
        return result
    _sign_bridge_ok = False
    return fallback_token

def test_sign_bridge():
    global _sign_bridge_ok
    _start_sign_bridge()
    result = _request_sign(json.dumps({
        "url": API_BASE + "/api/game/poster/playerimage/createposter",
        "method": "POST", "body": {},
    }))
    _sign_bridge_ok = bool(result)
    return _sign_bridge_ok

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
# PARSE HAR (Da xoa theo yeu cau, chuyen sang nhap token truc tiep)
# =============================================================================

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

def find_har_files(directory="."):
    return sorted(Path(directory).glob("*.har"))

# =============================================================================
# API HELPERS
# =============================================================================

def api_post(session, endpoint, payload, auth_token,
             retry_on_code1=False, max_retries=3, delay=3.0,
             fallback_token=None):
    hdrs = dict(FIXED_HEADERS)
    hdrs["content-type"]         = "application/json"
    hdrs["traceparent"]          = gen_traceparent()
    hdrs["priority"]             = "u=1, i"
    ft = fallback_token or auth_token
    hdrs["msdk-itopencodeparam"] = get_dynamic_encodeparam(endpoint, payload, ft)
    data = {}
    for attempt in range(max_retries):
        try:
            r = session.post(API_BASE+endpoint, json=payload, headers=hdrs, timeout=25)
            r.raise_for_status()
            data = r.json()
            if retry_on_code1 and data.get("code") == 1:
                wait = delay*(attempt+1)
                tprint(warn("  code=1 thu lai {}s [{}/{}]".format(int(wait), attempt+1, max_retries)))
                time.sleep(wait); continue
            return data
        except requests.exceptions.ConnectionError as e:
            tprint(err("Loi ket noi: "+str(e))); return {"code":-1,"msg":str(e)}
        except requests.exceptions.Timeout:
            if attempt < max_retries-1:
                tprint(warn("  Timeout [{}/{}] thu lai...".format(attempt+1, max_retries)))
                time.sleep(delay)
            else:
                return {"code":-1,"msg":"timeout"}
    return data

def cos_put(session, url, data, headers, label=""):
    for attempt in range(3):
        try:
            resp = session.put(url, data=data, headers=headers, timeout=60)
            if resp.status_code == 200: return resp
            tprint(warn("  COS {} [{}]: {}".format(label, resp.status_code, resp.text[:120])))
            if attempt < 2: time.sleep(2)
        except requests.exceptions.ConnectionError as e:
            tprint(err("COS loi: "+str(e))); return None
    return resp

def get_user_path(auth_token, mode="playerimage"):
    sess = make_session()
    if mode == "flowborn_marksman":
        payload = {"scene": "FlowbornPoster", "fileName": "5/1/test.png"}
    elif mode == "flowborn_mage":
        payload = {"scene": "FlowbornPoster", "fileName": "4/1/test.png"}
    else:
        payload = {"scene": "PlayerimagePoster", "fileName": "0/1/test.png"}
    rc = api_post(sess, "/api/game/poster/getcoscredential", payload, auth_token, fallback_token=auth_token)
    if rc.get("code") == 0 and rc.get("data"):
        val = rc["data"].get("path", "")
        if val:
            parts = val.strip("/").split("/")
            if len(parts) >= 3:
                return "/" + "/".join(parts[:3]) + "/"
    return None

def get_account_info(auth_token):
    """
    Xac thuc token va lay thong tin tai khoan.
    Tra ve: { token_valid, user_id, short_id, current_poster_url, user_path }
    """
    sess = make_session()

    # 1. Xac thuc token qua getcoscredential (lay user_id tu path)
    payload = {"scene": "PlayerimagePoster", "fileName": "0/1/test.png"}
    rc = api_post(sess, "/api/game/poster/getcoscredential", payload, auth_token, fallback_token=auth_token)

    if rc.get("code") != 0 or not rc.get("data"):
        return {"token_valid": False, "user_id": None, "short_id": None,
                "current_poster_url": None, "user_path": None}

    # Trich xuat user_id va user_path tu path
    val = rc["data"].get("path", "")
    user_id = None
    user_path = None
    if val:
        parts = val.strip("/").split("/")
        if len(parts) >= 3:
            user_id = parts[2]
            user_path = "/" + "/".join(parts[:3]) + "/"

    # 2. Lay anh poster hien tai (neu co)
    current_poster_url = None
    try:
        # Goi truc tiep khong dung api_post vi api_post goi raise_for_status()
        # API co the tra 403 nhung van co JSON body chua data poster
        hdrs = dict(FIXED_HEADERS)
        hdrs["content-type"] = "application/json"
        hdrs["traceparent"]  = gen_traceparent()
        hdrs["priority"]     = "u=1, i"
        endpoint2 = "/api/game/poster/playerimage/getpostereditinfo"
        hdrs["msdk-itopencodeparam"] = get_dynamic_encodeparam(endpoint2, {}, auth_token)
        resp2 = sess.post(API_BASE + endpoint2, json={}, headers=hdrs, timeout=25)
        try:
            r2 = resp2.json()
        except Exception:
            r2 = {}
        if r2.get("data") and r2["data"].get("picInfo"):
            pi = r2["data"]["picInfo"]
            # Thu lay tu stickerList truoc
            sticker_list = pi.get("stickerList", [])
            if sticker_list:
                # Get the last sticker (often the most recently added) instead of the first
                url_candidate = sticker_list[-1].get("picUrl") or ""
                if url_candidate:
                    current_poster_url = url_candidate
            # Neu stickerList khong co, thu lay tu bg.picUrl
            if not current_poster_url:
                bg_url = (pi.get("bg") or {}).get("picUrl") or ""
                if bg_url and bg_url.startswith("http"):
                    current_poster_url = bg_url
        elif r2.get("data"):
            # Truong hop khong co picInfo, thu doc picUrl truc tiep tu data
            direct_url = r2["data"].get("picUrl") or ""
            if direct_url and direct_url.startswith("http"):
                current_poster_url = direct_url
                
        endpoint_getposter = "/api/game/poster/playerimage/getposter"
        hdrs["msdk-itopencodeparam"] = get_dynamic_encodeparam(endpoint_getposter, {}, auth_token)
        resp_gp = sess.post(API_BASE + endpoint_getposter, json={}, headers=hdrs, timeout=25)
        try:
            r_gp = resp_gp.json()
            if r_gp.get("code") == 0 and r_gp.get("data") and r_gp["data"].get("picInfo"):
                pi_gp = r_gp["data"]["picInfo"]
                sl_gp = pi_gp.get("stickerList", [])
                if sl_gp:
                    url_gp = sl_gp[-1].get("picUrl")
                    if url_gp:
                        current_poster_url = url_gp
        except Exception:
            pass
            
    except Exception:
        pass

    return {
        "token_valid": True,
        "user_id": user_id,
        "short_id": user_id[:8] if user_id else None,
        "current_poster_url": current_poster_url,
        "user_path": user_path,
    }




# =============================================================================
# BUILD picInfo
# =============================================================================

def build_pic_info(pic_info_raw, sticker_url):
    bg = pic_info_raw.get("bg") or {}
    return {
        "bg": {
            "id":     bg.get("id",     PI_BG_ID),
            "picUrl": bg.get("picUrl", PI_BG_PICURL),
            "source": 1,
            "width":  bg.get("width",  PI_BG_W),
            "height": bg.get("height", PI_BG_H),
            "posX":   bg.get("posX",   0),
            "posY":   bg.get("posY",   0),
        },
        "stickerList": [{
            "id":     PI_STICKER_ID,
            "picUrl": sticker_url,
            "width":  PI_STICKER_W,
            "height": PI_STICKER_H,
            "posX":   PI_STICKER_X,
            "posY":   PI_STICKER_Y,
            "rotate": 0, "source": 1, "type": 1,
        }],
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
        file_prefix = f"5/{gender}/"
        mainJob = 5
        bg_id = "30"
        bg_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/4uxOQChv.png"
        skinColor = 1
        if gender == 1:
            baseInfo_id = "31"
            baseInfo_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/QQD3ebSX.png"
        else:
            baseInfo_id = "32"
            baseInfo_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/Pd7zTH2f.png"
    elif mode == "flowborn_mage":
        file_prefix = f"4/{gender}/"
        mainJob = 4
        bg_id = "30"
        bg_picUrl = "https://kg-camp.mobagarena.com/manage/flowborn_official/4uxOQChv.png"
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
        bg_id = ""
        bg_picUrl = ""
        baseInfo_id = ""
        baseInfo_picUrl = ""
        # gender is already passed in
        skinColor = 1

    if dry_run:
        tprint("{} [DRY RUN] Kiểm tra xong - không thực hiện tải lên ({:,}B)".format(step_tag, len(png_b)))
        results[idx-1] = (True, "DRY-RUN", "", "IMG"); return

    try:
        # A. Tạo poster mới trên server
        tprint("{} ⏳ Đang tạo slot poster trên server...".format(step_tag))
        r = api_post(session, create_url,
                     {}, auth_token, fallback_token=auth_token)
        if r.get("code") != 0:
            err_msg = r.get("msg", "Lỗi không rõ")
            tprint("{} ❌ Tạo poster thất bại: {}".format(step_tag, err_msg[:60]))
            results[idx-1] = (False, "Tạo poster: "+err_msg[:40]); return
        pid = r["data"]["posterId"]
        tprint("{} ✅ Tạo poster thành công (ID: {})".format(step_tag, pid))
        time.sleep(0.5)

        # B. Lấy quyền upload lên Cloud
        def get_creds(filename):
            rc = api_post(session, "/api/game/poster/getcoscredential",
                         {"scene": scene_name, "fileName": filename},
                         auth_token, fallback_token=auth_token)
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

        # D. Lưu thông tin khung ảnh (chỉ cho playerimage)
        if not is_flowborn:
            tprint("{} 💾 Đang lưu thiết lập khung ảnh...".format(step_tag))
            pi = build_pic_info(pic_info_raw, sticker_url)
            rs = api_post(session, "/api/game/poster/playerimage/savepostereditinfo",
                          {"picInfo": pi}, auth_token,
                          retry_on_code1=True, max_retries=4, delay=4.0, fallback_token=auth_token)
            if rs.get("code") == 0:
                tprint("{} ✅ Lưu khung ảnh thành công!".format(step_tag))
            else:
                tprint("{} ⚠️  Lưu khung ảnh không thuận lợi (code={}), tiếp tục...".format(step_tag, rs.get("code")))
            time.sleep(1.5)

        # E. Áp dụng poster
        tprint("{} 🔄 Đang áp dụng ảnh tải trận vào tài khoản...".format(step_tag))
        if is_flowborn:
            if pic_info_raw:
                bg_info = pic_info_raw.get("bg") or {}
                bg_id = bg_info.get("id", bg_id)
                bg_picUrl = bg_info.get("picUrl", bg_picUrl)
                base_info = pic_info_raw.get("baseInfo") or {}
                baseInfo_id = base_info.get("id", baseInfo_id)
                baseInfo_picUrl = base_info.get("picUrl", baseInfo_picUrl)

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
                "picInfo": pi
            }

        rp = api_post(session, save_url,
                      payload,
                      auth_token, retry_on_code1=True, max_retries=4, delay=4.0,
                      fallback_token=auth_token)

        unavail = (rp.get("data") or {}).get("unavailableResources", [])
        kind    = "GIF động" if anim_b else "Ảnh tĩnh"

        if rp.get("code") == 0 and not unavail:
            tprint("{} 🎉 THÀNH CÔNG! Ảnh tải trận đã được cập nhật! [{}]".format(step_tag, kind))
            results[idx-1] = (True, pid, sticker_url, kind)
        elif rp.get("code") == 0:
            tprint("{} ✅ Ảnh đã được lưu (một số tài nguyên phụ bị từ chối, nhưng không ảnh hưởng ảnh chính).".format(step_tag))
            results[idx-1] = (True, pid, sticker_url, kind)
        else:
            err_msg = rp.get("msg", "Lỗi không rõ")
            tprint("{} ❌ Áp dụng thất bại: {}".format(step_tag, err_msg[:60]))
            results[idx-1] = (False, "Áp dụng: "+err_msg[:40])

    except Exception as e:
        tprint("{} ❌ Lỗi hệ thống: {}".format(step_tag, str(e)[:80]))
        results[idx-1] = (False, "Lỗi: "+str(e)[:40])

# =============================================================================
# ACC WORKER
# =============================================================================

def acc_worker(acc, media_list, is_share, acc_results, dry_run=False, mode="playerimage", gender=1):
    lbl = acc["label"]
    tprint("\n" + sep(62, "=", C.CYAN))
    tprint("{}  BỮT ĐẦU  {}{}".format(C.CYAN+C.BOLD, lbl, C.RESET))
    tprint(sep(62, "=", C.CYAN))

    auth_token = acc.get("token")
    user_path = acc.get("user_path")
    if not auth_token or not user_path:
        tprint(err("  [{}] Thiếu token hoặc đường dẫn tài khoản -- bỏ qua".format(lbl)))
        acc_results[lbl] = {"ok":0,"fail":0,"rounds":[]}; return

    _start_sign_bridge()

    sess = make_session()
    pic_info_raw = {}
    if not mode.startswith("flowborn_"):
        tprint("🔍 Đang lấy thông tin khung ảnh hiện tại của bạn...")
        r = api_post(sess, "/api/game/poster/playerimage/getpostereditinfo",
                     {}, auth_token, fallback_token=auth_token)
        if r.get("code") == 0 and (r.get("data") or {}).get("picInfo"):
            pic_info_raw = r["data"]["picInfo"]
            tprint("✅ Lấy thông tin khung ảnh thành công!")
        else:
            tprint("⚠️  Sử dụng cấu hình khung ảnh mặc định.")
        time.sleep(0.5)

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
            args=(i, lbl, auth_token, user_path, m, pic_info_raw, is_share, results),
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
# MAIN
# =============================================================================

def run(image_dir, dry_run=False):
    print("")
    print("{}{}".format(C.CYAN, "="*62))
    print("{}  KGVN  Mod Anh Load Tran  .  Multi-Account  v3.0     ".format(C.WHITE+C.BOLD))
    print("{}  JPG . PNG . WEBP . GIF . MP4  |  Sign Bridge          ".format(C.CYAN))
    print("{}  Auto Resize 1080x1701   |  COS per-poster creds       ".format(C.CYAN))
    print("{}{}".format(C.CYAN, "="*62) + C.RESET)

    if dry_run:
        print("\n" + "{}  [DRY RUN MODE - KHONG THUC HIEN]{}".format(C.YELLOW+C.BOLD, C.RESET))

    print("\n" + info("Kiem tra ket noi..."))
    if not check_connectivity():
        print(err("Khong co ket noi internet!")); sys.exit(1)
    print(ok("Mang OK"))

    print(info("Kiem tra Sign Bridge..."))
    bridge_path = _find_sign_bridge()
    if bridge_path:
        sb_ok = test_sign_bridge()
        if sb_ok:
            print(ok("Sign Bridge HOAT DONG ({})".format(Path(bridge_path).name)))
        else:
            print(warn("Sign Bridge KHONG HOAT DONG -> dung token HAR"))
    else:
        print(warn("Khong tim thay sign_bridge -> dung token HAR (van chay duoc)"))

    print("\n" + bold("--- Nhap Thong Tin ---"))
    auth_token = cinput("  Nhap Token (msdk-itopencodeparam): ")
    if not auth_token:
        print(err("  Token khong duoc de trong!")); sys.exit(1)

    print(info("  Dang lay thong tin account..."))
    user_path = get_user_path(auth_token)
    
    if not user_path:
        print(warn("Khong lay duoc user_path tu server, ban se phai nhap thu cong."))
        user_path = cinput("  Nhap user_path (vd: /1/704/xxxx/): ")
        if not user_path.startswith("/"): user_path = "/" + user_path
        if not user_path.endswith("/"): user_path += "/"

    print(ok("  Token hop le!"))
    print(dim("  user_path: {}".format(user_path)))

    selected = [{"token": auth_token, "user_path": user_path, "label": "Account-1", "har": ""}]
    n_acc = 1

    print("\n" + info("Quet media trong: " + image_dir))
    all_files = scan_media(image_dir)
    print("  Tim thay {} file:".format(len(all_files)))
    TYPE_COLORS = {
        ".jpg":  "{}JPG{}".format(C.YELLOW, C.RESET),
        ".jpeg": "{}JPG{}".format(C.YELLOW, C.RESET),
        ".png":  "{}PNG{}".format(C.CYAN,   C.RESET),
        ".webp": "{}WEBP{}".format(C.CYAN,  C.RESET),
        ".gif":  "{}GIF{}".format(C.GREEN+C.BOLD, C.RESET),
        ".mp4":  "{}MP4{}".format(C.PURPLE+C.BOLD, C.RESET),
    }
    for i, p in enumerate(all_files, 1):
        tc = TYPE_COLORS.get(p.suffix.lower(), p.suffix.upper())
        print("  {}[{}]{}  {}  {}  {:.1f} KB".format(C.YELLOW, i, C.RESET, tc, p.name, p.stat().st_size/1024))

    if len(all_files) == 1:
        img_mode = "2"
        print("\n" + info("1 file duy nhat -> tat ca acc dung chung."))
    else:
        if len(all_files) < n_acc:
            print("\n" + warn("{} file < {} acc -- mode 1 se lap vong anh.".format(len(all_files), n_acc)))
        img_mode = ask_choice("Che do phan cong media:",
            {"1": "Moi acc 1 bo rieng  (acc1->file1, acc2->file2, ...)",
             "2": "Tat ca acc dung chung  (toi da {} file/acc)".format(MAX_MEDIA_PER_ACC)})

    if img_mode == "1":
        print("\n  Phan cong (rieng):")
        for i, a in enumerate(selected):
            f = all_files[i % len(all_files)]
            print("    {}{}{}  ->  {}".format(C.CYAN, a["label"][:30], C.RESET, f.name))
    else:
        shared = all_files[:MAX_MEDIA_PER_ACC]
        print("\n" + info("Dung chung {} file: {}".format(len(shared), ", ".join(p.name for p in shared))))

    save_mode = ask_choice("Che do LUU:",
        {"1": "{}Luu rieng{}  (chi minh toi dung)".format(C.CYAN, C.RESET),
         "2": "{}Quang truong{}  (moi nguoi thay)".format(C.YELLOW, C.RESET)})
    is_share = (save_mode == "2")



    if PILLOW_OK:
        resize_ans = cinput("\n  Auto resize anh 1080x1701? (ENTER=Co / n=Khong): ").lower()
        do_resize = (resize_ans != "n")
    else:
        do_resize = False
        print(warn("  Pillow chua cai -> bo qua resize (pip install Pillow)"))

    print("\n" + info("Xu ly media truoc khi chay..."))
    shared_media = None
    if img_mode == "2":
        shared_files = all_files[:MAX_MEDIA_PER_ACC]
        shared_media = []
        for p in shared_files:
            print(info("  Xu ly: {}".format(p.name)))
            shared_media.append(prepare_media(p, auto_resize=do_resize))

    acc_media_map = {}
    for i, a in enumerate(selected):
        lbl = a["label"]
        if img_mode == "1":
            f = all_files[i % len(all_files)]
            print(info("  {} -> {}".format(lbl[:25], f.name)))
            acc_media_map[lbl] = [prepare_media(f, auto_resize=do_resize)]
        else:
            acc_media_map[lbl] = shared_media

    imgs_per    = len(shared_media) if img_mode == "2" else 1
    grand_total = imgs_per * n_acc
    print("\n  {} acc  ~  {}{}{}  poster tong".format(
        n_acc, C.CYAN+C.BOLD, grand_total, C.RESET))
    print(dim("  Stagger poster: {}s  |  Stagger acc: {}s".format(
        POSTER_STAGGER, ACC_STAGGER)))
    if do_resize:
        print(dim("  Auto Resize: {}ON{} (1080x1701)".format(C.GREEN, C.GRAY)))

    if not dry_run:
        confirm = cinput("\n  Nhap 'ok' de bat dau, Ctrl+C de huy: ")
        if confirm.lower() != "ok":
            print(err("Huy")); sys.exit(0)

    acc_results = {}
    threads     = []
    print("\n" + bold("Bat dau {} acc SONG SONG...".format(n_acc)))
    for a in selected:
        t = threading.Thread(
            target=acc_worker,
            args=(a, acc_media_map[a["label"]], is_share, acc_results),
            kwargs={"dry_run": dry_run},
            daemon=True,
        )
        threads.append(t)

    for t in threads:
        t.start()
        time.sleep(ACC_STAGGER)

    for t in threads:
        t.join()

    print("")
    print(sep(62, "=", C.CYAN))
    print("{}  TONG KET  ({} acc song song){}".format(C.WHITE+C.BOLD, n_acc, C.RESET))
    print(sep(62, "-", C.GRAY))
    grand_ok=grand_fail=0
    for a in selected:
        res = acc_results.get(a["label"],{"ok":0,"fail":0})
        ok_a, fail_a = res["ok"], res["fail"]
        grand_ok+=ok_a; grand_fail+=fail_a
        print("  {}{:<30}{}  {}OK:{:<4}{}  {}FAIL:{:<4}{}  TONG:{}".format(
            C.CYAN, a["label"][:30], C.RESET,
            C.GREEN, ok_a, C.RESET,
            C.RED, fail_a, C.RESET,
            ok_a+fail_a))
    print(sep(62, "-", C.GRAY))
    print("  {}TONG CONG:  OK={}{}{}  FAIL={}{}{}  /  {} poster{}".format(
        C.BOLD,
        C.GREEN, grand_ok, C.RESET+C.BOLD,
        C.RED, grand_fail, C.RESET+C.BOLD,
        grand_total, C.RESET))
    print(sep(62, "=", C.CYAN))
    print("\n  {}Mo game -> Anh load tran de thay!{}\n".format(C.CYAN, C.RESET))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="KGVN Mod Anh Load Tran - Multi-Account Tool v3.0",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "TINH NANG:\n"
            "  * JPG / PNG / WEBP / GIF / MP4\n"
            "  * Sign Bridge (dynamic encodeparam, fix -5001)\n"
            "  * Auto Resize 1080x1701\n"
            "  * Delay 3.6s stagger fix loi -1999 frequency limited\n"
            "  * Acc chay song song dong thoi\n"
            "  * COS credentials rieng cho moi poster\n"
            "\nCAI DAT:\n"
            "  pip install requests Pillow\n"
            "  # MP4: pkg install ffmpeg  hoac  apt install ffmpeg\n"
            "\nVI DU:\n"
            "  python loadtran.py\n"
            "  python loadtran.py --rounds 3\n"
            "  python loadtran.py --dir /sdcard/DCIM\n"
            "  python loadtran.py --test-sign\n"
            "  python loadtran.py --dry-run\n"
        ),
    )
    ap.add_argument("--dir",       default=".")

    ap.add_argument("--test-sign", action="store_true",
                    help="Test sign bridge roi thoat")
    ap.add_argument("--dry-run",   action="store_true",
                    help="Kiem tra config, khong thuc hien upload")
    args = ap.parse_args()

    if args.test_sign:
        print(info("Dang test Sign Bridge..."))
        _start_sign_bridge()
        time.sleep(2)
        ok_sb = test_sign_bridge()
        if ok_sb:
            print(ok("Sign Bridge HOAT DONG!"))
        else:
            print(err("Sign Bridge KHONG HOAT DONG"))
            print(warn("  Kiem tra: node sign_bridge.js  hoac  python sign_bridge_py.py"))
        sys.exit(0 if ok_sb else 1)

    run(args.dir, dry_run=args.dry_run)
