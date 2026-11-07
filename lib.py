import threading, json, requests, time, random, datetime, string, os
from anhcodeclick.ReQAPI import *

# Optional telegram support (botgay logic) - không bắt buộc
try:
    import telebot
except ImportError:
    telebot = None

ADMIN_ID = 7143607080          # ★ FIX: đổi admin ID mới
bot_tg = None

def init_bot(token):
    global bot_tg
    if telebot is None:
        return None
    bot_tg = telebot.TeleBot(token)
    return bot_tg

def _tg_send(chat_id, text, **kwargs):
    """Safe telegram send - no-op if bot_tg not initialized"""
    if bot_tg is None:
        return
    try:
        bot_tg.send_message(chat_id, text, **kwargs)
    except Exception:
        pass

key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])
 
host = ""
class File:
 @staticmethod
 def add(filename):
  try:
   res = requests.post("{0}/add-file?filename={1}".format(host, filename), timeout=10)
   if res.status_code == 200:
    return True, res.json().get("message", "File created")
   return False, ""
  except requests.RequestException as e: return False, ""
  except json.JSONDecodeError as e: return False, ""
  except Exception as e: return False, ""

 @staticmethod
 def delete(filename):
  try:
   res = requests.delete("{0}/del-file?filename={1}".format(host, filename), timeout=10)
   if res.status_code == 200:
    return True, res.json().get("message", "File deleted")
   return False, ""
  except Exception as e: return False, ""

 @staticmethod
 def check(filename):
  try:
   if host:
    res = requests.get("{0}/check?filename={1}".format(host, filename), timeout=10)
    if res.status_code == 200:
     content = res.json().get("content", "")
     return True, content if content else "[]"
   if os.path.exists(filename):
    with open(filename, "r", encoding="utf-8") as f:
     content = f.read().strip()
     return True, content if content else '{"bots": []}'
   return True, '{"bots": []}'
  except Exception as e: return False, '{"bots": []}'

 @staticmethod
 def edit(filename, content):
  try:
   content_str = json.dumps(content) if isinstance(content, (list, dict)) else content
   res = requests.put("{0}/edit-file?filename={1}".format(host, filename), data=content_str, timeout=10)
   if res.status_code == 200:
    return True, res.json().get("message", "File updated")
   return False, ""
  except Exception as e: return False, ""

class UserLikeLimit:
 filename = "user_likes_limit.json"
 @staticmethod
 def all(): return UserLikeLimit._load()
 @staticmethod
 def _load():
  ok, content = File.check(UserLikeLimit.filename)
  return json.loads(content) if ok else {}
 @staticmethod
 def _save(data):
  File.edit(UserLikeLimit.filename, data)

 @staticmethod
 def get(user_id: int):
  user_id = str(user_id)
  data = UserLikeLimit._load()
  today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
  info = data.get(user_id, {"count": 0, "limit": 3, "date": today})

  if info.get("date") != today:
   info["count"] = 0
   info["date"] = today
  allowed = info["count"] < info["limit"]
  if allowed: info["count"] += 1
  data[user_id] = info
  UserLikeLimit._save(data)
  return allowed, f"{info['count']}/{info['limit']}"

 @staticmethod
 def add(user_id: int, count: int):
  user_id = str(user_id)
  data = UserLikeLimit._load()
  today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
  data[user_id] = {"count": 0, "limit": count, "date": today}
  UserLikeLimit._save(data)



class GiftCode:
 filename = "giftcode.json"
 @staticmethod
 def _load():
  ok, content = File.check(GiftCode.filename)
  return json.loads(content) if ok else {}
 @staticmethod
 def _save(data):
  File.edit(GiftCode.filename, data)
 
 @staticmethod
 def generate_code():
  chars = string.ascii_uppercase + string.digits
  code = "G-" + ''.join(random.choices(chars, k=5))
  return code
 
 @staticmethod
 def create(time_str, max_uses, creator_id):
  data = GiftCode._load()
  code = GiftCode.generate_code()
  while code in data:
   code = GiftCode.generate_code()
  
  now = datetime.datetime.now()
  data[code] = {
   "time": time_str,
   "max_uses": max_uses,
   "used_count": 0,
   "used_by": [],
   "created_by": creator_id,
   "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
   "status": "active"
  }  
  GiftCode._save(data)
  return code
 

 @staticmethod
 def redeem(code, user_id):
  data = GiftCode._load()
  if code not in data: return False, "Mã giftcode không tồn tại!"
  gift = data[code]
  if gift["status"] != "active": return False, "Not available!"
  if gift["used_count"] >= gift["max_uses"]:
   return False, "Mã giftcode đã hết lượt sử dụng :))"
  if user_id in gift["used_by"]:
   return False, "Mày đã sử dụng mã giftcode này rồi!"
  gift["used_count"] += 1
  gift["used_by"].append(user_id)
  GiftCode._save(data)
  return True, gift["time"]
 
 @staticmethod
 def list_all():
  data = GiftCode._load()
  return data
 
 @staticmethod
 def delete_code(code):
  data = GiftCode._load()
  if code in data:
   del data[code]
   GiftCode._save(data)
   return True
  return False

class AdminManager:
 filename = "admin_list.json"
 _cached_data = None

 @staticmethod
 def _load():
  ok, content = File.check(AdminManager.filename)
  return json.loads(content) if ok else {}

 @staticmethod
 def _save(data):
  File.edit(AdminManager.filename, data)
  AdminManager._cached_data = data

 @staticmethod
 def refresh():
  AdminManager._cached_data = AdminManager._load()

 @staticmethod
 def add_admin(bot_id, admin_id):
  data = AdminManager._cached_data or AdminManager._load()
  bot_key = str(bot_id)
  if bot_key not in data:
   data[bot_key] = []
  if admin_id not in data[bot_key]:
   data[bot_key].append(admin_id)
   AdminManager._save(data)
   return True
  return False

 @staticmethod
 def is_admin(bot_id, user_id):
  default_admins = [4025977640]           # ★ FIX: đổi admin ID mới
  try:
   user_id = int(user_id)
  except (TypeError, ValueError):
   pass
  if user_id in default_admins:
   return True
  if AdminManager._cached_data is None:
   AdminManager._cached_data = AdminManager._load()

  data = AdminManager._cached_data
  bot_key = str(bot_id)
  return user_id in data.get(bot_key, [])

 @staticmethod
 def get_admins(bot_id):
  default_admins = [4025977640]           # ★ FIX: đổi admin ID mới
  if AdminManager._cached_data is None:
   AdminManager._cached_data = AdminManager._load()

  data = AdminManager._cached_data
  bot_key = str(bot_id)
  bot_admins = data.get(bot_key, [])
  return list(set(default_admins + bot_admins))

class UserRegister:
    filename = "user_register.json"
    _cache = None


    @staticmethod
    def _load():
        if UserRegister._cache is not None:
            return UserRegister._cache
        if not os.path.exists(UserRegister.filename):
            with open(UserRegister.filename, "w", encoding="utf-8") as f:
                json.dump({}, f)
        try:
            with open(UserRegister.filename, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = {}
        UserRegister._cache = data
        return data

    @staticmethod
    def _save(data):
        UserRegister._cache = data
        with open(UserRegister.filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

def grcolor(): return random.choice(["FFFF00", "00FF00", "87CEEB", "AAFF00"])
class data1200:
 def __init__(self, data):
  self.valid = False
  try:
   info = json.loads(protobuf_dec(data.hex()[10:])).get("5", {})
   if not isinstance(info, dict): return None
   PlayerId, ClientId, self.type = info.get("1"), info.get("2"), info.get("3")
   if self.type == 1: PlayerId, ClientId = info["1"], info["2"]
   elif self.type == 2: PlayerId = ClientId = info["1"]
   self.cid = ClientId
   self.uid = PlayerId
   self.name = info.get("9", {}).get("1", "")
   real_text = info.get("4", "")
   # FIX: trước đây hễ có field "8" là ghi đè CỨNG message thành "/bot", bỏ qua
   # luôn nội dung thật ở field "4" — khiến /start, /help, @admin-... không bao
   # giờ được đọc đúng (log luôn hiện msg='/bot' dù người dùng gõ gì đi nữa).
   # Giờ ưu tiên text thật nếu có, chỉ dùng "/bot" khi thực sự không có field "4".
   self.message = (real_text if real_text else ("/bot" if "8" in info else "")).lower()
   self.has_field4 = bool(real_text)
   self.has_field8 = "8" in info
   self.valid = True
  except Exception as e:
   self.cid = self.uid = self.name = self.message = self.type = None

def extract_uid_fields(data):
 uids, seen = [], set()
 def add_uid(value):
  if isinstance(value, str) and value.isdigit():
   value = int(value)
  if isinstance(value, int) and value not in seen:
   seen.add(value)
   uids.append(value)
 if "1" in data: add_uid(data["1"])
 if "5" in data and isinstance(data["5"], dict):
  field_5 = data["5"]
  if "1" in field_5: add_uid(field_5["1"])
  if "6" in field_5 and isinstance(field_5["6"], list):
   for item in field_5["6"]:
    if isinstance(item, dict) and "1" in item:
     add_uid(item["1"])
 return uids


def fstr(text):
 data = bytes([91, 34, 100, 225, 187, 165, 34, 44, 32, 34, 196, 145, 225, 187, 165, 34, 44, 32, 34, 225, 187, 139, 116, 34, 44, 32, 34, 195, 169, 111, 34, 44, 32, 34, 98, 195, 186, 34, 44, 32, 34, 225, 187, 147, 110, 34, 44, 32, 34, 225, 186, 183, 99, 34, 44, 32, 34, 225, 187, 165, 99, 34, 44, 32, 34, 196, 169, 34, 44, 32, 34, 99, 225, 186, 183, 99, 34, 44, 32, 34, 108, 225, 187, 147, 110, 34, 44, 32, 34, 98, 117, 225, 187, 147, 105, 34, 44, 32, 34, 108, 105, 195, 170, 110, 34, 44, 32, 34, 98, 117, 102, 102, 34, 44, 32, 34, 196, 145, 196, 169, 34, 44, 32, 34, 99, 97, 118, 101, 34, 44, 32, 34, 103, 195, 161, 105, 34, 44, 32, 34, 116, 114, 97, 105, 34, 44, 32, 34, 115, 101, 120, 34, 44, 32, 34, 120, 120, 120, 34, 44, 32, 34, 112, 111, 114, 110, 34, 44, 32, 34, 100, 117, 99, 107, 34, 44, 32, 34, 115, 104, 105, 116, 34, 44, 32, 34, 100, 97, 109, 110, 34, 44, 32, 34, 97, 100, 100, 101, 100, 34, 44, 32, 34, 116, 104, 225, 186, 177, 110, 103, 34, 44, 32, 34, 99, 111, 110, 34, 44, 32, 34, 109, 195, 160, 121, 34, 44, 32, 34, 116, 97, 111, 34, 44, 32, 34, 99, 104, 195, 179, 34, 44, 32, 34, 104, 101, 111, 34, 44, 32, 34, 108, 225, 187, 163, 110, 34, 44, 32, 34, 107, 104, 225, 187, 145, 110, 34, 44, 32, 34, 110, 225, 186, 161, 110, 34, 44, 32, 34, 196, 145, 105, 195, 170, 110, 34, 44, 32, 34, 104, 116, 116, 112, 34, 44, 32, 34, 110, 103, 117, 34, 44, 32, 34, 196, 145, 225, 186, 167, 110, 34, 44, 32, 34, 99, 195, 162, 109, 34, 44, 32, 34, 196, 145, 105, 225, 186, 191, 99, 34, 44, 32, 34, 113, 117, 195, 168, 34, 44, 32, 34, 99, 225, 187, 165, 116, 34, 44, 32, 34, 116, 225, 186, 173, 116, 34, 44, 32, 34, 110, 103, 117, 121, 225, 187, 129, 110, 34, 44, 32, 34, 115, 195, 186, 99, 34, 44, 32, 34, 109, 111, 100, 34, 44, 32, 34, 97, 100, 100, 34, 44, 32, 34, 99, 104, 101, 99, 107, 34, 44, 32, 34, 104, 97, 99, 107, 34, 44, 32, 34, 98, 117, 121, 34, 44, 32, 34, 103, 97, 121, 34, 44, 32, 34, 107, 105, 108, 108, 34, 44, 32, 34, 100, 105, 101, 34, 44, 32, 34, 100, 101, 97, 116, 104, 34, 44, 32, 34, 116, 101, 108, 101, 103, 114, 97, 109, 34, 44, 32, 34, 46, 34, 44, 32, 34, 109, 101, 115, 115, 97, 103, 101, 34, 44, 32, 34, 116, 105, 116, 116, 108, 101, 34, 44, 32, 34, 117, 105, 100, 34, 44, 32, 34, 110, 105, 99, 107, 34, 44, 32, 34, 100, 105, 34, 44, 32, 34, 98, 117, 34, 44, 32, 34, 225, 186, 183, 34, 44, 32, 34, 225, 187, 147, 34, 44, 32, 34, 195, 186, 34, 44, 32, 34, 225, 187, 165, 34, 44, 32, 34, 115, 112, 97, 109, 34, 44, 32, 34, 114, 101, 113, 117, 101, 115, 116, 34, 44, 32, 34, 112, 108, 97, 121, 101, 114, 34, 44, 32, 34, 99, 111, 100, 101, 34, 44, 32, 34, 97, 100, 100, 105, 110, 103, 34, 44, 32, 34, 103, 114, 105, 110, 103, 111, 34, 44, 32, 34, 102, 117, 99, 107, 34, 44, 32, 34, 98, 105, 116, 99, 104, 34, 44, 32, 34, 97, 115, 115, 104, 111, 108, 101, 34, 44, 32, 34, 105, 100, 105, 111, 116, 34, 44, 32, 34, 115, 116, 117, 112, 105, 100, 34, 44, 32, 34, 110, 111, 111, 98, 34, 44, 32, 34, 116, 114, 97, 115, 104, 34, 93])
 bad_words = [(w, w.lower()) for w in json.loads(data.decode())]
 res = []
 text_lower = text.lower()
 i = 0
 n = len(text)
 while i < n:
  if text[i] == "[":
   end = text.find("]", i)
   if end != -1:
    res.append(text[i:end+1])
    i = end + 1
    continue
  matched = False
  for word, word_lower in bad_words:
   word_len = len(word_lower)
   if i + word_len <= n and text_lower[i:i+word_len] == word_lower:
    res.append("😏".join(text[i:i+word_len]))
    i += word_len
    matched = True
    break
  if matched: continue
  if text[i].isdigit():
   start = i
   while i < n and text[i].isdigit():
    i += 1
   num = text[start:i]
   res.append("😏".join(num) if len(num) > 2 else num)
  else:
   res.append(text[i])
   i += 1
 return "".join(res)

def get_user_input(message):
 parts = message.split()
 if len(parts) < 2:
  return "[b][c][FFFF00]Vui lòng nhập ID.\nVí dụ: {} 12345678".format(
   message.split()[0]
  )
 return parts[1].strip()

def getavatar():
 AvatarList = [902000237]
 return random.choice(AvatarList)

def ChooseEmote(token, url):
 url = "{}/ChooseEmote".format(url)
 headers = {
  "ReleaseVersion": "OB55", "X-GA": "v1 1",
  "Authorization": "Bearer %s" % token}
 data = "5D 16 45 26 18 C5 DE 3E E8 F4 C5 36 03 7F 84 B7"
 res = requests.post(url, data=bytes.fromhex(data), headers=headers)
 return res.content

def ConfirmFriendRequest(uid, token, url):
 url = "{}/ConfirmFriendRequest".format(url)
 headers = {
  "ReleaseVersion": "OB55", "X-GA": "v1 1",
  "Authorization": "Bearer {}".format(token)}
 packet = pb_encode({1: int(uid), 2: 1})
 payload = AES_CBC128(packet, key, iv)
 res = requests.post(url, data=payload, headers=headers)
 return res.content

def RequestAddingFriend(uid, token, url, from_uid=None):
 url = "{}/RequestAddingFriend".format(url)
 headers = {
  "ReleaseVersion": "OB55", "X-GA": "v1 1",
  "Authorization": "Bearer {}".format(token)}
 packet = pb_encode({1: int(from_uid or 17963525335), 2: int(uid), 3: 22})
 payload = AES_CBC128(packet, key, iv)
 res = requests.post(url, data=payload, headers=headers)
 return res.content

def GetPlayerPersonalShow(uid, token, url):
 base = (url or "https://clientbp.ppmainecoonghj.com").rstrip("/")
 if "ggblueshark" in base or not base.startswith("http"):
  base = "https://clientbp.ppmainecoonghj.com"
 endpoint = "{}/GetPlayerPersonalShow".format(base)
 headers = {
  "ReleaseVersion": "OB55",
  "X-GA": "v1 1",
  "X-Ga-Sv": str(int(time.time())),
  "Authorization": "Bearer {}".format(token),
  "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9; ASUS_Z01QD Build/PI)",
  "Content-Type": "application/x-www-form-urlencoded",
  "Connection": "Keep-Alive",
  "Accept-Encoding": "gzip",
 }
 packet = pb_encode({1: int(uid), 2: 1})
 payload = AES_CBC128(packet, key, iv)
 res = requests.post(endpoint, data=payload, headers=headers, timeout=15)
 return res.content

def send_info(uid, token, base_url):
 """Info player — token bot + GetPlayerPersonalShow (khong API ngoai)."""
 try:
  uid = str(uid).strip()
  if not uid.isdigit():
   return "[B][c][FF0000]UID khong hop le"

  raw = GetPlayerPersonalShow(uid, token, base_url)
  if not raw or len(raw) < 4:
   return "[B][c][FF0000]API info empty\n[FFFFFF]uid: %s" % uid

  data = None
  for off in (0, 5, 10, 16, 32):
   try:
    hx = raw.hex() if isinstance(raw, bytes) else str(raw)
    chunk = hx[off * 2:] if off else hx
    parsed = json.loads(protobuf_dec(chunk))
    if isinstance(parsed, dict) and parsed:
     data = parsed
     break
   except Exception:
    continue
  if not isinstance(data, dict):
   return "[B][c][FF0000]Parse info fail\n[FFFFFF]uid: %s\n[AAAAAA]size=%s" % (uid, len(raw))

  def g(d, *path, default=None):
   cur = d
   for k in path:
    if not isinstance(cur, dict):
     return default
    cur = cur.get(str(k), cur.get(k))
    if cur is None:
     return default
   return cur if cur not in (None, "") else default

  def as_str(v):
   if v is None:
    return None
   if isinstance(v, bytes):
    try:
     return v.decode("utf-8", "ignore")
    except Exception:
     return str(v)
   if isinstance(v, dict):
    for kk in ("1", "3", 1, 3):
     if kk in v:
      return as_str(v[kk])
    return None
   if isinstance(v, (int, float)):
    return None  # so khong phai nickname/region
   s = str(v).strip()
   return s if s else None

  REGIONS = {
   "VN", "IND", "BR", "SG", "TH", "ID", "ME", "BD", "PK", "TW",
   "US", "NA", "SAC", "RU", "CIS", "EU", "MAX",
  }

  def find_region(obj, depth=0):
   """Chi lay chuoi region hop le (VN/IND/...), khong lay so."""
   if depth > 8:
    return None
   if isinstance(obj, str):
    s = obj.strip().upper()
    if s in REGIONS:
     return s
    return None
   if isinstance(obj, bytes):
    try:
     return find_region(obj.decode("utf-8", "ignore"), depth + 1)
    except Exception:
     return None
   if isinstance(obj, dict):
    # uu tien cac field thuong chua region
    for prefer in ("11", 11, "10", 10, "region", "PlayerRegion", "lockRegion"):
     if prefer in obj:
      r = find_region(obj[prefer], depth + 1)
      if r:
       return r
    for v in obj.values():
     r = find_region(v, depth + 1)
     if r:
      return r
   if isinstance(obj, list):
    for it in obj[:12]:
     r = find_region(it, depth + 1)
     if r:
      return r
   return None

  basic = g(data, "1") or {}
  if not isinstance(basic, dict):
   basic = {}
  profile = g(data, "2") or {}
  if not isinstance(profile, dict):
   profile = {}
  clan = g(data, "6") or g(data, "7") or {}
  if not isinstance(clan, dict):
   clan = {}

  name = (
   as_str(g(basic, "3")) or as_str(g(basic, 3))
   or as_str(g(profile, "3")) or as_str(g(data, "3"))
   or as_str(g(basic, "4")) or "?"
  )
  level = g(basic, "6") or g(basic, 6) or g(basic, "5") or g(basic, 5) or "?"
  likes = g(basic, "8") or g(basic, 8) or g(basic, "21") or "?"
  rank = (
   g(basic, "15") or g(basic, 15) or g(basic, "16") or g(basic, 16)
   or g(basic, "14") or "?"
  )
  # Region: CHI chuoi VN/IND/... — khong dung so (100 la field khac)
  region = find_region(data) or find_region(basic) or "VN"
  if isinstance(region, (int, float)) or (isinstance(region, str) and region.isdigit()):
   region = find_region(data) or "VN"

  exp = g(basic, "7") or g(basic, 7) or "?"
  clan_name = as_str(g(clan, "2")) or as_str(g(clan, 2)) or as_str(g(clan, "3")) or ""

  if likes == "?" and isinstance(basic, dict):
   for k, v in basic.items():
    if isinstance(v, int) and 50 <= v <= 5000000 and v not in (level, rank, exp):
     likes = v
     break

  clan_line = "\n[FFFFFF]clan: [FF69B4]%s" % clan_name if clan_name else ""
  return (
   "[B][C]Player Info\n"
   "[FFFFFF]uid: [FFFF00]%s\n"
   "[FFFFFF]name: [00FF00]%s\n"
   "[FFFFFF]level: [00BFFF]%s\n"
   "[FFFFFF]likes: [FFCC00]%s\n"
   "[FFFFFF]rank: [FF69B4]%s\n"
   "[FFFFFF]region: [87CEEB]%s"
   "%s"
  ) % (uid, name, level, likes, rank, region, clan_line)
 except Exception as e:
  return "[B][c][FF0000]Loi info: %s" % str(e)[:80]


def send_region(uid, token=None, base_url=None):
 """Region tu GetPlayerPersonalShow — khong can API ngoai."""
 uid = str(uid).strip()
 if not uid.isdigit():
  return "[B][c][FF0000]UID khong hop le"
 try:
  raw_msg = send_info(uid, token, base_url)
  if "Player Info" in raw_msg:
   name, region = "?", "?"
   for line in raw_msg.splitlines():
    if "name:" in line:
     idx = line.find("name:")
     name = line[idx + 5:].strip()
     for c in ("[00FF00]", "[FFFFFF]", "[B]", "[C]", "[c]"):
      name = name.replace(c, "")
    if "region:" in line:
     idx = line.find("region:")
     region = line[idx + 7:].strip()
     for c in ("[87CEEB]", "[00BFFF]", "[FFFFFF]", "[B]", "[C]", "[c]"):
      region = region.replace(c, "")
   return (
    "[B][C]Region Info\n"
    "[FFFFFF]uid: [FFFF00]%s\n"
    "[FFFFFF]name: [00FF00]%s\n"
    "[FFFFFF]region: [00BFFF]%s"
   ) % (uid, name, region)
  if any(x in raw_msg for x in ("Loi", "fail", "empty")):
   return raw_msg
  try:
   res = napthe(uid)
   if isinstance(res, dict):
    nick = res.get("nickname") or res.get("name") or "?"
    region = res.get("region") or res.get("server") or "locked"
    return (
     "[B][C]Region Info\n"
     "[FFFFFF]uid: [FFFF00]%s\n"
     "[FFFFFF]name: [00FF00]%s\n"
     "[FFFFFF]region: [00BFFF]%s"
    ) % (uid, nick, region)
  except Exception:
   pass
  return "[B][c][FF0000]Khong lay duoc region\n[FFFFFF]uid: %s" % uid
 except Exception as e:
  return "[B][c][FF0000]Loi region: %s" % str(e)[:80]


def napthe(uid):
 url = "https://napthe.vn/api/auth/player_id_login"
 payload = {}
 payload["app_id"] = 100067
 payload["login_id"] = str(uid)
 payload["app_server_id"] = 0x000
 payload = json.dumps(payload)

 headers = {}
 headers["Accept-Encoding"] = "gzip, deflate, br, zstd"
 headers["Accept"] = "application/json"
 headers["Referer"] = "https://napthe.vn/app/100067/idlogin"
 headers["Accept-Language"] = "vi-VN,vi;q=0.9"
 headers["User-Agent"] = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Mobile Safari/537.36"
 headers["Cookie"] = "datadome=9SKY0NQDmJskwyYecdQm4AwRLX5Cw6QGHXVojTXdB9zyO2XqhZi3yP6FPDZ8tBTHxKwCLlIYRUL35e_XKcYDT4Sr3shME1ZypsukSWpj0rHxPX6fzlfg242Azyw3wIjQ"

 response = requests.post(url, data=payload, headers=headers)
 if response.status_code !=200:
  return response.text
 return response.json()

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config(data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

config = load_config()
LIKE_NOTIFY_CHAT_ID = config.get("like_notify_chat_id", ADMIN_ID)  # Mặc định ADMIN_ID

like_total = 0
like_by_uid = {}
like_reset_time = None


def set_capture_chat(chat_id):
    global LIKE_NOTIFY_CHAT_ID
    LIKE_NOTIFY_CHAT_ID = chat_id
    config["like_notify_chat_id"] = chat_id
    save_config(config)
    try:
        _tg_send(chat_id, "📸 <b>Đã set box nhận thông báo!</b>", parse_mode='HTML')
    except:
        pass
    return f"✅ Đã set box nhận thông báo: {chat_id}"


def send_like(uid: str, key: str = "quametlon", timeout: int = 45):
    global like_total, like_by_uid, like_reset_time, LIKE_NOTIFY_CHAT_ID

    now = datetime.datetime.now()
    if like_reset_time is None:
        like_reset_time = now
    elif (now - like_reset_time).total_seconds() >= 86400:
        like_total = 0
        like_by_uid = {}
        like_reset_time = now
        print(f"[RESET] Counter reset at {now.strftime('%H:%M:%S')}")

    if not uid or not str(uid).strip().isdigit():
        return "[c][FF0000]Sai định dạng"

    uid = str(uid).strip()

    like_total += 1
    like_by_uid[uid] = like_by_uid.get(uid, 0) + 1
    call_count = like_by_uid[uid]
    total_count = like_total

    seconds_left = 86400 - (now - like_reset_time).total_seconds()
    hours_left = int(seconds_left // 3600)
    minutes_left = int((seconds_left % 3600) // 60)

    try:
        url = f"http://127.0.0.1:2026/likes?uid={uid}&key={key}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=timeout)

        if res.status_code != 200:
            return f"[c][FF0000]API ERROR - Code {res.status_code}"

        data = res.json()
        result = data.get("result", {})
        api_info = result.get("API", {})
        likes_info = result.get("Likes Info", {})
        user_info = result.get("User Info", {})

        success = api_info.get("Success", False)

        if success:
            player_name = user_info.get("Account Name", "Không tìm thấy")
            account_uid = user_info.get("Account UID", uid)
            account_region = user_info.get("Account Region", "Không rõ")
            account_level = user_info.get("Account Level", "Không rõ")
            likes_added = likes_info.get("Likes Added", 0)
            likes_before = likes_info.get("Likes Before", 0)
            likes_after = likes_info.get("Likes After", 0)
            speed = api_info.get("speeds", "Không rõ")

            try:
                tg_msg = (
                    f"Name: {player_name}\n"
                    f"UID: {account_uid}\n"
                    f"Level: {account_level}\n\n"
                    f"Likes Added: {likes_added}\n"
                    f"Likes Before: {likes_before}\n"
                    f"Likes After: {likes_after}\n"
                    f"Lượt dùng : {total_count}/100"
                )
                _tg_send(LIKE_NOTIFY_CHAT_ID, tg_msg)
            except Exception as e:
                print(f"[TG] Lỗi gửi tin: {e}")

            return (
                f"[C][B]───── ୨୧ ─────\n"
                f"[00BFFF]Send Like Oke La ,Ngon!\n\n"
                f"[FFFFFF]➟ Name : [FF0000]{player_name}\n"
                f"[FFFFFF]➟ UID : {account_uid}\n"
                f"[FFFFFF]➟ Khu Vực : {account_region}\n"
                f"[FFFFFF]➟ Level : {account_level}\n"
                f"[FFFFFF]➟ Likes Added : [FFFF00]{likes_added}\n"
                f"[FFFFFF]➟ Likes Before : [00FF33]{likes_before}\n"
                f"[FFFFFF]➟ Likes After : [FFCC00]{likes_after}\n"
                f"[FFFFFF]➟ Lượt dùng : [FF0000]{total_count}/100\n"
                f"[FFFFFF][C][B]───── ୨୧ ─────\n"
            )

        return "[c][b][i]Max Like Rồi Baby !"

    except requests.exceptions.Timeout:
        return "[c][b]Timeout Api Như Lồn"
    except requests.exceptions.ConnectionError:
        return "[c][b]No Connect Api"
    except ValueError:
        return "[c][b]No Pasre json"
    except Exception as e:
        return f"[c][b]Error: {str(e)}"

def send_like1(uid: str, key: str = "ditmoemay", timeout: int = 45):
    global like_total, like_by_uid, like_reset_time, LIKE_NOTIFY_CHAT_ID

    now = datetime.datetime.now()
    if like_reset_time is None:
        like_reset_time = now
    elif (now - like_reset_time).total_seconds() >= 86400:
        like_total = 0
        like_by_uid = {}
        like_reset_time = now
        print(f"[RESET] Counter reset at {now.strftime('%H:%M:%S')}")

    if not uid or not str(uid).strip().isdigit():
        return "[c][FF0000]Sai định dạng"

    uid = str(uid).strip()

    like_total += 1
    like_by_uid[uid] = like_by_uid.get(uid, 0) + 1
    call_count = like_by_uid[uid]
    total_count = like_total

    seconds_left = 86400 - (now - like_reset_time).total_seconds()
    hours_left = int(seconds_left // 3600)
    minutes_left = int((seconds_left % 3600) // 60)

    try:
        url = f"http://192.168.1.8:2026/likes?uid={uid}&key={key}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=timeout)

        if res.status_code != 200:
            return f"[c][FF0000]API ERROR - Code {res.status_code}"

        data = res.json()
        result = data.get("result", {})
        api_info = result.get("API", {})
        likes_info = result.get("Likes Info", {})
        user_info = result.get("User Info", {})

        success = api_info.get("Success", False)

        if success:
            player_name = user_info.get("Account Name", "Không tìm thấy")
            account_uid = user_info.get("Account UID", uid)
            account_region = user_info.get("Account Region", "Không rõ")
            account_level = user_info.get("Account Level", "Không rõ")
            likes_added = likes_info.get("Likes Added", 0)
            likes_before = likes_info.get("Likes Before", 0)
            likes_after = likes_info.get("Likes After", 0)
            speed = api_info.get("speeds", "Không rõ")

            try:
                tg_msg = (
                    f"Name: {player_name}\n"
                    f"UID: {account_uid}\n"
                    f"Level: {account_level}\n\n"
                    f"Likes Added: {likes_added}\n"
                    f"Likes Before: {likes_before}\n"
                    f"Likes After: {likes_after}\n"
                    f"Lượt dùng : {total_count}/100"
                )
                _tg_send(LIKE_NOTIFY_CHAT_ID, tg_msg)
            except Exception as e:
                print(f"[TG] Lỗi gửi tin: {e}")

            return (
                f"[C][B]───── ୨୧ ─────\n"
                f"[00BFFF]Send Like Oke La ,Ngon!\n\n"
                f"[FFFFFF]➟ Name : [FF0000]{player_name}\n"
                f"[FFFFFF]➟ UID : {account_uid}\n"
                f"[FFFFFF]➟ Khu Vực : {account_region}\n"
                f"[FFFFFF]➟ Level : {account_level}\n"
                f"[FFFFFF]➟ Likes Added : [FFFF00]{likes_added}\n"
                f"[FFFFFF]➟ Likes Before : [00FF33]{likes_before}\n"
                f"[FFFFFF]➟ Likes After : [FFCC00]{likes_after}\n"
                f"[FFFFFF]➟ Lượt dùng : [FF0000]{total_count}/100\n"
                f"[FFFFFF][C][B]───── ୨୧ ─────\n"
            )

        return "[c][b][i]Max Like Rồi Baby !"

    except requests.exceptions.Timeout:
        return "[c][b]Timeout Api Như Lồn"
    except requests.exceptions.ConnectionError:
        return "[c][b]No Connect Api"
    except ValueError:
        return "[c][b]No Pasre json"
    except Exception as e:
        return f"[c][b]Error: {str(e)}"

def reset_like_counter():
    global like_total, like_by_uid, like_reset_time
    like_total = 0
    like_by_uid = {}
    like_reset_time = None
    try:
        _tg_send(LIKE_NOTIFY_CHAT_ID, "🔄 <b>Đã reset bộ đếm like!</b>", parse_mode='HTML')
    except:
        pass
    return "🔄 Đã reset bộ đếm like!"

def get_player_status(data):
 status_info = {
 0: ("OFFLINE", "{}"),
 1: ("ONLINE", "{}"),
 2: ("In Squads", "{}"),
 3: ("In Games", "{}"),
 4: ("In Rooms", "{}"),
 5: ("In Games", "{}"),
 6: ("In Social Island Mode", "{}"),
 7: ("In Social Island Mode", "{}")
 }
 player = data.get("5", {}).get("1")
 if not player: return {"status": status_info[0][1].format(status_info[0][0])}
 uid = player.get("1")
 stt = player.get("3", 0)
 name, color = status_info.get(stt, ("null", "[AAAAAA]{}"))
 base = {"status": color.format(name), "uid": uid}
 if name == "In Squads":
  g, c = player.get("9"), player.get("10")
  if g is not None and c is not None: base["group"] = "{}/{}".format(g, c + 1)
 if name == "In Rooms":
  base["roomid"] = player.get("15")
 return base


def check_banned(uid):
 url = f"https://ff.garena.com/api/antihack/check_banned?lang=vi&uid={uid}"
 headers = {
   "Accept": "application/json, text/plain, */*",
   "authority": "ff.garena.com",
   "referer": "https://ff.garena.com/en/support/",
   "x-requested-with": "B6FksShzIgjfrYImLpTsadjS86sddhFH"}
 res = requests.get(url, headers=headers)
 if res.status_code == 200:
  data = res.json().get("data", {})
  is_banned = data.get("is_banned", 0)
  return True if is_banned else False
 return False


def send_likes(uid):
 try:
  url = f"cu"
  res = requests.get(url, timeout=15)

  if res.status_code != 200:
   return "[c][FF0000]API ERROR"

  data = res.json().get("result", {})

  api = data.get("API", {})
  likes = data.get("Likes Info", {})
  user = data.get("User Info", {})

  likes_added = likes.get("Likes Added", 0)
  likes_before = likes.get("Likes Before", 0)
  likes_after = likes.get("Likes After", 0)

  # nếu không tăng likes → MAX
  if not likes_added or likes_added == 0 or likes_before == likes_after:
   return f"""[b][c][FF0000]MAXX LIKES
   
[FF0000]Trạng thái: Đã đạt giới hạn likes hôm nay
[AAAAAA]Vui lòng thử lại vào ngày mai
"""

  result = f"""[b][c][00FF00]LIKES SENT SUCCESS

=>[ffffff] Nick UID: [00FFFF]{user.get('Account UID', uid)}
=>[ffffff] Nick Name: [00FFFF]{user.get('Account Name', 'null')}
=>[ffffff] Nick Region: [00FFFF]{user.get('Account Region', 'null')}
=>[ffffff] Nick Level: [00FFFF]{user.get('Account Level', 'null')}
=> [ffffff]Nick Before: [00FFFF]{likes_before}
=> [ffffff]Nick Likes After: [00FFFF]{likes_after}
=> [ffffff]Nick Likes Added: [00FFFF]{likes_added}
"""

  return result

 except Exception as e:
  return f"[c][FF0000]ERROR: {str(e)}"


def send_visit(uid):
 try:
  url = f"sit?region=vn&uid={uid}"
  res = requests.get(url, timeout=15)

  if res.status_code != 200:
   return "[c][FF0000]VISIT API ERROR"

  data = res.json()

  success = data.get("success", 0)
  fail = data.get("fail", 0)
  nickname = data.get("nickname", "null")
  region = data.get("region", "null")
  level = data.get("level", "null")
  likes = data.get("likes", "null")
  tokens_used = data.get("tokens_used", "null")
  token_rotation = data.get("token_rotation", "null")

  # nếu không gửi được visit
  if success == 0:
   return f"""[b][c][FF0000]VISIT FAILED

[FF0000]Không thể gửi visit cho UID: {uid}
[AAAAAA]Vui lòng thử lại sau
"""

  # thành công
  result = f"""[b][c][00FF00]VISIT SENT SUCCESS

[FFFF00]User Info:
Nick UID: {uid}
Nick Name: {nickname}
Nick Region: {region}
Nick Level: {level}
Nick Likes: {likes}

[FFFF00]Visit Info:
Visit Sent: {success}
Visit Fail: {fail}
"""

  return result

 except Exception as e:
  return f"[c][FF0000]VISIT ERROR"

get_history_grok = []