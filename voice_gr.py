# -*- coding: utf-8 -*-
"""
voice_gr.py — GRTC Voice Music Module
Fix ffprobe parse (bỏ warning, lấy đúng số duration)
"""

import asyncio
import threading
import time
import os
import re
import socket
import struct
import subprocess
from typing import Optional, Dict

try:
    import opuslib
    _OPUS_OK = True
except ImportError:
    opuslib = None
    _OPUS_OK = False

from ReQAPI import pb_encode

VOICE_APP_ID = "FFD58FB4F76F648C2A5E21EBCFA3AAE81B4C9B7D97"
VOICE_DEFAULT_UUID = "682761f7-3f39-4912-b019-ced851732362"

# ============================================================
# FIX: đọc đủ n bytes, KHÔNG timeout — chỉ EOF khi pipe đóng thật
# ============================================================
def _read_frame(pipe, n):
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = pipe.read(n - len(buf))
        except Exception:
            break
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)

# ============================================================
# REGISTRY
# ============================================================
_RUNNING: Dict[str, "OpusVoiceClientGRTC"] = {}
_RUNNING_LOCK = threading.RLock()

def _reg_set(bid, c):
    with _RUNNING_LOCK: _RUNNING[str(bid)] = c

def _reg_del(bid):
    with _RUNNING_LOCK: _RUNNING.pop(str(bid), None)

def is_music_running(bot_id) -> bool:
    with _RUNNING_LOCK:
        c = _RUNNING.get(str(bot_id))
    return bool(c and c.is_running)

def voice_status() -> dict:
    with _RUNNING_LOCK:
        return {"total": len(_RUNNING), "sessions": [
            {"bot_id": k, "running": v.is_running}
            for k, v in _RUNNING.items()]}

# ============================================================
# DISPATCHER
# ============================================================
class VoiceDispatcherGRTC:
    def __init__(self, dispatcher_ip="148.222.82.60", dispatcher_port=6674):
        self.dispatcher_ip = dispatcher_ip
        self.dispatcher_port = dispatcher_port

    def build_protobuf(self, uid, room_id, app_id, uuid_str, auth_type):
        clean_room_id = str(room_id).replace("VN_", "")
        voice_token = f"{app_id}VN_{clean_room_id}"
        device_dict = {
            1: 17, 2: 11, 3: 1, 4: "Redmi",
            5: str(uid), 6: 562135116, 7: "arm64-v8a",
            8: "", 9: uuid_str, 10: app_id,
            11: "voiceb", 12: "24094RAD4G", 13: 2, 14: "mt6855",
        }
        device_bytes = pb_encode(device_dict)
        outer_dict = {1: voice_token, 2: device_bytes, 3: auth_type, 4: "vn"}
        return pb_encode(outer_dict)

    def decode_varint(self, data, start_idx):
        result = 0; shift = 0; idx = start_idx
        while True:
            b = data[idx]
            result |= (b & 0x7F) << shift
            idx += 1
            if not (b & 0x80): break
            shift += 7
        return result, idx

    async def get_voice_server(self, uid, room_id, app_id, uuid_str):
        print(f"\n[STEP 2] Kết nối Dispatcher {self.dispatcher_ip}:{self.dispatcher_port} (UDP)...")
        try:
            pb_payload = self.build_protobuf(uid, room_id, app_id, uuid_str, auth_type=2)
            reader, writer = await asyncio.open_connection(
                self.dispatcher_ip, self.dispatcher_port)
            writer.write(struct.pack(">I", len(pb_payload)) + pb_payload)
            await writer.drain()
            print(f"[STEP 2] TX {len(pb_payload)}B")
            try:
                resp_len_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
            except asyncio.TimeoutError:
                print("[STEP 2] ❌ Timeout — token/room_id hết hạn?")
                return None, None
            except asyncio.IncompleteReadError:
                print("[STEP 2] ❌ Server đóng kết nối — gói sai?")
                return None, None
            resp_len = struct.unpack(">I", resp_len_bytes)[0]
            data = await reader.readexactly(resp_len)
            print(f"[STEP 2] RX {resp_len}B")
            writer.close()
            await writer.wait_closed()
            voice_ip, voice_tcp_port = None, None
            idx = 0
            if idx < len(data) and data[idx] == 0x0A:
                idx += 1; ip_len = data[idx]; idx += 1
                voice_ip = data[idx:idx+ip_len].decode("utf-8"); idx += ip_len
            if idx < len(data) and data[idx] == 0x10:
                idx += 1; voice_tcp_port, _ = self.decode_varint(data, idx)
            if not voice_ip:
                print("[STEP 2] ❌ Không parse được IP:port")
                return None, None
            print(f"[✅ STEP 2] voice_ip={voice_ip}  tcp_port={voice_tcp_port}")
            return voice_ip, voice_tcp_port
        except Exception as e:
            print(f"[❌ STEP 2] Lỗi Dispatcher: {repr(e)}")
            return None, None

# ============================================================
# TCP HANDSHAKE
# ============================================================
class VoiceTCPHandshakeGRTC:
    def __init__(self, voice_ip, voice_tcp_port):
        self.voice_ip = voice_ip
        self.voice_tcp_port = voice_tcp_port

    def build_f9_auth_packet(self, uid, room_id, app_id, uuid_str):
        clean_room_id = str(room_id).replace("VN_", "")
        voice_token = f"{app_id}VN_{clean_room_id}"
        device_dict = {
            1: 7, 2: 11, 3: 1, 4: "Redmi",
            5: str(uid), 6: 562135116, 7: "arm64-v8a",
            8: "", 9: uuid_str, 10: app_id,
            11: "voiceb", 12: "24094RAD4G", 13: 2, 14: "mt6855",
        }
        device_bytes = pb_encode(device_dict)
        outer_dict = {1: device_bytes, 2: voice_token, 10: 1,
                      11: str(uid), 12: 0, 14: 0, 16: 1}
        return pb_encode(outer_dict)

    def decode_varint(self, data, start_idx):
        result = 0; shift = 0; idx = start_idx
        while idx < len(data):
            b = data[idx]
            result |= (b & 0x7F) << shift
            idx += 1
            if not (b & 0x80): break
            shift += 7
        return result, idx

    async def execute_handshake(self, uid, room_id, app_id, uuid_str):
        print(f"\n[STEP 3] Đang kết nối TCP tới VOICE SERVER {self.voice_ip}:{self.voice_tcp_port}...")
        try:
            reader, writer = await asyncio.open_connection(
                self.voice_ip, self.voice_tcp_port)
            pb_payload = self.build_f9_auth_packet(uid, room_id, app_id, uuid_str)
            writer.write(struct.pack(">I", len(pb_payload)) + pb_payload)
            await writer.drain()
            resp1_len_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
            resp1_len = struct.unpack(">I", resp1_len_bytes)[0]
            resp1_payload = await reader.readexactly(resp1_len)
            udp_port = None; ssrc = None
            fields_r1 = {}
            idx = 0
            while idx < len(resp1_payload):
                tag_type = resp1_payload[idx]; idx += 1
                field_num = tag_type >> 3
                wire_type = tag_type & 0x07
                if wire_type == 0:
                    val, idx = self.decode_varint(resp1_payload, idx)
                    fields_r1[field_num] = val
                elif wire_type == 2:
                    length, idx = self.decode_varint(resp1_payload, idx)
                    raw = resp1_payload[idx:idx+length]; idx += length
                    fields_r1[field_num] = raw
                else:
                    break
            udp_port = fields_r1.get(2) or fields_r1.get(5)
            f13 = fields_r1.get(13, 0)
            f13_32 = f13 & 0xFFFFFFFF
            f3 = fields_r1.get(3, 0)
            if f13_32 > 0:
                ssrc = f13_32
            elif f3 > 0:
                ssrc = f3
            else:
                import random
                ssrc = random.randint(0x10000000, 0x7FFFFFFF)
            f3_val = f3 & 0xFFFFFFFF
            print(f"[STEP3] UDP={udp_port} SSRC=0x{ssrc:08X} fixed_2=0x{f3_val:08X}")
            f1_raw = fields_r1.get(1, b"")
            if f1_raw:
                custom_pb = bytes([0x0A, len(f1_raw)]) + f1_raw
            else:
                custom_pb = resp1_payload
            custom_bin = struct.pack(">I", len(custom_pb)) + custom_pb
            print(f"[STEP3] TX echo field1 ({len(custom_bin)}b)")
            writer.write(custom_bin)
            await writer.drain()
            try:
                resp2_len_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=5.0)
                resp2_len = struct.unpack(">I", resp2_len_bytes)[0]
                resp2_payload = await reader.readexactly(resp2_len)
                print(f"[✅ STEP3] Server READY ({len(resp2_payload)}b)")
            except asyncio.TimeoutError:
                print("[⚠️ STEP3] Timeout RESP-2 — tiếp tục")
            print(f"[✅ STEP 3] UDP={udp_port} | SSRC={hex(ssrc)} | fixed_2=0x{f3_val:08X}")
            return udp_port, ssrc, f3_val, reader, writer
        except Exception as e:
            print(f"[❌ STEP 3] Lỗi Handshake: {repr(e)}")
            import traceback; traceback.print_exc()
            return None, None, None, None, None

# ============================================================
# OPUS UDP
# ============================================================
class OpusVoiceClientGRTC:
    def __init__(self, voice_ip, voice_udp_port, ssrc, fixed_2=0x00002662, bot_id=None):
        self.voice_ip = voice_ip
        self.voice_udp_port = voice_udp_port
        self.ssrc = ssrc
        self.bot_id = str(bot_id) if bot_id else "?"
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(2.0)
        self.is_running = False
        self.encoder = opuslib.Encoder(48000, 1, opuslib.APPLICATION_AUDIO)
        self.sample_rate = 48000
        self.frame_size = 960
        self.seq_num = 1
        self.timestamp = 0
        self.fixed_2 = fixed_2
        self._mp3_path = None
        print(f"[OpusClient#{self.bot_id}] voice={voice_ip}:{voice_udp_port} "
              f"ssrc=0x{ssrc:08x} fixed_2=0x{fixed_2:08x}")

    def send_open_mic(self, ka_seq=None, ka_ts=None):
        seq = ka_seq if ka_seq is not None else (self.seq_num & 0xFFFFFF)
        ts  = ka_ts  if ka_ts  is not None else (self.timestamp & 0xFFFFFFFF)
        pkt = bytearray()
        pkt.append(0x71)
        pkt += (seq & 0xFFFFFF).to_bytes(3, 'big')
        pkt += struct.pack(">I", ts & 0xFFFFFFFF)
        pkt += struct.pack(">I", self.ssrc & 0xFFFFFFFF)
        pkt += struct.pack(">I", 0x00000311)
        pkt += bytes.fromhex("0000010720210000286e4672656520466972650000000000000000000000")
        pkt += bytes.fromhex("e7877176")
        self.sock.sendto(bytes(pkt), (self.voice_ip, self.voice_udp_port))
        if ka_seq is None:
            self.seq_num += 1
            self.timestamp += 960

    def build_opus_packet(self, opus_data):
        header = bytearray()
        header.extend(b"\x41\x6f")
        header.extend(struct.pack(">H", self.seq_num & 0xFFFF))
        header.extend(struct.pack(">I", self.timestamp & 0xFFFFFFFF))
        header.extend(struct.pack(">I", self.ssrc & 0xFFFFFFFF))
        header.extend(struct.pack(">I", self.fixed_2 & 0xFFFFFFFF))
        self.seq_num += 1
        self.timestamp += 960
        return bytes(header) + opus_data

    def start_music_stream(self, mp3_file="s1.mp3", on_finish=None):
        self.is_running = True
        self._on_finish = on_finish
        self._mp3_path = mp3_file
        _reg_set(self.bot_id, self)
        print(f"[STEP 4] Mở Mic UDP...")
        for _ in range(3):
            self.send_open_mic()
            time.sleep(0.02)
        threading.Thread(target=self.audio_stream_loop,
                         args=(mp3_file, on_finish), daemon=True).start()
        threading.Thread(target=self.udp_keepalive_loop, daemon=True).start()

    def send_udp_ping(self, seq, ts):
        pkt = bytearray()
        pkt.append(0x71)
        pkt += (seq & 0xFFFFFF).to_bytes(3, 'big')
        pkt += struct.pack(">I", ts & 0xFFFFFFFF)
        pkt += struct.pack(">I", self.ssrc & 0xFFFFFFFF)
        pkt += struct.pack(">I", 0x00002662)
        try:
            self.sock.sendto(bytes(pkt), (self.voice_ip, self.voice_udp_port))
        except Exception:
            pass

    def udp_keepalive_loop(self):
        print(f"[UDP KA#{self.bot_id}] Start (2s/lần)")
        ka_seq = 0xF00000
        ka_ts  = 0x74000000
        ping_count = 0
        while self.is_running:
            time.sleep(2.0)
            if not self.is_running: break
            try:
                self.send_udp_ping(ka_seq, ka_ts)
                ping_count += 1
                if ping_count % 30 == 0:
                    print(f"[UDP KA#{self.bot_id}] Ping #{ping_count}")
                ka_seq = (ka_seq + 1) & 0xFFFFFF
                ka_ts  = (ka_ts + 960) & 0xFFFFFFFF
            except Exception as e:
                print(f"[UDP KA#{self.bot_id}] Lỗi: {e}")

    # ============================================================
    # FIX: parse ffprobe duration bằng regex, bỏ mọi warning/rác
    # ============================================================
    def _ffprobe_duration(self, mp3_file):
        try:
            proc = subprocess.run(
                ["ffprobe", "-v", "error",
                 "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1",
                 mp3_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=10,
            )
            text = proc.stdout.decode("utf-8", "ignore")
            # tìm số thực đầu tiên trong output (VD: 134.896327)
            m = re.search(r"(\d+\.\d+)", text)
            if m:
                dur = float(m.group(1))
                print(f"[Producer#{self.bot_id}] ffprobe duration = {dur:.1f}s")
                return dur
            print(f"[Producer#{self.bot_id}] ffprobe parse fail: {text!r}")
            return None
        except Exception as e:
            print(f"[Producer#{self.bot_id}] ffprobe failed: {e}")
            return None

    def _drain_stderr(self, proc, tag):
        try:
            for raw in iter(proc.stderr.readline, b""):
                if not raw:
                    break
                line = raw.decode("utf-8", "ignore").rstrip()
                if line:
                    print(f"[FFmpegErr#{tag}] {line}")
        except Exception:
            pass

    def _producer_thread(self, mp3_file, q):
        import queue

        self._ffprobe_duration(mp3_file)

        # Bỏ alimiter → giảm CPU/RAM, tránh ffmpeg bị OOM kill
        cmd = [
            'ffmpeg', '-i', mp3_file,
            '-filter:a', 'volume=3.5',
            '-f', 's16le', '-ac', '1', '-ar', '48000',
            '-loglevel', 'error',
            '-nostats',
            'pipe:1'
        ]
        print(f"[Producer#{self.bot_id}] START ffmpeg: {mp3_file}")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=65536,
            )
        except FileNotFoundError:
            print(f"[Producer#{self.bot_id}] ❌ ffmpeg not found!")
            try: q.put(None, block=False)
            except Exception: pass
            return

        threading.Thread(
            target=self._drain_stderr,
            args=(proc, self.bot_id),
            daemon=True,
            name=f"FFmpegErr-{self.bot_id}",
        ).start()

        chunk_size = 1920
        total_bytes = 0
        total_frames = 0
        try:
            while self.is_running:
                raw = _read_frame(proc.stdout, chunk_size)
                if not raw:
                    print(f"[Producer#{self.bot_id}] HET FILE NHAC that su "
                          f"(total={total_bytes}b, {total_frames} frames, "
                          f"{total_bytes/2/48000:.1f}s) → sentinel")
                    try:
                        q.put(None, block=True, timeout=5.0)
                    except Exception: pass
                    break

                if len(raw) < chunk_size:
                    raw = raw + b"\x00" * (chunk_size - len(raw))

                total_bytes += len(raw)

                try:
                    opus_data = self.encoder.encode(raw, 960)
                    q.put(opus_data, block=True, timeout=5.0)
                    total_frames += 1
                except queue.Full:
                    print(f"[Producer#{self.bot_id}] q full, drop frame #{total_frames}")
                except Exception as e:
                    print(f"[Producer#{self.bot_id}] encode err: {e}")
        except Exception as e:
            print(f"[Producer#{self.bot_id}] Error: {e}")
            try: q.put(None, block=False)
            except: pass
        finally:
            try:
                proc.terminate()
                try:
                    rc = proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    rc = proc.wait(timeout=2)
                if rc != 0:
                    print(f"[Producer#{self.bot_id}] ⚠️ ffmpeg exit code = {rc} "
                          f"(≠ 0 → ffmpeg bị lỗi/killed)")
                else:
                    print(f"[Producer#{self.bot_id}] ffmpeg exit code = 0")
            except Exception as e:
                print(f"[Producer#{self.bot_id}] wait err: {e}")
            print(f"[Producer#{self.bot_id}] EXIT total={total_bytes}b "
                  f"({total_bytes/2/48000:.1f}s) frames={total_frames}")

    def audio_stream_loop(self, mp3_file, on_finish=None):
        import queue
        q = queue.Queue(maxsize=500)
        producer = threading.Thread(
            target=self._producer_thread, args=(mp3_file, q), daemon=True)
        producer.start()
        while q.qsize() < 100 and self.is_running:
            time.sleep(0.05)
        print(f"[Audio#{self.bot_id}] Buffer đủ ({q.qsize()} frames) → stream")
        packets_sent = 0
        next_send = time.perf_counter()
        reason = "unknown"
        try:
            while self.is_running:
                try:
                    opus_data = q.get(timeout=0.5)
                except queue.Empty:
                    next_send = time.perf_counter()
                    continue
                if opus_data is None:
                    reason = "sentinel (EOF)"
                    print(f"[Audio#{self.bot_id}] Hết nhạc sau {packets_sent} frames "
                          f"({packets_sent*0.02:.1f}s) → dừng")
                    break
                packet = self.build_opus_packet(opus_data)
                try:
                    self.sock.sendto(packet, (self.voice_ip, self.voice_udp_port))
                except OSError as e:
                    print(f"[Audio#{self.bot_id}] Socket warn: {e}")
                packets_sent += 1
                if packets_sent % 500 == 0:
                    print(f"  [Audio#{self.bot_id}] {packets_sent} frames "
                          f"({packets_sent*0.02:.1f}s, buf={q.qsize()})")
                next_send += 0.020
                sleep_for = next_send - time.perf_counter()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                elif sleep_for < -0.060:
                    next_send = time.perf_counter()
        except Exception as e:
            reason = f"exception: {e}"
            print(f"[Audio#{self.bot_id}] Fatal: {e}")
            import traceback; traceback.print_exc()
        finally:
            print(f"[Audio#{self.bot_id}] EXIT reason={reason} "
                  f"sent={packets_sent} ({packets_sent*0.02:.1f}s)")
            self.is_running = False
            _reg_del(self.bot_id)
            try: self.sock.close()
            except Exception: pass
            if on_finish:
                try: on_finish()
                except Exception as e:
                    print(f"[Audio#{self.bot_id}] on_finish error: {e}")

# ============================================================
# TRIGGER PIPELINE
# ============================================================
def trigger_music_pipeline(bot, gvoice_room_id, gvoice_squad_id,
                           mp3_file="s1.mp3", on_finish=None):
    def _start_music():
        time.sleep(0.5)
        _uuid   = VOICE_DEFAULT_UUID
        _app_id = VOICE_APP_ID
        _uid    = str(bot.botid)

        loop = asyncio.new_event_loop()

        async def master_voice_pipeline():
            print(f"[PIPELINE] Bắt đầu GRTC. Room: {gvoice_room_id}")

            async def send_tcp_cmd(writer, cmd_id):
                try:
                    clean_room_id = str(gvoice_room_id).replace("VN_", "")
                    voice_token = f"{_app_id}VN_{clean_room_id}"
                    f1_bytes = pb_encode({1: cmd_id, 2: 0, 3: 0})
                    f3_bytes = pb_encode({1: str(_uid), 2: 1})
                    payload = pb_encode({1: f1_bytes, 2: voice_token, 3: f3_bytes})
                    writer.write(struct.pack(">I", len(payload)) + payload)
                    await writer.drain()
                    print(f"  [TCP TX] Đã gửi CMD={cmd_id}")
                except Exception as e:
                    print(f"  [TCP TX] Lỗi CMD={cmd_id}: {e}")

            async def send_agora_join(writer):
                try:
                    agora_pkt = bytes.fromhex("feffff7f")
                    writer.write(struct.pack(">I", len(agora_pkt)) + agora_pkt)
                    await writer.drain()
                    print("  [TCP TX] Đã gửi AGORA_JOIN (FE FF FF 7F)")
                except Exception:
                    pass

            dispatcher = VoiceDispatcherGRTC()
            voice_ip, voice_tcp_port = await dispatcher.get_voice_server(
                _uid, gvoice_room_id, _app_id, _uuid)
            if not voice_ip or not voice_tcp_port:
                if on_finish:
                    try: on_finish()
                    except: pass
                return

            await asyncio.sleep(0.1)
            handshake = VoiceTCPHandshakeGRTC(voice_ip, voice_tcp_port)
            udp_port, ssrc, fixed_2, v_reader, v_writer = await handshake.execute_handshake(
                _uid, gvoice_room_id, _app_id, _uuid)
            if not udp_port or not ssrc:
                if on_finish:
                    try: on_finish()
                    except: pass
                return

            print("[PIPELINE] Đồng bộ Game Server...")
            await send_tcp_cmd(v_writer, 9)
            await asyncio.sleep(0.05)
            await send_agora_join(v_writer)

            opus_client = OpusVoiceClientGRTC(
                voice_ip=voice_ip, voice_udp_port=udp_port,
                ssrc=ssrc, fixed_2=fixed_2, bot_id=_uid)
            opus_client.send_open_mic()
            await asyncio.sleep(0.1)

            await send_tcp_cmd(v_writer, 24)
            await send_tcp_cmd(v_writer, 35)

            async def tcp_reader_and_keepalive():
                last_cmd9_time = time.time()
                music_started = False

                while not v_writer.is_closing():
                    current_time = time.time()
                    if current_time - last_cmd9_time >= 18:
                        await send_tcp_cmd(v_writer, 9)
                        print(f"  [TCP KA] CMD=9 start_speak (keepalive)")
                        last_cmd9_time = current_time
                    phase = "header"
                    pay_len = 0
                    try:
                        hdr = await asyncio.wait_for(v_reader.readexactly(4), timeout=1.0)
                        pay_len = struct.unpack(">I", hdr)[0]
                        if pay_len == 0:
                            continue
                        if pay_len > 500_000:
                            print(f"[TCP Loop] pay_len bat thuong ({pay_len}), ngat")
                            break
                        phase = "payload"
                        payload = await asyncio.wait_for(
                            v_reader.readexactly(pay_len), timeout=10.0)
                        phase = "done"
                        print(f"  [TCP RX] {pay_len}B")
                        cmd_id = None
                        if len(payload) >= 3 and payload[0] == 0x0a:
                            inner_len = payload[1]
                            if inner_len >= 2 and payload[2] == 0x08:
                                cmd_id = payload[3] if len(payload) > 3 else None
                        if pay_len > 100 and not music_started:
                            print("  [RX] Member Info → kích nhạc")
                            await send_agora_join(v_writer)
                            await send_tcp_cmd(v_writer, 33)
                            music_started = True
                            if not getattr(opus_client, 'is_running', False):
                                def _on_music_finish():
                                    print(f"[FINISH#{_uid}] Nhạc xong")
                                    try:
                                        opus_client.is_running = False
                                        try: v_writer.close()
                                        except Exception: pass
                                    except Exception as e:
                                        print(f"[FINISH#{_uid}] Error: {e}")
                                    finally:
                                        if on_finish:
                                            try: on_finish()
                                            except Exception: pass
                                opus_client.start_music_stream(mp3_file, on_finish=_on_music_finish)
                        elif cmd_id == 11:
                            await send_tcp_cmd(v_writer, 11)
                        elif cmd_id == 10 or b"\x08\x0a" in payload[:15]:
                            await send_tcp_cmd(v_writer, 11)
                        else:
                            if cmd_id:
                                print(f"  [RX] CMD={cmd_id} (bỏ qua)")
                    except asyncio.TimeoutError:
                        if phase == "payload":
                            print(f"[TCP Loop] Timeout doc payload, ngat")
                            break
                    except Exception as e:
                        print(f"\n[TCP Loop] Server ngat ket noi: {e}")
                        print("[TCP Loop] Thử renew mic session...")
                        try:
                            for _ in range(3):
                                opus_client.send_open_mic()
                                time.sleep(0.05)
                        except Exception: pass
                        break
                while getattr(opus_client, 'is_running', False):
                    await asyncio.sleep(0.5)

            await tcp_reader_and_keepalive()

        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(master_voice_pipeline())
        except Exception as e:
            print(f"[PIPELINE] err: {e}")
            if on_finish:
                try: on_finish()
                except: pass
        finally:
            try: loop.close()
            except: pass
    threading.Thread(target=_start_music, daemon=True).start()

# ============================================================
# PUBLIC API
# ============================================================
def start_voice_music(bot, room_id, mp3_file="s1.mp3", on_finish=None) -> bool:
    if not _OPUS_OK:
        if on_finish:
            try: on_finish()
            except: pass
        return False
    uid = str(getattr(bot, "botid", "") or "").strip()
    if not uid or not room_id:
        if on_finish:
            try: on_finish()
            except: pass
        return False
    if not os.path.isabs(mp3_file):
        mp3_file = os.path.join(os.getcwd(), mp3_file)

    with _RUNNING_LOCK:
        old = _RUNNING.get(str(uid))
    if old and old.is_running:
        print(f"[StartVoice] Dừng session cũ của bot #{uid}")
        old.is_running = False
        time.sleep(0.3)

    trigger_music_pipeline(bot, room_id, 0, mp3_file=mp3_file, on_finish=on_finish)
    return True

def wait_room_and_start(bot, mp3_file="s1.mp3", timeout=5.0, on_finish=None) -> bool:
    ev = getattr(bot, "room_id_event", None)
    if ev is None:
        if on_finish:
            try: on_finish()
            except: pass
        return False
    ok = ev.wait(timeout=timeout)
    if not ok or not getattr(bot, "last_room_id", None):
        if on_finish:
            try: on_finish()
            except: pass
        return False
    room_id = bot.last_room_id
    print(f"[wait_room] Got room_id={room_id} → start music {mp3_file}")
    return start_voice_music(bot, room_id, mp3_file, on_finish=on_finish)

def stop_voice_music(bot_id=None, all=False) -> int:
    stopped = 0
    with _RUNNING_LOCK:
        if all:
            for k, c in list(_RUNNING.items()):
                try: c.is_running = False; stopped += 1
                except: pass
            _RUNNING.clear()
        elif bot_id is not None:
            c = _RUNNING.pop(str(bot_id), None)
            if c:
                try: c.is_running = False; stopped += 1
                except: pass
    return stopped