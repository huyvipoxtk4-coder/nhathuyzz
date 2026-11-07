#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KB TOOL - Free Fire Add Friend
Login: Majologin từ ReQAPI.py
Send KB: Friend Request với ID trong game FF
Updated headers đồng bộ với ReQAPI.py (Unity 2022.3.47f1)
"""

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from ReQAPI import FreeFireAPI, requests
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# Encrypt ID helper (by teelez)
# ============================================================
x_list = ['1','01','02','03','04','05','06','07','08','09','0a','0b','0c','0d','0e','0f',
          '10','11','12','13','14','15','16','17','18','19','1a','1b','1c','1d','1e','1f',
          '20','21','22','23','24','25','26','27','28','29','2a','2b','2c','2d','2e','2f',
          '30','31','32','33','34','35','36','37','38','39','3a','3b','3c','3d','3e','3f',
          '40','41','42','43','44','45','46','47','48','49','4a','4b','4c','4d','4e','4f',
          '50','51','52','53','54','55','56','57','58','59','5a','5b','5c','5d','5e','5f',
          '60','61','62','63','64','65','66','67','68','69','6a','6b','6c','6d','6e','6f',
          '70','71','72','73','74','75','76','77','78','79','7a','7b','7c','7d','7e','7f']
dec = ['80','81','82','83','84','85','86','87','88','89','8a','8b','8c','8d','8e','8f',
       '90','91','92','93','94','95','96','97','98','99','9a','9b','9c','9d','9e','9f',
       'a0','a1','a2','a3','a4','a5','a6','a7','a8','a9','aa','ab','ac','ad','ae','af',
       'b0','b1','b2','b3','b4','b5','b6','b7','b8','b9','ba','bb','bc','bd','be','bf',
       'c0','c1','c2','c3','c4','c5','c6','c7','c8','c9','ca','cb','cc','cd','ce','cf',
       'd0','d1','d2','d3','d4','d5','d6','d7','d8','d9','da','db','dc','dd','de','df',
       'e0','e1','e2','e3','e4','e5','e6','e7','e8','e9','ea','eb','ec','ed','ee','ef',
       'f0','f1','f2','f3','f4','f5','f6','f7','f8','f9','fa','fb','fc','fd','fe','ff']

def Encrypt_ID(x):
    """Encode UID thành dạng base128 (max 5 bytes => UID < 128^5)."""
    x = int(x) / 128
    if x > 128:
        x = x / 128
        if x > 128:
            x = x / 128
            if x > 128:
                x = x / 128
                strx = int(x)
                y = (x - strx) * 128; stry = int(y)
                z = (y - stry) * 128; strz = int(z)
                n = (z - strz) * 128; strn = int(n)
                m = (n - strn) * 128
                return dec[int(m)] + dec[int(n)] + dec[int(z)] + dec[int(y)] + x_list[int(x)]
            strx = int(x)
            y = (x - strx) * 128; stry = int(y)
            z = (y - stry) * 128; strz = int(z)
            n = (z - strz) * 128; strn = int(n)
            return dec[int(n)] + dec[int(z)] + dec[int(y)] + x_list[int(x)]
    return None

# ============================================================
# AES-CBC encrypt cho payload API (key/iv cố định của FF client)
# ============================================================
_FF_KEY = bytes([89,103,38,116,99,37,68,69,117,104,54,37,90,99,94,56])
_FF_IV  = bytes([54,111,121,90,68,114,50,50,69,51,121,99,104,106,77,37])

def encrypt_api(plain_text_hex: str) -> str:
    plain_text = bytes.fromhex(plain_text_hex)
    cipher = AES.new(_FF_KEY, AES.MODE_CBC, _FF_IV)
    return cipher.encrypt(pad(plain_text, AES.block_size)).hex()

# ============================================================
# Build headers thống nhất
# ============================================================
def build_headers(token: str, release_version: str, host: str) -> dict:
    """
    Headers đồng bộ với APIClient.session trong ReQAPI.py
    - Unity 2022.3.47f1
    - X-GA-SV: timestamp
    - Host: host của base_url (clientbp.ggpolarbear.com)
    """
    return {
        "User-Agent": "UnityPlayer/2022.3.47f1(UnityWebRequest/1.0,libcurl/8.5.0-DEV)",
        "X-Unity-Version": "2022.3.47f1",
        "X-GA": "v1 1",
        "X-GA-SV": str(int(time.time())),
        "ReleaseVersion": release_version,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept-Encoding": "deflate, gzip",
        "Accept": "*/*",
        "Authorization": f"Bearer {token}",
        "Host": host,
        "Connection": "Keep-Alive",
    }

def _host_from_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").split("/")[0]

# ============================================================
# LOGIN
# ============================================================
def login(uid, pw):
    """Đăng nhập qua Majologin"""
    try:
        api = FreeFireAPI()
        result = api.get(f"{uid}:{pw}")
        if result and "UserAuthToken" in result:
            name = result.get("UserNickName", "Unknown")
            token = result["UserAuthToken"]
            release_version = api.client.release_version

            # KB URL luôn dùng clientbp (đã test: loginbp=500, clientbp=200)
            kb_url = "https://clientbp.ggpolarbear.com/RequestAddingFriend"
            print(f"  📍 Server: {kb_url}")
            print(f"  📦 Release: {release_version}")
            return name, token, kb_url, release_version
    except Exception as e:
        print(f"  ❌ Login error: {e}")
    return None, None, None, None

# ============================================================
# SEND KB (Add Friend)
# ============================================================
def send_kb(uid_target, token, kb_url, release_version="OB55"):
    """Gửi KB (Friend Request) cho 1 UID"""
    encrypted_id = Encrypt_ID(uid_target)
    if not encrypted_id:
        return False, "Encrypt_ID failed (UID out of range)"

    # field 1 = account_id varint (tag 0x08), prefix "a7c4839f1e" giữ nguyên như bản gốc
    payload = f"08a7c4839f1e10{encrypted_id}1801"
    encrypted_payload = encrypt_api(payload)

    host = _host_from_url(kb_url)
    headers = build_headers(token, release_version, host)

    print(f"    🔍 UID target: {uid_target}")
    print(f"    🔍 EncryptedID: {encrypted_id}")
    print(f"    🔍 Payload hex: {payload}")
    print(f"    🔍 Token: {token[:30]}...")
    print(f"    🔍 ReleaseVersion: {release_version}")
    print(f"    🔍 Host: {host}")

    try:
        res = requests.post(
            kb_url,
            data=bytes.fromhex(encrypted_payload),
            headers=headers,
            timeout=15,
            verify=False
        )
        print(f"    📋 Status: {res.status_code}")
        print(f"    📋 Response: {res.text[:300]}")

        if res.status_code == 200:
            return True, "Gửi KB thành công!"
        elif res.status_code == 401:
            return False, "Token không hợp lệ hoặc đã hết hạn"
        elif res.status_code == 400:
            return False, f"Gửi thất bại. Server: {res.text[:200]}"
        elif res.status_code == 404:
            return False, "Không tìm thấy người chơi"
        elif res.status_code == 429:
            return False, "Rate limit - chậm lại"
        else:
            return False, f"Gửi thất bại. HTTP {res.status_code} | {res.text[:150]}"
    except Exception as e:
        return False, str(e)

# ============================================================
# REMOVE KB (Remove Friend)
# ============================================================
def remove_kb(uid_target, token, kb_url, release_version="OB55"):
    """Xóa bạn bè - Remove Friend"""
    encrypted_id = Encrypt_ID(uid_target)
    if not encrypted_id:
        return False, "Encrypt_ID failed (UID out of range)"

    # Payload: 1802 = Remove Friend (1801 = Add Friend)
    payload = f"08a7c4839f1e10{encrypted_id}1802"
    encrypted_payload = encrypt_api(payload)

    remove_url = kb_url.replace("RequestAddingFriend", "RemoveFriend")
    host = _host_from_url(remove_url)
    headers = build_headers(token, release_version, host)

    print(f"    🔍 UID target: {uid_target}")
    print(f"    🔍 EncryptedID: {encrypted_id}")
    print(f"    🔍 Payload hex: {payload}")
    print(f"    🔍 URL: {remove_url}")
    print(f"    🔍 Host: {host}")

    try:
        res = requests.post(
            remove_url,
            data=bytes.fromhex(encrypted_payload),
            headers=headers,
            timeout=15,
            verify=False
        )
        print(f"    📋 Status: {res.status_code}")
        print(f"    📋 Response: {res.text[:300]}")

        if res.status_code == 200:
            return True, "Xóa thành công!"
        elif res.status_code == 401:
            return False, "Token không hợp lệ hoặc đã hết hạn"
        elif res.status_code == 400:
            return False, f"Xóa thất bại. Server: {res.text[:200]}"
        elif res.status_code == 404:
            return False, "Người chơi không có trong danh sách bạn bè"
        elif res.status_code == 429:
            return False, "Rate limit - chậm lại"
        else:
            return False, f"Xóa thất bại. HTTP {res.status_code} | {res.text[:150]}"
    except Exception as e:
        return False, f"Lỗi khi xóa: {str(e)}"

# ============================================================
# MAIN
# ============================================================
def main():
    print()
    print("  ╔══════════════════════════════════════╗")
    print("  ║    KB TOOL - Free Fire Add Friend    ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    # Bước 1: Đăng nhập
    my_uid = input("  [?] UID của bạn: ").strip()
    my_pw  = input("  [?] Password: ").strip()

    print("\n  ⏳ Đang đăng nhập...")
    name, token, kb_url, release_version = login(my_uid, my_pw)

    if not token:
        print("  ❌ Sai UID/Password hoặc lỗi mạng!")
        return

    print(f"  ✅ Đăng nhập thành công: {name}")

    # Bước 2: Chọn chế độ
    print("\n  ┌─ Chọn chế độ ──────────────────┐")
    print("  │ 1. Gửi KB (Add Friend)         │")
    print("  │ 2. Xóa bạn bè (Remove Friend)  │")
    print("  └────────────────────────────────┘")
    mode = input("\n  [?] Chọn (1/2): ").strip()

    if mode not in ["1", "2"]:
        print("  ❌ Lựa chọn không hợp lệ!")
        return

    # Bước 3: Nhập UID
    if mode == "1":
        print("\n  📤 Chế độ: GỬI KB (Add Friend)")
    else:
        print("\n  🗑️  Chế độ: XÓA BẠN BÈ (Remove Friend)")

    targets = input("  [?] UID(s) (cách nhau dấu phẩy): ").strip()
    if not targets:
        print("  ❌ Không có UID!")
        return

    uid_list = [u.strip() for u in targets.split(",") if u.strip()]
    action = "gửi KB" if mode == "1" else "xóa"
    print(f"\n  📤 Đang {action} {len(uid_list)} UID...\n")

    # Bước 4: Xử lý lần lượt
    ok_count = 0
    for i, uid_t in enumerate(uid_list, 1):
        if mode == "1":
            ok, info = send_kb(uid_t, token, kb_url, release_version)
        else:
            ok, info = remove_kb(uid_t, token, kb_url, release_version)

        if ok:
            ok_count += 1

        icon = "✅" if ok else "❌"
        print(f"  {icon} [{i}/{len(uid_list)}] UID {uid_t} -> {info}")
        if i < len(uid_list):
            time.sleep(1.5)

    print(f"\n  ═══ DONE: {ok_count}/{len(uid_list)} thành công ═══")

if __name__ == "__main__":
    main()