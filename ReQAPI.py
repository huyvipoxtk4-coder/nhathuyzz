# -*- coding: utf-8 -*-
import requests, json, base64, time, struct, datetime, re
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from protobuf_decoder.protobuf_decoder import Parser
from typing import Dict, Any, Optional, Tuple, Union, TypedDict, List
from dataclasses import dataclass
from enum import IntEnum
import hashlib


_XK = bytes([
    0x75, 0x5A, 0x5F, 0x54, 0x10, 0x08, 0x08, 0x4F, 0x06, 0x03, 0x0B,
    0x0A, 0x55, 0x02, 0x02, 0x01, 0x0E, 0x0E, 0x03, 0x06, 0x51, 0x02,
    0x0A, 0x04, 0x50, 0x06, 0x02, 0x5C, 0x59, 0x03, 0x50, 0x51, 0x57,
    0x55, 0x05, 0x51, 0x52, 0x02, 0x0D, 0x5A, 0x10, 0x02, 0x02, 0x4F,
    0x76, 0x5E, 0x43, 0x45, 0x4A, 0x11, 0x08, 0x1F, 0x02, 0x1A, 0x10,
    0x02, 0x01, 0x4F, 0x1A, 0x41, 0x69, 0x72, 0x5F, 0x54, 0x43, 0x77,
    0x72, 0x5D, 0x55, 0x48, 0x66, 0x7A, 0x48, 0x18, 0x5A, 0x5C, 0x4B,
    0x06, 0x51, 0x44, 0x42, 0x69, 0x55, 0x69, 0x62, 0x0E, 0x10, 0x02,
])

def _xb(d: bytes) -> bytes:
    kl = len(_XK)
    return bytes(d[i] ^ _XK[i % kl] for i in range(len(d)))

def _d(tok: str) -> str:
    try:
        pad_ = "=" * (-len(tok) % 4)
        return _xb(base64.urlsafe_b64decode(tok + pad_)).decode("utf-8")
    except Exception:
        return ""

def _e(s: str) -> str:
    return base64.urlsafe_b64encode(_xb(s.encode("utf-8"))).decode("ascii")



_CFG_B64 = (
    "Dng0dioqPXYwNDk8YjY0Mjw7NzJlNz0xZj4xams2ZTBhZjA0YTovdjJrIHVUbXVzLCYxKmMuJDUzfChyW0ZqZ3BAS2tmfl5MKSw-bn4kfWYhGndTQDx1Z0FuZ2UpbTEtMjYyMm02NzA6PzMwZmA4PGEwMG1hNGQ1ZzEwNWVja2N0OmR4E25zJnt0PSs1KyVgNisrJFpQc3Y2KAQ4J2pcWCBsLiw4PH5rNAwnGgthfiwSPSg8eXxtJ2d0YCQ2bW8uYmd1Y350b3Z-dmosey9yJAgydzA8di9gMmp2OwYteWplcH1rajR3Y3MqdCBHETA5bBgTKCEgSR09fSkoZHI-LycHeg4Qb352V3Z9IU9hZjx2Zmh-dzggaXp6c3VrLSVlJXJqcj5iIjQ5NCsyPW8iNXF3didZKiwuL38ndmxpYGdiOzhtSxoAIiYFUGd3PgMIO3E1MmVhNjMqACEMCm9naVs5MDkyJConWW9kbTxsIDssYmxhOGxodH52cjE4aj40NDpqPzVqZ3RzbW9tWnwiNSNOYHBxbjI4Iyx2KAwcKzYzWQItOCkPFC17NTMlYTkubAo6BEAiMncUBSo6eXxxbTwhXmQ8dntRYm96YyMtODRhPixodzJiN2Z1LQQ8a3kjR2dgHRMvNiA5ZScuLCo8Im0meCIcADN7e1lHc2VlIj8eMXhwaXMwGzocOwAWdzI4V2hvZSgmPGE3MW07dy4gaWF9d1k3Y2ZoMmdhN3s5cjkjIXUiaC0iNn9layEULm01Onxpdmx_c21uIX0pA1w8Oy5YUHF3LAMMaiIhfiR1Di0sDzpLWCxRbBEoMD10KEccJjorJXVDUkgjPDsmeVZaNREoMG5pNWJleWU0ZX1RNGooR1oXJWwBEgsjIT0uOHRndyZ5JDYUMCYuVUh_HSkIHiB9NjhpKnMnIxsnAAd8MjhXDBYaUVhAAEhGKSZ3bGd1eWFxbQ52c3Q1JDh-DkoWGHV5JyIxcGg_fl11bUxndXVmM3t8cH91bF4nOHtcRm94YRMCNHdyREt-KHhwaWUhMR0AOw8NLCogNAgSIicoXglWdTgqG0dNTy5yIzRhMjokLCY2fnUhIjA6CmgzcDg-YyQyLm0RLjZncDNJe3B_fm0hZ04MQFJqYHNVXn8yJDkfJn8zMi4ka2YNGTAHJUIwRyZ6bHoiKCB7KDYlOnUvIkN7Z29icTE7KmAoM2xoLWJgZGAsc34gfi5_cGcQHzphf2hWZ3BldnV-N30qd10RbmJuEkA4Y2VSQn4vdz0uMWZpIVk3WFM8IzRHbTs2MiQqPWNiZ1U8ciA7LD8tM2IsOzJkKDtqey9yPTY7Yg4gZ2ozf2wgdVQoLWdmM2x6dHNzZ14pdTMEQH1uYT8TMzEgAxYsOnZ-L2MnLSEMCgQNanVuV2B9J3FlezpoZCtZGC9ROD42RiR9IH9tNFkwfmMhBh91eScyM3B_M3VwXX1UZGETA19JT0pVXkcjYzgvDAYoOzEcLW93ckQtAV4TfmckNSE0ADYMPWd0XR07LDwyMip4MjEzaGc3MWVraGA3ZzY6NWhlNGxtYmE0NTdjNDBma3g8IG8qGwE3Kj5wZD04KyI6OXcsbUsfOjkcFgQ8PCREQHkpbWt-MH1mLww4NgR8dWdXYGhtKTAkbWtmZlU3d2QjNDs0MWMuKGk1a10_OGA4NDN3P2BgNj5oJi4gIhMzHDF4MzIuMCIoOjdjOCwMHwAgcFVIbGd8VUh-NHgxLmsOMHZLb1hQNig6Q3Z9OHlqVz9nd2MobyAtZW96YikwcnorM2lvcj13I38xJ2A0NGt_P2RqLwAYCxZ9AVxPZV1efTFZOFsbXzgtAhJKT3I5IQRVKWo3an8kfWYjGT42Cm9jaioqPiB4KjJtZDtuOjZmN2Q8NzZjNGc-NjYzOmppZ2Myb2NgZWoxaT5sLWYuAj9sJDphJ3xtdz5mdTw0JxsXOjIqBRcpPWUpFB1NYhcGQSsbBgRmMRVPSjQ_KAkFLTUnLWdwbiQ0cmkjIixlajBlVT1iJDhkbzZnfXUxYCc7YWgFZG1pKhh8eWcBYHtXVihGczF4SnEkNioZehYAKTYDNA8sdSwxZEcrEHYFITErZ150LQNoDCJ5bHwtR0JbMntrSEpEb0R-ZmtXYWhtKA1tIAktJzASFk5jFWhjMQgYBgspC3R-RSlWdU5seSgoByMIPxozK2gveBc-ajR4NC5-DnVyW3dTQDojN0ZubmUlODp6ZzNuOmA2NzE9Ozc3ZzdrMWE3MGk6MmBnNWVhZGI3bm8hMmR4QGsicXwkOyljKyA3NH8rdAxDaWInQhZtY3tfWGQ6PDAqYQ51cl13U1M9IjNHdn03dGZXOnRveChvIGp1en5wPH4tbmh-YW8_d2UiNDIzbCM3b2I4eW5nYRUxLmomeH56LVtSSm47TzENEysxMFgONSE8FglyN3U_JHQ0aSUENkcEfHVnEzMtMX1naiZqZiVpOm8tbWd4ZikQQEJrJFNyODh3NSJ4KTI3NGNubCA1ZylEZydyLHc9e2ArJWQxLnhxCxE7MnRBUHF3OwMJO3E1MhRuMDcqS29LUyAlZkNsazBzPjEqPmFpa2UwIHxz"
)

def _load_cfg() -> dict:
    """Decode blob cfg → dict. Trả {} nếu lỗi."""
    try:
        raw = _xb(base64.urlsafe_b64decode(_CFG_B64 + "=" * (-len(_CFG_B64) % 4)))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}

_CFG = _load_cfg()



_FM_RAW = {
    3:  "dGltZXN0YW1w",
    4:  "YXBwX25hbWU",
    5:  "ZmxhZ181",
    7:  "ZmZfdmVyc2lvbg==",
    8:  "b3NfaW5mbw==",
    9:  "ZGV2aWNlX2Zvcm0=",
    10: "Y2Fycmllcg==",
    11: "bmV0d29ya190eXBl",
    12: "c2NyZWVuX3c=",
    13: "c2NyZWVuX2g=",
    14: "ZHBp",
    15: "Y3B1X2luZm8=",
    16: "cmFtX21i",
    17: "Z3B1",
    18: "Z2xfZW5naW5l",
    19: "c3RvcmVfaWQ=",
    20: "cmVhbF9pcA==",
    21: "bGFuZ19yZWdpb24=",
    22: "dWlkX2hhc2g=",
    23: "ZmxhZ18yMw==",
    24: "ZGV2aWNlX2Zvcm0y",
    25: "ZGV2aWNlX21vZGVs",
    26: "dWlkXzI=",
    29: "aW50ZWdyaXR5X2hhc2g=",
    30: "ZmxhZ18zMA==",
    41: "Y2Fycmllcl8y",
    42: "bmV0d29ya18y",
    57: "ZGV2aWNlX2lkX2hhc2g=",
    60: "bWVtX3RvdGFs",
    61: "bWVtX2F2YWls",
    62: "bWVtX2ZyZWU=",
    63: "bWVtX2J1Zg==",
    64: "bWVtX2NhY2hlZA==",
    65: "bWVtX3Qy",
    66: "bWVtX3Qz",
    67: "bWVtX3Q0",
    73: "ZmxhZ183Mw==",
    74: "bGliX3BhdGg=",
    76: "ZmxhZ183Ng==",
    77: "YXBrX2hhc2hfcGF0aA==",
    78: "ZmxhZ183OA==",
    79: "ZmxhZ183OQ==",
    81: "YXJjaF9iaXRz",
    83: "YnVpbGRfZGF0ZQ==",
    85: "ZmllbGRfODU=",
    86: "Z2xfYXBp",
    87: "Z2xfZXh0X2ZsYWdz",
    88: "ZmxhZ184OA==",
    92: "ZmxhZ185Mg==",
    93: "cGxhdGZvcm0=",
    94: "ZGV2aWNlX3Rva2Vu",
    95: "ZmxhZ185NQ==",
    96: "c2RrX2pzb24=",
    97: "ZmxhZ185Nw==",
    98: "ZmxhZ185OA==",
    99: "ZmxhZ185OQ==",
    100: "bG9naW5fc2Vx",
    102: "ZW5jcnlwdGVkX2Jsb2I=",
    104: "ZmxhZ18xMDQ=",
    105: "ZmxhZ18xMDU=",
    106: "Y2RuX3VybHM=",
    107: "c2Vzc2lvbl9oYXNo",
}
FIELD_MAP = {k: _d(v) for k, v in _FM_RAW.items()}




def _get_key() -> bytes:
    h = _CFG.get("k")
    if h:
        try: return bytes.fromhex(h)
        except Exception: pass
    return bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])

def _get_iv() -> bytes:
    h = _CFG.get("i")
    if h:
        try: return bytes.fromhex(h)
        except Exception: pass
    return bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

def _get_client_secret() -> str:
    v = _CFG.get("cs")
    if v: return v
    return ("2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3")

def _get_url(name: str, fallback: str) -> str:
    return _CFG.get(name) or fallback

def _get_dev(key: str, fallback):
    d = _CFG.get("dev") or {}
    v = d.get(key)
    return v if v is not None else fallback


class ProtoBuf:
 def __init__(self, data):
  self.data = data

 def varint(self, buffer: bytes, pos: int = 0) -> Tuple[int, int]:
  result, shift = 0, 0
  while shift < 64 and pos < len(buffer):
   byte = buffer[pos]
   pos += 1
   result |= (byte & 0x7F) << shift
   if not (byte & 0x80):
    return result, pos
   shift += 7
  return result, pos

 def repeated(self, data: bytes) -> List[int]:
  pos, out = 0, []
  while pos < len(data):
   val, pos = self.varint(data, pos)
   out.append(val)
  return out

 def string(self, buffer: bytes, pos: int) -> Tuple[str, int]:
  length, pos = self.varint(buffer, pos)
  newpos = min(pos + length, len(buffer))
  value = buffer[pos:newpos]
  try: value = value.decode("utf-8")
  except: pass
  return value, newpos

 def fixed32(self, buffer: bytes, pos: int) -> Tuple[int, int]:
  return (struct.unpack("<I", buffer[pos:pos + 4])[0], pos + 4) if pos + 4 <= len(buffer) else (0, pos)

 def fixed64(self, buffer: bytes, pos: int) -> Tuple[int, int]:
  return (struct.unpack("<Q", buffer[pos:pos + 8])[0], pos + 8) if pos + 8 <= len(buffer) else (0, pos)

 def parse_field(self, buffer: bytes, pos: int) -> Tuple[int, Any, int]:
  if pos >= len(buffer): return 0, None, pos
  key, pos = self.varint(buffer, pos)
  field_number, wire_type = key >> 3, key & 0x7
  try:
   if wire_type == 0: value, pos = self.varint(buffer, pos)
   elif wire_type == 1: value, pos = self.fixed64(buffer, pos)
   elif wire_type == 2: value, pos = self.string(buffer, pos)
   elif wire_type == 5: value, pos = self.fixed32(buffer, pos)
   else: return field_number, None, pos
  except (struct.error, IndexError):
   return field_number, None, pos
  return field_number, value, pos

 def protobuf(self, buffer: Optional[bytes] = None, offset: int = 0) -> Dict[str, Any]:
  if buffer is None:
   buffer = self.data
  result = {}
  while offset < len(buffer):
   field_number, value, offset = self.parse_field(buffer, offset)
   if isinstance(value, bytes) and value:
    try:
     nested = self.protobuf(value)
     if nested: value = nested
    except: pass
   key = str(field_number)
   result.setdefault(key, []).append(value)
  return {k: v[0] if len(v) == 1 else v for k, v in result.items()}

 def fieldsRaw(self, buf: bytes, pos: int) -> Tuple[int, int, bytes, int, int]:
  start = pos
  key, pos = self.varint(buf, pos)
  num, wt = key >> 3, key & 0x7
  if wt == 0: _, end = self.varint(buf, pos)
  elif wt == 1: end = pos + 8
  elif wt == 2:
   length, lp = self.varint(buf, pos)
   end = lp + length
  elif wt == 5: end = pos + 4
  else: return num, wt, b'', pos, pos
  return num, wt, buf[start:end], pos, end

 def EXTRACT_FIELDS(self, fields: List[int], mode: str = "repeated") -> List:
  cur = self.data
  for depth, target in enumerate(fields):
   pos = 0; found = False
   if depth == len(fields) - 1:
    results = []
    while pos < len(cur):
     num, wt, raw, val_start, val_end = self.fieldsRaw(cur, pos)
     if num == target:
      if mode == "repeated":
       if wt == 0:
        val, _ = self.varint(cur, val_start)
        results.append(val)
       elif wt == 2:
        _, lp = self.varint(cur, val_start)
        packed = cur[lp:val_end]
        results += self.repeated(packed)
      elif mode == "bytes":
       if wt == 2:
        _, lp = self.varint(cur, val_start)
        results.append(cur[lp:val_end])
       else:
        results.append(cur[val_start:val_end])
     pos = val_end
    if len(results) == 0: return []
    if len(results) == 1: return results[0]
    return results
   else:
    while pos < len(cur):
     num, wt, raw, val_start, val_end = self.fieldsRaw(cur, pos)
     if num == target and wt == 2:
      _, lp = self.varint(cur, val_start)
      cur = cur[lp:val_end]
      found = True; break
     pos = val_end
    if not found: return []
  return []


def Encrypt(value):
 value = int(value)
 result = []
 while value > 0x7F:
  result.append((value & 0x7F) | 0x80)
  value >>= 7
 result.append(value)
 return bytes(result)

def Decrypt(value):
 result, shift = 0, 0
 for byte in bytes.fromhex(value):
  result |= (byte & 0x7F) << shift
  if not (byte & 0x80):
   break
  shift += 7
 return result

def parse_results(parsed_results):
 result_dict = {}
 for result in parsed_results:
  if result.field not in result_dict:
   result_dict[result.field] = []
  field_data = {}
  if result.wire_type in ["varint", "string", "bytes"]:
   field_data = result.data
  elif result.wire_type == "length_delimited":
   field_data = parse_results(result.data.results)
  result_dict[result.field].append(field_data)
 return {
  key: value[0] if len(value) == 1
  else value for key, value in result_dict.items()
  }

protobuf_dec = lambda data: json.dumps(parse_results(
 Parser().parse(data)
 ), ensure_ascii=False)

def AES_CBC128(data, key, iv):
 cipher = AES.new(key, AES.MODE_CBC, iv)
 return cipher.encrypt(pad(data, 0x10))

def _scalar(v):
 while isinstance(v, (list, tuple)) and v:
  v = v[0]
 return v

def _as_bytes(v):
 v = _scalar(v)
 if v is None: return None
 if isinstance(v, bytes): return v
 if isinstance(v, bytearray): return bytes(v)
 if isinstance(v, str): return v.encode("latin-1")
 if isinstance(v, (list, tuple)):
  try: return bytes(v)
  except Exception: return None
 return None

def create_varint_field(field_number, value):
 field_header = (field_number << 3) | 0
 return Encrypt(field_header) + Encrypt(value)

def create_length_delimited_field(field_number, value):
 field_header = (field_number << 3) | 2
 encoded_value = value.encode() if isinstance(value, str) else value
 return Encrypt(field_header) + Encrypt(len(encoded_value)) + encoded_value

def pb_encode(fields):
 packet = bytearray()
 for field, value in fields.items():
  field = int(field)
  if isinstance(value, list):
   for item in value:
    if isinstance(item, dict):
     packet.extend(create_length_delimited_field(field, pb_encode(item)))
  elif isinstance(value, dict):
   nested_packet = pb_encode(value)
   packet.extend(create_length_delimited_field(field, nested_packet))
  elif isinstance(value, int):
   packet.extend(create_varint_field(field, value))
  elif isinstance(value, str) or isinstance(value, bytes):
   packet.extend(create_length_delimited_field(field, value))
 return bytes(packet)

class gayerr(Exception): pass

@dataclass
class account_data:
 access_token = ""
 open_id = ""
 platform = 0x4
 login_platform = 0x4
 main_active_platform = 0x4
 chat_ip = chat_port = online_ip = online_port  = ""
 create_time = None
 expiry_time = None
 guild_id = None
 guild_code = None
 login_token  = None
 account_id = None
 server = None
 base_url = None
 login_time = None
 key = None
 iv = None


class gringay:
 @staticmethod
 def tokendecode(token):
  try:
   parts = token.split(".")
   if len(parts) != 3: raise gayerr("Invalid token format")
   payload = parts[1]
   payload += "=" * (0x4 - len(payload) % 0x4)
   return json.loads(base64.urlsafe_b64decode(payload).decode('utf-8'))
  except (ValueError, json.JSONDecodeError) as e: pass
 
 @staticmethod
 def format_timestamp(timestamp):
  if timestamp is None: return ""
  return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(timestamp))

def storeApps(package):
 try:
  I = requests.get("https://play.google.com/store/apps/%s" % package, timeout=10)
  I = re.search(r'\[\[\["(\d+\.\d+\.\d+)"\]\]', I.text)
  if I: return I.group(1)
 except Exception:
  pass
 return None

def bdversion(ver: str = None):
    try:
        if not ver:
            ver = "1.132.11"
        url = _get_url("u_ver", "https://version.ggwhitehawk.com/live/ver.php")
        url = (
            f"{url}"
            f"?version={ver}"
            f"&lang=vn&device=android&channel=android"
            f"&appstore=googleplay&region=VN"
            f"&release_version=OB55"
            f"&whitelist_version=1.8.0&whitelist_sp_version=1.0.0"
            f"&device_name=samsung%20SM-S908E"
            f"&device_CPU=ARMv7%20VFPv3%20NEON"
            f"&device_GPU=Adreno%20%28TM%29%20540"
            f"&device_mem=3940"
        )
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "deflate, gzip",
            "Content-Type": "application/x-www-form-urlencoded",
            "Host": _CFG.get("h_ver") or "version.ggwhitehawk.com",
            "User-Agent": _CFG.get("ua_unity") or "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
            "X-GA-SV": str(int(time.time())),
            "X-Unity-Version": _CFG.get("ua_xunity") or "2018.4.12f1",
        }
        r = requests.get(url, headers=headers, verify=False, timeout=10).json()
        data = {
            "server_url": r['server_url'],
            "latest_release_version": r.get('latest_release_version') or "OB55",
            "remote_version": r.get('remote_version') or ver
        }
        return data
    except Exception as e:
        return {
            "server_url": _CFG.get("host_fallback") or "https://loginbp.ppmainecoonghj.com/",
            "latest_release_version": "OB55",
            "remote_version": "1.132.11"
        }

class APIClient:
 def __init__(self):
  self._data = account_data()
  self.logindata = {}
  detail_vers = bdversion()
  self.is_emulator = False
  self.language = "vn"
  self.base_url = detail_vers["server_url"]
  self.client_version = detail_vers.get("remote_version") or "1.132.11"
  self.release_version = detail_vers.get("latest_release_version") or "OB55"
  self.key = _get_key()
  self.iv  = _get_iv()
  host_name = _CFG.get("h_login") or "loginbp.ppmainecoonghj.com"
  self.session = requests.Session()
  self.session.headers.update({
   "User-Agent": _CFG.get("ua_unity") or "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
   "X-GA": "v1 1",
   "X-GA-SV": str(int(time.time())),
   "Content-Type": "application/x-www-form-urlencoded",
   "Accept-Encoding": "deflate, gzip",
   "Accept": "*/*",
   "X-Unity-Version": _CFG.get("ua_xunity") or "2018.4.12f1",
   "Host": host_name,
   "ReleaseVersion": self.release_version
  })

 def auth_guest_token(self, uid, password):
  payload = {
   "uid": str(uid), "password": str(password),
   "response_type": "token", "client_type": "2", "client_id": "100067", 
   "client_secret": _get_client_secret(),
  }
  try:
   data = requests.post(
    _get_url("u_grant", "https://auth.garena.com/oauth/guest/token/grant"),
    data=payload,
    headers={
     "Accept-Encoding": "gzip, deflate",
     "Content-Type": "application/x-www-form-urlencoded",
     "User-Agent": "Mozilla/5.0 (Android 9; Mobile; rv:91.0) Gecko/91.0 Firefox/91.0",
    },
    timeout=10
   ).json()
   if "access_token" not in data: return "account not found"
   self._data.access_token = data["access_token"]
   self._data.open_id = data["open_id"]
   self._data.platform = data.get("platform", 0x4)
   self._data.login_platform = data.get("login_platform", 0x4)
   self._data.main_active_platform = data.get("main_active_platform")
   self._data.create_time = data.get("create_time")
   self._data.expiry_time = data.get("expiry_time")
  except Exception as e:
   print(f"[AuthGuest] Error: {e}")

 def auth_token_inspect(self, access_token):
  try:
   data = requests.get(
    _get_url("u_inspect", "https://auth.garena.com/oauth/token/inspect"),
    params={"token": access_token},
    timeout=10
   ).json()
   if "open_id" not in data: raise gayerr("Invalid access token")
   self._data.access_token = access_token
   self._data.open_id = data["open_id"]
   self._data.platform = data.get("platform", 0x4)
   self._data.login_platform = data.get("login_platform", 0x4)
   self._data.main_active_platform = data.get("main_active_platform")
   self._data.create_time = data.get("create_time")
   self._data.expiry_time = data.get("expiry_time")
  except Exception as e:
   pass

 def MajorLogin(self):
  try:
   fields = {}
   fields[3] = time.strftime("%Y-%m-%d %H:%M:%S")
   fields[4] = "free fire"
   fields[5] = 1
   fields[7] = self.client_version or "1.132.11"
   fields[8] = _get_dev("os_info", "Android OS 9 / API-28 (TP1A.220624.014/S908EXXS2BWA2)")
   fields[9] = _get_dev("device_form", "Handheld")
   fields[10] = _get_dev("carrier", "VINAPHONE")
   fields[11] = _get_dev("network_type", "WIFI")
   fields[12] = _get_dev("screen_w", 960)
   fields[13] = _get_dev("screen_h", 540)
   fields[14] = _get_dev("dpi", "160")
   fields[15] = _get_dev("cpu_info", "ARMv7 VFPv3 NEON | 2000 | 4")
   fields[16] = _get_dev("ram_mb", 3940)
   fields[17] = _get_dev("gpu", "Adreno (TM) 540")
   fields[18] = _get_dev("gl_engine", "OpenGL ES 3.2 (4.5.0 - Build 31.0.101.2135)")
   fields[19] = _get_dev("store_id", "Google|62064c16-e2e6-4867-ae77-c0b1123627db")
   fields[20] = _get_dev("real_ip", "1.53.164.96")
   fields[21] = _get_dev("lang_region", "vn")
   fields[22] = str(self._data.open_id)
   fields[23] = str(self._data.login_platform or 4)
   fields[24] = _get_dev("device_form2", "Handheld")
   fields[25] = _get_dev("device_model", "samsung SM-S908E")
   fields[26] = _get_dev("uid_2", "VN")
   fields[29] = str(self._data.access_token)
   fields[30] = 1
   fields[41] = _get_dev("carrier_2", "VINAPHONE")
   fields[42] = _get_dev("network_2", "WIFI")
   fields[57] = _get_dev("device_id_hash", "7428b253defc164018c604a1ebbfebdf")
   fields[60] = _get_dev("mem_total", 128886)
   fields[61] = _get_dev("mem_avail", 117756)
   fields[62] = _get_dev("mem_free", 7998)
   fields[63] = _get_dev("mem_buf", 5772)
   fields[64] = _get_dev("mem_cached", 124326)
   fields[65] = _get_dev("mem_t2", 128886)
   fields[66] = _get_dev("mem_t3", 124326)
   fields[67] = _get_dev("mem_t4", 128886)
   fields[73] = 2
   fields[74] = _get_dev("lib_path", "/data/app/com.dts.freefireth-OnUU8KMGz_Dm3XwAZ6JrVQ==/lib/arm64")
   fields[76] = 1
   fields[77] = _get_dev("apk_hash_path", "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/com.dts.freefireth-OnUU8KMGz_Dm3XwAZ6JrVQ==/base.apk")
   fields[78] = 3
   fields[79] = 2
   fields[81] = "64"
   fields[83] = "2019121229"
   fields[86] = "OpenGLES2"
   fields[87] = 4095
   fields[88] = 4
   fields[92] = _get_dev("flag_92", 8657)
   fields[93] = "android"
   fields[94] = _get_dev("device_token", "KqsHT2Vq07P0MDuM9artcKRudmvm/AzT4ltXIiNvXY7X2qd3+DIQgyiIDJlB/daS1notTnpXzr5CDLnOxa3GnXHlAevZ+LeLm62inQWkYDY5z0qD")
   fields[95] = 111207
   fields[96] = '{"cur_rate":null,"support_etc2":false}'
   fields[97] = 1
   fields[98] = 1
   fields[99] = str(self._data.platform or 4)
   fields[100] = str(self._data.platform or 4)
   hex102 = _get_dev("hex_102", "43534115025a0e05450354165a51125c106b0d505c510f765a46536a1055015e166d5d0639")
   fields[102] = bytes.fromhex(hex102)
   fields[104] = _get_dev("flag_104", 13212)
   fields[105] = 1
   fields[106] = _get_dev("cdn_urls", "https://dl.gmc.freefiremobile.com/live/ABHotUpdates/|https://core-gmc.freefiremobile.com/live/ABHotUpdates/|7ffac607ef29d7ff5db15f0ab0bcdf76")
   fields[107] = _get_dev("session_hash", "1.5d664dc69e8bba02")

   login_url = self.base_url if str(self.base_url).endswith("/") else str(self.base_url) + "/"
   response = self.session.post(
    "%s%s" % (login_url, "MajorLogin"),
    data = AES_CBC128(pb_encode(fields), self.key, self.iv),
    timeout=15
   )
   if getattr(response, "status_code", 0) != 200:
    return
   raw = response.content or b""
   pb = ProtoBuf(raw)
   res = pb.protobuf()
   if len(raw) > 64:
    pb2 = ProtoBuf(raw[64:])
    res2 = pb2.protobuf()
    if res2.get("8") or res2.get("1"):
     pb, res = pb2, res2
   tok = _scalar(res.get("8"))
   if isinstance(tok, bytes):
    tok = tok.decode("utf-8", "replace")
   if not (isinstance(tok, str) and tok.count(".") == 2):
    return
   self._data.account_id = _scalar(res.get("1"))
   self._data.server = _scalar(res.get("3"))
   self._data.login_token = tok
   bu = _scalar(res.get("10"))
   if isinstance(bu, bytes):
    bu = bu.decode("utf-8", "replace")
   self._data.base_url = bu
   self._data.login_time = _scalar(res.get("21"))
   self._data.key = _as_bytes(pb.EXTRACT_FIELDS([22], mode="bytes"))
   self._data.iv = _as_bytes(pb.EXTRACT_FIELDS([23], mode="bytes"))
  except Exception as e:
   print(f"[MajorLogin] Error: {e}")

 def GetLoginData(self):
  try:
   tokendec = gringay.tokendecode(self._data.login_token)
   fields = {}
   fields[3] = time.strftime("%Y-%m-%d %H:%M:%S")
   fields[4] = "free fire"
   fields[5] = 1
   fields[7] = self.client_version or "1.132.11"
   fields[8] = _get_dev("os_info", "Android OS 9 / API-28 (TP1A.220624.014/S908EXXS2BWA2)")
   fields[9] = _get_dev("device_form", "Handheld")
   fields[10] = _get_dev("carrier", "VINAPHONE")
   fields[11] = _get_dev("network_type", "WIFI")
   fields[12] = _get_dev("screen_w", 960)
   fields[13] = _get_dev("screen_h", 540)
   fields[14] = _get_dev("dpi", "160")
   fields[15] = _get_dev("cpu_info", "ARMv7 VFPv3 NEON | 2000 | 4")
   fields[16] = _get_dev("ram_mb", 3940)
   fields[17] = _get_dev("gpu", "Adreno (TM) 540")
   fields[18] = _get_dev("gl_engine", "OpenGL ES 3.2 (4.5.0 - Build 31.0.101.2135)")
   fields[19] = _get_dev("store_id", "Google|62064c16-e2e6-4867-ae77-c0b1123627db")
   fields[20] = _get_dev("real_ip", "1.53.164.96")
   fields[21] = _get_dev("lang_region", "vn")
   fields[22] = str(self._data.open_id)
   fields[23] = str(tokendec.get("external_type", 4)) if tokendec else "4"
   fields[24] = _get_dev("device_form2", "Handheld")
   fields[25] = _get_dev("device_model", "samsung SM-S908E")
   fields[26] = _get_dev("uid_2", "VN")
   fields[29] = str(tokendec.get("external_id", "")) if tokendec else ""
   fields[30] = 1
   fields[41] = _get_dev("carrier_2", "VINAPHONE")
   fields[42] = _get_dev("network_2", "WIFI")
   fields[57] = str(tokendec.get("signature_md5", _get_dev("device_id_hash", "7428b253defc164018c604a1ebbfebdf"))) if tokendec else _get_dev("device_id_hash", "7428b253defc164018c604a1ebbfebdf")
   fields[60] = _get_dev("mem_total", 128886)
   fields[61] = _get_dev("mem_avail", 117756)
   fields[62] = _get_dev("mem_free", 7998)
   fields[63] = _get_dev("mem_buf", 5772)
   fields[64] = _get_dev("mem_cached", 124326)
   fields[65] = _get_dev("mem_t2", 128886)
   fields[66] = _get_dev("mem_t3", 124326)
   fields[67] = _get_dev("mem_t4", 128886)
   fields[73] = 2
   fields[74] = _get_dev("lib_path", "/data/app/com.dts.freefireth-OnUU8KMGz_Dm3XwAZ6JrVQ==/lib/arm64")
   fields[76] = 1
   fields[77] = _get_dev("apk_hash_path", "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/com.dts.freefireth-OnUU8KMGz_Dm3XwAZ6JrVQ==/base.apk")
   fields[78] = 3
   fields[79] = 2
   fields[81] = "64"
   fields[83] = "2019121229"
   fields[86] = "OpenGLES2"
   fields[87] = 4095
   fields[88] = 4
   fields[92] = _get_dev("flag_92", 8657)
   fields[93] = "android"
   fields[94] = _get_dev("device_token", "KqsHT2Vq07P0MDuM9artcKRudmvm/AzT4ltXIiNvXY7X2qd3+DIQgyiIDJlB/daS1notTnpXzr5CDLnOxa3GnXHlAevZ+LeLm62inQWkYDY5z0qD")
   fields[95] = 111207
   fields[96] = '{"cur_rate":null,"support_etc2":false}'
   fields[97] = 1
   fields[98] = 1
   fields[99] = str(self._data.platform or 4)
   fields[100] = str(self._data.platform or 4)
   hex102 = _get_dev("hex_102", "43534115025a0e05450354165a51125c106b0d505c510f765a46536a1055015e166d5d0639")
   fields[102] = bytes.fromhex(hex102)
   fields[104] = _get_dev("flag_104", 13212)
   fields[105] = 1
   fields[106] = _get_dev("cdn_urls", "https://dl.gmc.freefiremobile.com/live/ABHotUpdates/|https://core-gmc.freefiremobile.com/live/ABHotUpdates/|7ffac607ef29d7ff5db15f0ab0bcdf76")
   fields[107] = _get_dev("session_hash", "1.5d664dc69e8bba02")

   base = str(self._data.base_url or "")
   url = base.rstrip("/") + "/GetLoginData"
   host_header = base.replace("https://", "").replace("http://", "").rstrip("/")
   response = self.session.post(
    url,
    headers = {
     "Authorization": "Bearer %s" % self._data.login_token,
     "Host": host_header
    },
    data = AES_CBC128(pb_encode(fields), self.key, self.iv),
    timeout=15
   )
   data = json.loads(protobuf_dec(response.content.hex()))
   self.logindata = data
   self._data.guild_id = data.get("20")
   self._data.guild_code = data.get("55")
   sv, chat = _scalar(data.get("14")), _scalar(data.get("32"))
   sv, chat = str(sv or ""), str(chat or "")
   if len(chat) > 6: self._data.chat_port, self._data.chat_ip = chat[-5:], chat[:-6]
   if len(sv) > 6: self._data.online_port, self._data.online_ip = sv[-5:], sv[:-6]
  except Exception as e:
   pass

 def _auth_packet(self, fox=True):
  regions = self.logindata.get("19") or []
  if isinstance(regions, dict):
   regions = [regions]
  esid = lambda rec: (
   lambda s: s[str(rec).upper()] if str(rec).upper() in s else None)(
    {str(x["2"]).upper(): x["1"] for x in regions if isinstance(x, dict) and "1" in x and "2" in x}
   )
  tok = self._data.login_token
  if isinstance(tok, bytes):
   tok = tok.decode("utf-8", "replace")
  encrypts = AES_CBC128(str(tok).encode(), self._data.key, self._data.iv)
  region = int(_scalar(esid(self._data.server)) or 1)
  aid = int(_scalar(self._data.account_id) or 0)
  kts = int(_scalar(self._data.login_time) or 0)
  cmd = 1 if fox else (101 + (aid % 50))
  hdr = (
   bytes([cmd & 0xFF, region & 0xFF])
   + struct.pack(">Q", aid)
   + struct.pack(">I", kts & 0xFFFFFFFF)
  )
  if fox:
   return hdr + struct.pack(">I", len(encrypts)) + encrypts
  return hdr + struct.pack(">Q", len(encrypts)) + encrypts

 def TAO_PACKET_XT(self) -> bytes:
  try:
   return self._auth_packet(True)
  except Exception as e:
   print(e)

 def TAO_PACKET_LOBBY(self) -> bytes:
  try:
   return self._auth_packet(False)
  except Exception as e:
   print(e)

 def auth(self, access_token, is_emulator = False):
  try:
   self.is_emulator = is_emulator
   if ":" in access_token:
    uid, password = access_token.split(":")
    self.auth_guest_token(int(uid), password)
   else:
    self.auth_token_inspect(access_token)
   self.MajorLogin()
   self.GetLoginData()
   if not self.logindata:
    return "account not found"
   pkt = self.TAO_PACKET_XT()
   if not pkt: return "account not found"
   return self._build_api_response(pkt)
  except Exception as e:
   pass
 
 def _build_api_response(self, authpacket):
  if not self._data.login_token or not authpacket: return "account not found"
  if not self._data.key or not self._data.iv: return "account not found"
  tok = self._data.login_token
  if isinstance(tok, bytes):
   tok = tok.decode("utf-8", "replace")
  data = gringay.tokendecode(tok)
  if self._data.guild_id:
   guild = {}
   guild["id"] = self._data.guild_id
   guild["secret_code"] = self._data.guild_code
  else:
   guild = False

  saddress = {}
  saddress["chatip"] = self._data.chat_ip
  saddress["chatport"] = self._data.chat_port
  saddress["onlineip"] = self._data.online_ip
  saddress["onlineport"] = self._data.online_port  
  
  response = {}
  response["CreateTime"] = gringay.format_timestamp(self._data.create_time)
  response["ExpiryTime"] = gringay.format_timestamp(self._data.expiry_time)
  response["UserAuthPacket"] = list(authpacket)
  lobby_pkt = self.TAO_PACKET_LOBBY()
  response["UserAuthPacketLobby"] = list(lobby_pkt) if lobby_pkt else list(authpacket)
  response["UserAuthToken"] = tok
  response["UserNickName"] = data.get("nickname")
  response["UserAccountUID"] = data.get("account_id")
  response["LockRegion"] = data.get("lock_region")
  response["ClientVersion"] = data.get("client_version")
  response["IsEmulator"] = data.get("is_emulator")
  response["GuildData"] = guild
  response["BaseUrl"] = self._data.base_url or ""
  response["key"] = list(self._data.key)
  response["iv"] = list(self._data.iv)
  response["logindata"] = self.logindata
  response["GameServerAddress"] = saddress
  return response

class FreeFireAPI: 
 def __init__(self):
  self.client = APIClient()
 def get(self, target: str, is_emulator: bool = False):
  return self.client.auth(target, is_emulator)


# ══════════════════════════════════════════════════════════════
#  TOOL SINH BLOB CFG — chạy 1 lần, copy kết quả dán vào _CFG_B64
#  Usage:
#     python ReQAPI.py --gen-cfg
# ══════════════════════════════════════════════════════════════
_CFG_PLAIN = {
    "k":  "5967267463254445756836255a635e38",
    "i":  "366f795a447232324533796368 6a4d25".replace(" ", ""),
    "cs": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
    "u_ver":     "https://version.ggwhitehawk.com/live/ver.php",
    "u_grant":   "https://auth.garena.com/oauth/guest/token/grant",
    "u_inspect": "https://auth.garena.com/oauth/token/inspect",
    "h_ver":     "version.ggwhitehawk.com",
    "h_login":   "loginbp.ppmainecoonghj.com",
    "api_host":  "clientbp.ppmainecoonghj.com",
    "ua_unity":  "UnityPlayer/2018.4.12f1 (UnityWebRequest/1.0, libcurl/8.5.0-DEV)",
    "ua_xunity": "2018.4.12f1",
    "host_fallback": "https://loginbp.ppmainecoonghj.com/",
    "dev": {
        "os_info":       "Android OS 9 / API-28 (TP1A.220624.014/S908EXXS2BWA2)",
        "device_form":   "Handheld",
        "carrier":       "VINAPHONE",
        "network_type":  "WIFI",
        "screen_w":      960,
        "screen_h":      540,
        "dpi":           "160",
        "cpu_info":      "ARMv7 VFPv3 NEON | 2000 | 4",
        "ram_mb":        3940,
        "gpu":           "Adreno (TM) 540",
        "gl_engine":     "OpenGL ES 3.2 (4.5.0 - Build 31.0.101.2135)",
        "store_id":      "Google|62064c16-e2e6-4867-ae77-c0b1123627db",
        "real_ip":       "1.53.164.96",
        "lang_region":   "vn",
        "device_form2":  "Handheld",
        "device_model":  "samsung SM-S908E",
        "uid_2":         "VN",
        "carrier_2":     "VINAPHONE",
        "network_2":     "WIFI",
        "device_id_hash":"7428b253defc164018c604a1ebbfebdf",
        "mem_total":     128886,
        "mem_avail":     117756,
        "mem_free":      7998,
        "mem_buf":       5772,
        "mem_cached":    124326,
        "mem_t2":        128886,
        "mem_t3":        124326,
        "mem_t4":        128886,
        "lib_path":      "/data/app/com.dts.freefireth-OnUU8KMGz_Dm3XwAZ6JrVQ==/lib/arm64",
        "apk_hash_path": "b8e0cd5e295eee42f5860d3c86e483dd|/data/app/com.dts.freefireth-OnUU8KMGz_Dm3XwAZ6JrVQ==/base.apk",
        "flag_92":       8657,
        "device_token":  "KqsHT2Vq07P0MDuM9artcKRudmvm/AzT4ltXIiNvXY7X2qd3+DIQgyiIDJlB/daS1notTnpXzr5CDLnOxa3GnXHlAevZ+LeLm62inQWkYDY5z0qD",
        "hex_102":       "43534115025a0e05450354165a51125c106b0d505c510f765a46536a1055015e166d5d0639",
        "flag_104":      13212,
        "cdn_urls":      "https://dl.gmc.freefiremobile.com/live/ABHotUpdates/|https://core-gmc.freefiremobile.com/live/ABHotUpdates/|7ffac607ef29d7ff5db15f0ab0bcdf76",
        "session_hash":  "1.5d664dc69e8bba02",
    },
}


def _gen_cfg_b64() -> str:
    raw = json.dumps(_CFG_PLAIN, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    xored = _xb(raw)
    return base64.urlsafe_b64encode(xored).decode("ascii")