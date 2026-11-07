import threading
import json
import socket
import time
import random
import datetime
import os
import struct
import uuid
import queue
import logging
import requests
import hmac
import hashlib
from enum import Enum
try:
    from anhcodeclick.lib import *
    from anhcodeclick.GPackGEN import *
    from anhcodeclick.ReQAPI import *
except ImportError:
    from lib import *
    from GPackGEN import *
    from ReQAPI import *

from flask import Flask, jsonify, request 
import telebot
import traceback
import concurrent.futures

app = Flask(__name__)

# ====================== LOGGING SETUP ======================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("BotScheduler")

# ============================================================
# VOICE MUSIC MODULE
# ============================================================
try:
    from voice_gr import (
        start_voice_music, stop_voice_music,
        wait_room_and_start, is_music_running, voice_status
    )
    VOICE_ENABLED = True
    logger.info("[Main] voice_gr loaded OK")
except ImportError as e:
    VOICE_ENABLED = False
    logger.warning(f"[Main] voice_gr khong load duoc ({e}) → tat music feature")
    def start_voice_music(*a, **kw): return False
    def stop_voice_music(*a, **kw): return 0
    def wait_room_and_start(*a, **kw): return False
    def is_music_running(*a, **kw): return False
    def voice_status(*a, **kw): return {"total": 0, "sessions": []}

# ============================================================
# VOICE OWNER LOCK
# ============================================================
_VOICE_TC_ACTIVE = set()
_VOICE_TC_LOCK   = threading.Lock()

def _voice_claim_tc(tc) -> bool:
    try:
        tc = int(tc)
    except Exception:
        return False
    with _VOICE_TC_LOCK:
        if tc in _VOICE_TC_ACTIVE:
            return False
        _VOICE_TC_ACTIVE.add(tc)
        return True

def _voice_release_tc(tc):
    try:
        tc = int(tc)
    except Exception:
        return
    with _VOICE_TC_LOCK:
        _VOICE_TC_ACTIVE.discard(tc)

# ============================================================
# ★ ANTI-BAN / SAFE LAG CONFIG (vá triệt để theo src cũ chạy lâu)
# ============================================================
_LAST_LAG_TS = 0.0
_LAG_COOLDOWN = 90          # giây tối thiểu giữa 2 lần /lagff
_LAG_MAX_BOTS = 2           # tối đa 2 bot (giảm từ 3)
_LAG_SAFE_MODE = True       # True = pattern nhẹ, khó ban

def _can_start_lag() -> bool:
    """Global cooldown chống spam lag liên tục."""
    global _LAST_LAG_TS
    now = time.time()
    if now - _LAST_LAG_TS < _LAG_COOLDOWN:
        return False
    _LAST_LAG_TS = now
    return True

# ============================================================
# ★ PROMO
# ============================================================
PROMO_TEXT = (
    "[B][C][00ff00]B[c]o[c]t [C][B][007AFF]H[C][B][339BFF]Đ[C][B][66BBFF] L"
    "[C][B][99DFFF]V[C][B][CCF5FF]7[C][B][E0FAFF]![C][B][F0FDFF]!\n\n"
    "[00ff00]M[c]a[c]k[c]e: [F0FDFF]A[c]N[c]H[c]C[C][B][007AFF]O[C][B][339BFF]D"
    "[C][B][66BBFF]E[C][B][99DFFF].IO[C][B][CCF5FF].[C][B][E0FAFF]V[C][B][F0FDFF]N\n"
    "[00ff00]T[c]e[c]l[c]e: [F0FDFF]@[C][B][007AFF]a[C][B][339BFF]n[C][B][66BBFF]h"
    "[C][B][99DFFF]c[C][B][CCF5FF]o[C][B][E0FAFF]de[C][B][F0FDFF]click"
)

PROMO_SQUAD_MSG = (
    "[B][C][00ff00]B[c]o[c]t [C][B][007AFF]H[C][B][339BFF]Đ[C][B][66BBFF] L"
    "[C][B][99DFFF]V[C][B][CCF5FF]7[C][B][E0FAFF]![C][B][F0FDFF]!\n\n"
    "[00ff00]M[c]a[c]k[c]e: [F0FDFF]A[c]N[c]H[c]C[C][B][007AFF]O[C][B][339BFF]D"
    "[C][B][66BBFF]E[C][B][99DFFF].IO[C][B][CCF5FF].[C][B][E0FAFF]V[C][B][F0FDFF]N\n"
    "[00ff00]T[c]e[c]l[c]e: [F0FDFF]@[C][B][007AFF]a[C][B][339BFF]n[C][B][66BBFF]h"
    "[C][B][99DFFF]c[C][B][CCF5FF]o[C][B][E0FAFF]de[C][B][F0FDFF]click"
)

def _force_promo_on_join(bot):
    try:
        bot.rstatus = (4, '')
    except Exception:
        pass

# ============================================================
# ★ JOIN WORKER
# ============================================================
def _run_join_worker(bot, tc_int, uids_param, voice_owner):
    music_done = threading.Event()
    music_started = {"flag": False}
    _mf = "s1.mp3"
    if getattr(bot, "bot_config", None):
        _mf = bot.bot_config.get("voice_music_file", "s1.mp3")

    if not os.path.isabs(_mf):
        for base in (os.getcwd(), "/home/workdir/artifacts"):
            cand = os.path.join(base, _mf)
            if os.path.isfile(cand):
                _mf = cand
                break

    try:
        if not getattr(bot, "sock39699", None):
            raise Exception("Bot khong co socket")

        def _valid(n):
            try:
                n = int(n)
                return 10**8 <= n <= 10**12
            except Exception:
                return False

        def _all_members():
            out = []
            if uids_param:
                for x in str(uids_param).replace(",", " ").split():
                    x = x.strip()
                    if x.isdigit() and _valid(x):
                        xi = int(x)
                        if xi not in out:
                            out.append(xi)
            for x in list(getattr(bot, "ids", None) or []):
                try:
                    xi = int(x)
                except Exception:
                    continue
                if _valid(xi) and xi not in out:
                    out.append(xi)
            botid = getattr(bot, "botid", None)
            if botid is None and getattr(bot, "bot_config", None):
                botid = bot.bot_config.get("bot_id") or bot.bot_config.get("botid")
            try:
                if botid is not None and str(botid).isdigit():
                    bi = int(botid)
                    if _valid(bi) and bi not in out:
                        out.append(bi)
            except Exception:
                pass
            return out

        bot.ids = []
        bot.is_trolling = True
        bot.is_busy = True
        bot.rstatus = (4, '')

        if voice_owner:
            bot.last_room_id = None
            try:
                bot.room_id_event.clear()
            except Exception:
                bot.room_id_event = threading.Event()
            _tc_released = {"done": False}

            def _voice_finish_cb():
                music_done.set()
                if not _tc_released["done"]:
                    _tc_released["done"] = True
                    _voice_release_tc(tc_int)

            def _voice_watcher(b=bot, f=_mf, tc=tc_int):
                try:
                    if wait_room_and_start(b, f, timeout=30.0, on_finish=_voice_finish_cb):
                        music_started["flag"] = True
                        logger.info(f"[Join] Voice OK tc={tc} file={f}")
                    else:
                        rid = getattr(b, "last_room_id", None)
                        if rid and start_voice_music(b, rid, f, on_finish=_voice_finish_cb):
                            music_started["flag"] = True
                            return
                        logger.warning(f"[Join] Voice FAIL tc={tc} room={rid}")
                        music_done.set()
                        if not _tc_released["done"]:
                            _tc_released["done"] = True
                            _voice_release_tc(tc)
                except Exception as e:
                    logger.error(f"[Join] Voice err tc={tc}: {e}")
                    music_done.set()
                    if not _tc_released["done"]:
                        _tc_released["done"] = True
                        _voice_release_tc(tc)

            threading.Thread(target=_voice_watcher, daemon=True, name=f"JVoice-{tc_int}").start()
        else:
            music_done.set()

        try:
            bot.sock39699.sendall(bot._bot.join_squad(tc_int))
        except Exception:
            bot.sock39699.send(bot._bot.join_squad(tc_int))

        ids = []
        prev_count = -1
        stable = 0
        deadline = time.time() + 5.0
        while time.time() < deadline:
            time.sleep(0.3)
            ids = _all_members()
            cur = len(ids)
            if cur > 0 and cur == prev_count:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev_count = cur
        if not ids:
            time.sleep(0.8)
            ids = _all_members()
        if not ids:
            bf = getattr(bot, "botid", None) or (
                bot.bot_config.get("bot_id") if getattr(bot, "bot_config", None) else None
            )
            if bf and str(bf).isdigit():
                ids = [int(bf)]
            else:
                raise Exception("Khong co UID de mua")

        active_ids = list(ids)
        emotes = list(getattr(bot, "Emotes", None) or [])
        if not emotes:
            raise Exception("Bot khong co Emotes")

        promo_target = None
        if uids_param:
            for x in str(uids_param).replace(",", " ").split():
                x = x.strip()
                if x.isdigit():
                    promo_target = int(x)
                    break
        if not promo_target and active_ids:
            promo_target = active_ids[0]
        if promo_target:
            try:
                bot._bot.reply(int(promo_target), None, PROMO_SQUAD_MSG)
                logger.info(f"[Join] promo → squad uid={promo_target}")
                time.sleep(1.0)
            except Exception as pe:
                logger.warning(f"[Join] promo fail: {pe}")

        known = set(active_ids)

        def _merge_new():
            added = []
            try:
                for xi in _all_members():
                    if xi not in known:
                        known.add(xi)
                        active_ids.append(xi)
                        added.append(xi)
            except Exception:
                pass
            return added

        try:
            bot.sock39699.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

        total_em = len(emotes)
        logger.info(f"[Join] tc={tc_int} members={len(active_ids)} {active_ids} emotes={total_em}")

        for idx, emote in enumerate(emotes, 1):
            try:
                bot.rstatus = (10, '')
            except Exception:
                pass
            if not getattr(bot, "sock39699", None):
                logger.warning(f"[Join] mat socket {idx}/{total_em}")
                break
            _merge_new()
            try:
                pkt = bot._bot.play_emote(emote, list(active_ids))
                if pkt:
                    try:
                        bot.sock39699.sendall(pkt)
                    except Exception:
                        bot.sock39699.send(pkt)
                logger.info(f"[Join] emote {idx}/{total_em} id={emote} targets={len(active_ids)}")
            except (socket.error, ConnectionResetError, BrokenPipeError):
                break
            except Exception as ee:
                logger.warning(f"[Join] emote err: {ee}")
            time.sleep(random.uniform(6.8, 9.5))  # ★ anti-ban: random delay emote

        if voice_owner and music_started.get("flag") and not music_done.is_set():
            for _ in range(30):
                if music_done.is_set():
                    break
                time.sleep(0.5)
            if not music_done.is_set():
                logger.info(f"[Join] chờ nhạc xong (file={_mf}, max 3600s)...")
                music_done.wait(timeout=3600)

        time.sleep(1.5)
        botid = getattr(bot, "botid", None)
        if botid is None and getattr(bot, "bot_config", None):
            botid = bot.bot_config.get("bot_id") or bot.bot_config.get("botid")
        if botid and str(botid).isdigit() and getattr(bot, "sock39699", None):
            try:
                bot.sock39699.sendall(bot._bot.leave_squad(int(botid)))
            except Exception:
                try:
                    bot.sock39699.send(bot._bot.leave_squad(int(botid)))
                except Exception:
                    pass
        logger.info(f"[Join] xong tc={tc_int} leave")

    except Exception as e:
        logger.error(f"[Join Error] tc={tc_int}: {e}")
        try:
            music_done.set()
            if voice_owner:
                stop_voice_music(bot_id=getattr(bot, "botid", None))
                _voice_release_tc(tc_int)
        except Exception:
            pass
        raise
    finally:
        try:
            bot.rstatus = (0, 0)
            bot.is_trolling = False
            bot.is_busy = False
        except Exception:
            pass
        if voice_owner:
            try:
                if not music_done.is_set():
                    stop_voice_music(bot_id=getattr(bot, "botid", None))
                    music_done.set()
            except Exception:
                pass
            _voice_release_tc(tc_int)

# ============================================================
# ★ LAG WORKER
# ============================================================
def _lag_task_worker(bot, tc_int, duration, is_voice_owner):
    """
    ★ SAFE LAG WORKER – vá triệt để chống ban
    - Giảm burst / wave mạnh
    - Delay lớn + jitter cao (human-like)
    - Ít join/leave
    - Cooldown giữa các cycle
    """
    if not getattr(bot, "sock39699", None):
        raise Exception("Bot khong co socket")

    bot.is_trolling = True
    end_time = time.time() + duration

    def _send(sock, data):
        try:
            sock.sendall(data)
            return True
        except (socket.error, ConnectionResetError, BrokenPipeError, OSError):
            return False

    def _jitter(base, pct=0.45):
        """Jitter mạnh hơn để tránh pattern cố định."""
        dev = base * pct
        return max(0.05, base + random.uniform(-dev, dev))

    try:
        sock = bot.sock39699
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

        RoiDoi = bot._bot.leave_squad(0x00)
        VaoDoi = bot._bot.join_squad(tc_int)
        try:
            LagVer = bot._gen.lag_ver()
        except Exception:
            raise Exception("Khong tao duoc LagVer packet")

        if is_voice_owner:
            bot._lag_music_started = True
            bot.last_room_id = None
            try:
                bot.room_id_event.clear()
            except Exception:
                bot.room_id_event = threading.Event()
            _mf = bot.bot_config.get("voice_music_file", "s2.mp3") \
                  if getattr(bot, "bot_config", None) else "s2.mp3"

            def _lag_voice_watcher(b=bot, f=_mf, tc=tc_int):
                _released = {"done": False}
                def _release_tc():
                    if not _released["done"]:
                        _released["done"] = True
                        _voice_release_tc(tc)
                try:
                    if wait_room_and_start(b, f, on_finish=_release_tc):
                        logger.info(f"[LagFF] Voice started tc={tc} file={f}")
                    else:
                        logger.warning(f"[LagFF] Voice failed tc={tc}")
                        _release_tc()
                except Exception:
                    _release_tc()

            threading.Thread(
                target=_lag_voice_watcher,
                daemon=True,
                name=f"LagVoice-{tc_int}",
            ).start()
            logger.info(f"[LagFF] Voice watcher started tc={tc_int} (OWNER)")

        _force_promo_on_join(bot)
        _send(sock, VaoDoi)
        time.sleep(_jitter(random.uniform(2.8, 4.5)))   # delay join lớn hơn

        ids = list(set(bot.ids)) if getattr(bot, "ids", None) else []
        botid_v = getattr(bot, "botid", None)
        if botid_v and str(botid_v).isdigit() and int(botid_v) not in ids:
            ids.append(int(botid_v))

        def emote_loop():
            emotes = list(getattr(bot, "Emotes", []) or [])
            if not emotes:
                return
            while bot.is_trolling and time.time() < end_time:
                emote = random.choice(emotes)
                s = getattr(bot, "sock39699", None)
                if not s:
                    return
                try:
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except Exception:
                    pass
                live_ids = []
                for x in list(getattr(bot, "ids", None) or []) + list(ids):
                    try:
                        xi = int(x)
                        if 10**8 <= xi <= 10**12 and xi not in live_ids:
                            live_ids.append(xi)
                    except Exception:
                        pass
                if botid_v and str(botid_v).isdigit():
                    bi = int(botid_v)
                    if 10**8 <= bi <= 10**12 and bi not in live_ids:
                        live_ids.append(bi)
                if not live_ids:
                    continue
                if not _send(s, bot._bot.play_emote(emote, live_ids)):
                    return
                # delay emote dài + random mạnh
                time.sleep(_jitter(random.uniform(7.0, 14.0), pct=0.3))

        if ids:
            threading.Thread(target=emote_loop, daemon=True,
                             name=f"LagEmote-{tc_int}").start()

        # ========== SAFE LAG PARAMETERS (src cũ style) ==========
        WAVE_MIN   = 2          # giảm mạnh từ 6
        WAVE_MAX   = 4          # giảm mạnh từ 14
        BURST_SIZE = 2          # giảm mạnh từ 8

        while bot.is_trolling and time.time() < end_time:
            sock = getattr(bot, "sock39699", None)
            if not sock:
                break

            # Join
            if not _send(sock, VaoDoi):
                break
            time.sleep(_jitter(random.uniform(1.5, 3.2)))

            n_bursts = random.randint(WAVE_MIN, WAVE_MAX)
            for i in range(n_bursts):
                if not bot.is_trolling or time.time() >= end_time:
                    break
                sock = getattr(bot, "sock39699", None)
                if not sock:
                    break

                # Chỉ 1~2 packet mỗi lần, không nhân lớn
                burst = LagVer * random.randint(1, BURST_SIZE)
                if not _send(sock, burst):
                    break
                # Delay giữa packet lớn hơn rất nhiều (120-400ms)
                time.sleep(_jitter(random.uniform(0.12, 0.40), pct=0.4))

            # Leave
            sock = getattr(bot, "sock39699", None)
            if sock:
                _send(sock, RoiDoi)

            # Cooldown dài giữa các cycle (human-like)
            if random.random() < 0.35:
                time.sleep(_jitter(random.uniform(5.0, 9.0)))
            else:
                time.sleep(_jitter(random.uniform(2.5, 5.0)))

        # Leave cuối
        sock = getattr(bot, "sock39699", None)
        if sock:
            _send(sock, RoiDoi)

    except Exception as e:
        logger.warning(f"[LAG] Error: {e}")
        raise
    finally:
        bot.is_trolling = False
        bot.is_busy = False
        try:
            bot._lag_music_started = False
        except Exception:
            pass
        try:
            bot_id = getattr(bot, "botid", None)
            if getattr(bot, "bot_config", None):
                bot_id = bot.bot_config.get("bot_id") or bot.bot_config.get("botid") or bot_id
            if bot_id:
                BOT_POOL.set_status(bot_id, BotStatus.IDLE)
        except Exception:
            pass


def _run_lag_batch(tc_int, duration, need_bots=None, on_done=None):
    # ★ SAFE: default 2 bot + global cooldown
    if need_bots is None:
        need_bots = _LAG_MAX_BOTS
    need_bots = max(1, min(int(need_bots), _LAG_MAX_BOTS))

    if not _can_start_lag():
        logger.warning(f"[LagFF] Cooldown {_LAG_COOLDOWN}s – bỏ qua tc={tc_int}")
        return 0, False

    claimed = []
    for _ in range(need_bots):
        bot = BOT_POOL.pick_idle_bot()
        if not bot:
            break
        try:
            bot_id = None
            if getattr(bot, "bot_config", None):
                bot_id = bot.bot_config.get("bot_id") or bot.bot_config.get("botid")
            if bot_id is None:
                bot_id = getattr(bot, "botid", None)
            if bot_id is not None:
                BOT_POOL.set_status(bot_id, BotStatus.BUSY, f"/lagff tc={tc_int}")
            bot.is_busy = True
            bot.is_trolling = True
        except Exception:
            pass
        claimed.append(bot)

    if not claimed:
        return 0, False

    _lag_voice_owner = VOICE_ENABLED and _voice_claim_tc(tc_int)
    if VOICE_ENABLED:
        if _lag_voice_owner:
            logger.info(f"[LagFF] Voice OWNER claimed tc={tc_int}")
        else:
            logger.info(f"[LagFF] Voice skip tc={tc_int}")

    done_lock = threading.Lock()
    done_state = {"ok": 0, "fail": 0, "total": len(claimed)}

    def _wrap(bot, is_owner):
        try:
            _lag_task_worker(bot, tc_int, duration, is_owner)
            with done_lock:
                done_state["ok"] += 1
            if on_done:
                try:
                    on_done(True, "")
                except Exception:
                    pass
        except Exception as e:
            with done_lock:
                done_state["fail"] += 1
            if on_done:
                try:
                    on_done(False, str(e))
                except Exception:
                    pass

    started = 0
    for idx, bot in enumerate(claimed):
        try:
            is_owner = bool(_lag_voice_owner and idx == 0)
            threading.Thread(
                target=_wrap,
                args=(bot, is_owner),
                daemon=True,
                name=f"Lag3-{tc_int}-{getattr(bot, 'botid', started)}",
            ).start()
            started += 1
        except Exception as e:
            logger.error(f"[LAG] start thread fail: {e}")
            try:
                bot.is_trolling = False
                bot.is_busy = False
                bid = None
                if getattr(bot, "bot_config", None):
                    bid = bot.bot_config.get("bot_id") or bot.bot_config.get("botid")
                if bid is None:
                    bid = getattr(bot, "botid", None)
                if bid is not None:
                    BOT_POOL.set_status(bid, BotStatus.IDLE)
            except Exception:
                pass

    if started <= 0 and _lag_voice_owner:
        _voice_release_tc(tc_int)

    return started, _lag_voice_owner

# ============================================================
# THREAD POOL
# ============================================================
_PACKET_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=16, thread_name_prefix="Pkt"
)

TELEGRAM_BOT_TOKEN = "8696284052:AAH27yMB8QWQKQFJZ6vS8arD1nfrD4ZlsY0"
telegram_bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=False)
TELEGRAM_ADMINS = [7143607080]   # ★ FIX: admin ID mới

# ====================== KEY SYSTEM CONSTANTS ======================
KEY_API_BASE    = ""
ADMIN_PANEL_URL = ""
ADMIN_PASS      = ""
KEY_VALIDITY    = 10 * 3600
KEY_USER_FILE   = "key_users.json"

BOT_API_SECRET_CACHE = {"secret": None, "updated": 0, "ttl": 300}
KEY_VERIFY_CACHE = {}
KEY_VERIFY_CACHE_TTL = 30
KEY_STRICT_MODE = False

ALLOWED_GROUPS = set()

def load_allowed_groups():
    global ALLOWED_GROUPS
    try:
        if os.path.exists("allowed_groups.json"):
            with open("allowed_groups.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                ALLOWED_GROUPS = set(data.get("groups", []))
    except:
        ALLOWED_GROUPS = set()

def save_allowed_groups():
    try:
        with open("allowed_groups.json", "w", encoding="utf-8") as f:
            json.dump({"groups": list(ALLOWED_GROUPS)}, f, indent=4, ensure_ascii=False)
    except:
        pass

load_allowed_groups()


# ====================== KEY SYSTEM FUNCTIONS ======================
def vn_now():
    return datetime.datetime.now() + datetime.timedelta(hours=7)

def fmt_time(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S %d/%m/%Y")

def load_key_users():
    try:
        if os.path.exists(KEY_USER_FILE):
            with open(KEY_USER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return {}

def save_key_users(data):
    try:
        with open(KEY_USER_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error saving key users: {e}")

def get_key(user_id):
    data = load_key_users()
    user_key = data.get(str(user_id))
    if user_key:
        expiry = user_key.get("expiry", 0)
        if time.time() < expiry:
            return expiry
    return None

def get_key_entry(user_id):
    data = load_key_users()
    return data.get(str(user_id), {})

def set_key(user_id, expiry, key_str=""):
    data = load_key_users()
    data[str(user_id)] = {
        "expiry": expiry,
        "key_str": key_str,
        "created_at": time.time(),
    }
    save_key_users(data)

def remove_key(user_id):
    data = load_key_users()
    data.pop(str(user_id), None)
    save_key_users(data)

def verify_key_via_panel(user_id):
    entry = get_key_entry(user_id)
    key_str = entry.get("key_str", "")
    if not key_str:
        return {"ok": False, "valid": False, "reason": "no_key"}

    secret = get_bot_api_secret()
    if not secret:
        return {"ok": None, "reason": "no_secret"}

    ts = int(time.time())
    sig = make_hmac_sig(user_id, key_str, ts, secret=secret)
    if not sig:
        return {"ok": None, "reason": "bad_signature"}

    try:
        resp = requests.post(
            f"{ADMIN_PANEL_URL}?act=verify",
            data={
                "key":     key_str,
                "user_id": str(user_id),
                "ts":      str(ts),
                "sig":     sig,
                "bot_ip":  "0.0.0.0",
            },
            headers={
                "User-Agent": "TelegramBot/3.0-BotAPI",
                "Accept":     "application/json",
            },
            timeout=10,
            verify=False,
        )
        return resp.json()
    except requests.exceptions.Timeout:
        return {"ok": None, "reason": "timeout"}
    except Exception as e:
        logger.error(f"Lỗi verify key panel user={user_id}: {e}")
        return {"ok": None, "reason": "network_error"}

def get_bot_api_secret(force_refresh=False):
    now = time.time()
    cache = BOT_API_SECRET_CACHE
    if not force_refresh and cache["secret"] and now - cache["updated"] < cache["ttl"]:
        return cache["secret"]

    url_header = f"{ADMIN_PANEL_URL}?act=get_secret"
    url_query  = f"{ADMIN_PANEL_URL}?act=get_secret&pass={ADMIN_PASS}"
    headers    = {
        "Authorization": f"Bearer {ADMIN_PASS}",
        "User-Agent": "TelegramBot/3.0-BotAPI",
        "Accept": "application/json",
    }

    attempts = [
        ("POST", url_header, headers),
        ("GET",  url_header, headers),
        ("GET",  url_query,  {}),
    ]

    for method, u, h in attempts:
        try:
            if method == "POST":
                resp = requests.post(u, headers=h, timeout=10, verify=False)
            else:
                resp = requests.get(u, headers=h, timeout=10, verify=False)

            logger.info(f"[KeySystem] get_secret {method} → HTTP {resp.status_code} | {resp.text[:200]}")

            try:
                data = resp.json()
            except Exception:
                continue

            if data.get("ok") and data.get("secret"):
                cache["secret"] = data["secret"]
                cache["updated"] = now
                logger.info(f"[KeySystem] ✅ HMAC secret OK (len={len(data['secret'])})")
                return cache["secret"]
        except Exception as e:
            logger.warning(f"[KeySystem] get_secret attempt fail ({method}): {e}")
            continue

    logger.error("[KeySystem] ❌ Không lấy được secret từ panel — check ADMIN_PASS & URL")
    return cache.get("secret")

def make_hmac_sig(user_id, key_str, ts, secret=None):
    if secret is None:
        secret = get_bot_api_secret()
    if not secret:
        return ""
    payload = f"user_id={user_id}&key={key_str}&ts={ts}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

def is_admin(user_id):
    return user_id in TELEGRAM_ADMINS

def is_allowed_group(chat_id):
    return chat_id in ALLOWED_GROUPS or chat_id > 0

def check_member_in_groups(user_id):
    return True

def check_key_validity(user_id):
    expiry = get_key(user_id)
    if not expiry or time.time() >= expiry:
        return False
    entry = get_key_entry(user_id)
    key_str = entry.get("key_str", "")
    if not key_str:
        return False
    now = time.time()
    cache = KEY_VERIFY_CACHE.get(str(user_id), {})
    if cache.get("key") == key_str and now - cache.get("checked_at", 0) < KEY_VERIFY_CACHE_TTL:
        if cache.get("valid"):
            return True
        logger.warning(f"Cached key invalid for user={user_id}")
        remove_key(user_id)
        return False
    result = verify_key_via_panel(user_id)
    if result.get("ok") is False and result.get("valid") is False:
        logger.warning(f"Key revoked on server for user={user_id} reason={result.get('reason')}")
        remove_key(user_id)
        KEY_VERIFY_CACHE.pop(str(user_id), None)
        return False
    if result.get("ok") and result.get("valid"):
        expire_at = result.get("expire_at")
        if isinstance(expire_at, (int, float)) and expire_at > time.time():
            set_key(user_id, float(expire_at), key_str=key_str)
        KEY_VERIFY_CACHE[str(user_id)] = {"key": key_str, "valid": True, "checked_at": now}
        return True

    reason = result.get("reason", "unknown")
    if KEY_STRICT_MODE and reason in ("network_error", "timeout", "no_secret", "bad_signature"):
        logger.warning(f"STRICT: Server key không phản hồi (reason={reason}) → từ chối user={user_id}")
        KEY_VERIFY_CACHE[str(user_id)] = {"key": key_str, "valid": False, "checked_at": now}
        return False

    logger.info(f"Key server verify fallback local expiry for user={user_id} ({reason})")
    KEY_VERIFY_CACHE[str(user_id)] = {"key": key_str, "valid": True, "checked_at": now}
    return True

def is_group_allowed(chat_id):
    return chat_id in ALLOWED_GROUPS or chat_id > 0

def group_only(handler):
    def wrapper(message):
        if message.chat.type == 'private' or is_group_allowed(message.chat.id):
            return handler(message)
        else:
            telegram_bot.reply_to(message, "❌ Bot chỉ hoạt động trong nhóm được phép.")
    return wrapper


# ====================== BOT STATUS ENUM ======================
class BotStatus(Enum):
    IDLE     = "IDLE"
    BUSY     = "BUSY"
    OFFLINE  = "OFFLINE"
    ERROR    = "ERROR"
    COOLDOWN = "COOLDOWN"


# ====================== SCHEDULER LOG ======================
class SchedulerLogger:
    def __init__(self):
        self._lock = threading.Lock()
        self._logs = []

    def log(self, request_id, command, bot_name, processing_time=None,
            success=None, failed=None, retry_count=0, extra=""):
        entry = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "request_id": request_id,
            "command": command,
            "selected_bot": bot_name,
            "processing_time": processing_time,
            "success": success,
            "failed": failed,
            "retry_count": retry_count,
            "extra": extra,
        }
        with self._lock:
            self._logs.append(entry)
            if len(self._logs) > 500:
                self._logs = self._logs[-500:]
        status = "SUCCESS" if success else ("FAILED" if failed else "QUEUED")
        logger.info(
            f"[Scheduler] Bot={bot_name} | Command={command} | ReqID={request_id} "
            f"| Status={status} | Retry={retry_count}"
        )

    def get_logs(self, limit=50):
        with self._lock:
            return list(reversed(self._logs[-limit:]))


SCHED_LOGGER = SchedulerLogger()


# ====================== REQUEST QUEUE ======================
class SchedulerRequest:
    MAX_RETRIES = 3
    TIMEOUT_SEC = 120

    def __init__(self, command, task_fn, callback=None):
        self.request_id = str(uuid.uuid4())[:8].upper()
        self.command    = command
        self.task_fn    = task_fn
        self.callback   = callback
        self.retry_count = 0
        self.created_at  = time.time()
        self.done_event  = threading.Event()
        self.result      = None

    def is_expired(self):
        return (time.time() - self.created_at) > self.TIMEOUT_SEC


# ====================== BOT POOL ======================
class BotPool:
    HEARTBEAT_TIMEOUT = 15
    COOLDOWN_SEC      = 2

    def __init__(self):
        self._bots = {}
        self._lock = threading.RLock()

    @staticmethod
    def _nid(bot_id):
        try:
            return int(bot_id)
        except (TypeError, ValueError):
            return bot_id

    def register(self, bot_id, bot_instance):
        bid = self._nid(bot_id)
        with self._lock:
            self._bots[bid] = {
                "instance":     bot_instance,
                "status":       BotStatus.OFFLINE,
                "current_task": None,
                "last_active":  None,
                "heartbeat":    None,
                "task_count":   0,
            }

    def heartbeat(self, bot_id):
        bid = self._nid(bot_id)
        with self._lock:
            if bid not in self._bots:
                return
            meta = self._bots[bid]
            meta["heartbeat"] = time.time()
            meta["last_active"] = datetime.datetime.now()
            inst = meta["instance"]
            socket_ok = bool(
                getattr(inst, "running_event", None)
                and inst.running_event.is_set()
                and getattr(inst, "sock39699", None)
            )
            if meta["status"] == BotStatus.OFFLINE and socket_ok:
                meta["status"] = BotStatus.IDLE

    def set_status(self, bot_id, status: BotStatus, task: str = None):
        bid = self._nid(bot_id)
        with self._lock:
            if bid not in self._bots:
                return
            self._bots[bid]["status"] = status
            self._bots[bid]["current_task"] = task
            if status == BotStatus.IDLE:
                self._bots[bid]["current_task"] = None

    def mark_online(self, bot_id):
        bid = self._nid(bot_id)
        with self._lock:
            if bid not in self._bots:
                return
            self._bots[bid]["status"] = BotStatus.IDLE
            self._bots[bid]["heartbeat"] = time.time()
            self._bots[bid]["last_active"] = datetime.datetime.now()
            self._bots[bid]["current_task"] = None

    def mark_offline(self, bot_id):
        bid = self._nid(bot_id)
        with self._lock:
            if bid not in self._bots:
                return
            self._bots[bid]["status"] = BotStatus.OFFLINE
            self._bots[bid]["current_task"] = None

    def mark_error(self, bot_id):
        bid = self._nid(bot_id)
        with self._lock:
            if bid in self._bots:
                self._bots[bid]["status"] = BotStatus.ERROR

    def pick_idle_bot(self):
        with self._lock:
            candidates = [
                (bid, meta) for bid, meta in self._bots.items()
                if meta["status"] == BotStatus.IDLE
                and meta["instance"].running_event.is_set()
                and getattr(meta["instance"], "sock39699", None)
                and not getattr(meta["instance"], "is_trolling", False)
                and not getattr(meta["instance"], "is_busy", False)
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda x: (
                x[1]["task_count"],
                -(x[1]["last_active"].timestamp() if x[1]["last_active"] else 0)
            ))
            return candidates[0][1]["instance"]

    def get_all_online(self):
        with self._lock:
            return [
                meta["instance"] for meta in self._bots.values()
                if meta["status"] not in (BotStatus.OFFLINE, BotStatus.ERROR)
                and meta["instance"].running_event.is_set()
                and getattr(meta["instance"], "sock39699", None)
            ]

    def check_heartbeats(self):
        now = time.time()
        with self._lock:
            for bid, meta in self._bots.items():
                hb = meta["heartbeat"]
                if hb and (now - hb) > self.HEARTBEAT_TIMEOUT:
                    if meta["status"] not in (BotStatus.OFFLINE, BotStatus.BUSY):
                        meta["status"] = BotStatus.OFFLINE
                        logger.warning(f"[Pool] Bot#{bid} OFFLINE (heartbeat timeout)")

    def snapshot(self):
        with self._lock:
            result = []
            for bid, meta in self._bots.items():
                inst = meta["instance"]
                result.append({
                    "bot_id":        bid,
                    "nickname":      getattr(inst, "nickname", None) or "?",
                    "status":        meta["status"].value,
                    "current_task":  meta["current_task"],
                    "task_count":    meta["task_count"],
                    "last_active":   str(meta["last_active"]) if meta["last_active"] else None,
                    "heartbeat_ago": round(time.time() - meta["heartbeat"], 1) if meta["heartbeat"] else None,
                    "has_socket":    bool(getattr(inst, "sock39699", None)),
                    "running":       bool(getattr(inst, "running_event", None) and inst.running_event.is_set()),
                    "game_uid":      getattr(inst, "botid", None),
                })
            return result

    def increment_task(self, bot_id):
        bid = self._nid(bot_id)
        with self._lock:
            if bid in self._bots:
                self._bots[bid]["task_count"] += 1

    def unregister(self, bot_id):
        bid = self._nid(bot_id)
        with self._lock:
            self._bots.pop(bid, None)


BOT_POOL = BotPool()


# ====================== CENTRAL SCHEDULER ======================
class Scheduler:
    MAX_CONCURRENT = 5

    def __init__(self, pool: BotPool):
        self.pool  = pool
        self._q: queue.Queue[SchedulerRequest] = queue.Queue()
        self._running = True
        self._worker = threading.Thread(target=self._loop, daemon=True, name="Scheduler-Worker")
        self._worker.start()
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="Scheduler-HB")
        self._hb_thread.start()

    def submit(self, command: str, task_fn, callback=None, timeout: int = None) -> SchedulerRequest:
        req = SchedulerRequest(command, task_fn, callback)
        if timeout:
            req.TIMEOUT_SEC = timeout
        self._q.put(req)
        SCHED_LOGGER.log(req.request_id, command, "QUEUED", extra="Waiting for bot")
        logger.info(f"[Scheduler] SUBMIT | ReqID={req.request_id} | Command={command} | QSize={self._q.qsize()}")
        return req

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                req: SchedulerRequest = self._q.get(timeout=1)
            except queue.Empty:
                continue
            if req.is_expired():
                logger.warning(f"[Scheduler] TIMEOUT | ReqID={req.request_id} | Command={req.command}")
                if req.callback:
                    req.callback(False, "⏰ Yêu cầu hết thời gian chờ (timeout)")
                self._q.task_done()
                continue
            bot = self._wait_for_bot(timeout=60)
            if not bot:
                if req.is_expired():
                    logger.warning(f"[Scheduler] NO_BOT_EXPIRED | ReqID={req.request_id}")
                    if req.callback:
                        req.callback(False, "⚠️ Toàn bộ bot đang bận, yêu cầu bị hủy do timeout.")
                    self._q.task_done()
                    continue
                self._q.put(req)
                self._q.task_done()
                time.sleep(0.5)
                continue
            threading.Thread(
                target=self._execute,
                args=(req, bot),
                daemon=True,
                name=f"Task-{req.request_id}"
            ).start()
            self._q.task_done()

    def _wait_for_bot(self, timeout=60) -> object:
        deadline = time.time() + timeout
        while time.time() < deadline:
            bot = self.pool.pick_idle_bot()
            if bot:
                return bot
            time.sleep(0.3)
        return None

    def _execute(self, req: SchedulerRequest, bot):
        bot_id   = bot.bot_config.get("bot_id") or getattr(bot, "botid", "?")
        nickname = getattr(bot, "nickname", str(bot_id))
        t_start  = time.time()
        self.pool.set_status(bot_id, BotStatus.BUSY, req.command)
        self.pool.increment_task(bot_id)
        bot.is_busy = True
        success = False
        error_msg = ""
        try:
            logger.info(f"[Scheduler] START | ReqID={req.request_id} | Bot={nickname} | Command={req.command}")
            req.task_fn(bot)
            success = True
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Scheduler] ERROR | ReqID={req.request_id} | Bot={nickname} | Err={e}")
            self.pool.mark_error(bot_id)
            if req.retry_count < SchedulerRequest.MAX_RETRIES:
                req.retry_count += 1
                logger.info(f"[Scheduler] RETRY {req.retry_count}/{SchedulerRequest.MAX_RETRIES} | ReqID={req.request_id}")
                self._q.put(req)
            else:
                if req.callback:
                    req.callback(False, f"❌ Bot lỗi sau {req.retry_count} lần thử: {error_msg}")
                SCHED_LOGGER.log(req.request_id, req.command, nickname,
                                 processing_time=round(time.time()-t_start, 2),
                                 failed=True, retry_count=req.retry_count)
        finally:
            bot.is_busy = False
            self.pool.set_status(bot_id, BotStatus.COOLDOWN, None)
            time.sleep(BotPool.COOLDOWN_SEC)
            self.pool.set_status(bot_id, BotStatus.IDLE)
        if success:
            proc_time = round(time.time() - t_start, 2)
            SCHED_LOGGER.log(req.request_id, req.command, nickname,
                             processing_time=proc_time, success=True,
                             retry_count=req.retry_count)
            if req.callback:
                req.callback(True, f"✅ Hoàn thành [{proc_time}s] | Bot: {nickname}")

    def _heartbeat_loop(self):
        while self._running:
            self.pool.check_heartbeats()
            time.sleep(5)

    def queue_size(self):
        return self._q.qsize()


SCHEDULER: Scheduler = None


# ====================== BOT MANAGER ======================
class BotManager:
    def __init__(self):
        self.bots = {}
        self.lock = threading.RLock()
        self.current_index = 0
        self.filename = "bot.json"
        self.config = {"bots": []}
        self.load_config()

    def load_config(self):
        try:
            if not os.path.exists(self.filename):
                with open(self.filename, "w", encoding="utf-8") as f:
                    json.dump({"bots": []}, f, indent=4, ensure_ascii=False)
            with open(self.filename, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                self.config = {"bots": []}
                return
            self.config = json.loads(content)
            if "bots" not in self.config: self.config["bots"] = []
            self.bots.clear()
            for bot_data in self.config["bots"]:
                try:
                    bot_id = bot_data.get("bot_id")
                    if not bot_id or "auth_bot_login" not in bot_data: continue
                    bot_instance = FreeFireTCP(bot_data, self)
                    bot_instance.bot_config = bot_data
                    bot_instance.botid = bot_data.get("botid")
                    bot_instance.nickname = bot_data.get("nickname")
                    self.bots[bot_id] = bot_instance
                except: pass
        except:
            self.config = {"bots": []}

    def save_config(self):
        try:
            with self.lock:
                new_list = []
                for bot_id, bot_instance in self.bots.items():
                    bot_config = bot_instance.bot_config.copy()
                    bot_config["bot_id"] = bot_id
                    if getattr(bot_instance, "botid", None): bot_config["botid"] = bot_instance.botid
                    if getattr(bot_instance, "nickname", None): bot_config["nickname"] = bot_instance.nickname
                    if "access_bot" not in bot_config: bot_config["access_bot"] = []
                    new_list.append(bot_config)
                self.config["bots"] = new_list
                with open(self.filename, "w", encoding="utf-8") as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
        except: pass

    def get_available_bot(self):
        return BOT_POOL.pick_idle_bot()

    def get_all_online_bots(self):
        return BOT_POOL.get_all_online()

    # ★ FIX: resolve bot — nhận cả system key (int/str) và game UID (botid)
    def _resolve_bot(self, bot_id):
        if bot_id is None:
            return None
        # Try direct dict lookup
        if bot_id in self.bots:
            return self.bots[bot_id]
        # Try int/str key
        try:
            bi = int(str(bot_id).strip())
            if bi in self.bots:
                return self.bots[bi]
            if str(bi) in self.bots:
                return self.bots[str(bi)]
        except Exception:
            pass
        # Try game UID (botid) — quan trọng khi admin gõ UID game dài
        try:
            target = str(bot_id).strip()
            for k, b in self.bots.items():
                b_id = getattr(b, "botid", None)
                if b_id is not None and str(b_id).strip() == target:
                    return b
                bc = getattr(b, "bot_config", None)
                if isinstance(bc, dict):
                    for _k in ("botid", "bot_id"):
                        v = bc.get(_k)
                        if v is not None and str(v).strip() == target:
                            return b
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_duration(time_str):
        time_str = str(time_str).strip().lower()
        try:
            if time_str.endswith("d"):
                return datetime.timedelta(days=int(time_str[:-1]))
            elif time_str.endswith("h"):
                return datetime.timedelta(hours=int(time_str[:-1]))
            elif time_str.endswith("m"):
                return datetime.timedelta(minutes=int(time_str[:-1]))
            if time_str.isdigit():
                return datetime.timedelta(days=int(time_str))
        except Exception:
            pass
        return None

    def check_permission(self, bot_id, uid):
        try:
            uid = int(str(uid).strip())
        except:
            return False, "UID không hợp lệ"
        bot = self._resolve_bot(bot_id)
        if not bot:
            return False, f"Bot không tồn tại (id={bot_id!r})"
        access_list = bot.bot_config.get("access_bot", [])
        now = datetime.datetime.now()
        for entry in access_list:
            try:
                entry_uid = int(str(entry.get("uid", "")).strip())
            except Exception:
                continue
            if entry_uid == uid:
                expire_str = str(entry.get("expire", "")).strip()
                try:
                    exp_time = datetime.datetime.strptime(expire_str, "%Y-%m-%d %H:%M:%S")
                    remaining = exp_time - now
                    if remaining.total_seconds() <= 0:
                        self.deleteId(bot_id, uid)
                        return False, f"Quyền đã hết hạn lúc {expire_str}"
                    days = remaining.days
                    hours, rem = divmod(remaining.seconds, 3600)
                    minutes = rem // 60
                    remain_str = f"{days}d {hours}h {minutes}m"
                    return True, remain_str
                except Exception:
                    return False, "Lỗi dữ liệu quyền"
        return False, "Chưa được cấp quyền"

    def add_uid_to_access(self, bot_id, uid, time_str):
        try:
            uid = int(str(uid).strip())
        except:
            return "invalid_params"
        delta = self._parse_duration(str(time_str).strip())
        if delta is None:
            return "invalid_time"
        bot = self._resolve_bot(bot_id)
        if not bot:
            logger.warning(
                f"[add_uid_to_access] Bot {bot_id!r} không tìm thấy. "
                f"system_keys={list(self.bots.keys())} "
                f"game_uids={[getattr(b,'botid',None) for b in self.bots.values()]}"
            )
            return "invalid_params"
        now = datetime.datetime.now()
        new_expire = now + delta
        new_expire_str = new_expire.strftime("%Y-%m-%d %H:%M:%S")
        with self.lock:
            access_list = bot.bot_config.get("access_bot", [])
            found = False
            for entry in access_list:
                try:
                    if int(str(entry.get("uid", "")).strip()) == uid:
                        entry["expire"] = new_expire_str
                        entry["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                        found = True
                        break
                except Exception:
                    continue
            if not found:
                access_list.append({
                    "uid": uid,
                    "expire": new_expire_str,
                    "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "updated_at": now.strftime("%Y-%m-%d %H:%M:%S")
                })
            bot.bot_config["access_bot"] = access_list
            self.save_config()
        return True, new_expire_str

    def deleteId(self, bot_id, uid):
        try:
            uid = int(str(uid).strip())
        except:
            return False
        bot = self._resolve_bot(bot_id)
        if not bot:
            return False
        with self.lock:
            access_list = bot.bot_config.get("access_bot", [])
            new_list = [e for e in access_list if int(str(e.get("uid", "")).strip()) != uid]
            if len(new_list) == len(access_list):
                return False
            bot.bot_config["access_bot"] = new_list
            self.save_config()
        return True


# ============================================================
# ★ BOT ADMIN HELPER
# ============================================================
def _is_bot_admin(bot, uid) -> bool:
    try:
        uid = int(str(uid).strip())
    except Exception:
        return False

    try:
        if uid in TELEGRAM_ADMINS:
            logger.info(f"[AdminCheck] uid={uid} → TG admin")
            return True
    except Exception:
        pass

    try:
        if getattr(bot, "botid", None) and int(bot.botid) == uid:
            logger.info(f"[AdminCheck] uid={uid} → bot owner")
            return True
    except Exception:
        pass

    try:
        bid = bot.bot_config.get("bot_id") if getattr(bot, "bot_config", None) else None
        if bid is not None and AdminManager.is_admin(bid, uid):
            logger.info(f"[AdminCheck] uid={uid} → AdminManager")
            return True
    except Exception:
        pass

    try:
        for e in (bot.bot_config.get("access_bot") or []):
            if int(str(e.get("uid", "")).strip()) == uid:
                lv = int(e.get("vip", 0))
                if lv >= 8:
                    logger.info(f"[AdminCheck] uid={uid} → VIP{lv}")
                    return True
    except Exception:
        pass

    logger.info(f"[AdminCheck] uid={uid} → DENIED")
    return False


# ====================== FREE FIRE TCP BOT ======================
class FreeFireTCP:
 def __init__(self, bot_config, manager):
  self.running = True
  self.bot_config = bot_config
  self.manager = manager
  self.running_event = threading.Event()
  self.running_event.set()
  self.rstatus = (0, 0)
  self.ids = []
  self.status = True
  self.started = False
  self.base_url = "https://loginbp.ppmainecoonghj.com"
  self.reconnect_lock = threading.Lock()
  self._online_lock = threading.Lock()
  self._online_gen = 0
  self._chat_gen = 0
  self.last_spam_time = {}
  self.roomcode = self.packetAuth = self.packetAuthLobby = self.playerstatus = None
  self.AuthenCode = self.sock39699 = self.sock39801 = None
  self.ChatIP = self.OnlineIP = self.OnlinePort = self.ChatPort = None
  self.roomid = self.GuildIds = self.DesId = self.botid = None
  self.key = self.iv = self.token = b''
  self.login_session = self._data = None
  self.botid = self.nickname = self.region = None
  self.is_trolling = False
  self.is_busy = False
  self.last_room_id       = None
  self.room_id_event      = threading.Event()
  self._lag_music_started = False
  self.squad_chat_uid     = None
  self.antibot_active     = False
  self.antibot_thread     = None
  self.antibot_promo_thread = None
  self.antibot_kicked     = set()
  self.antibot_scanned    = {}
  self.Emotes = [
    909054004, 909055007, 909049010, 909041005, 909038010,
    909039011, 909040010, 909000081, 909000085, 909000063,
    909000075, 909033001, 909000090, 909000068, 909000098,
    909051003, 909037011, 909038012, 909035012, 909042008,
    909033002, 909042007, 909045001, 909035007, 909053015
  ]

 def _get_pool(self):
  p = getattr(self.manager, "pool", None)
  return p if p is not None else BOT_POOL

 def _IIl(self, logindata, jsdata):
  self._online_gen += 1
  self._chat_gen += 1
  self.cleanup()
  time.sleep(0.5)
  self._data = jsdata
  self._gen = TAO_PACKET(logindata, jsdata)
  self._bot = self.bot_session(self)
  self.running_event.set()
  time.sleep(1)
  threading.Thread(target=self.connect39801, daemon=True).start()
  threading.Thread(target=self.connect39699, daemon=True).start()
  threading.Thread(target=self._heartbeat_sender, daemon=True).start()

 def _heartbeat_sender(self):
  bot_id = self.bot_config.get("bot_id")
  while self.running_event.is_set() and bot_id:
      self._get_pool().heartbeat(bot_id)
      time.sleep(5)

 def visit_thread(bot, cid, type, uid):
  result = send_visit(uid)
  bot.reply(cid, type, result)

 def cleanup(self):
  self.running_event.clear()
  self.antibot_active = False
  bot_id = self.bot_config.get("bot_id")
  if bot_id:
      self._get_pool().mark_offline(bot_id)
  sockets = [self.sock39699, self.sock39801]
  for sock in sockets:
   try:
    if sock:
     sock.shutdown(2)
     sock.close()
   except: pass
  self.sock39699 = self.sock39801 = None

 def restart_bot(self):
  self.cleanup()
  time.sleep(2)
  self.running_event.set()
  self.started = False
  self.start()

 def AntiDisconnect(self, sock):
  while True:
   sock.send(bytes([0, 2, 0, 1]))
   time.sleep(25)

 def connect39801(self):
  gen = self._chat_gen
  with self.reconnect_lock:
   if not self.running_event.is_set() or gen != self._chat_gen: return
   client = None
   bot_label = self.bot_config.get("bot_id", "?")
   try:
    client = socket.create_connection((self.ChatIP, int(self.ChatPort)), timeout=10)
    client.settimeout(10)
    client.sendall(self.packetAuth)
    logger.info(f"[Bot#{bot_label}] Chat OK {self.ChatIP}:{self.ChatPort}")
    guild_active = self.bot_config.get("active-clan", True)
    if self.GuildIds and guild_active:
     client.send(self._bot.join_channel(self.GuildIds, self.AuthenCode, 1))
    client.send(self._bot.join_channel(None, None, 5))
    self.sock39801 = client
    while self.running_event.is_set() and gen == self._chat_gen:
     try:
      data = client.recv(4096)
      if len(data) == 0: break
      if data.hex()[:4] == "1200" and len(data) > 10:
       try:
        _PACKET_EXECUTOR.submit(self.C1200, data, client)
       except RuntimeError:
        pass
     except socket.timeout:
      continue
     except Exception:
      break
   except Exception as e:
    logger.warning(f"[Bot#{bot_label}] Chat connection error: {e}")
   finally:
    if client:
     try: client.close()
     except: pass
    if self.sock39801 is client:
     self.sock39801 = None
    if self.running_event.is_set() and gen == self._chat_gen:
     time.sleep(5)
     if self.running_event.is_set() and gen == self._chat_gen:
      threading.Thread(target=self.connect39801, daemon=True).start()

 def connect39699(self):
  gen = self._online_gen
  if not self.running_event.is_set() or gen != self._online_gen: return
  if not self._online_lock.acquire(blocking=False): return
  client = None
  bot_label = self.bot_config.get("bot_id", "?")
  try:
   pkt = self.packetAuthLobby or self.packetAuth
   if not pkt:
    raise RuntimeError("Online missing auth packet")
   client = socket.create_connection((self.OnlineIP, int(self.OnlinePort)), timeout=10)
   client.settimeout(10)
   client.sendall(pkt)
   self.sock39699 = client
   logger.info(f"[Bot#{bot_label}] Online OK uid={self.botid} nick={self.nickname} pkt={len(pkt)} {self.OnlineIP}:{self.OnlinePort}")
   self._get_pool().mark_online(bot_label)
   while self.running_event.is_set() and gen == self._online_gen:
    try:
     data = client.recv(4096)
     if len(data) == 0:
      logger.warning(f"[Bot#{bot_label}] Online closed by server")
      break
     hx = data.hex()
     if hx[:4] == "0f00":
      try:
       decdata = json.loads(protobuf_dec(hx[10:]))
       self.playerstatus = decdata
       rid = decdata.get("5", {}).get("1", {}).get("15", None)
       self.roomid = rid if rid else None
      except Exception:
       pass
     if hx[:4] == "0600" and len(data) <= 55:
      try:
       res = json.loads(protobuf_dec(hx[10:]))
       uid = res.get("5", {}).get("1")
       if uid:
        messages = """[c][b][C678DD]const [61AFEF]Response [E5C07B]= [C678DD]() [ABB2BF]=> [ABB2BF]{{
  [C678DD]return [ABB2BF]{{
    [E5C07B]uid[E5C07B]: [E5C07B]{}[ABB2BF],
    [E5C07B]tittle[ABB2BF]: [98C379]"Request accepted"[ABB2BF],
    [E5C07B]telegram[ABB2BF]: [98C379]"@anhcodeclick"[ABB2BF]
  [ABB2BF]}}
[ABB2BF]}}""".format(uid)
        self._bot.reply(uid, 2, messages)
      except Exception:
       pass
     if self.status and hx[:4] in ("0500", "0f00", "0600"):
      try:
       _PACKET_EXECUTOR.submit(self.gringay, data)
      except RuntimeError:
       pass
    except socket.timeout:
     continue
    except Exception as e:
     if not self.running_event.is_set() or gen != self._online_gen: break
     logger.warning(f"[Bot#{bot_label}] Online recv error: {e}")
     break
  except Exception as e:
   logger.warning(f"[Bot#{bot_label}] Online connection error: {e} | {self.OnlineIP}:{self.OnlinePort}")
  finally:
   try: self._online_lock.release()
   except Exception: pass
   if client:
    try: client.close()
    except: pass
   if self.sock39699 is client:
    self.sock39699 = None
   if self.running_event.is_set() and gen == self._online_gen:
    self._get_pool().mark_offline(bot_label)
    time.sleep(3)
    if self.running_event.is_set() and gen == self._online_gen:
     threading.Thread(target=self.connect39699, daemon=True).start()

 def C1200(self, data, client):
  try:
   data = data1200(data)
   if not data.valid: return False
   uid, cid, type = data.uid, data.cid, data.type
   if int(self.botid) in [cid, uid]: return False
   message, name = data.message, data.name
   idlist = self.get_user_status(1)
   is_admin = _is_bot_admin(self, uid)

   try:
    logger.info(f"[C1200] uid={uid} cid={cid} type={type} is_admin={is_admin} msg={message!r}")
   except Exception:
    pass

   if is_admin and message.startswith("@"):
    if message.startswith("@kb"):
     RequestAddingFriend(int(message.split()[1]), self.token, self.base_url)
     self._bot.reply(cid, type, "OK")

    elif message.startswith("@admin-aduser"):
     try:
      clean = "".join(c for c in message if c.isprintable() or c == " ")
      parts = clean.split()
      logger.info(f"[admin-aduser] parts={parts} sender={uid} this_bot_game_uid={self.botid}")
      logger.info(f"[admin-aduser] system_keys={list(self.manager.bots.keys())}")
      logger.info(f"[admin-aduser] game_uids={[getattr(b, 'botid', None) for b in self.manager.bots.values()]}")

      # ★ Cú pháp chuẩn: @admin-aduser <BOT_GAME_UID> <USER_UID> <TIME>
      #   BOT_GAME_UID là field "botid" trong bot.json (KHÔNG phải bot_id)
      #   VD: @admin-aduser 18350293449 3240445748 1d
      #   → bot có botid=18350293449 (system key = 6), grant user 3240445748 trong 1 ngày
      # Fallback 2: @admin-aduser <USER_UID> <TIME> → grant cho bot hiện tại
      if len(parts) < 3:
       self._bot.reply(cid, type,
        "[B][c][FF0000]Sai cú pháp!\n"
        "[FFFFFF]Dùng:\n"
        "[FFFF00]@admin-aduser <BOT_GAME_UID> <USER_UID> <TIME>\n"
        "[FFFF00]@admin-aduser <USER_UID> <TIME>\n"
        "[AAAAAA]VD: @admin-aduser 18350293449 3240445748 1d")
       return

      ext  = parts[-1].strip()
      args = parts[1:-1]

      # ★ Helper: tìm system key từ spec.
      #   Ưu tiên 1: nếu spec >= 10^8 → coi là GAME UID, match theo field "botid"
      #   Ưu tiên 2: match theo system key (int/str)
      def _find_bot_key(spec):
       spec_s = str(spec).strip()
       try:
        spec_i = int(spec_s)
       except Exception:
        spec_i = None

       # ── Match theo GAME UID (field "botid") nếu spec là UID dài
       if spec_i is not None and spec_i >= 10**8:
        for k, b in self.manager.bots.items():
         b_id = getattr(b, "botid", None)
         if b_id is not None:
          try:
           if int(str(b_id).strip()) == spec_i:
            logger.info(f"[_find_bot_key] game_uid {spec_i} → system_key={k!r}")
            return k
          except Exception:
           pass
         bc = getattr(b, "bot_config", None)
         if isinstance(bc, dict):
          for _k in ("botid", "bot_id"):
           v = bc.get(_k)
           if v is not None:
            try:
             if int(str(v).strip()) == spec_i:
              logger.info(f"[_find_bot_key] game_uid {spec_i} (bc.{_k}) → system_key={k!r}")
              return k
            except Exception:
             pass
        return None

       # ── Match theo system key trực tiếp
       for k in self.manager.bots.keys():
        if str(k) == spec_s:
         return k
        if spec_i is not None:
         try:
          if int(k) == spec_i:
           return k
         except Exception:
          pass
       return None

      target_botid = self.bot_config["bot_id"]
      user_uid_str = None
      note = ""

      if len(args) == 1:
       user_uid_str = args[0]

      elif len(args) == 2:
       x, y = args
       kx = _find_bot_key(x)
       ky = _find_bot_key(y)
       logger.info(f"[admin-aduser] _find_bot_key({x!r})={kx!r} | _find_bot_key({y!r})={ky!r}")

       # Chuẩn: x = bot game uid, y = user uid
       if kx is not None:
        target_botid = kx
        user_uid_str = y
        note = f" (bot game_uid={x})"
       elif ky is not None:
        target_botid = ky
        user_uid_str = x
        note = f" (bot game_uid={y})"
       else:
        # Không match bot nào → fallback grant user=y cho bot hiện tại
        user_uid_str = y
        note = f" (FALLBACK bot '{x}' không match → dùng bot hiện tại {target_botid})"
        logger.warning(f"[admin-aduser] {note}")
      else:
       self._bot.reply(cid, type, "[B][c][FF0000]Quá nhiều tham số (max 3)!"); return

      try:
       add_uid_int = int(str(user_uid_str).strip())
      except Exception:
       self._bot.reply(cid, type, f"[B][c][FF0000]UID user không hợp lệ: {user_uid_str!r}")
       return

      target_nickname = "?"
      try:
       _tb = self.manager._resolve_bot(target_botid)
       if _tb:
        target_nickname = getattr(_tb, "nickname", None) or "?"
      except Exception:
       pass

      result = self.manager.add_uid_to_access(target_botid, add_uid_int, ext)
      logger.info(
       f"[admin-aduser] ADD bot_key={target_botid!r} nick={target_nickname} "
       f"user={add_uid_int} ext={ext} → {result}"
      )

      if isinstance(result, tuple) and result[0] == True:
       self._bot.reply(cid, type,
        f"[B][c][00FF00]✓ Cấp quyền OK!{note}\n"
        f"[FFFFFF]Bot key: [FFFF00]{target_botid}\n"
        f"[FFFFFF]Bot nick: [FFFF00]{target_nickname}\n"
        f"[FFFFFF]User UID: [FFFF00]{add_uid_int}\n"
        f"[FFFFFF]Hết hạn: [FFFF00]{result[1]}")
      elif result == "invalid_time":
       self._bot.reply(cid, type,
        f"[B][c][FF0000]Sai thời gian: {ext!r}\n[AAAAAA]VD: 30d, 12h, 60m")
      elif result == "invalid_params":
       self._bot.reply(cid, type,
        f"[B][c][FF0000]Bot không tồn tại!\n"
        f"[AAAAAA]target_key={target_botid}\n"
        f"[AAAAAA]system_keys={list(self.manager.bots.keys())}\n"
        f"[AAAAAA]game_uids={[getattr(b,'botid',None) for b in self.manager.bots.values()]}")
      else:
       self._bot.reply(cid, type, f"[B][c][FF0000]Lỗi: {result}")
     except Exception as _e:
      logger.error(f"[admin-aduser] EXC: {_e}\n{traceback.format_exc()}")
      try: self._bot.reply(cid, type, f"[B][c][FF0000]Lỗi: {str(_e)[:80]}")
      except Exception: pass
     return

    elif message.startswith("@admin-deluser"):
     parts = message.split()
     if len(parts) < 2: self._bot.reply(cid, type, "@admin-deluser uid"); return
     success = self.manager.deleteId(self.bot_config["bot_id"], parts[1])
     if success: self._bot.reply(cid, type, f"[B][c][00FF00]✓ Đã xóa quyền UID: {parts[1]}")
     else: self._bot.reply(cid, type, f"[B][c][FF0000]× Không tìm thấy UID: {parts[1]}")
     return

    elif message.startswith("@admin-setvip"):
     parts = message.split()
     if len(parts) < 3:
      self._bot.reply(cid, type, "[B][c][FF0000]Dùng: @admin-setvip [UID] [VIP_level]")
      return
     try:
      setvip_uid = int(parts[1].strip())
      setvip_level = int(parts[2].strip())
     except Exception:
      self._bot.reply(cid, type, "[B][c][FF0000]UID/VIP không hợp lệ!"); return

     # Search VIP across ALL bots
     found_in = []
     with self.manager.lock:
      for bid, binst in self.manager.bots.items():
       al = binst.bot_config.get("access_bot", [])
       changed = False
       for entry in al:
        try:
         if int(str(entry.get("uid", "")).strip()) == setvip_uid:
          entry["vip"] = setvip_level
          entry["updated_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
          changed = True
        except Exception:
         continue
       if changed:
        binst.bot_config["access_bot"] = al
        found_in.append(bid)
      if found_in:
       self.manager.save_config()

     if found_in:
      self._bot.reply(cid, type,
       f"[B][c][00FF00]✓ Set VIP {setvip_level} cho UID: {setvip_uid}\n"
       f"[FFFFFF]Bots: [FFFF00]{found_in}")
     else:
      self._bot.reply(cid, type,
       f"[B][c][FF0000]× UID {setvip_uid} chưa có quyền ở BẤT KỲ bot nào!\n"
       f"[AAAAAA]Dùng @admin-aduser {setvip_uid} 30d trước")
     return

    elif message.startswith("@gen"):
     parts = message.split()
     if len(parts) != 3:
      self._bot.reply(cid, type, "[b][c]Sử dụng: @gen time count"); return
     time_str, max_uses_str = parts[1], parts[2]
     try:
      max_uses = int(max_uses_str)
      code = GiftCode.create(time_str, max_uses, uid)
      self._bot.reply(cid, type, str(code))
      self._bot.reply(cid, type, "Tạo giftcode thành công!\nCode: {}\nTime: {}\nCount: {}/{}\nTạo bởi: {}".format(code, time_str, 0, max_uses, name))
     except ValueError: self._bot.reply(cid, type, "Lỗi")

   elif message.startswith("@redeem"):
    parts = message.split()
    if len(parts) != 2:
     self._bot.reply(cid, type, "Sử dụng: @redeem giftcode"); return
    self._bot.reply(cid, type, "Đang xử lí..")
    code = parts[1].upper()
    success, result = GiftCode.redeem(code, uid)
    if success:
     botid = self.bot_config["bot_id"]
     add_result = self.manager.add_uid_to_access(botid, int(uid), result)
     if isinstance(add_result, tuple) and add_result[0] == True:
      self._bot.reply(cid, type, "Nhập code thành công")
      self._bot.reply(cid, type, "/help - show all command")
     else: self._bot.reply(cid, type, "Lỗi!")
    else: self._bot.reply(cid, type, "%s" % result)

   if message and (message.startswith("/start") or message.startswith("/help")):
    try: exps = self.get_user_status(3, uid)
    except Exception: exps = "N/A"
    self._bot.reply(cid, type,
     "[B][C][00FF00]FREE FIRE SQUAD BOT\n"
     "[FFFF00]     DANH SACH LENH\n"
     "[AAAAAA]--------------------\n"
     "[00BFFF][ TAO DOI / MOI ]\n"
     "[FFFFFF]/2 /3 /4 /5 /6\n"
     "[FFFFFF]/5 [UID] — tao team 5 + moi UID\n"
     "[FFFFFF]/6 [UID] — tao team 6 + moi UID\n"
     "[FF69B4]/antibot [UID] — kick acc < lv10\n"
     "[FF69B4]/antibot stop — tat anti-bot + out phong\n"
     "[AAAAAA]--------------------\n"
     "[00BFFF][ SQUAD / JOIN ]\n"
     "[00FF00]/join [TC] — vao phong + mua + nhac\n"
     "[FFFFFF]/chat [TC] [msg] — chat squad\n"
     "[FFFFFF]/chat [TC] hello — bot o lai squad\n"
     "[FFFFFF]/sms [TC] [msg] — gui tin squad\n"
     "[FFFFFF]/sinv [UID] — spam moi vao squad\n"
     "[FFFFFF]/rinv — nhan loi moi"
    )
    time.sleep(0.55)
    self._bot.reply(cid, type,
     "[00BFFF][ INFO / TOOL ]\n"
     "[FFFFFF]/info [UID] — xem thong tin\n"
     "[FFFFFF]/status [UID] — trang thai online\n"
     "[FFFFFF]/region [UID] — khu vuc nap the\n"
     "[FFFFFF]/isbanned [UID] — check ban\n"
     "[FFFFFF]/likes [UID] — buff like\n"
     "[FFFFFF]/visit [UID] — buff visit\n"
     "[FFFFFF]/vip — xem VIP cua ban\n"
     "[AAAAAA]--------------------\n"
     "[00BFFF][ KHAC ]\n"
     "[FFFFFF]/share bot — chia se do (VIP8)\n"
     "[FFFFFF]/share [UID] vip8 — xin do\n"
     "[FFFFFF]/mute [channel] — khoa mom\n"
     "[FFFFFF]/unmute [channel]\n"
     "[FFFFFF]/ai [cau hoi] — AI chat\n"
     "[FFFFFF]/help /start — menu nay"
    )
    time.sleep(0.55)
    self._bot.reply(cid, type,
     "[00BFFF][ ADMIN ]\n"
     "[FFFFFF]@admin-aduser [UID] 30d\n"
     "[FFFFFF]@admin-deluser [UID]\n"
     "[FFFFFF]@admin-setvip [UID] [lv]\n"
     "[FFFFFF]@redeem [CODE]\n"
     "[AAAAAA]--------------------\n"
     f"[00FF00]uid: [FFFF00]{uid}\n"
     f"[00FF00]name: [FFFFFF]{name}\n"
     f"[00FF00]time: [FFD700]{exps}"
    )
    return

   if type in [2, None] and not is_admin:
    allowed, perm_reason = self.manager.check_permission(self.bot_config["bot_id"], uid)
    if not allowed:
     self._bot.reply(cid, type,
      f"[B][c][FF0000]× Bạn chưa được cấp quyền dùng bot\n"
      f"[FFFFFF]Lý do: {perm_reason}\n"
      f"[AAAAAA]Gõ /help xem lệnh | Liên hệ admin: @anhcodeclick"
     )
     return

   if message.startswith("/sms"):
    parts = message.split(maxsplit=2)
    if len(parts) < 3: self._bot.reply(cid, type, "[B][c]/sms [teamcode] [message]"); return
    tcode = int(parts[1])
    self.rstatus = (1, parts[2])
    self.sock39699.send(self._bot.join_squad(tcode))
    self._bot.reply(cid, type, "[B][c]Đang gửi tin nhắn..")
    payload = json.dumps({"StickerStr": "[1=1200000002-11]", "type": "Sticker"})
    self.sock39801.send(self._bot.send_object(payload, cid, type))

   elif message.startswith("/5"):
    if len(message) > 3: self.GenSquads(5, cid, message.split()[1], type, name); return
    self.GenSquads(5, cid, uid, type, name)

   elif message.startswith("/6"):
    if len(message) > 3: self.GenSquads(6, cid, message.split()[1], type); return
    self.GenSquads(6, cid, uid, type)

   elif message.startswith("/antibot"):
    parts = message.strip().split()
    if len(parts) < 2:
     self._bot.reply(cid, type, "[B][c][FF0000]Dùng:\n[FFFF00]/antibot [UID]   [FFFFFF]— bat anti-bot\n[FFFF00]/antibot stop    [FFFFFF]— tat anti-bot + out phong")
     return
    sub = parts[1].strip().lower()
    if sub in ("stop", "off", "end", "dung", "dừng"):
     if getattr(self, "antibot_active", False):
      try: self._bot.reply(cid, type, "[B][c][FFFF00]⏳ Dang tat anti-bot va roi phong...")
      except Exception: pass
      self._antibot_stop(leave=True)
      try: self._bot.reply(cid, type, "[B][c][00FF00]✓ DA DUNG ANTI-BOT\n[FFFFFF]• Watcher da tat\n[FFFFFF]• Promo loop da tat\n[FFFFFF]• Bot DA ROI PHONG")
      except Exception: pass
      logger.info(f"[AntiBot] stopped by command, bot={self.botid} left squad")
     else:
      self._bot.reply(cid, type, "[B][c][FFFF00]AntiBot khong chay (chua bat)")
     return
    target = "".join(c for c in sub if c.isdigit())
    if not target or not target.isdigit():
     self._bot.reply(cid, type, "[B][c][FF0000]UID khong hop le\n[AAAAAA]Hoac dung: /antibot stop")
     return
    self.GenAntiBot(cid, int(target), type, name)

   elif message.startswith("/status"):
    text = get_user_input(str(message))
    if ":" in text: self._bot.reply(cid, type, text); return
    target_uid = str(text).strip()
    if not target_uid.isdigit():
     self._bot.reply(cid, type, "[B][c][FF0000]UID khong hop le"); return
    self._bot.reply(cid, type, "[B][c]Dang lay thong tin..")
    try:
     self.playerstatus = None
     pkt = self._bot.get_history(target_uid)
     if not pkt:
      self._bot.reply(cid, type, "[B][c][FF0000]Khong tao duoc packet status"); return
     if not getattr(self, "sock39699", None):
      self._bot.reply(cid, type, "[B][c][FF0000]Bot mat socket online"); return
     self.sock39699.send(pkt)
     for _ in range(15):
      time.sleep(0.2)
      if self.playerstatus: break
     if self.playerstatus:
      data = get_player_status(self.playerstatus)
      form = self.format_status_message(data, target_uid)
      self._bot.reply(cid, type, form)
     else:
      self._bot.reply(cid, type, f"[B][c][FF0000]Timeout status\n[FFFFFF]uid: {target_uid}")
    except Exception as e:
     self._bot.reply(cid, type, f"[B][c][FF0000]Loi status: {str(e)[:80]}")

   elif message.startswith("/rinv"):
    msg = get_user_input(str(message))
    if ":" in msg: self._bot.reply(cid, type, msg); return
    threading.Thread(target=self.GenSpamRoom, args=(msg,)).start()
    time.sleep(2)
    if self.roomid: self._bot.reply(cid, type, "[B][c]Đang spam '%s' tới phòng '%s'" % (msg[:5], self.roomid))
    else: self._bot.reply(cid, type, "PLAYER IS NOT ON ROOM")

   elif message.startswith("/sinv"):
    parts = message.strip().split()
    if len(parts) != 2:
        self._bot.reply(cid, type, "❌ Dùng: /sinv <uid>")
        return
    sinv_uid = parts[1].strip()
    if not sinv_uid.isdigit(): return self._bot.reply(cid, type, "❌ UID phải là số!")
    sinv_uid = int(sinv_uid)
    if not self.sock39699:
        self._bot.reply(cid, type, "[B][c][FF0000]❌ Bot chưa kết nối!")
        return
    self._bot.reply(cid, type, "[B][c]Đang spam...")
    def run_spam():
        try:
            for i in range(123):
                if not self.sock39699:
                    self._bot.reply(cid, type, "[B][c][FF0000]❌ Mất kết nối!")
                    return
                self.sock39699.send(self._bot.request_join_squad(sinv_uid))
                time.sleep(0.35)
            self._bot.reply(cid, type, "✅ Spam xong!")
        except Exception as e:
            self._bot.reply(cid, type, f"[B][c][FF0000]❌ Lỗi: {str(e)[:80]}")
    threading.Thread(target=run_spam, daemon=True).start()

   elif message.startswith("@share"):
    parts = message.split()
    if len(parts) < 2: return self._bot.reply(cid, type, "[B][C][FF0000]❌ Ví dụ: @share 123456789")
    try: target_uid = int(parts[1])
    except: return self._bot.reply(cid, type, "[B][C][FF0000]❌ UID không hợp lệ")
    self._bot.reply(cid, type, f"[B][C][00FF00]📦 Đang xin đồ từ UID {target_uid}...")
    def do_share():
        try:
            time.sleep(1.2)
            self.sock39699.send(self._bot.ask_for_skin([target_uid]))
            time.sleep(1.2)
            self._bot.reply(cid, type, "[B][C][00FF00]✅ Đã gửi yêu cầu xin đồ!")
        except: self._bot.reply(cid, type, "[B][C][FF0000]❌ Xin đồ thất bại")
    threading.Thread(target=do_share, daemon=True).start()

   elif message.startswith("/share"):
    parts = message.strip().split()
    if len(parts) >= 3 and parts[2].lower() == "vip8":
     target_uid_str = parts[1].strip()
     if not target_uid_str.isdigit():
      self._bot.reply(cid, type, "[B][c][FF0000]❌ UID không hợp lệ!\n[FFFFFF]Ví dụ: /share 123456789 vip8")
      return
     target_uid = int(target_uid_str)
     target_vip = self._get_vip_level(target_uid)
     if target_vip < 8:
      self._bot.reply(cid, type, f"[B][c][FF0000]❌ UID {target_uid} không có VIP 8!\n[FFFFFF]VIP: [FFFF00]{target_vip}")
      return
     if not self.sock39699:
      self._bot.reply(cid, type, "[B][c][FF0000]❌ Bot chưa kết nối!"); return
     self._bot.reply(cid, type, f"[B][c][00FF00]📦 VIP {target_vip} xác nhận!\n[FFFFFF]Đang xin đồ từ UID {target_uid}...")
     def do_share_vip8():
      try:
       time.sleep(1.2)
       self.sock39699.send(self._bot.ask_for_skin([target_uid]))
       time.sleep(1.2)
       self._bot.reply(cid, type, f"[B][c][00FF00]✅ Đã gửi yêu cầu xin đồ từ UID {target_uid}!")
      except Exception as e:
       self._bot.reply(cid, type, f"[B][c][FF0000]❌ Xin đồ thất bại: {str(e)[:80]}")
     threading.Thread(target=do_share_vip8, daemon=True).start()
     return
    if len(parts) >= 2 and parts[1].lower() == "bot":
     vip_level = self._get_vip_level(uid)
     if vip_level < 8:
      self._bot.reply(cid, type, f"[B][c][FF0000]❌ Bạn cần VIP 8!\n[FFFFFF]VIP hiện tại: [FFFF00]{vip_level}\n[AAAAAA]Liên hệ admin: @anhcodeclick")
      return
     self._bot.reply(cid, type, f"[B][c][00FF00]📦 VIP {vip_level} được xác nhận!\n[FFFFFF]Đang gửi yêu cầu chia sẻ đồ...")
     def do_share_bot():
      try:
       time.sleep(1.2)
       self.sock39699.send(self._bot.ask_for_skin([int(uid)]))
       time.sleep(1.2)
       self._bot.reply(cid, type, "[B][c][00FF00]✅ Đã gửi yêu cầu chia sẻ đồ!")
      except: self._bot.reply(cid, type, "[B][c][FF0000]❌ Chia sẻ thất bại")
     threading.Thread(target=do_share_bot, daemon=True).start()
     return
    ids = list(set(self.ids))
    if not ids: self._bot.reply(cid, type, "[B][c][FF0000]❌ Bot chưa vào squad!"); return
    self._bot.reply(cid, type, "[B][c][00FF00]📦 Đang chia sẻ đồ...")
    def do_share():
     try:
      time.sleep(1.2)
      self.sock39699.send(self._bot.ask_for_skin(ids))
      time.sleep(1.2)
      self._bot.reply(cid, type, "[B][c][00FF00]✅ Đã chia sẻ đồ xong!")
     except: self._bot.reply(cid, type, "[B][c][FF0000]❌ Chia sẻ thất bại")
    threading.Thread(target=do_share, daemon=True).start()

   elif message.startswith("/mute"):
    msg = get_user_input(message)
    if ":" in msg: self._bot.reply(cid, type, msg); return
    self.sock39801.send(self._bot.join_channel(msg, "Gayx2", None))
    self._bot.reply(cid, type, "[B][c]Đã khoá mõm '%s'" % msg)

   elif message.startswith("/unmute"):
    msg = get_user_input(message)
    if ":" in msg: self._bot.reply(cid, type, msg); return
    self.sock39801.send(self._bot.leave_channel(msg, None))
    self._bot.reply(cid, type, "[B][c]OK")

   elif message.startswith("/ai"):
    msg = get_user_input(message)
    if ":" in msg: self._bot.reply(cid, type, msg); return
    self._bot.reply(cid, type, gemini(msg))

   elif message.startswith("/likes"):
    msg = get_user_input(message)
    if ":" in msg: return self._bot.reply(cid, type, msg)
    self._bot.reply(cid, type, f"[B][c][00FFFF]Đang buff likes cho UID: [FFFFFF]{msg}...")
    result = send_likes(msg)
    self._bot.reply(cid, type, result)

   elif message.startswith("/visit"):
    parts = message.split()
    if len(parts) != 2: return self._bot.reply(cid, type, "[c][FF0000]Usage: /visit uid")
    v_uid = parts[1]
    self._bot.reply(cid, type, f"""[b][c][FFFF00]ĐANG BUFF VISIT...\n[AAAAAA]UID: {v_uid}""")
    def run():
        result = send_visit(v_uid)
        self._bot.reply(cid, type, result)
    threading.Thread(target=run, daemon=True).start()

   elif message.startswith("/info"):
    text = get_user_input(str(message))
    if ":" in text: self._bot.reply(cid, type, text); return
    target = str(text).strip()
    if not target.isdigit():
     self._bot.reply(cid, type, "[B][c][FF0000]UID khong hop le"); return
    self._bot.reply(cid, type, "[B][c]Dang lay info..")
    try:
     result = send_info(target, self.token, self.base_url)
     self._bot.reply(cid, type, result)
    except Exception as e:
     self._bot.reply(cid, type, f"[B][c][FF0000]Loi info: {str(e)[:80]}")

   elif message.startswith("/region"):
    index = get_user_input(message)
    if ":" in index: self._bot.reply(cid, type, index); return
    target = str(index).strip()
    if not target.isdigit():
     self._bot.reply(cid, type, "[B][c][FF0000]UID khong hop le"); return
    self._bot.reply(cid, type, "[B][c]Dang lay region..")
    try:
     result = send_region(target, self.token, self.base_url)
     self._bot.reply(cid, type, result)
    except Exception as e:
     self._bot.reply(cid, type, f"[B][c][FF0000]Loi region: {str(e)[:80]}")

   elif message.startswith("/isbanned"):
    b_uid = get_user_input(message)
    if ":" in b_uid: self._bot.reply(cid, type, b_uid); return
    target = str(b_uid).strip()
    if not target.isdigit():
     self._bot.reply(cid, type, "[B][c][FF0000]UID khong hop le"); return
    try:
     I = check_banned(target)
     self._bot.reply(cid, type, f"[B][c][FF0000]PLAYER IS BANNED\n[FFFFFF]uid: {target}" if I else f"[B][c][00FF00]NOT BANNED\n[FFFFFF]uid: {target}")
    except Exception as e:
     self._bot.reply(cid, type, f"[B][c][FF0000]Loi isbanned: {str(e)[:80]}")

   elif message.startswith("/chat"):
    parts = message.strip().split(maxsplit=2)
    if len(parts) < 3 or not parts[2].strip():
     self._bot.reply(cid, type, "[B][c][FF0000]❌ Dùng: /chat [teamcode] [tin nhắn]")
     return
    tcode_str = ''.join(c for c in parts[1].strip() if c.isdigit())
    if not tcode_str:
     self._bot.reply(cid, type, "[B][c][FF0000]❌ Teamcode không hợp lệ!"); return
    chat_msg = parts[2].strip()
    try:
     tcode = int(tcode_str)
     if chat_msg.lower() == "hello":
      self.rstatus = (7, tcode)
      self.sock39699.send(self._bot.join_squad(tcode))
      self._bot.reply(cid, type, "[B][c][00FF00]✅ Bot đã tham gia squad!")
     else:
      self.rstatus = (6, chat_msg)
      self.sock39699.send(self._bot.join_squad(tcode))
      self._bot.reply(cid, type, "[B][c][00FF00]✅ Đã gửi vào Squad chat!")
    except Exception as e:
     self._bot.reply(cid, type, f"[B][c][FF0000]❌ Gửi thất bại: {e}")

   elif message.startswith("/join"):
    parts = message.strip().split()
    if len(parts) < 2:
     self._bot.reply(cid, type, "[B][c][FF0000]❌ Dùng: /join [teamcode] [uid1] [uid2] ...")
     return
    allowed, perm_reason = self.manager.check_permission(self.bot_config["bot_id"], uid)
    if not allowed:
     self._bot.reply(cid, type, f"[B][c][FF0000]❌ Bạn chưa có quyền dùng /join\n[FFFFFF]Lý do: {perm_reason}")
     return
    tc_str = ''.join(c for c in parts[1] if c.isdigit())
    if not tc_str or len(tc_str) != 7:
     self._bot.reply(cid, type, "[B][c][FF0000]❌ Teamcode phải đúng 7 chữ số!")
     return
    tc_int = int(tc_str)
    target_uids = []
    if len(parts) >= 3:
     raw_uids = " ".join(parts[2:])
     for x in raw_uids.replace(",", " ").split():
      x = x.strip()
      if x.isdigit(): target_uids.append(int(x))
    target_uids = list(dict.fromkeys(target_uids))
    if self.is_busy:
     self._bot.reply(cid, type, "[B][c][FF0000]Bot dang ban, vui long cho!"); return
    _join_voice_owner = VOICE_ENABLED and _voice_claim_tc(tc_int)
    self._bot.reply(cid, type, f"[B][c][FFFF00]Dang vao phong {tc_str}...\n[AAAAAA]Nhac: {'ON (owner)' if _join_voice_owner else 'OFF'}")
    _self_ref = self
    def join_task():
        _run_join_worker(_self_ref, tc_int, (" ".join(str(u) for u in target_uids) if target_uids else None), _join_voice_owner)
    threading.Thread(target=join_task, daemon=True, name=f"IGJoin-{tc_int}").start()

   elif message.startswith("/vip"):
    parts = message.strip().split()
    if len(parts) < 3:
     self._bot.reply(cid, type, "[B][c][FF0000]❌ Dùng: /vip [teamcode] [uid1] [uid2] ...")
     return
    tc_str = ''.join(c for c in parts[1] if c.isdigit())
    if not tc_str or len(tc_str) != 7:
     self._bot.reply(cid, type, "[B][c][FF0000]❌ Teamcode phải đúng 7 chữ số!"); return
    tc_int = int(tc_str)
    target_uids = []
    for x in parts[2:]:
     x = x.strip()
     if x.isdigit(): target_uids.append(int(x))
    target_uids = list(dict.fromkeys(target_uids))
    if not target_uids:
     self._bot.reply(cid, type, "[B][c][FF0000]❌ Không có UID hợp lệ!"); return
    if self.is_busy:
     self._bot.reply(cid, type, "[B][c][FF0000]⏳ Bot đang bận!"); return
    self._bot.reply(cid, type, f"[B][c][FFFF00]⏳ Đang vào phòng {tc_str} VIP cho {len(target_uids)} người...")
    _self_ref2 = self
    def vip_task():
        bot = _self_ref2
        bot.is_busy = True
        try:
            bot.rstatus = (4, "")
            bot.sock39699.send(bot._bot.join_squad(tc_int))
            time.sleep(2.5)
            botid_v = getattr(bot, "botid", None)
            all_uids = list(target_uids)
            if botid_v and str(botid_v).isdigit() and int(botid_v) not in all_uids:
                all_uids.append(int(botid_v))
            emote_lists = []
            base_emotes = list(bot.Emotes)
            for _ in all_uids:
                e = base_emotes[:]
                random.shuffle(e)
                emote_lists.append(e)
            total_rounds = len(base_emotes)
            bot.sock39699.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            for round_i in range(total_rounds):
                for j, u in enumerate(all_uids):
                    emote = emote_lists[j][round_i]
                    try:
                        bot.sock39699.sendall(bot._bot.play_emote(emote, [u]))
                    except (socket.error, ConnectionResetError): break
                    except: continue
                time.sleep(random.uniform(6.8, 9.5))  # ★ anti-ban: random delay emote
            bot.rstatus = (10, '')
            bot._bot.reply(cid, type, "[B][c][00FF00]✅ VIP đã múa xong!")
        finally:
            bot.is_busy = False
    threading.Thread(target=vip_task, daemon=True).start()

   else: return False
  except Exception as e: self.rstatus, self.ids = (0, 0), []

 def leave(self, uid, delay):
  try:
   time.sleep(int(delay))
   self.rstatus = (0, 0)
   self.ids = []
   self.sock39801.send(self._bot.leave_channel(uid, None))
   self.sock39699.send(self._bot.leave_squad(uid))
  except: self.rstatus, self.ids = (0, 0), []

 def gringay(self, data):
  if data.hex()[:4] == "0500" and len(data) >= 80:
   data = json.loads(protobuf_dec(data.hex()[10:]))
   if not isinstance(data.get("4"), (str, int)): return
   ptype = int(data["4"])
   rs0 = self.rstatus[0] if isinstance(self.rstatus, tuple) else self.rstatus

   def _capture_room(_d5, src="?"):
    if not isinstance(_d5, dict):
     return
    for _fk in ("17", 17, "8", 8, "15", 15, "16", 16, "9", 9):
     v = _d5.get(_fk)
     if v is None:
      continue
     s = str(v).strip()
     if not s:
      continue
     if s.isdigit() or s.startswith("VN_") or len(s) >= 6:
      if getattr(self, "last_room_id", None) != s:
       self.last_room_id = s
       try: self.room_id_event.set()
       except Exception: pass
       logger.info(f"[gringay] AUTO-CAPTURE room_id={s} (ptype={src})")
      return

   if ptype in (6, 3, 8):
    try: _capture_room(data.get("5") or {}, src=str(ptype))
    except Exception as e: logger.debug(f"[gringay] room_id capture err: {e}")

   if ptype in [3, 6, 8, 44, 56] and (rs0 == 10 or getattr(self, "is_trolling", False)):
    try:
     extracted = list(extract_uid_fields(data) or [])
     cleaned = [int(x) for x in extracted if isinstance(x, (int, str)) and str(x).isdigit() and 10**8 <= int(x) <= 10**12]
     if cleaned:
      self.ids = list(set((self.ids or []) + cleaned))
    except Exception:
     pass

   if ptype == 3:
    uid = data.get("5").get("1")
    rc = data.get("5").get("8")
    self.sock39801.send(self._bot.join_channel(uid, rc, None))
    g01 = "[B][c]\n[%s]Dịch vụ: [U]LIKE - BOT - API.[/U][%s]\n\nTelegram: [00FFFF]@cdanb\n[000000]"%(grcolor(), grcolor())
    g02 = "\n".join([f"[{grcolor()}]Cdanhday  " * 8 for _ in range(55)])
    self.sock39699.send(self._bot.reject_invite(random.choice([g01, g02]), uid, uid))

   if int(data["4"]) == 6:
    if isinstance(self.rstatus, tuple) and self.rstatus[0] == 1:
     try:
      uid = data.get("5", {}).get("1")
      recruit_code = data.get("5", {}).get("17")
      self.sock39801.send(self._bot.join_channel(uid, recruit_code, None))
      self.ids = list(set(extract_uid_fields(data)))
      time.sleep(0.5)
      for _ in range(10):
       self._bot.reply(uid, None, self.rstatus[1])
       time.sleep(1)
      self.rstatus = (0, 0)
      self.sock39699.send(self._bot.leave_squad(000))
     except: self.rstatus, self.ids = (0, 0), []

    if isinstance(self.rstatus, tuple) and self.rstatus[0] == 6:
     try:
      uid = data.get("5", {}).get("1")
      recruit_code = data.get("5", {}).get("17")
      self.sock39801.send(self._bot.join_channel(uid, recruit_code, None))
      self.ids = list(set(extract_uid_fields(data)))
      time.sleep(0.5)
      for _ in range(10):
       self._bot.reply(uid, None, self.rstatus[1])
       time.sleep(1)
      self.rstatus = (0, 0)
     except: self.rstatus, self.ids = (0, 0), []

    if isinstance(self.rstatus, tuple) and self.rstatus[0] == 7:
     try:
      uid = data.get("5", {}).get("1")
      recruit_code = data.get("5", {}).get("17")
      self.sock39801.send(self._bot.join_channel(uid, recruit_code, None))
      self.ids = list(set(extract_uid_fields(data)))
      time.sleep(0.5)
      self._bot.reply(uid, None, "[B][c][00FF00]👋 Bot đã vào squad! Xin chào mọi người~")
     except: self.rstatus, self.ids = (0, 0), []

    if isinstance(self.rstatus, tuple) and self.rstatus[0] == 8:
     try:
      uid = data.get("5", {}).get("1")
      recruit_code = data.get("5", {}).get("17")
      self.sock39801.send(self._bot.join_channel(uid, recruit_code, None))
      new_ids = list(set(extract_uid_fields(data)))
      self.ids = list(set((self.ids or []) + new_ids))
      if uid:
       if self.squad_chat_uid != uid:
        self.squad_chat_uid = uid
        logger.info(f"[AntiBot] captured squad_chat_uid={uid}")
       time.sleep(1.0)
       try:
        self._bot.reply(uid, None, PROMO_SQUAD_MSG)
        logger.info(f"[AntiBot] ✅ promo sent → squad uid={uid}")
       except Exception as pe:
        logger.warning(f"[AntiBot] promo send fail: {pe}")
       for _mid in new_ids:
        try:
         _mid_i = int(_mid)
         if _mid_i in (int(self.botid) if self.botid else -1, int(uid)):
          continue
         self._bot.reply(_mid_i, None, PROMO_TEXT)
        except Exception:
         continue
     except Exception as _e:
      logger.warning(f"[AntiBot] channel join err: {_e}")

    if isinstance(self.rstatus, tuple) and self.rstatus[0] == 2:
     try:
      uid = data.get("5", {}).get("1")
      secret_code = data.get("5", {}).get("31")
      self.rstatus = (0, 0)
      if not uid or not secret_code: return False
      current_code = self.rstatus[1]
      self.sock39699.send(self._bot.leave_squad(00000))
      packetjs = self._bot.join_squad(current_code)
      bots = []
      for bot in self.manager.bots.values():
       if bot is not self and bot.sock39699 and bot._bot: bots.append(bot)
       if len(bots) == 3: break
      for bot in bots: bot.sock39699.send(bot._bot.ghost(uid, secret_code))
      for _ in range(555):
       self.sock39699.sendall(packetjs)
       self.sock39699.sendall(self._bot.leave_squad(0x00))
       time.sleep(0.005)
       self.sock39699.sendall(self._bot.ghost(uid, secret_code))
      time.sleep(1)
      self.sock39699.sendall(self._bot.leave_squad(0x00))
      self.sock39699.sendall(self._bot.ghost(uid, secret_code))
      return True
     except: self.rstatus, self.ids = (0, 0), []

    if isinstance(self.rstatus, tuple) and self.rstatus[0] == 3:
     try:
      uid = data.get("5", {}).get("1")
      secret_code = data.get("5", {}).get("31")
      self.sock39699.send(self._bot.leave_squad(1))
      if not uid or not secret_code: return False
      current_code = self.rstatus[1]
      self.rstatus = (0, 0)
      self.send_ghost(uid, secret_code)
     except: self.rstatus, self.ids = (0, 0), []

    if isinstance(self.rstatus, tuple) and self.rstatus[0] == 4:
     try:
      uid = data.get("5", {}).get("1")
      recruit_code = data.get("5", {}).get("17")
      self.sock39801.send(self._bot.join_channel(uid, recruit_code, None))
      time.sleep(1.2)
      self._bot.reply(uid, None, PROMO_SQUAD_MSG)
      self.rstatus = (10, '')
      self.ids.extend(extract_uid_fields(data))
     except: self.rstatus, self.ids = (0, 0), []

 def playcd(self):
     self.sock39699.send(self._bot.play_animation(914050001))
     time.sleep(3)
     self.sock39699.send(self._bot.play_animation(914051001))
     time.sleep(3.5)
     self.sock39699.send(self._bot.play_animation(914039001))
     time.sleep(3.5)
     self.sock39699.send(self._bot.play_animation(914044001))
     time.sleep(3.5)
     self.sock39699.send(self._bot.play_animation(914048001))
     time.sleep(3.5)
     self.sock39699.send(self._bot.play_animation(914042001))
     time.sleep(3.5)
     self.sock39699.send(self._bot.play_animation(914000002))

 def send_ghost(self, uid, secret):
  bots = []
  for i in self.manager.bots.values():
   if i is not self and i.running_event.is_set() and i.sock39699 and i._bot: bots.append(i)
   if len(bots) == 3: break
  for bot in bots: bot.sock39699.send(bot._bot.ghost(uid, secret))

 def GenSpamRoom(self, cid):
  self.sock39699.send(self._bot.get_history(cid))
  time.sleep(1.5)
  rid = self.roomid
  if rid:
   packetjr = self._bot.request_join_room(rid, cid)
   for i in range(123):
    if not self.sock39699: return
    self.sock39699.send(packetjr)
    time.sleep(0.35)

 def GenSquads(self, team, cid, uid, Type, name="User"):
        if not self.sock39699:
            self._bot.reply(cid, Type, "Thử lại!")
            return
        self.status = False
        self.sock39699.sendall(self._bot.open_squad(team))
        time.sleep(0.5)
        self.sock39699.send(self._bot.invite_squad(uid, 1))
        self.sock39699.send(self._bot.invite_squad(uid, 2))
        self._bot.reply(cid, Type, f"""[B][C][FFFFFF]Xin Chào! {name}\n[FFFFFF]Đã tạo team {team} thành công!\n[C0C0C0]Vui lòng chấp nhận lời mời từ bot!""")
        threading.Thread(target=self.playcd).start()
        threading.Thread(target=self.closesquads).start()

 def _get_player_level(self, target_uid):
  try:
   raw = GetPlayerPersonalShow(int(target_uid), self.token, self.base_url)
   if not raw or len(raw) < 4: return None
   data = None
   for off in (0, 5, 10, 16, 32):
    try:
     hx = raw.hex() if isinstance(raw, bytes) else str(raw)
     chunk = hx[off * 2:] if off else hx
     parsed = json.loads(protobuf_dec(chunk))
     if isinstance(parsed, dict) and parsed: data = parsed; break
    except Exception: continue
   if not isinstance(data, dict): return None
   basic = data.get("1") or data.get(1) or {}
   if not isinstance(basic, dict): basic = {}
   for k in ("6", 6, "5", 5, "7", 7):
    v = basic.get(k)
    if isinstance(v, int) and 1 <= v <= 100: return v
   def walk(obj, depth=0):
    if depth > 5 or not isinstance(obj, dict): return None
    for kk, vv in obj.items():
     if isinstance(vv, int) and 1 <= vv <= 80: return vv
     if isinstance(vv, dict):
      r = walk(vv, depth + 1)
      if r is not None: return r
    return None
   return walk(data)
  except Exception as e:
   logger.debug(f"[AntiBot] level err uid={target_uid}: {e}")
   return None

 def _antibot_promo_loop(self, target_uid, interval=45):
  logger.info(f"[AntiBot-Promo] started target={target_uid} interval={interval}s")
  first_round = True
  while self.antibot_active:
   try:
    time.sleep(8 if first_round else interval)
    first_round = False
    if not self.antibot_active: break
    suid = getattr(self, "squad_chat_uid", None) or target_uid
    if not suid or not getattr(self, "sock39801", None): continue
    try:
     self._bot.reply(int(suid), None, PROMO_SQUAD_MSG)
     logger.info(f"[AntiBot-Promo] ✅ sent → squad uid={suid}")
    except Exception as pe:
     logger.warning(f"[AntiBot-Promo] send fail: {pe}")
   except Exception as e:
    logger.debug(f"[AntiBot-Promo] loop err: {e}")
  logger.info("[AntiBot-Promo] stopped")

 def _antibot_stop(self, leave=True):
  self.antibot_active = False
  t = getattr(self, "antibot_thread", None)
  if t and t.is_alive():
   try: t.join(timeout=2.0)
   except Exception: pass
  self.antibot_thread = None
  pt = getattr(self, "antibot_promo_thread", None)
  if pt and pt.is_alive():
   try: pt.join(timeout=2.0)
   except Exception: pass
  self.antibot_promo_thread = None
  if leave:
   try:
    sock39699 = getattr(self, "sock39699", None)
    sock39801 = getattr(self, "sock39801", None)
    my_botid = None
    try: my_botid = int(self.botid) if self.botid and str(self.botid).isdigit() else None
    except Exception: my_botid = None
    if sock39699:
     try:
      pkt = self._bot.leave_squad(my_botid if my_botid else 0)
      try: sock39699.sendall(pkt)
      except Exception: sock39699.send(pkt)
     except Exception as le:
      logger.warning(f"[AntiBot] leave_squad fail: {le}")
    if sock39801:
     try:
      suid = getattr(self, "squad_chat_uid", None)
      if suid:
       try: sock39801.send(self._bot.leave_channel(int(suid), None))
       except Exception: pass
     except Exception: pass
    logger.info(f"[AntiBot] ✅ bot left squad (botid={my_botid}, squad_uid={getattr(self, 'squad_chat_uid', None)})")
   except Exception as e:
    logger.warning(f"[AntiBot] leave squad EXC: {e}")
   try:
    self.ids = []
    self.rstatus = (0, 0)
    self.squad_chat_uid = None
    self.antibot_kicked = set()
    self.antibot_scanned = {}
   except Exception: pass
  try:
   self.is_trolling = False
   self.is_busy = False
  except Exception: pass
  try:
   bot_id = self.bot_config.get("bot_id")
   if bot_id: BOT_POOL.set_status(bot_id, BotStatus.IDLE)
  except Exception: pass

 def _antibot_watcher_loop(self, notify_fn, target_uid, bot_uid):
  fail_count = {}
  idle_rounds = 0
  MAX_RUNTIME = 3600
  start_t     = time.time()
  logger.info("[AntiBot-Watch] started — quét liên tục, kick acc < level 10")
  try:
   while self.antibot_active and (time.time() - start_t) < MAX_RUNTIME:
    if not getattr(self, "sock39699", None):
     logger.info("[AntiBot-Watch] dừng: mất socket"); break
    try: members = list(set(self.ids or []))
    except Exception: members = []
    if not members:
     idle_rounds += 1
     if idle_rounds >= 30:
      logger.info("[AntiBot-Watch] dừng: squad trống 60s"); break
    else: idle_rounds = 0
    for mid in members:
     try: mid_i = int(mid)
     except Exception: continue
     if mid_i in self.antibot_kicked: continue
     if bot_uid and mid_i == bot_uid:
      self.antibot_kicked.add(mid_i); continue
     if mid_i == target_uid:
      self.antibot_kicked.add(mid_i); continue
     if mid_i in self.antibot_scanned: continue
     lv = self._get_player_level(mid_i)
     if lv is None:
      cnt = fail_count.get(mid_i, 0) + 1
      fail_count[mid_i] = cnt
      if cnt >= 3:
       logger.info(f"[AntiBot-Watch] uid={mid_i} API fail 3 lần → bỏ qua")
       self.antibot_scanned[mid_i] = -1
      continue
     self.antibot_scanned[mid_i] = lv
     logger.info(f"[AntiBot-Watch] uid={mid_i} level={lv}")
     if lv < 10:
      try:
       pkt = self._bot.kick_member(mid_i)
       if pkt:
        try: self.sock39699.sendall(pkt)
        except Exception: self.sock39699.send(pkt)
        time.sleep(0.15)
        try: self.sock39699.sendall(pkt)
        except Exception: pass
       self.antibot_kicked.add(mid_i)
       logger.info(f"[AntiBot-Watch] KICK uid={mid_i} lv={lv}")
       try:
        notify_fn(f"[B][C][FF0000]AUTO KICK\n[FFFFFF]uid: [FFFF00]{mid_i}\n[FFFFFF]level: [FF69B4]{lv} [AAAAAA](<10)")
       except Exception: pass
       try:
        suid = getattr(self, "squad_chat_uid", None)
        if suid: self._bot.reply(suid, None, PROMO_SQUAD_MSG)
       except Exception: pass
      except Exception as ke:
       logger.warning(f"[AntiBot-Watch] kick fail {mid_i}: {ke}")
     else:
      self.antibot_scanned[mid_i] = lv
      try:
       suid = getattr(self, "squad_chat_uid", None)
       if suid: self._bot.reply(suid, None, PROMO_SQUAD_MSG)
      except Exception: pass
    time.sleep(2)
  finally:
   try:
    self.is_trolling = False
    self.is_busy = False
   except Exception: pass
   try:
    bot_id = self.bot_config.get("bot_id")
    if bot_id: BOT_POOL.set_status(bot_id, BotStatus.IDLE)
   except Exception: pass
  try:
   total = len(self.antibot_kicked)
   if bot_uid and bot_uid in self.antibot_kicked: total -= 1
   if target_uid in self.antibot_kicked: total -= 1
   total = max(0, total)
   if total > 0:
    notify_fn(f"[B][C][FF0000]ANTI-BOT TỔNG KẾT\n[FFFFFF]Tổng đã kick: [FFFF00]{total} acc\n[AAAAAA]Watcher đã dừng.")
  except Exception: pass
  logger.info(f"[AntiBot-Watch] stopped. kicked={len(self.antibot_kicked)}")

 def GenAntiBot(self, cid, target_uid, Type, name="User"):
  if not self.sock39699:
   self._bot.reply(cid, Type, "[B][c][FF0000]Bot mat socket!"); return
  if self.antibot_active:
   logger.info("[AntiBot] stop watcher cũ trước khi start watcher mới")
   self._antibot_stop(leave=False)
   time.sleep(0.5)
  self_ref = self
  def _run():
   bot = self_ref
   bot.is_busy = True
   bot.is_trolling = True
   bot.status = True
   bot.ids = []
   bot.squad_chat_uid = None
   bot.rstatus = (8, "")
   bot.antibot_active = True
   bot.antibot_kicked = set()
   bot.antibot_scanned = {}
   bot_uid = None
   try: bot_uid = int(bot.botid) if bot.botid and str(bot.botid).isdigit() else None
   except Exception: bot_uid = None
   if bot_uid: bot.antibot_kicked.add(bot_uid)
   try: bot.antibot_kicked.add(int(target_uid))
   except Exception: pass
   try:
    bot.sock39699.sendall(bot._bot.open_squad(5))
   except Exception:
    try: bot.sock39699.send(bot._bot.open_squad(5))
    except Exception as e:
     bot._bot.reply(cid, Type, f"[B][c][FF0000]Loi tao team: {e}")
     bot.is_busy = False; bot.is_trolling = False; bot.antibot_active = False
     return
   time.sleep(0.5)
   try:
    bot.sock39699.send(bot._bot.invite_squad(target_uid, 1))
    bot.sock39699.send(bot._bot.invite_squad(target_uid, 2))
   except Exception: pass
   for _ in range(40):
    if getattr(bot, "squad_chat_uid", None): break
    time.sleep(0.3)
   squad_uid_default = getattr(bot, "squad_chat_uid", None) or int(target_uid)
   logger.info(f"[AntiBot] squad_uid={squad_uid_default}")
   def _notify(msg):
    suid = getattr(bot, "squad_chat_uid", None) or squad_uid_default
    try: bot._bot.reply(suid, None, msg)
    except Exception:
     try: bot._bot.reply(cid, Type, msg)
     except Exception: pass
   _notify(f"[B][C][00FF00]ANTI-BOT ON\n[FFFFFF]Team 5 da tao — moi UID [FFFF00]{target_uid}\n[AAAAAA]Bot O LAI squad VĨNH VIỄN\n[FF69B4]Auto kick MỌI acc < Level 10 khi vào phòng\n[C0C0C0]Chap nhan loi moi tu bot!")
   bot.antibot_thread = threading.Thread(target=bot._antibot_watcher_loop, args=(_notify, int(target_uid), bot_uid), daemon=True, name=f"AntiBotWatch-{target_uid}")
   bot.antibot_thread.start()
   logger.info(f"[AntiBot] watcher spawned target={target_uid} bot={bot_uid}")
   bot.is_busy = False
   bot.antibot_promo_thread = threading.Thread(target=bot._antibot_promo_loop, args=(int(target_uid),), daemon=True, name=f"AntiBotPromo-{target_uid}")
   bot.antibot_promo_thread.start()
   logger.info(f"[AntiBot] promo loop spawned target={target_uid}")
  threading.Thread(target=_run, daemon=True, name=f"AntiBotInit-{target_uid}").start()

 def _get_vip_level(self, uid):
  try:
   uid_int = int(str(uid).strip())
   for entry in self.bot_config.get("access_bot", []):
    if int(str(entry.get("uid", "")).strip()) == uid_int:
     return int(entry.get("vip", 0))
  except: pass
  return 0

 def closesquads(self):
  time.sleep(25.5)
  self.rstatus, self.ids = (0, 0), []
  try: self.sock39699.send(self._bot.leave_squad(0x000000))
  except: pass
  self.status = True

 def get_user_status(self, type, uid=None):
  if type == 1:
   access_uids = []
   for u in self.bot_config.get("access_bot", []):
    try: access_uids.append(int(str(u["uid"]).strip()))
    except: pass
   if self.botid:
    try: access_uids.append(int(self.botid))
    except: pass
   if self.GuildIds:
    try: access_uids.append(int(self.GuildIds))
    except: pass
   return access_uids
  if type in [2, 3] and uid is not None:
   try: uid_int = int(str(uid).strip())
   except: return False if type == 2 else "null"
   now = datetime.datetime.now()
   for u in self.bot_config.get("access_bot", []):
    try:
     if int(str(u["uid"]).strip()) == uid_int:
      exp = str(u["expire"]).strip()
      exp_time = datetime.datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
      if exp_time < now:
       self.manager.deleteId(self.bot_config["bot_id"], uid_int)
       return False if type == 2 else "Hết hạn"
      if type == 2: return True, False
      if type == 3:
       delta = exp_time - now
       days = delta.days
       hours, remainder = divmod(delta.seconds, 3600)
       minutes, seconds = divmod(remainder, 60)
       parts = []
       if days: parts.append(f"{days} ngày")
       if hours: parts.append(f"{hours} giờ")
       if minutes: parts.append(f"{minutes} phút")
       return ", ".join(parts) if parts else "< 1 phút"
    except: continue
   return "∞"
  return "∞"

 def format_status_message(self, info, uid):
  status = info.get("status", "null")
  uid_val = info.get("uid", uid) or uid
  group = info.get("group")
  roomid = info.get("roomid")
  lines = [
   "[B][C]Player Status Info:",
   f"[FFFFFF]status: [00FF00]{status}",
   f"[FFFFFF]uid: [FFFF00]{uid_val}",
  ]
  if group and "Squads" in str(status):
   lines.append(f"[FFFFFF]group: [00BFFF]{group}")
  if roomid and "Rooms" in str(status):
   lines.append(f"[FFFFFF]room: [00BFFF]{roomid}")
  return "\n".join(lines)

 class bot_session:
  def __init__(self, parent): self.par = parent
  def __getattr__(self, name): return getattr(self.par._gen, name)
  def reply(self, Id, Tp, Ms):
   try:
    if not self.par.running_event.is_set():
     logger.warning(f"[reply] Bo qua: bot khong chay Id={Id} Tp={Tp}")
     return
    if not self.par.sock39801:
     logger.warning(f"[reply] Bo qua: chua ket noi chat socket Id={Id} Tp={Tp}")
     return
    self.par.sock39801.sendall(self.par._gen.send_message(Ms, Tp, Id))
   except Exception as e:
    logger.error(f"[reply] Gui that bai Id={Id} Tp={Tp}: {e}")

 def rstart(self):
    access_token = self.bot_config['auth_bot_login']['access_token']
    while self.running_event.is_set():
        try:
            data = FreeFireAPI().get(access_token, is_emulator=False)
            if "account not found" in data:
                self.running_event.clear()
                break
            if data.get("GuildData"):
                self.AuthenCode = data.get("GuildData").get("secret_code")
                self.GuildIds = data.get("GuildData").get("id")
            self.packetAuth = bytes(data["UserAuthPacket"])
            lobby = data.get("UserAuthPacketLobby")
            self.packetAuthLobby = bytes(lobby) if lobby else self.packetAuth
            self.botid = int(data["UserAccountUID"])
            try:
                self.nickname = data.get("logindata", {}).get("4")
                if not self.nickname: raise Exception("Empty nickname")
            except:
                import base64
                try:
                    raw = data.get("UserNickName", "")
                    self.nickname = base64.b64decode(raw).decode("utf-8", errors="ignore")
                except: self.nickname = "Unknown"
            self.manager.save_config()
            self.region = str(data["LockRegion"])
            self.token = data["UserAuthToken"]
            self.ChatIP = data["GameServerAddress"]["chatip"]
            self.OnlineIP = data["GameServerAddress"]["onlineip"]
            self.OnlinePort = data["GameServerAddress"]["onlineport"]
            self.ChatPort = data["GameServerAddress"]["chatport"]
            self.key, self.iv = bytes(data["key"]), bytes(data["iv"])
            self.base_url = data["BaseUrl"]
            bot_label = self.bot_config.get("bot_id", "?")
            logger.info(f"[Bot#{bot_label}] login OK nick={self.nickname} uid={self.botid} region={self.region} online={self.OnlineIP}:{self.OnlinePort}")
            ChooseEmote(self.token, self.base_url)
            self._IIl(data["logindata"], data)
            if not self.running_event.is_set(): break
            time.sleep(14555)
        except Exception as e:
            logger.warning(f"[Bot#{self.bot_config.get('bot_id', '?')}] rstart error: {e}")
            if self.running_event.is_set(): time.sleep(1111)

 def start(self):
  if self.started: return
  self.started = True
  self.running_event.set()
  bot_id = self.bot_config.get("bot_id")
  if bot_id:
      self._get_pool().mark_offline(bot_id)
  threading.Thread(target=self.rstart, daemon=True).start()


# ====================== BOTMNG ======================
class BOTMNG(BotManager):
    def add_bot(self, token):
        try:
            data = FreeFireAPI().get(token, is_emulator=False)
            if not data or "account not found" in str(data):
                return {"status": False, "message": "Token không hợp lệ hoặc tài khoản không tồn tại"}
            bot_id = int(data["UserAccountUID"])
            if bot_id in self.bots:
                return {"status": False, "message": f"Bot UID {bot_id} đã tồn tại"}
            bot_config = {
                "bot_id": bot_id,
                "botid": bot_id,
                "nickname": data.get("logindata", {}).get("4", "Unknown"),
                "auth_bot_login": {"access_token": token},
                "access_bot": [],
                "active-clan": True
            }
            bot_instance = FreeFireTCP(bot_config, self)
            bot_instance.bot_config = bot_config
            bot_instance.botid = bot_id
            with self.lock:
                self.bots[bot_id] = bot_instance
                BOT_POOL.register(bot_id, bot_instance)
                self.save_config()
            return {"status": True, "bot_id": bot_id, "message": "Thêm bot thành công"}
        except Exception as e:
            return {"status": False, "message": str(e)}

    def delete_bot(self, bot_id):
        try:
            bot_id = int(bot_id)
        except:
            return False
        with self.lock:
            if bot_id not in self.bots:
                return False
            self.bots[bot_id].cleanup()
            del self.bots[bot_id]
            BOT_POOL.unregister(bot_id)
            self.save_config()
        return True


# ====================== TELEGRAM HANDLERS ======================

@telegram_bot.message_handler(commands=["laykey"])
def cmd_laykey(message):
    if not is_allowed_group(message.chat.id):
        telegram_bot.reply_to(message, "❌ Bot chỉ hoạt động trong nhóm chính thức!", parse_mode="HTML")
        return
    user_id = message.from_user.id
    if is_admin(user_id):
        telegram_bot.reply_to(message, "🔓 <b>Admin không cần key!</b>\nDùng lệnh thoải mái mọi lúc.", parse_mode="HTML")
        return
    if not check_member_in_groups(user_id):
        telegram_bot.reply_to(message, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ⚠️ <b>CHƯA ĐỦ ĐIỀU KIỆN!</b>\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML", disable_web_page_preview=True)
        return
    link = f"{KEY_API_BASE}?user_id={user_id}"
    now_str = vn_now().strftime("%H:%M:%S %d/%m/%Y")
    telegram_bot.reply_to(
        message,
        "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  🔑 <b>NHẬN KEY MIỄN PHÍ</b>\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  ⏳ Hiệu lực: <b>10 giờ</b>\n"
        f"┃  🆔 User ID: <code>{user_id}</code>\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  🌐 <a href='{link}'>👆 Nhấn đây để lấy key</a>\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        "┃  📋 <b>Sau khi vượt link:</b>\n"
        "┃  Copy key → gửi:\n"
        "┃  <code>/key [dán_key_vào_đây]</code>\n"
        "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
        f"┃  🕐 {now_str}\n┃  👤 @anhcodeclick\n"
        "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    logger.info(f"/laykey: user {user_id}")

@telegram_bot.message_handler(commands=["key"])
def cmd_key(message):
    if not is_allowed_group(message.chat.id):
        return
    user_id = message.from_user.id
    if is_admin(user_id):
        telegram_bot.reply_to(message, "🔓 <b>Admin không cần key!</b>", parse_mode="HTML")
        return
    args = message.text.split()
    if len(args) < 2:
        telegram_bot.reply_to(message, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ⚠️ <b>THIẾU MÃ KEY!</b>\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML")
        return
    input_key = args[1].strip()
    if len(input_key) < 8:
        telegram_bot.reply_to(message, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ❌ <b>Key không hợp lệ!</b>\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML")
        return
    if check_key_validity(user_id):
        expiry = get_key(user_id)
        expiry_str = fmt_time(expiry)
        telegram_bot.reply_to(message, f"┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ℹ️ <b>KEY VẪN CÒN HIỆU LỰC!</b>\n┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n┃  🆔 ID: <code>{user_id}</code>\n┃  ⌛ Hết hạn: <code>{expiry_str}</code>\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML")
        return
    secret = get_bot_api_secret()
    if not secret:
        telegram_bot.reply_to(message, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ⚠️ <b>Không thể kết nối server key.</b>\n┃  Thử lại sau!\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML")
        return
    ts = int(time.time())
    sig = make_hmac_sig(user_id, input_key, ts)
    if not sig:
        telegram_bot.reply_to(message, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ⚠️ <b>Lỗi xác thực key.</b>\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML")
        return
    try:
        resp = requests.post(
            f"{ADMIN_PANEL_URL}?act=verify",
            data={"key": input_key, "user_id": str(user_id), "ts": str(ts), "sig": sig, "bot_ip": "0.0.0.0"},
            headers={"User-Agent": "TelegramBot/3.0-BotAPI", "Accept": "application/json"},
            timeout=15, verify=False)
        data = resp.json()
        logger.info(f"/key user={user_id} key={input_key[:12]}... → {data}")
        if data.get("ok") and data.get("valid"):
            expire_at = float(data.get("expire_at") or (time.time() + KEY_VALIDITY))
            set_key(user_id, expire_at, key_str=input_key)
            expiry_str = fmt_time(expire_at)
            ttl_left = int(data.get("ttl_left") or max(0, expire_at - time.time()))
            ttl_hours = max(1, round(ttl_left / 3600))
            telegram_bot.reply_to(
                message,
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ✅ <b>Key kích hoạt thành công!</b>\n"
                "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  🆔 ID: <code>{user_id}</code>\n"
                f"┃  ⏳ Còn lại: <b>{ttl_hours} giờ</b>\n"
                f"┃  ⌛ Hết hạn: <code>{expiry_str}</code>\n"
                "┃  🎮 Dùng /join [TC] múa + nhạc ngay!\n"
                "┃  👥 Dùng /2 /3 /4 /5 [UID] vào squad\n"
                "┃  /lagff \n┃  /spam_inv\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
                parse_mode="HTML")
            logger.info(f"/key activated: user={user_id} expires={expiry_str}")
        else:
            reason = data.get("reason", "")
            reason_text = {
                "key_not_found": "Key không tồn tại trong hệ thống!",
                "key_revoked": "Key đã bị thu hồi bởi admin!",
                "key_expired": "Key đã hết hạn!",
                "user_mismatch": "Key này không thuộc về tài khoản của bạn!",
                "ip_mismatch": "Key gắn với IP khác. Lấy key mới!",
                "ip_abuse_auto_revoked": "Key bị thu hồi do lạm dụng!",
                "invalid_signature": "Lỗi xác thực. Thử lại!",
                "rate_limited": "Quá nhiều yêu cầu. Đợi vài giây!",
            }.get(reason, f"Key không hợp lệ! ({reason})" if reason else "Key không hợp lệ!")
            telegram_bot.reply_to(
                message,
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  ❌ <b>KEY KHÔNG HỢP LỆ!</b>\n"
                "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                f"┃  {reason_text}\n"
                "┃  Dùng /laykey để lấy key mới.\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
                parse_mode="HTML")
    except requests.exceptions.Timeout:
        telegram_bot.reply_to(message, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ⏱️ <b>Server key phản hồi chậm.</b>\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML")
        logger.error(f"/key timeout: user={user_id}")
    except Exception as e:
        logger.error(f"/key error: {e}")
        telegram_bot.reply_to(message, "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n┃  ⚠️ <b>Lỗi kết nối server key.</b>\n┃  Thử lại sau!\n┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛", parse_mode="HTML")


def require_key(handler):
    def wrapper(message):
        user_id = message.from_user.id
        if is_admin(user_id):
            return handler(message)
        if not check_key_validity(user_id):
            telegram_bot.reply_to(
                message,
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
                "┃  🔐 <b>CẦN KEY ĐỂ DÙNG LỆNH!</b>\n"
                "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
                "┃  Bước 1: <code>/laykey</code> → lấy link\n"
                "┃  Bước 2: Vượt link → copy key\n"
                "┃  Bước 3: <code>/key [mã_key]</code>\n"
                "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛",
                parse_mode="HTML")
            logger.warning(f"User {user_id} tried to use command without key")
            return
        return handler(message)
    return wrapper


@telegram_bot.message_handler(commands=['start', 'help'])
@group_only
def telegram_help(message):
    menu_text = (
        "╔══════════════════════════════╗\n"
        "║   🔥  FREE FIRE BOT  🔥      ║\n"
        "║   Multi-bot · Scheduler Pool  ║\n"
        "╚══════════════════════════════╝\n"
        "\n"
        "🔐 <b>KEY SYSTEM</b>\n"
        "┌─────────────────────────────\n"
        "│ /laykey      —  Lấy key miễn phí\n"
        "│ /key [code]  —  Kích hoạt key\n"
        "└─────────────────────────────\n"
        "\n"
        "👥 <b>BASIC TEAM COMMANDS</b>\n"
        "┌─────────────────────────────\n"
        "│ /2 /3 /4 /5 /6 [UID]  —  Create team\n"
        "└─────────────────────────────\n"
        "\n"
        "🎮 <b>SQUAD FUNCTIONS</b>\n"
        "┌─────────────────────────────\n"
        "│ /spam_inv [UID]      —  Send squad invites\n"
        "│ /join [TEAMCODE]     —  Múa emote + voice s1.mp3\n"
        "│ /lagff [TEAMCODE]    —  Lag squad (3 bot)\n"
        "└─────────────────────────────\n"
        "\n"
        "👑 <b>ADMIN COMMANDS</b>\n"
        "┌─────────────────────────────\n"
        "│ /addgroup /delgroup /listgroups\n"
        "│ /check /pool /queuesize\n"
        "│ /refresh_secret  —  Force refresh HMAC secret\n"
        "└─────────────────────────────\n"
    )
    telegram_bot.reply_to(message, menu_text, parse_mode='HTML')


@telegram_bot.message_handler(commands=['addgroup'])
def handle_addgroup(message):
    if message.from_user.id not in TELEGRAM_ADMINS:
        telegram_bot.reply_to(message, "❌ Chỉ admin mới dùng được lệnh này.")
        return
    parts = message.text.strip().split()
    if len(parts) > 1:
        try: group_id = int(parts[1])
        except:
            telegram_bot.reply_to(message, "❌ Group ID không hợp lệ.")
            return
    else: group_id = message.chat.id
    if group_id in ALLOWED_GROUPS:
        telegram_bot.reply_to(message, f"✅ Nhóm <code>{group_id}</code> đã có trong whitelist.", parse_mode='HTML')
        return
    ALLOWED_GROUPS.add(group_id)
    save_allowed_groups()
    telegram_bot.reply_to(message, f"✅ Đã thêm nhóm <code>{group_id}</code> vào whitelist.", parse_mode='HTML')


@telegram_bot.message_handler(commands=['delgroup'])
def handle_delgroup(message):
    if message.from_user.id not in TELEGRAM_ADMINS:
        telegram_bot.reply_to(message, "❌ Chỉ admin mới dùng được lệnh này.")
        return
    parts = message.text.strip().split()
    if len(parts) > 1:
        try: group_id = int(parts[1])
        except:
            telegram_bot.reply_to(message, "❌ Group ID không hợp lệ.")
            return
    else: group_id = message.chat.id
    if group_id not in ALLOWED_GROUPS:
        telegram_bot.reply_to(message, f"❌ Nhóm <code>{group_id}</code> chưa có trong whitelist.", parse_mode='HTML')
        return
    ALLOWED_GROUPS.remove(group_id)
    save_allowed_groups()
    telegram_bot.reply_to(message, f"✅ Đã xóa nhóm <code>{group_id}</code> khỏi whitelist.", parse_mode='HTML')


@telegram_bot.message_handler(commands=['listgroups'])
def handle_listgroups(message):
    if message.from_user.id not in TELEGRAM_ADMINS:
        telegram_bot.reply_to(message, "❌ Chỉ admin mới dùng được lệnh này.")
        return
    if not ALLOWED_GROUPS:
        telegram_bot.reply_to(message, "📋 Chưa có nhóm nào trong whitelist.")
        return
    text = "<b>📋 DANH SÁCH NHÓM ĐƯỢC PHÉP:</b>\n\n"
    for gid in sorted(ALLOWED_GROUPS):
        text += f"• <code>{gid}</code>\n"
    telegram_bot.reply_to(message, text, parse_mode='HTML')


@telegram_bot.message_handler(commands=['refresh_secret'])
def handle_refresh_secret(message):
    if message.from_user.id not in TELEGRAM_ADMINS:
        telegram_bot.reply_to(message, "❌ Chỉ admin mới dùng được lệnh này.")
        return
    BOT_API_SECRET_CACHE["secret"] = None
    BOT_API_SECRET_CACHE["updated"] = 0
    s = get_bot_api_secret(force_refresh=True)
    if s:
        telegram_bot.reply_to(
            message,
            f"✅ <b>Secret refreshed!</b>\n"
            f"<code>{s[:16]}...{s[-8:]}</code>\n"
            f"Độ dài: {len(s)} ký tự",
            parse_mode='HTML')
    else:
        telegram_bot.reply_to(
            message,
            "❌ <b>Không lấy được secret từ panel!</b>\n"
            "Kiểm tra:\n"
            "• URL: <code>https://lagv7.freepage.cc/server-key/api.php</code>\n"
            "• <code>config.php</code>: <code>ADMIN_PASS = 'anhcodeclick'</code>\n"
            "• Bot log: tìm dòng <code>[KeySystem] get_secret</code>",
            parse_mode='HTML')


@telegram_bot.message_handler(commands=['2', '3', '4', '5', '6'])
@group_only
@require_key
def handle_team_creation(message):
    cmd = message.text.split()[0][1:]
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        telegram_bot.reply_to(message, f"<b>❌ SAI CÚ PHÁP: /{cmd} [UID_CỦA_BẠN]</b>", parse_mode='HTML')
        return
    uid = int(parts[1])
    team_size = int(cmd)
    chat_id = message.chat.id
    base_msg = telegram_bot.reply_to(message, f"<b>⏳ Đang tìm bot rảnh để tạo Team {team_size}...</b>", parse_mode='HTML')
    msg_id  = base_msg.message_id

    def task(bot):
        bot.sock39699.send(bot._bot.open_squad(team_size))
        time.sleep(0.5)
        bot.sock39699.send(bot._bot.invite_squad(uid, 1))
        bot.sock39699.send(bot._bot.invite_squad(uid, 2))
        time.sleep(4)
        botid = getattr(bot, 'botid', None)
        if botid and str(botid).isdigit():
            bot.sock39699.send(bot._bot.leave_squad(int(botid)))

    def cb(success, msg_txt):
        try:
            if success:
                text = (f"<b>✅ TẠO TEAM {team_size} THÀNH CÔNG!</b>\n"
                        f"<b>──────────────────────</b>\n"
                        f"👤 <b>UID được mời:</b> <code>{uid}</code>\n"
                        f"👥 <b>Kích thước đội:</b> {team_size} người\n"
                        f"📨 <b>Lời mời đã gửi!</b>")
            else: text = f"<b>❌ THẤT BẠI:</b> {msg_txt}"
            telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML')
        except: pass

    SCHEDULER.submit(f"/team{team_size} uid={uid}", task, callback=cb)


@telegram_bot.message_handler(commands=['spam_inv'])
@group_only
@require_key
def handle_telegram_spam_inv(message):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        telegram_bot.reply_to(message, "<b>❌ SAI CÚ PHÁP: /spam_inv [UID_MỤC_TIÊU]</b>", parse_mode='HTML')
        return
    uid = int(parts[1])
    chat_id = message.chat.id

    def task(bot):
        end_time = time.time() + 30
        while time.time() < end_time:
            bot.sock39699.send(bot._bot.request_join_squad(uid))
            time.sleep(0.35)

    base_msg = telegram_bot.reply_to(message, f"<b>⏳ Đang xếp hàng spam lời mời đến UID: {uid}...</b>", parse_mode='HTML')
    msg_id = base_msg.message_id

    def cb(success, msg_txt):
        try:
            if success:
                text = (f"<b>💣 SPAM LỜI MỜI HOÀN TẤT!</b>\n"
                        f"🎯 <b>UID mục tiêu:</b> <code>{uid}</code>\n"
                        f"✅ <b>Đã gửi xong toàn bộ lời mời!</b>")
            else: text = f"<b>❌ THẤT BẠI:</b> {msg_txt}"
            telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML')
        except: pass

    SCHEDULER.submit(f"/spam_inv uid={uid}", task, callback=cb)


@telegram_bot.message_handler(commands=['join'])
@group_only
@require_key
def handle_telegram_join_cmd(message):
    base_msg = telegram_bot.reply_to(message, "<b>⚙️ ĐANG XỬ LÝ...</b>", parse_mode='HTML')
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        telegram_bot.edit_message_text(chat_id=message.chat.id, message_id=base_msg.message_id, text="<b>❌ SAI CÚ PHÁP:\n/join [teamcode] [uid1] [uid2] ...</b>", parse_mode='HTML')
        return
    rest = parts[1].strip().split(maxsplit=1)
    tc = rest[0]
    uids_param = rest[1] if len(rest) > 1 else None
    try: tc_int = int(tc)
    except Exception:
        telegram_bot.edit_message_text(chat_id=message.chat.id, message_id=base_msg.message_id, text="<b>❌ Teamcode phải là số!</b>", parse_mode='HTML')
        return
    chat_id = message.chat.id
    msg_id = base_msg.message_id
    _join_voice_owner = VOICE_ENABLED and _voice_claim_tc(tc_int)
    telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"<b>⏳ XẾP HÀNG JOIN phòng {tc}... (1 bot · múa · promo · nhạc s1.mp3)</b>", parse_mode='HTML')

    def task(bot):
        _run_join_worker(bot, tc_int, uids_param, _join_voice_owner)

    def cb(success, msg_txt):
        try:
            if success:
                text = f"<b>✅ JOIN HOÀN TẤT phòng {tc}!</b>\n🎵 Voice: {'có' if _join_voice_owner else 'không (đã có bot khác phát)'}"
            else:
                if _join_voice_owner:
                    try: _voice_release_tc(tc_int)
                    except Exception: pass
                text = f"<b>❌ THẤT BẠI: {msg_txt}</b>"
            telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML')
        except Exception: pass

    online = [b for b in TCPbot.bots.values() if b.running_event.is_set() and getattr(b, "sock39699", None)]
    if not online:
        if _join_voice_owner:
            _voice_release_tc(tc_int)
        telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="<b>❌ Không có bot online</b>", parse_mode='HTML')
        return
    SCHEDULER.submit(f"/join tc={tc}", task, callback=cb)


@telegram_bot.message_handler(commands=['lagff'])
@group_only
@require_key
def handle_telegram_lag_cmd(message):
    base_msg = telegram_bot.reply_to(message, "<b>⚙️ ĐANG XẾP HÀNG LAG (3 BOT)...</b>", parse_mode='HTML')
    parts = message.text.split()
    if len(parts) < 2:
        telegram_bot.edit_message_text(chat_id=message.chat.id, message_id=base_msg.message_id, text="<b>❌ SAI CÚ PHÁP: /lagff [teamcode]</b>", parse_mode='HTML')
        return
    tc = parts[1]
    if not tc.isdigit() or len(tc) != 7:
        telegram_bot.edit_message_text(chat_id=message.chat.id, message_id=base_msg.message_id, text="<b>❌ Teamcode phải là 7 chữ số!</b>", parse_mode='HTML')
        return
    tc_int = int(tc)
    chat_id = message.chat.id
    msg_id = base_msg.message_id
    duration = 60
    done_lock = threading.Lock()
    done_state = {"ok": 0, "fail": 0, "total": 3}

    def _on_done(success, err):
        with done_lock:
            if success: done_state["ok"] += 1
            else: done_state["fail"] += 1
            finished = done_state["ok"] + done_state["fail"]
            if finished < done_state["total"]: return
            try:
                if done_state["ok"] > 0:
                    text = (f"<b>✅ LAG HOÀN TẤT</b>\n"
                            f"🏠 <b>Teamcode:</b> <code>{tc}</code>\n"
                            f"🤖 <b>Bot đã dùng:</b> {done_state['ok']}/3 bot\n"
                            f"⚡ <b>Thời gian:</b> {duration}s")
                else: text = f"<b>❌ LAG THẤT BẠI</b>\n🏠 <code>{tc}</code>"
                telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text, parse_mode='HTML')
            except Exception: pass

    started, _voice_owner = _run_lag_batch(tc_int, duration, need_bots=_LAG_MAX_BOTS, on_done=_on_done)
    if started <= 0:
        telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="<b>❌ Không có bot rảnh để lag!</b>", parse_mode='HTML')
        return
    done_state["total"] = started
    telegram_bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"<b>⏳ Đã xếp hàng LAG phòng {tc} — {started} bot · {duration}s</b>", parse_mode='HTML')


@telegram_bot.message_handler(commands=['check'])
@group_only
def tele_check(message):
    text = "<b>📊 BẢNG TRẠNG THÁI BOT 📊</b>\n<b>─────────────────────────────</b>\n\n"
    if not TCPbot.bots: text += "<b>❌ Không có bot nào.</b>"
    for bid, bot in TCPbot.bots.items():
        running = bot.running_event.is_set()
        has_sock = bool(getattr(bot, "sock39699", None))
        if not running: status = "🔴 OFFLINE"
        elif getattr(bot, "is_busy", False) or getattr(bot, "is_trolling", False): status = "🟡 BUSY"
        elif has_sock: status = "🟢 IDLE"
        else: status = "🟠 CONNECTING"
        nickname = getattr(bot, "nickname", None) or "Chưa đồng bộ"
        uid_bot = bot.bot_config.get("botid", getattr(bot, "botid", "Trống"))
        text += f"▪️ <b>Bot ID: {bid}</b>\n▪️ <b>Nickname: {nickname}</b>\n▪️ <b>UID: {uid_bot}</b>\n👉 <b>Trạng thái: {status}</b> {'🔌' if has_sock else '⛔'}\n<b>─────────────────────────────</b>\n\n"
    text += f"<b>📥 Queue đang chờ: {SCHEDULER.queue_size()} request</b>"
    telegram_bot.reply_to(message, text, parse_mode='HTML')


@telegram_bot.message_handler(commands=['pool'])
@group_only
def tele_pool(message):
    snap = BOT_POOL.snapshot()
    status_icon = {"IDLE": "🟢", "BUSY": "🟡", "OFFLINE": "🔴", "ERROR": "🔥", "COOLDOWN": "🔵"}
    text = "<b>🤖 BOT POOL DASHBOARD</b>\n<b>══════════════════════</b>\n\n"
    for b in snap:
        icon = status_icon.get(b["status"], "⚪")
        sock_icon = "🔌" if b.get("has_socket") else "⛔"
        run_icon = "▶️" if b.get("running") else "⏹️"
        text += (f"{icon} <b>{b['nickname']}</b> (ID: {b['bot_id']})\n"
                 f"   Status: <code>{b['status']}</code> {sock_icon} {run_icon}\n"
                 f"   Task: <code>{b['current_task'] or '-'}</code>\n"
                 f"   Total tasks: {b['task_count']}\n"
                 f"   Last active: {b['last_active'] or '-'}\n"
                 f"   Heartbeat ago: {b['heartbeat_ago']}s\n\n")
    text += f"<b>📥 Queue size: {SCHEDULER.queue_size()}</b>"
    telegram_bot.reply_to(message, text, parse_mode='HTML')


@telegram_bot.message_handler(commands=['queuesize'])
@group_only
def tele_qsize(message):
    telegram_bot.reply_to(message, f"<b>📥 Scheduler Queue: {SCHEDULER.queue_size()} request đang chờ</b>", parse_mode='HTML')


# ====================== FLASK API ======================
@app.route("/lagff", methods=["GET"])
def api_lag():
    tc = request.args.get("tc")
    if not tc or not tc.isdigit() or len(tc) != 7:
        return jsonify({"success": False, "message": "quen nhap teamcode"}), 400
    tc_int = int(tc)
    try: duration = int(request.args.get("duration", 60))
    except Exception: duration = 60
    duration = max(10, min(duration, 600))
    if SCHEDULER is None:
        return jsonify({"success": False, "message": "Scheduler chua san sang (bot.json)"}), 503
    started, _voice_owner = _run_lag_batch(tc_int, duration, need_bots=_LAG_MAX_BOTS)
    if started <= 0:
        return jsonify({"success": False, "message": "Khong co bot ranh trong bot.json"}), 503
    return jsonify({
        "success": True,
        "message": f"Da bat dau lag ({started} bot) Anh Code ",
        "bots": started, "requested": 3, "duration": f"{duration}s",
        "pattern": "3-bot parallel: lag_ver + offline/online + nonblock jitter + play_emote + voice s2.mp3 (1 bot)",
        "voice_owner": _voice_owner, "pool": "bot.json",
    })


@app.route("/check", methods=["GET"])
def ktr_bot():
    data = []
    for bid, bot in TCPbot.bots.items():
        data.append({
            "id": bid,
            "access-token": bot.bot_config['auth_bot_login']['access_token'],
            "access-user": bot.bot_config.get('access_bot', []),
            "bot-id": bot.bot_config.get("botid", getattr(bot, "botid", None)),
            "nickname": bot.bot_config.get('nickname', getattr(bot, 'nickname', None)),
            "active-guild?": bot.bot_config.get("active-clan", True),
            "status": ("busy" if getattr(bot, 'is_busy', False) else "online") if bot.running_event.is_set() else "Inactive"
        })
    return jsonify({"data": data, "total": len(data), "queue_size": SCHEDULER.queue_size()})


@app.route("/pool", methods=["GET"])
def api_pool():
    return jsonify({"pool": BOT_POOL.snapshot(), "queue_size": SCHEDULER.queue_size(), "logs": SCHED_LOGGER.get_logs(20)})


@app.route("/logs", methods=["GET"])
def api_logs():
    limit = int(request.args.get("limit", 50))
    return jsonify({"logs": SCHED_LOGGER.get_logs(limit)})


@app.route("/join", methods=["GET"])
def join_api():
    tc = request.args.get("tc")
    uids_param = request.args.get("uids")
    if not tc:
        return jsonify({"success": False, "message": "Missing tc"}), 400
    try: tc_int = int(tc)
    except: return jsonify({"success": False, "message": "Mã phòng không đúng định dạng"}), 400
    return _execute_join_task(tc_int, uids_param)


@app.route("/5/<tc>", methods=["GET"])
@app.route("/5", methods=["POST"])
def join_api_shortcut(tc=None):
    if not tc:
        tc = request.form.get("tc") or request.json.get("tc") if request.is_json else None
    if not tc or not str(tc).isdigit():
        return jsonify({"success": False, "message": "Sai định dạng mã phòng! Dùng: /5/3619364157"}), 400
    try: tc_int = int(tc)
    except: return jsonify({"success": False, "message": "Mã phòng không hợp lệ"}), 400
    uids_param = request.args.get("uids") or (request.json.get("uids") if request.is_json else None)
    return _execute_join_task(tc_int, uids_param)


def _execute_join_task(tc_int, uids_param):
    _join_voice_owner = VOICE_ENABLED and _voice_claim_tc(tc_int)
    def task(bot):
        _run_join_worker(bot, tc_int, uids_param, _join_voice_owner)
    try:
        online = [b for b in TCPbot.bots.values() if b.running_event.is_set() and getattr(b, "sock39699", None)]
        if not online:
            if _join_voice_owner: _voice_release_tc(tc_int)
            return jsonify({"success": False, "message": "Khong co bot online", "tc": tc_int}), 503
        req = SCHEDULER.submit(f"/join tc={tc_int}", task)
        if req is None:
            if _join_voice_owner: _voice_release_tc(tc_int)
            return jsonify({"success": False, "message": "Bot dang ban"}), 503
        return jsonify({"success": True, "message": "1 bot: múa đồng loạt + promo + voice s1.mp3", "tc": tc_int, "bots": 1, "voice_owner": _join_voice_owner}), 200
    except Exception as e:
        logger.error(f"[Join Error] Loi submit task: {e}")
        if _join_voice_owner: _voice_release_tc(tc_int)
        return jsonify({"success": False, "message": f"Loi: {str(e)[:120]}", "tc": tc_int}), 500


@app.route("/sinv", methods=["GET"])
def api_sinv():
    uid = request.args.get("uid")
    if not uid or not uid.isdigit():
        return jsonify({"status": False, "error": "Sai định dạng UID"}), 400
    uid_int = int(uid)
    def task(bot):
        end_time = time.time() + 30
        while time.time() < end_time:
            bot.sock39699.send(bot._bot.request_join_squad(uid_int))
            time.sleep(0.35)
    SCHEDULER.submit(f"/sinv uid={uid}", task)
    return jsonify({"status": True, "message": f"Đã xếp hàng spam lời mời đến UID {uid}"})


@app.route("/team5", methods=["GET"])
def api_team5():
    uid = request.args.get("uid")
    if not uid or not uid.isdigit():
        return jsonify({"status": False, "error": "Sai cú pháp UID"}), 400
    uid_int = int(uid)
    def task(bot):
        bot.sock39699.send(bot._bot.open_squad(5))
        time.sleep(0.5)
        bot.sock39699.send(bot._bot.invite_squad(uid_int, 1))
        bot.sock39699.send(bot._bot.invite_squad(uid_int, 2))
        time.sleep(4)
        botid = getattr(bot, 'botid', None)
        if botid and str(botid).isdigit():
            bot.sock39699.send(bot._bot.leave_squad(int(botid)))
    SCHEDULER.submit(f"/team5 uid={uid}", task)
    return jsonify({"status": True, "message": f"Đã xếp hàng tạo Squad 5 cho UID {uid}"})


@app.route("/addid", methods=["GET"])
def add_uid():
    bid = request.args.get("id"); uid = request.args.get("uid"); timee = request.args.get("time")
    if not bid or not uid or not timee: return "RES_INVALID_PARAMS", 201
    try: bid = int(bid)
    except: return "RES_INVALID_ID", 201
    result = TCPbot.add_uid_to_access(bid, uid, timee)
    if isinstance(result, tuple) and result[0] == True: return "RES_OK", 200
    elif result == "invalid_time": return "RES_INVALID_TIME", 201
    elif result == "invalid_params": return "RES_INVALID_PARAMS", 201
    else: return "RES_FAILED", 201


@app.route("/delid", methods=["GET"])
def delete_uid():
    bid = request.args.get("botid"); uid = request.args.get("uid")
    if not bid or not uid: return "RES_INVALID_PARAMS", 201
    try: bid = int(bid)
    except: return "RES_INVALID_ID", 201
    if TCPbot.deleteId(bid, uid): return "RES_OK", 200
    return "RES_FAILED", 201


@app.route("/addbot", methods=["GET"])
def add_bot():
    token = request.args.get("token")
    if not token: return "RES_INVALID_PARAMS", 201
    I = TCPbot.add_bot(token)
    if I["status"]:
        TCPbot.bots[I["bot_id"]].start()
        return "RES_OK", 200
    return str(I["message"]), 201


@app.route("/delbot", methods=["GET"])
def delete_bot():
    bid = request.args.get("botid")
    if not bid: return "RES_INVALID_PARAMS", 201
    bid = int(bid)
    if TCPbot.delete_bot(bid): return "RES_OK", 200
    return "RES_BOT_NOT_FOUND", 201


@app.route("/get", methods=["GET"])
def api_gettoken():
    account = request.args.get("token")
    emulator = request.args.get("emu", "false").lower() == "true"
    if not account: return jsonify({"success": False, "error": "Missing account"}), 400
    try:
        data = FreeFireAPI().get(account, emulator)
        result = {"uid": data.get("UserAccountUID"), "region": data.get("LockRegion"), "token": data.get("UserAuthToken")}
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/addadmin", methods=["GET"])
def add_admin():
    bid, aid = request.args.get("botid"), request.args.get("uid")
    if not bid or not aid: return "RES_INVALID_PARAMS", 201
    try: bid, aid = int(bid), int(aid)
    except Exception as e: return str(e), 201
    if AdminManager.add_admin(bid, aid): return "RES_OK", 200
    return "RES_ADMIN_ALREADY_EXISTS", 201


# ====================== KHỞI TẠO ======================
TCPbot = BOTMNG()
for _bid, _binst in TCPbot.bots.items():
    BOT_POOL.register(_bid, _binst)

SCHEDULER = Scheduler(BOT_POOL)
logger.info("[Main] Scheduler đã khởi động (bot.json).")


def sbot():
    for bot in TCPbot.bots.values():
        try: bot.start()
        except Exception as e:
            logger.error(f"[ERROR] Khởi động bot thất bại: {e}")


def run_telegram():
    logger.info("🤖 Telegram bot đang chạy...")
    telegram_bot.infinity_polling()


if __name__ == "__main__":
    logger.info("🚀 Khởi động Free Fire Squad Bot Multi – Scheduler Mode + Voice Music")
    logger.info("=" * 60)
    logger.info(f"[KeySystem] KEY_API_BASE    = {KEY_API_BASE}")
    logger.info(f"[KeySystem] ADMIN_PANEL_URL = {ADMIN_PANEL_URL}")
    logger.info(f"[KeySystem] ADMIN_PASS      = {'*' * len(ADMIN_PASS)} (len={len(ADMIN_PASS)})")
    logger.info(f"[KeySystem] KEY_VALIDITY    = {KEY_VALIDITY}s ({KEY_VALIDITY//3600}h)")
    logger.info(f"[KeySystem] KEY_STRICT_MODE = {KEY_STRICT_MODE}")
    logger.info("=" * 60)
    if VOICE_ENABLED:
        logger.info("[Main] 🎵 Voice music ENABLED — /join→s1.mp3 | /lagff→s2.mp3")
    else:
        logger.warning("[Main] 🎵 Voice music DISABLED — cai opuslib + ffmpeg + voice_gr.py")
    threading.Thread(target=run_telegram, daemon=True).start()
    threading.Thread(target=sbot, daemon=True).start()
    app.run(host="0.0.0.0", port=2011, debug=False)