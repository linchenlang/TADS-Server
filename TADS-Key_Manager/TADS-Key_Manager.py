# -*- coding: utf-8 -*-
"""
TADS 物理密钥及密码管理系统
"""

# ============================================================================
# TADS 兼容层 —— 仅做 CPU 二次检测，不弹提示窗
# ============================================================================
import os
import sys
import ctypes
import threading
import traceback


def _compat_probe():
    def _q(code):
        try:
            return ctypes.windll.kernel32.IsProcessorFeaturePresent(code) != 0
        except Exception:
            return False
    try:
        f = {
            'SSE3': _q(13), 'AVX': _q(40), 'AVX2': _q(41), 'AVX512F': _q(42),
            'AVX512_VBMI': _q(43), 'FMA': _q(45),
        }
        f['ProbeOK'] = True
        return f
    except Exception:
        return {'SSE3': False, 'AVX': False, 'AVX2': False,
                'AVX512F': False, 'AVX512_VBMI': False, 'FMA': False,
                'ProbeOK': False}


def _compat_apply(features):
    _DIS_AVX512 = ("AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,"
                   "AVX512_CNL,AVX512_ICL,AVX512_VBMI,AVX512_VBMI2")
    _DIS_AVX2 = _DIS_AVX512 + ",AVX2,FMA3,F16C"
    _DIS_AVX = _DIS_AVX2 + ",AVX"
    if not features['ProbeOK']:
        os.environ["OPENBLAS_CORETYPE"] = "ATOM"
        os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX
        return
    if features['AVX512F'] or features['AVX2']:
        return
    if features['AVX']:
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX2
        return
    if features['SSE3']:
        os.environ["OPENBLAS_CORETYPE"] = "ATOM"
        os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX
        return
    os.environ["OPENBLAS_CORETYPE"] = "ATOM"
    os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
    os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX


try:
    _feat = _compat_probe()
    _compat_apply(_feat)
except Exception:
    pass
# ============================================================================

import json
import datetime
import time
import binascii
import base64
import hashlib
import re
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import serial
import serial.tools.list_ports

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding


# ================== 路径配置 ==================
APP_CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'TADS', 'Server', 'config')
if not os.path.exists(APP_CONFIG_DIR):
    os.makedirs(APP_CONFIG_DIR)

ENV_FILE = os.path.join(APP_CONFIG_DIR, ".env")
KEY_STATUS_FILE = os.path.join(APP_CONFIG_DIR, "key_status.env")
NAME_FILE = os.path.join(APP_CONFIG_DIR, "name.env")
CONFIG_FILE = os.path.join(APP_CONFIG_DIR, "config.json")
AES_SALT = b"TADS_UID_PASSWORD_SALT_v1"

# 日志路径（由 _init_log_paths() 填充）
_LOG_FILE = None
_ERROR_FILE = None


# ================== 模块级日志函数（带 [物理密钥与密码管理系统]- 前缀） ==================
def _init_log_paths():
    """从 config.json 的 paths.log_dir 初始化日志路径"""
    global _LOG_FILE, _ERROR_FILE
    log_dir = ""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            log_dir = cfg.get('paths', {}).get('log_dir', '')
    except Exception:
        log_dir = ""
    if not log_dir:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(CONFIG_FILE)), 'log')
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        pass
    _LOG_FILE = os.path.join(log_dir, 'operations.log')
    _ERROR_FILE = os.path.join(log_dir, 'error.log')


def log_action(action, detail=""):
    """写入总日志"""
    if not _LOG_FILE:
        return
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{ts}] [物理密钥与密码管理系统]-{action}"
        if detail:
            msg += f" – {detail}"
        os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
        with open(_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(msg + "\n")
    except Exception:
        pass


def log_error(message):
    """写入报错日志"""
    if not _ERROR_FILE:
        return
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{ts}] [物理密钥与密码管理系统]-{message}"
        os.makedirs(os.path.dirname(_ERROR_FILE), exist_ok=True)
        with open(_ERROR_FILE, 'a', encoding='utf-8') as f:
            f.write(msg + "\n")
    except Exception:
        pass


# ================== 密码工具函数 ==================
def hash_password(password):
    salt = os.urandom(16)
    pwd_bytes = password.encode('utf-8')
    computed = hashlib.sha256(pwd_bytes + salt).digest()
    return base64.b64encode(salt + computed).decode('utf-8')


def verify_password(input_pwd, stored_hash_b64):
    if not stored_hash_b64:
        return False
    try:
        combined = base64.b64decode(stored_hash_b64)
        if len(combined) != 48:
            return False
        salt = combined[:16]
        stored_hash = combined[16:]
        computed = hashlib.sha256(input_pwd.encode('utf-8') + salt).digest()
        return computed == stored_hash
    except Exception:
        return False


def encrypt_password(plain_password: str, aes_key: bytes) -> str:
    if not plain_password:
        return ""
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv),
                    backend=default_backend())
    enc = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain_password.encode('utf-8')) + padder.finalize()
    ct = enc.update(padded) + enc.finalize()
    return base64.b64encode(iv + ct).decode('utf-8')


def decrypt_password(encrypted_data: str, aes_key: bytes) -> str:
    if not encrypted_data:
        return ""
    try:
        combined = base64.b64decode(encrypted_data)
        iv = combined[:16]
        ct = combined[16:]
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv),
                        backend=default_backend())
        dec = cipher.decryptor()
        padded = dec.update(ct) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode('utf-8')
    except Exception:
        return ""


# ================== PN532 读卡器驱动 ==================
def find_pn532_port(baudrate=115200, timeout=0.5):
    ports = serial.tools.list_ports.comports()
    for port in ports:
        device = port.device
        try:
            ser = serial.Serial(device, baudrate, timeout=timeout)
            wake = b'\x55\x55\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\x03\xfd\xd4\x14\x01\x17\x00'
            ser.write(wake)
            time.sleep(0.1)
            ser.reset_input_buffer()
            ser.write(b'\x00\x00\xff\x04\xfc\xd4\x14\x01\xe7')
            time.sleep(0.1)
            header = ser.read(5)
            if len(header) == 5 and header[0:3] == b'\x00\x00\xff':
                ser.close()
                return device
            ser.close()
        except Exception:
            continue
    return None


class PN532Reader:
    def __init__(self, port="COM4", baudrate=115200, auto=False):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._connected = False
        self._lock = threading.Lock()

        if auto or port is None or (isinstance(port, str) and port.lower() == "auto"):
            auto_port = find_pn532_port(baudrate)
            if auto_port:
                self.port = auto_port
            else:
                ports = serial.tools.list_ports.comports()
                if ports:
                    self.port = ports[0].device
                else:
                    if isinstance(self.port, str) and self.port.lower() == "auto":
                        self.port = "COM4"
        self._init_reader()

    def _init_reader(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(
                port=self.port, baudrate=self.baudrate, timeout=0.3,
                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, bytesize=8)
            self._wake()
            self.ser.reset_input_buffer()
            self._init_rf()
            self._connected = True
        except Exception as e:
            log_error(f"PN532 初始化失败: {e}")
            self._connected = False

    def _wake(self):
        self.ser.write(bytes.fromhex(
            "55 55 00 00 00 00 00 00 00 00 00 00 00 00 00 00 ff 03 fd d4 14 01 17 00"))
        time.sleep(0.015)
        try:
            self.ser.read(25)
        except Exception:
            pass

    def _init_rf(self):
        self.ser.write(bytes.fromhex("00 00 FF 04 FC D4 14 01 E7 00"))
        time.sleep(0.015)
        try:
            self.ser.read(32)
        except Exception:
            pass

    def _send_command(self, cmd, params=b'', timeout=0.2):
        if not self.ser or not self.ser.is_open:
            return None
        data = b'\xd4' + bytes([cmd]) + params
        length = len(data)
        lcs = (0x100 - length) & 0xFF
        frame = b'\x00\x00\xff' + bytes([length, lcs]) + data
        dcs = (0x100 - (sum(data) & 0xFF)) & 0xFF
        frame += bytes([dcs])
        with self._lock:
            try:
                self.ser.write(frame)
                time.sleep(timeout)
                self.ser.read(6)  # ACK
                header = self.ser.read(5)
                if len(header) != 5 or header[:3] != b'\x00\x00\xff':
                    return None
                resp_len = header[3]
                resp = self.ser.read(resp_len + 1)
                if len(resp) != resp_len + 1:
                    return None
                resp_data = resp[:-1]
                if resp_data and resp_data[0] == 0xD5:
                    return resp_data[1:]
                return resp_data
            except Exception:
                return None

    def read_m1_uid(self):
        self._wake()
        try:
            self.ser.write(bytes.fromhex("00 00 FF 04 FC D4 4A 02 00 E0 00"))
            time.sleep(0.015)
            redata = binascii.b2a_hex(self.ser.read(25)).decode().upper()
            if len(redata) >= 50:
                uid = redata[-12:-4]
                if len(uid) == 8:
                    return uid, 4
        except Exception:
            pass
        return None, None

    def read_ntag_uid(self, retry=5):
        self._wake()
        try:
            self.ser.reset_input_buffer()
            self._init_rf()
        except Exception:
            pass
        time.sleep(0.1)
        for _ in range(retry):
            resp = self._send_command(0x4A, b'\x01\x00', timeout=0.3)
            if resp:
                if resp[0] == 0xD5:
                    resp = resp[1:]
                if len(resp) >= 7 and resp[0] == 0x4B and resp[1] != 0:
                    uid_len = resp[6]
                    if 0 < uid_len <= len(resp) - 7:
                        return resp[7:7 + uid_len].hex().upper(), uid_len
            time.sleep(0.2)
        return None, None

    def reset(self):
        try:
            self.ser.reset_input_buffer()
            self._wake()
            self._init_rf()
        except Exception:
            pass

    def is_connected(self):
        return self._connected and self.ser is not None and self.ser.is_open

    def check_connection(self):
        try:
            if not self.ser or not self.ser.is_open:
                return False
            self.ser.timeout = 0.1
            self.ser.read(1)
            return True
        except Exception:
            self._connected = False
            return False

    def reconnect(self):
        auto_port = find_pn532_port(self.baudrate)
        if auto_port:
            self.port = auto_port
        else:
            ports = serial.tools.list_ports.comports()
            if ports:
                self.port = ports[0].device
        self._init_reader()
        return self._connected


# ================== 密钥及密码管理类 ==================
class KeyManager:
    def __init__(self):
        self.admin_uids = []
        self.root_uids = []
        self.key_status = {}
        self.uid_passwords = {}
        self.name_map = {}
        self.card_types = {}
        self.config = {}
        self.config_version = 0
        self.aes_key = self._get_or_create_uid_encryption_key()
        self.load()

    # 包装模块级日志函数（保持原有调用点不变）
    def log_action(self, action, detail=""):
        log_action(action, detail)

    def log_error(self, message):
        log_error(message)

    def _get_or_create_uid_encryption_key(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                key_b64 = cfg.get('uid_encryption_key', '')
                if key_b64:
                    return base64.b64decode(key_b64)
        except Exception as e:
            self.log_error(f"读取 uid_encryption_key 失败: {e}")

        new_key = os.urandom(32)
        self.aes_key = new_key
        self._increment_config_version()
        return new_key

    def load(self):
        self.admin_uids = []
        self.root_uids = []
        self.key_status = {}
        self.uid_passwords = {}
        self.name_map = {}
        self.card_types = {}
        self.config = {}
        self.config_version = 0

        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                    self.uid_passwords = self.config.get('uid_passwords', {})
                    self.config_version = self.config.get('config_version', 0)
            except Exception as e:
                self.log_error(f"加载 config.json 失败: {e}")

        if os.path.exists(ENV_FILE):
            try:
                with open(ENV_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, val = line.split('=', 1)
                            key = key.strip()
                            val = val.strip()
                            if key == 'ADMIN_UID' and val:
                                self.admin_uids = [u.strip() for u in val.split(',') if u.strip()]
                            elif key == 'ROOT_UID' and val:
                                self.root_uids = [u.strip() for u in val.split(',') if u.strip()]
            except Exception as e:
                self.log_error(f"加载 .env 失败: {e}")

        if os.path.exists(KEY_STATUS_FILE):
            try:
                with open(KEY_STATUS_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split('|')
                        if len(parts) >= 5:
                            uid = parts[0].strip().upper()
                            self.key_status[uid] = {
                                "card_type": parts[1].strip(),
                                "permission": parts[2].strip(),
                                "name": parts[3].strip(),
                                "enabled": parts[4].strip().upper() == 'TRUE',
                            }
                            if parts[3].strip():
                                self.name_map[uid] = parts[3].strip()
                            self.card_types[uid] = parts[1].strip()
            except Exception as e:
                self.log_error(f"加载 key_status.env 失败: {e}")

        if os.path.exists(NAME_FILE):
            try:
                with open(NAME_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, val = line.split('=', 1)
                            key = key.strip()
                            val = val.strip()
                            if key.startswith('NAME_'):
                                uid = key[5:]
                                if uid not in self.name_map or not self.name_map[uid]:
                                    self.name_map[uid] = val
                                    if uid in self.key_status:
                                        self.key_status[uid]['name'] = val
                            elif key.startswith('TYPE_'):
                                uid = key[5:]
                                if uid not in self.card_types or not self.card_types[uid]:
                                    self.card_types[uid] = val
                                    if uid in self.key_status:
                                        self.key_status[uid]['card_type'] = val
            except Exception as e:
                self.log_error(f"加载 name.env 失败: {e}")

    def _increment_config_version(self):
        try:
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            self.config_version = config.get('config_version', 0) + 1
            config['config_version'] = self.config_version
            config['uid_passwords'] = self.uid_passwords
            if hasattr(self, 'aes_key') and self.aes_key:
                config['uid_encryption_key'] = base64.b64encode(self.aes_key).decode('utf-8')
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_error(f"更新 config.json 失败: {e}")

    def save_all(self):
        try:
            other_lines = []
            if os.path.exists(ENV_FILE):
                with open(ENV_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith('ADMIN_UID=') or s.startswith('ROOT_UID='):
                            continue
                        other_lines.append(line.rstrip())
            with open(ENV_FILE, 'w', encoding='utf-8') as f:
                for line in other_lines:
                    if line.strip():
                        f.write(line + '\n')
                if self.admin_uids:
                    f.write(f'ADMIN_UID={",".join(self.admin_uids)}\n')
                if self.root_uids:
                    f.write(f'ROOT_UID={",".join(self.root_uids)}\n')
        except Exception as e:
            raise Exception(f"保存 .env 失败: {e}")

        try:
            with open(KEY_STATUS_FILE, 'w', encoding='utf-8') as f:
                for uid, data in self.key_status.items():
                    f.write(f"{uid}|{data['card_type']}|{data['permission']}|"
                            f"{data['name']}|{'TRUE' if data['enabled'] else 'FALSE'}\n")
        except Exception as e:
            raise Exception(f"保存 key_status.env 失败: {e}")

        try:
            with open(NAME_FILE, 'w', encoding='utf-8') as f:
                for uid, name in self.name_map.items():
                    f.write(f'NAME_{uid}={name}\n')
                for uid, ct in self.card_types.items():
                    f.write(f'TYPE_{uid}={ct}\n')
        except Exception as e:
            raise Exception(f"保存 name.env 失败: {e}")

        self._increment_config_version()

    def get_all_keys(self):
        keys = []
        for uid, data in self.key_status.items():
            has_pwd = bool(self.uid_passwords.get(uid, ''))
            permission = data.get('permission', 'Administrator')
            if permission == 'Developer':
                keys.append({
                    'uid': uid, 'card_type': '--', 'permission': 'Developer',
                    'name': data.get('name', ''),
                    'enabled': data.get('enabled', True),
                    'has_password': has_pwd,
                    'is_special': True, 'is_developer': True,
                })
            else:
                keys.append({
                    'uid': uid, 'card_type': data.get('card_type', 'M1'),
                    'permission': permission,
                    'name': data.get('name', ''),
                    'enabled': data.get('enabled', True),
                    'has_password': has_pwd,
                    'is_special': False, 'is_developer': False,
                })

        keys.append({
            'uid': 'ADMIN_GENERAL', 'card_type': '--',
            'permission': 'Administrator', 'name': 'Administrator通用密码',
            'enabled': True,
            'has_password': bool(self.config.get('admin_password_hash', '')),
            'is_special': True, 'is_developer': False,
        })
        keys.append({
            'uid': 'ROOT_GENERAL', 'card_type': '--',
            'permission': 'ROOT', 'name': 'ROOT通用密码',
            'enabled': True,
            'has_password': bool(self.config.get('root_password_hash', '')),
            'is_special': True, 'is_developer': False,
        })
        return keys

    def get_key_by_uid(self, uid):
        uid = uid.upper()
        for key in self.get_all_keys():
            if key['uid'] == uid:
                return key
        return None

    def get_password(self, uid):
        uid = uid.upper()
        encrypted = self.uid_passwords.get(uid, '')
        if not encrypted:
            return ''
        return decrypt_password(encrypted, self.aes_key)

    def set_password(self, uid, plain_password):
        uid = uid.upper()
        if uid not in self.key_status:
            return False, f"未找到 UID: {uid}"
        if plain_password and len(plain_password) < 4:
            return False, "密码长度至少4位"
        if plain_password:
            self.uid_passwords[uid] = encrypt_password(plain_password, self.aes_key)
        else:
            self.uid_passwords.pop(uid, None)
        self.save_all()
        return True, "密码已设置"

    def add_key(self, uid, permission, card_type, name='', password=''):
        uid = uid.strip().upper()
        if not uid:
            return False, "UID 不能为空"
        if permission != 'Developer':
            if not re.match(r'^[0-9A-F]+$', uid):
                return False, "UID 只能包含十六进制字符 (0-9, A-F)"
            if len(uid) not in (8, 14):
                return False, f"UID 长度必须是 8 位(M1) 或 14 位(NTAG)，当前: {len(uid)}"
        if uid in self.key_status:
            return False, f"UID {uid} 已存在"

        self.key_status[uid] = {
            "card_type": card_type, "permission": permission,
            "name": name, "enabled": True,
        }
        self._update_uid_lists(uid, permission, 'add')
        if name:
            self.name_map[uid] = name
        self.card_types[uid] = card_type
        if password and len(password) >= 4:
            self.uid_passwords[uid] = encrypt_password(password, self.aes_key)
        self.save_all()
        return True, f"已添加密钥: {uid} ({permission})"

    def update_key_uid(self, old_uid, new_uid):
        old_uid = old_uid.upper()
        new_uid = new_uid.upper()
        if old_uid not in self.key_status:
            return False, f"未找到 UID: {old_uid}"
        if new_uid in self.key_status and new_uid != old_uid:
            return False, f"新 UID {new_uid} 已存在"

        data = self.key_status[old_uid]
        permission = data['permission']
        encrypted_pwd = self.uid_passwords.get(old_uid, '')
        name = data.get('name', '')
        card_type = data.get('card_type', 'M1')
        enabled = data.get('enabled', True)

        self.key_status.pop(old_uid, None)
        self.uid_passwords.pop(old_uid, None)
        self.name_map.pop(old_uid, None)
        self.card_types.pop(old_uid, None)
        if old_uid in self.admin_uids:
            self.admin_uids.remove(old_uid)
        if old_uid in self.root_uids:
            self.root_uids.remove(old_uid)

        self.key_status[new_uid] = {
            "card_type": card_type, "permission": permission,
            "name": name, "enabled": enabled,
        }
        if encrypted_pwd:
            self.uid_passwords[new_uid] = encrypted_pwd
        if name:
            self.name_map[new_uid] = name
        self.card_types[new_uid] = card_type
        self._update_uid_lists(new_uid, permission, 'add')
        self.save_all()
        return True, f"UID 已从 {old_uid} 更新为 {new_uid}"

    def _update_uid_lists(self, uid, permission, action):
        if permission == 'Developer':
            return
        if action == 'add':
            if permission in ('Both', 'Administrator') and uid not in self.admin_uids:
                self.admin_uids.append(uid)
            if permission in ('Both', 'ROOT') and uid not in self.root_uids:
                self.root_uids.append(uid)
        elif action == 'remove':
            if uid in self.admin_uids:
                self.admin_uids.remove(uid)
            if uid in self.root_uids:
                self.root_uids.remove(uid)

    def update_permission(self, uid, new_permission):
        uid = uid.upper()
        if uid not in self.key_status:
            return False, f"未找到 UID: {uid}"
        old = self.key_status[uid]['permission']
        self._update_uid_lists(uid, old, 'remove')
        self.key_status[uid]['permission'] = new_permission
        self._update_uid_lists(uid, new_permission, 'add')
        self.save_all()
        return True, f"权限已更新为 {new_permission}"

    def update_name(self, uid, name):
        uid = uid.upper()
        if uid not in self.key_status:
            return False, f"未找到 UID: {uid}"
        self.key_status[uid]['name'] = name
        self.name_map[uid] = name
        self.save_all()
        return True, "名称已更新"

    def set_enabled(self, uid, enabled):
        uid = uid.upper()
        if uid not in self.key_status:
            return False, f"未找到 UID: {uid}"
        self.key_status[uid]['enabled'] = enabled
        if not enabled:
            self._update_uid_lists(uid, self.key_status[uid]['permission'], 'remove')
        else:
            self._update_uid_lists(uid, self.key_status[uid]['permission'], 'add')
        self.save_all()
        return True, f"密钥已{'启用' if enabled else '禁用'}"

    def delete_key(self, uid):
        uid = uid.upper()
        if uid not in self.key_status:
            return False, f"未找到 UID: {uid}"
        self._update_uid_lists(uid, self.key_status[uid]['permission'], 'remove')
        self.key_status.pop(uid, None)
        self.uid_passwords.pop(uid, None)
        self.name_map.pop(uid, None)
        self.card_types.pop(uid, None)
        self.save_all()
        return True, f"已删除密钥: {uid}"

    def set_general_password(self, pwd_type, plain_password):
        if plain_password and len(plain_password) < 4:
            return False, "密码长度至少4位"
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception as e:
                return False, f"加载 config.json 失败: {e}"

        if plain_password:
            hashed = hash_password(plain_password)
            if pwd_type == 'admin':
                self.config['admin_password_hash'] = hashed
            elif pwd_type == 'root':
                self.config['root_password_hash'] = hashed
            elif pwd_type == 'developer':
                self.config['developer_password_hash'] = hashed
            else:
                return False, "无效的密码类型"
        else:
            if pwd_type == 'admin':
                self.config['admin_password_hash'] = ''
            elif pwd_type == 'root':
                self.config['root_password_hash'] = ''
            elif pwd_type == 'developer':
                self.config['developer_password_hash'] = ''
            else:
                return False, "无效的密码类型"

        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return False, f"保存 config.json 失败: {e}"

        self.save_all()
        self._reload_config()
        return True, f"{pwd_type}通用密码已{'设置' if plain_password else '清空'}"

    def _reload_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                    self.uid_passwords = self.config.get('uid_passwords', {})
        except Exception as e:
            self.log_error(f"重新加载 config.json 失败: {e}")

    def _get_log_usage_count(self, uid, hours=4):
        try:
            if not os.path.exists(CONFIG_FILE):
                return -1
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            log_dir = cfg.get('paths', {}).get('log_dir', '')
            if not log_dir:
                log_dir = os.path.join(os.path.dirname(os.path.dirname(CONFIG_FILE)), 'log')
            log_file = os.path.join(log_dir, 'operations.log')
            if not os.path.exists(log_file):
                return -1

            cutoff = datetime.datetime.now() - datetime.timedelta(hours=hours)
            uid_str = uid

            info = self.key_status.get(uid_str)
            if uid_str == 'ADMIN_GENERAL':
                kind = 'ADMIN_GENERAL'
            elif uid_str == 'ROOT_GENERAL':
                kind = 'ROOT_GENERAL'
            elif info and info.get('permission') == 'Developer':
                kind = 'DEVELOPER'
            else:
                kind = 'UID'

            def is_login(line):
                if kind == 'ADMIN_GENERAL':
                    if '通用密码' not in line:
                        return False
                    if '[TADS Administrator] 验证通过' in line and '管理员 (UID:' in line:
                        return True
                    if 'TADS Administrator 登录成功' in line:
                        return True
                    return False

                if kind == 'ROOT_GENERAL':
                    if '通用密码' not in line:
                        return False
                    if '[TADS Root] 验证通过' in line and 'ROOT (UID:' in line:
                        return True
                    if 'TADS Root 登录成功' in line:
                        return True
                    return False

                if kind == 'DEVELOPER':
                    name = uid_str
                    if '[TADS Developer] 验证通过' in line and '开发者 (用户名:' in line:
                        m = re.search(r'开发者 \(用户名:\s*([^,，]+)', line)
                        if m and m.group(1).strip() == name:
                            return True
                    if 'TADS Developer 登录成功' in line:
                        m = re.search(r'用户名:\s*([^,，）)]+)', line)
                        if m and m.group(1).strip() == name:
                            return True
                    return False

                if kind == 'UID':
                    u = uid_str.upper()
                    if '[TADS Administrator] 验证通过' in line and '管理员 (UID:' in line:
                        m = re.search(r'管理员 \(UID:\s*([0-9A-Fa-f]+)', line)
                        if m and m.group(1).upper() == u:
                            return True
                    if '[TADS Root] 验证通过' in line and 'ROOT (UID:' in line:
                        m = re.search(r'ROOT \(UID:\s*([0-9A-Fa-f]+)', line)
                        if m and m.group(1).upper() == u:
                            return True
                    if 'TADS Administrator 登录成功' in line or 'TADS Root 登录成功' in line:
                        m = re.search(r'UID=([0-9A-Fa-f]+)', line)
                        if m and m.group(1).upper() == u:
                            return True
                    return False

                return False

            return self._scan_log_since_cutoff(log_file, cutoff, is_login)
        except Exception as e:
            self.log_error(f"读取日志使用次数失败: {e}")
            return -1

    def _scan_log_since_cutoff(self, log_file, cutoff, line_matcher):
        """从文件尾向前分块扫描日志：
        - 每块 64KB
        - 块内时间戳均早于 cutoff → 停止（更早的块也不会更新）
        - 逐行判断时间戳：>= cutoff 才交给 line_matcher
        """
        count = 0
        chunk_size = 64 * 1024
        time_pattern = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]')
        try:
            with open(log_file, 'rb') as f:
                f.seek(0, 2)
                pos = f.tell()
                leftover = b''
                while pos > 0:
                    read_size = min(chunk_size, pos)
                    pos -= read_size
                    f.seek(pos)
                    data = f.read(read_size) + leftover

                    parts = data.split(b'\n')
                    if pos > 0:
                        leftover = parts[0]
                        complete = parts[1:]
                    else:
                        leftover = b''
                        complete = parts

                    has_fresh = False
                    for line_bytes in complete:
                        line = line_bytes.decode('utf-8', errors='ignore').strip()
                        if not line:
                            continue
                        m = time_pattern.search(line)
                        if not m:
                            continue
                        try:
                            ts = datetime.datetime.strptime(
                                m.group(1), '%Y-%m-%d %H:%M:%S')
                        except Exception:
                            continue
                        if ts < cutoff:
                            continue
                        has_fresh = True
                        if line_matcher(line):
                            count += 1

                    if not has_fresh and pos > 0:
                        break
            return count
        except Exception as e:
            self.log_error(f"扫描日志失败: {e}")
            return count

# ================== 主窗口 ==================
class MainWindow(tk.Tk):
    def resource_path(self, relative_path):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    def __init__(self):
        super().__init__()
        self.withdraw()

        # 全局状态（供后续 mainloop 阶段的验证流程使用）
        self.emergency_mode = False
        self.manager = None
        self._selected_uid = None
        self.pn532 = None
        self._reading = False
        self._display_state = {}
        self._hide_timers = {}

        # 记录启动日志
        try:
            _init_log_paths()
            log_action("系统启动", "物理密钥与密码管理系统已启动")
        except Exception:
            pass

        # 统一绑定关闭事件
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        # 延后执行验证（让 mainloop 先跑起来）
        self.after(10, self._start_auth_flow)

    def _on_window_close(self):
        """统一处理窗口关闭：记日志 -> 退出"""
        try:
            log_action("系统关闭", "物理密钥与密码管理系统退出")
        except Exception:
            pass
        self.destroy()

    def _get_saved_com_port(self):
        """从 config.json 读取上次选择的 COM 口"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                return (cfg.get('com_port') or '').strip()
        except Exception:
            pass
        return ''

    def _save_com_port(self, port):
        """把选择结果写入 config.json，并同步到 manager 内存"""
        if not port:
            return
        try:
            cfg = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            cfg['com_port'] = port
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            if getattr(self, 'manager', None) is not None:
                try:
                    self.manager.config['com_port'] = port
                except Exception:
                    pass
        except Exception as e:
            log_error(f"保存 com_port 失败: {e}")

    def _show_port_selection_dialog(self, ports):
        """串口选择对话框，返回选择的端口名或 None"""
        result = {'port': None}

        top = tk.Toplevel(self)
        top.title("选择 PN532 串口")
        top.geometry("560x532")
        top.transient(self)
        top.grab_set()
        top.resizable(True, True)

        tk.Label(
            top,
            text=f"检测到 {len(ports)} 个串口设备，请选择 PN532 所在的端口：",
            font=('微软雅黑', 10), bg='#f0f0f0', anchor='w'
        ).pack(pady=10, padx=10, fill=tk.X)

        list_frame = tk.Frame(top, bg='#f0f0f0')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('串口', '名称', '描述')
        tree = ttk.Treeview(list_frame, columns=columns, show='headings',
                            selectmode='browse', height=9)
        for col in columns:
            tree.heading(col, text=col)
        tree.column('串口', width=90, anchor='center')
        tree.column('名称', width=180, anchor='w')
        tree.column('描述', width=240, anchor='w')

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        first_item = None
        for p in ports:
            item = tree.insert(
                '', 'end',
                values=(p.device, getattr(p, 'name', '') or '',
                        getattr(p, 'description', '') or ''))
            if first_item is None:
                first_item = item
        if first_item:
            tree.selection_set(first_item)
            tree.focus(first_item)

        def on_confirm(event=None):
            selection = tree.selection()
            if not selection:
                messagebox.showwarning("提示", "请先选择一个串口", parent=top)
                return
            values = tree.item(selection[0], 'values')
            if values and values[0]:
                result['port'] = values[0]
            top.destroy()

        def on_cancel():
            result['port'] = None
            top.destroy()

        tree.bind('<Double-1>', on_confirm)

        btn_frame = tk.Frame(top, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=10)
        tk.Button(btn_frame, text="确认连接", command=on_confirm, width=12,
                  font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=20)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=12,
                  font=('微软雅黑', 10)).pack(side=tk.RIGHT, padx=20)

        top.protocol("WM_DELETE_WINDOW", on_cancel)
        self.wait_window(top)
        return result['port']

    def _connect_pn532_with_selection(self, silent_on_success=False, silent_if_no_port=False):
        """
        统一的 PN532 连接流程：
          - 0 个串口：silent_if_no_port=True 静默失败，否则报错
          - 1 个串口：直接使用
          - 多个串口：弹框让用户选择
        - 选择后把 com_port 写回 config.json
        """
        try:
            ports = list(serial.tools.list_ports.comports())
        except Exception as e:
            log_error(f"枚举串口失败: {e}")
            if not silent_if_no_port:
                messagebox.showerror("错误", f"枚举串口失败: {e}", parent=self)
            return False

        if not ports:
            log_error("PN532 连接：系统未检测到任何串口设备")
            if not silent_if_no_port:
                messagebox.showerror(
                    "错误", "系统未检测到任何串口设备，请检查 PN532 是否已连接", parent=self)
            return False

        if len(ports) == 1:
            selected_port = ports[0].device
            log_action("PN532 连接", f"仅检测到 1 个串口 {selected_port}，直接使用")
        else:
            selected_port = self._show_port_selection_dialog(ports)
            if selected_port is None:
                log_action("PN532 连接", "用户取消端口选择")
                return False
            log_action("PN532 连接", f"用户手动选择串口 {selected_port}")

        self._save_com_port(selected_port)

        try:
            if self.pn532 is None:
                self.pn532 = PN532Reader(port=selected_port, auto=False)
            else:
                self.pn532.port = selected_port
                self.pn532._init_reader()
        except Exception as e:
            log_error(f"PN532 连接失败 {selected_port}: {e}")
            if not silent_if_no_port:
                messagebox.showerror("错误", f"PN532 连接失败: {e}", parent=self)
            return False

        if self.pn532.is_connected():
            log_action("PN532 连接", f"已连接 {selected_port}")
            if not silent_on_success:
                messagebox.showinfo("成功", f"PN532 已连接（{selected_port}）", parent=self)
            return True
        else:
            log_error(f"PN532 端口 {selected_port} 打开失败或初始化失败")
            if not silent_if_no_port:
                messagebox.showerror(
                    "错误", f"端口 {selected_port} 连接失败，请检查设备", parent=self)
            return False

    def _ensure_pn532_connected(self):
        """
        确保 PN532 已连接：
        - 已连接：直接返回 True
        - 未连接：用上次保存的 com_port 直接连接
        - 保存端口不可用/不存在：提示用户点击【连接PN532】重新选择
        """
        try:
            if (self.pn532 and self.pn532.is_connected()
                    and self.pn532.ser and self.pn532.ser.is_open):
                return True
        except Exception:
            pass

        saved_port = self._get_saved_com_port()
        if not saved_port:
            messagebox.showerror(
                "错误",
                "尚未选择 PN532 串口。\n"
                "请先点击【连接PN532】选择端口后再继续。",
                parent=self)
            return False

        try:
            current_ports = {p.device.upper() for p in serial.tools.list_ports.comports()}
            if saved_port.upper() not in current_ports:
                messagebox.showerror(
                    "错误",
                    f"上次选择的串口 {saved_port} 当前不存在。\n"
                    f"请点击【连接PN532】重新选择端口后再继续。",
                    parent=self)
                return False
        except Exception as e:
            log_error(f"检查端口列表失败: {e}")

        try:
            if self.pn532 is None:
                self.pn532 = PN532Reader(port=saved_port, auto=False)
            else:
                self.pn532.port = saved_port
                self.pn532._init_reader()
        except Exception as e:
            log_error(f"使用上次端口 {saved_port} 连接 PN532 失败: {e}")
            messagebox.showerror(
                "错误",
                f"使用上次选择的串口 {saved_port} 连接 PN532 失败。\n"
                f"请点击【连接PN532】重新选择端口。",
                parent=self)
            return False

        if not self.pn532.is_connected():
            log_error(f"PN532 端口 {saved_port} 打开失败或初始化失败")
            messagebox.showerror(
                "错误",
                f"串口 {saved_port} 连接 PN532 失败。\n"
                f"请点击【连接PN532】重新选择端口。",
                parent=self)
            return False

        log_action("PN532 连接", f"复用上次选择的串口 {saved_port}")
        return True

    def _prepare_reader_for_auth(self):
        """
        为认证准备读卡器：
        - 已连接：True
        - 复用上次端口成功：True
        - 需要选择端口：弹出选择框
        """
        try:
            if (self.pn532 and self.pn532.is_connected()
                    and self.pn532.ser and self.pn532.ser.is_open):
                return True
        except Exception:
            pass

        saved = self._get_saved_com_port()
        if saved:
            try:
                current_ports = {p.device.upper() for p in serial.tools.list_ports.comports()}
                if saved.upper() in current_ports:
                    if self.pn532 is None:
                        self.pn532 = PN532Reader(port=saved, auto=False)
                    else:
                        self.pn532.port = saved
                        self.pn532._init_reader()
                    if self.pn532.is_connected():
                        log_action("PN532 连接", f"认证时复用上次端口 {saved}")
                        return True
            except Exception as e:
                log_error(f"复用端口 {saved} 失败: {e}")

        return self._connect_pn532_with_selection(
            silent_on_success=True, silent_if_no_port=False)

    def _init_reader(self):
        """主界面初始化时仅检测并展示当前读卡器状态，不主动重连。
        启动验证阶段已经完成连接，若未连接则让用户手动点【连接PN532】。"""
        try:
            if (self.pn532 and self.pn532.is_connected()
                    and self.pn532.ser and self.pn532.ser.is_open):
                port = (self.pn532.port or '').strip()
                self.status_label.config(text=f"读卡器已连接（{port}）")
                return
        except Exception:
            pass
        self.status_label.config(text="读卡器未连接，请点击【连接PN532】")

    def _connect_pn532(self):
        """标题栏【连接PN532】按钮：走统一的选择逻辑"""
        ok = self._connect_pn532_with_selection(
            silent_on_success=False, silent_if_no_port=False)
        try:
            if ok and self.pn532 and self.pn532.is_connected():
                port = (self.pn532.port or '').strip()
                self.status_label.config(text=f"读卡器已连接（{port}）")
            else:
                self.status_label.config(text="读卡器未连接")
        except Exception:
            pass

    def _ensure_reader(self):
        """兼容旧调用：委托给 _ensure_pn532_connected。"""
        return self._ensure_pn532_connected()

    def _read_card_and_search(self):
        """读卡 → 自动填入 UID 查询框 → 自动触发查询"""
        if self._reading:
            self.label_search_result.config(text="⚠ 正在读卡，请稍候...", fg='#e67e22')
            return

        if not self._ensure_reader():
            self.label_search_result.config(text="✗ 读卡器未就绪", fg='red')
            return

        self._reading = True
        self.label_search_result.config(
            text="⏳ 请刷卡（15 秒超时）...", fg='#2980b9')
        try:
            self.btn_search_read_card.config(state='disabled')
        except Exception:
            pass

        def do_read():
            uid = None
            try:
                deadline = time.time() + 15
                while time.time() < deadline:
                    u1, _ = self.pn532.read_ntag_uid(retry=1)
                    if not u1:
                        u2, _ = self.pn532.read_m1_uid()
                        u1 = u2
                    if u1:
                        uid = u1.upper()
                        break
                    time.sleep(0.2)
            except Exception as e:
                log_error(f"读卡查询-读取异常: {e}")
            finally:
                self._reading = False
                self.after(0, lambda u=uid: self._on_read_card_search_done(u))

        threading.Thread(target=do_read, daemon=True).start()

    def _on_read_card_search_done(self, uid):
        """读卡查询回调：恢复按钮 → 填入 UID → 触发查询"""
        try:
            if self.btn_search_read_card.winfo_exists():
                self.btn_search_read_card.config(state='normal')
        except Exception:
            pass

        if not uid:
            self.label_search_result.config(
                text="✗ 读卡超时或未检测到卡片", fg='red')
            return

        self.entry_search_uid.delete(0, tk.END)
        self.entry_search_uid.insert(0, uid)
        self._search_and_select_uid()

    # ================== 启动验证流程 ==================
    def _start_auth_flow(self):
        try:
            _init_log_paths()
        except Exception:
            pass

        try:
            root_hash = self._get_root_password_hash()
        except Exception as e:
            messagebox.showerror("错误", f"读取配置失败: {e}", parent=self)
            self.after(100, self._on_window_close)
            return

        if not root_hash:
            messagebox.showerror(
                "环境未初始化",
                "未找到 root_password_hash。\n\n"
                "请先运行 TADS 辅助部署程序 完成初始化配置，\n"
                "然后再启动本程序。",
                parent=self)
            log_error("启动失败: 未找到 root_password_hash")
            self.after(100, self._on_window_close)
            return

        # ==================== 主窗口变身：验证界面 ====================
        self.deiconify()
        self.title(" TADS ROOT 身份验证 · QS Studio      v26.9.9")
        # ★ 修改：宽度 620 → 700，为新增按钮腾空间
        self.geometry("700x520")
        self.minsize(700, 520)
        self.maxsize(700, 520)
        self.resizable(False, False)
        self.configure(bg='#f0f0f0')
        try:
            self.iconbitmap(self.resource_path('ic_directions_train_128_28252.ico'))
        except Exception:
            pass

        if not getattr(self, '_toplevel_patched', False):
            original_toplevel_init = tk.Toplevel.__init__

            def get_icon_path():
                if hasattr(sys, '_MEIPASS'):
                    return os.path.join(sys._MEIPASS, 'ic_directions_train_128_28252.ico')
                return os.path.join(os.path.abspath("."), 'ic_directions_train_128_28252.ico')

            def new_toplevel_init(self_t, master=None, cnf={}, **kw):
                original_toplevel_init(self_t, master, cnf, **kw)
                try:
                    icon_path = get_icon_path()
                    if os.path.exists(icon_path):
                        self_t.iconbitmap(icon_path)
                except Exception:
                    pass
            tk.Toplevel.__init__ = new_toplevel_init
            self._toplevel_patched = True

        for w in self.winfo_children():
            w.destroy()

        header = tk.Frame(self, bg='#2c3e50', height=75)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="TADS ROOT 身份验证",
                 font=('微软雅黑', 17, 'bold'),
                 bg='#2c3e50', fg='white').pack(pady=20)
        tk.Label(header, text="物理密钥与密码管理系统",
                 font=('微软雅黑', 9),
                 bg='#2c3e50', fg='#b0c4de').pack(pady=(0, 10))

        body = tk.Frame(self, bg='#f0f0f0', padx=30, pady=20)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="① 输入 ROOT 密码",
                 font=('微软雅黑', 11, 'bold'),
                 bg='#f0f0f0', anchor='w').pack(fill=tk.X, pady=(0, 5))

        pwd_row = tk.Frame(body, bg='#f0f0f0')
        pwd_row.pack(fill=tk.X, pady=(0, 5))
        pwd_var = tk.StringVar()
        pwd_entry = tk.Entry(pwd_row, textvariable=pwd_var, show='*',
                             font=('微软雅黑', 12), width=32)
        pwd_entry.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        pwd_entry.focus_set()

        pwd_visible = {'v': False}

        def toggle_pwd():
            pwd_visible['v'] = not pwd_visible['v']
            pwd_entry.config(show='' if pwd_visible['v'] else '*')

        tk.Button(pwd_row, text="👁", command=toggle_pwd,
                  bg='#f0f0f0', fg='#333',
                  font=('微软雅黑', 10), width=3).pack(side=tk.LEFT)

        tk.Label(body, text="② 选择验证方式",
                 font=('微软雅黑', 11, 'bold'),
                 bg='#f0f0f0', anchor='w').pack(fill=tk.X, pady=(15, 5))

        mode_var = tk.StringVar(value='card')

        tk.Radiobutton(body,
                       text="刷卡验证（完整功能，需要 ROOT 物理密钥）",
                       variable=mode_var, value='card',
                       font=('微软雅黑', 10), bg='#f0f0f0',
                       anchor='w').pack(fill=tk.X, pady=2)
        tk.Radiobutton(body,
                       text="应急挂失模式（仅可禁用密钥，跳过刷卡）",
                       variable=mode_var, value='emergency',
                       font=('微软雅黑', 10), bg='#f0f0f0',
                       anchor='w').pack(fill=tk.X, pady=2)

        status_frame = tk.Frame(body, bg='#ecf0f1',
                                relief=tk.SUNKEN, bd=1, height=70)
        status_frame.pack(fill=tk.X, pady=(15, 15))
        status_frame.pack_propagate(False)
        status_label = tk.Label(
            status_frame,
            text="请先输入 ROOT 密码，然后选择验证方式。",
            font=('微软雅黑', 10), bg='#ecf0f1', fg='#2c3e50',
            anchor='w', justify='left', wraplength=540)
        status_label.pack(fill=tk.BOTH, padx=10, pady=8)

        btn_row = tk.Frame(body, bg='#f0f0f0')
        btn_row.pack(fill=tk.X, pady=(5, 0))

        # ★ 新增：连接PN532 按钮
        pn532_btn = tk.Button(btn_row, text="连接PN532",
                              bg='#2980b9', fg='white',
                              font=('微软雅黑', 11), width=14)
        pn532_btn.pack(side=tk.LEFT, padx=(0, 10))

        ok_btn = tk.Button(btn_row, text="确认验证",
                           bg='#27ae60', fg='white',
                           font=('微软雅黑', 11, 'bold'), width=16)
        ok_btn.pack(side=tk.LEFT, padx=(0, 10))

        cancel_btn = tk.Button(btn_row, text="退出程序",
                               bg='#c0392b', fg='white',
                               font=('微软雅黑', 11), width=16)
        cancel_btn.pack(side=tk.LEFT)

        busy = {'v': False}

        def set_status(text, color='#2c3e50'):
            try:
                if status_label.winfo_exists():
                    status_label.config(text=text, fg=color)
            except Exception:
                pass

        def on_cancel():
            if busy['v']:
                return
            self._on_window_close()

        cancel_btn.config(command=on_cancel)

        def on_pn532_btn():
            self._connect_pn532_with_selection(
                silent_on_success=False, silent_if_no_port=False)
            try:
                self.update_idletasks()
            except Exception:
                pass

        pn532_btn.config(command=on_pn532_btn)

        def finish_success(mode, msg):
            busy['v'] = False

            try:
                self.manager = KeyManager()
            except Exception as e:
                log_error(f"KeyManager 初始化失败: {e}")
                messagebox.showerror("错误", f"初始化失败: {e}", parent=self)
                self.after(100, self._on_window_close)
                return

            if mode == 'emergency':
                self.emergency_mode = True
                self.manager.log_action(
                    "ROOT 验证通过",
                    "应急挂失模式（仅密码验证，未刷卡）")
            else:
                self.emergency_mode = False
                self.manager.log_action(
                    "ROOT 验证通过",
                    f"密码 + 物理密钥（{msg}）")

            for w in self.winfo_children():
                w.destroy()

            self.title(" TADS 物理密钥及密码管理系统 · QS Studio      v26.9.9")
            self.minsize(1400, 740)
            self.maxsize(16777215, 16777215)
            self.resizable(True, True)
            self.geometry("1700x900")

            self._build_main_ui()

        def finish_fail_card(msg):
            busy['v'] = False
            log_action("验证失败", f"ROOT 读卡失败: {msg}")
            set_status(
                f"❌ {msg}\n请重新刷卡，或切换为【应急挂失模式】后再次点击【确认验证】。",
                '#c0392b')
            try:
                ok_btn.config(state='normal')
                cancel_btn.config(state='normal')
                pwd_entry.config(state='normal')
                pwd_entry.focus_set()
            except Exception:
                pass

        def do_card_verify():
            try:
                deadline = time.time() + 15
                uid = None
                while time.time() < deadline:
                    u1, _ = self.pn532.read_ntag_uid(retry=1)
                    if not u1:
                        u2, _ = self.pn532.read_m1_uid()
                        u1 = u2
                    if u1:
                        uid = u1.upper()
                        break
                    time.sleep(0.2)

                if not uid:
                    self.after(0, lambda: finish_fail_card("读卡超时，未检测到卡片"))
                    return

                try:
                    km = KeyManager()
                except Exception as e:
                    err = str(e)
                    self.after(0, lambda: finish_fail_card(f"加载密钥数据失败: {err}"))
                    return

                key_data = km.get_key_by_uid(uid)
                if not key_data:
                    self.after(0, lambda: finish_fail_card(f"UID {uid} 未注册"))
                    return
                if not key_data.get('enabled', False):
                    self.after(0, lambda: finish_fail_card(f"UID {uid} 已被禁用"))
                    return
                if key_data.get('permission') not in ('ROOT', 'Both'):
                    self.after(0, lambda: finish_fail_card(f"UID {uid} 不是 ROOT/Both 权限"))
                    return

                self.after(0, lambda: finish_success('card', f"刷卡通过: UID {uid}"))
            except Exception as e:
                err = str(e)
                self.after(0, lambda: finish_fail_card(f"读卡异常: {err}"))

        def on_submit():
            if busy['v']:
                return

            pwd = pwd_var.get()
            if not pwd:
                set_status("❌ 请输入 ROOT 密码", '#c0392b')
                pwd_entry.focus_set()
                return

            if not verify_password(pwd, root_hash):
                set_status("❌ ROOT 密码错误，请重试", '#c0392b')
                log_action("验证失败", "ROOT 密码输入错误")
                return

            mode = mode_var.get()
            if mode == 'emergency':
                busy['v'] = True
                set_status("✅ 密码正确，正在进入应急挂失模式...", '#27ae60')
                log_action("ROOT 验证", "应急挂失流程（仅密码）")
                self.after(300, lambda: finish_success('emergency', '进入应急挂失模式'))
                return

            busy['v'] = True
            try:
                ok_btn.config(state='disabled')
                cancel_btn.config(state='disabled')
                pwd_entry.config(state='disabled')
            except Exception:
                pass

            set_status("⏳ 正在准备读卡器...", '#2980b9')
            self.update_idletasks()

            if not self._prepare_reader_for_auth():
                busy['v'] = False
                set_status(
                    "❌ 读卡器未就绪，请检查设备，或切换为【应急挂失模式】后重试。",
                    '#c0392b')
                try:
                    ok_btn.config(state='normal')
                    cancel_btn.config(state='normal')
                    pwd_entry.config(state='normal')
                    pwd_entry.focus_set()
                except Exception:
                    pass
                return

            set_status("⏳ 请将 ROOT 物理密钥放到读卡器上（15 秒超时）...", '#2980b9')
            threading.Thread(target=do_card_verify, daemon=True).start()

        ok_btn.config(command=on_submit)
        pwd_entry.bind('<Return>', lambda e: on_submit())

    def _verify_root_card_ui(self):
        """已废弃：综合验证已内联在 _start_auth_flow 中。保留空实现以兼容。"""
        return False

    def _get_root_password_hash(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f).get('root_password_hash', '')
        except Exception:
            pass
        return ''

    # ================== 主界面构建 ==================
    def _build_main_ui(self):
        self.deiconify()
        self.title(" TADS 物理密钥及密码管理系统 · QS Studio      v26.9.9")
        self.geometry("1700x760")
        self.minsize(1400, 740)
        self.configure(bg='#f0f0f0')
        try:
            self.iconbitmap(self.resource_path('ic_directions_train_128_28252.ico'))
        except Exception:
            pass

        # Toplevel 图标继承
        original_toplevel_init = tk.Toplevel.__init__

        def get_icon_path():
            if hasattr(sys, '_MEIPASS'):
                return os.path.join(sys._MEIPASS, 'ic_directions_train_128_28252.ico')
            return os.path.join(os.path.abspath("."), 'ic_directions_train_128_28252.ico')

        def new_toplevel_init(self_t, master=None, cnf={}, **kw):
            original_toplevel_init(self_t, master, cnf, **kw)
            try:
                icon_path = get_icon_path()
                if os.path.exists(icon_path):
                    self_t.iconbitmap(icon_path)
            except Exception:
                pass
        tk.Toplevel.__init__ = new_toplevel_init

        self._create_widgets()
        self._refresh_list()
        self._init_reader()

        if self.emergency_mode:
            self._apply_emergency_mode()
            self.manager.log_action("进入应急模式", "已完成 UI 应用")

    def _init_reader(self):
        # 验证阶段已建立连接则直接复用
        if self.pn532 is not None:
            try:
                if self.pn532.check_connection():
                    self.status_label.config(text="读卡器已连接")
                else:
                    self.status_label.config(text="读卡器未连接")
            except Exception:
                self.status_label.config(text="读卡器连接异常")
            return

        def do_connect():
            try:
                self.pn532 = PN532Reader(auto=True)
                if self.pn532.check_connection():
                    self.after(0, lambda: self.status_label.config(text="读卡器已连接"))
                else:
                    self.after(0, lambda: self.status_label.config(text="读卡器未连接"))
            except Exception as e:
                self.pn532 = None
                log_error(f"读卡器初始化失败: {e}")
                self.after(0, lambda: self.status_label.config(text="读卡器初始化失败"))
        threading.Thread(target=do_connect, daemon=True).start()

    def _create_widgets(self):
        header = tk.Frame(self, bg='#2c3e50', height=55)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="TADS 物理密钥及密码管理系统",
                 font=('微软雅黑', 16, 'bold'),
                 bg='#2c3e50', fg='white').pack(side=tk.LEFT, padx=20, pady=12)
        tk.Label(header, text=f"配置目录: {APP_CONFIG_DIR}",
                 font=('微软雅黑', 9),
                 bg='#2c3e50', fg='#b0c4de').pack(side=tk.RIGHT, padx=20, pady=12)

        main_frame = tk.Frame(self, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        list_frame = tk.Frame(main_frame, bg='#f0f0f0')
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        title_frame = tk.Frame(list_frame, bg='#f0f0f0')
        title_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(title_frame, text="已注册的物理密钥及对应密码",
                 font=('微软雅黑', 12, 'bold'),
                 bg='#f0f0f0').pack(side=tk.LEFT)

        btn_title_frame = tk.Frame(title_frame, bg='#f0f0f0')
        btn_title_frame.pack(side=tk.RIGHT)
        tk.Button(btn_title_frame, text="刷新", command=self._refresh_list,
                  bg='#2c3e50', fg='white', font=('微软雅黑', 9),
                  width=6).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(btn_title_frame, text="连接PN532", command=self._connect_pn532,
                  bg='#2c3e50', fg='white', font=('微软雅黑', 9),
                  width=10).pack(side=tk.LEFT)

        tree_frame = tk.Frame(list_frame, bg='#f0f0f0')
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('序号', 'UID', '卡类型', '权限等级', '名称', '对应密码', '允许使用')
        self.tree = ttk.Treeview(tree_frame, columns=columns,
                                 show='headings', selectmode='browse')
        for c in columns:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor='center',
                             width=50 if c == '序号' else
                                   (70 if c in ('卡类型', '允许使用') else
                                    (130 if c == '权限等级' else 120)))
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<<TreeviewSelect>>', self._on_select)
        self.tree.bind("<Button-3>", self._show_context_menu)

        right_frame = tk.Frame(main_frame, bg='#f0f0f0', width=420)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_frame.pack_propagate(False)

        tk.Label(right_frame, text="操作", font=('微软雅黑', 12, 'bold'),
                 bg='#f0f0f0').pack(anchor='w', pady=(0, 10))

        self.add_frame = tk.LabelFrame(right_frame, text="新增密钥及对应密码",
                                       bg='#f0f0f0', font=('微软雅黑', 10))
        self.add_frame.pack(fill=tk.X, pady=5)

        uid_row = tk.Frame(self.add_frame, bg='#f0f0f0')
        uid_row.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky='ew')
        tk.Label(uid_row, text="UID:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).pack(side=tk.LEFT)
        self.entry_uid = tk.Entry(uid_row, font=('微软雅黑', 10), width=20)
        self.entry_uid.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(uid_row, text="读卡", command=self._read_card,
                  bg='#2c3e50', fg='white', font=('微软雅黑', 9),
                  width=6).pack(side=tk.LEFT, padx=5)

        tk.Label(self.add_frame, text="权限等级:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.combo_permission = ttk.Combobox(
            self.add_frame,
            values=['Administrator', 'ROOT', 'Both', 'Developer'],
            state='readonly', width=25)
        self.combo_permission.set('Administrator')
        self.combo_permission.grid(row=1, column=1, padx=5, pady=5, sticky='ew')

        tk.Label(self.add_frame, text="名称:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.entry_name = tk.Entry(self.add_frame, font=('微软雅黑', 10), width=25)
        self.entry_name.grid(row=2, column=1, padx=5, pady=5, sticky='ew')

        pwd_row = tk.Frame(self.add_frame, bg='#f0f0f0')
        pwd_row.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky='ew')
        tk.Label(pwd_row, text="对应密码:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).pack(side=tk.LEFT)
        self.entry_add_pwd = tk.Entry(pwd_row, show='*',
                                      font=('微软雅黑', 10), width=20)
        self.entry_add_pwd.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.add_pwd_visible = False
        self.btn_show_add_pwd = tk.Button(pwd_row, text="👁",
                                          command=self._toggle_add_pwd_visibility,
                                          bg='#f0f0f0', fg='#333',
                                          font=('微软雅黑', 9), width=3)
        self.btn_show_add_pwd.pack(side=tk.LEFT, padx=2)

        self.btn_add = tk.Button(self.add_frame, text="添加密钥",
                                 command=self._add_key,
                                 bg='#2c3e50', fg='white',
                                 font=('微软雅黑', 10), width=20)
        self.btn_add.grid(row=4, column=0, columnspan=2, pady=8)

        self.select_frame = tk.LabelFrame(right_frame, text="选中密钥操作",
                                          bg='#f0f0f0', font=('微软雅黑', 10))
        self.select_frame.pack(fill=tk.X, pady=10)

        self.selected_label = tk.Label(self.select_frame, text="未选中任何密钥",
                                       bg='#f0f0f0',
                                       font=('微软雅黑', 9), fg='#666')
        self.selected_label.pack(anchor='w', padx=10, pady=5)

        name_frame = tk.Frame(self.select_frame, bg='#f0f0f0')
        name_frame.pack(fill=tk.X, padx=10, pady=3)
        tk.Label(name_frame, text="名称:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).pack(side=tk.LEFT)
        self.entry_edit_name = tk.Entry(name_frame,
                                        font=('微软雅黑', 10), width=25)
        self.entry_edit_name.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        perms_frame = tk.Frame(self.select_frame, bg='#f0f0f0')
        perms_frame.pack(fill=tk.X, padx=10, pady=3)
        tk.Label(perms_frame, text="权限:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).pack(side=tk.LEFT)
        self.combo_edit_permission = ttk.Combobox(
            perms_frame,
            values=['Administrator', 'ROOT', 'Both', 'Developer'],
            state='readonly', width=25)
        self.combo_edit_permission.set('Administrator')
        self.combo_edit_permission.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        uid_edit_frame = tk.Frame(self.select_frame, bg='#f0f0f0')
        uid_edit_frame.pack(fill=tk.X, padx=10, pady=3)
        tk.Label(uid_edit_frame, text="新UID:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).pack(side=tk.LEFT)
        self.entry_edit_uid = tk.Entry(uid_edit_frame,
                                       font=('微软雅黑', 10), width=20)
        self.entry_edit_uid.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.btn_read_uid = tk.Button(uid_edit_frame, text="读卡",
                                      command=self._read_card_for_edit_uid,
                                      bg='#2c3e50', fg='white',
                                      font=('微软雅黑', 9), width=6)
        self.btn_read_uid.pack(side=tk.RIGHT, padx=2)

        edit_pwd_frame = tk.Frame(self.select_frame, bg='#f0f0f0')
        edit_pwd_frame.pack(fill=tk.X, padx=10, pady=3)
        tk.Label(edit_pwd_frame, text="新密码:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).pack(side=tk.LEFT)
        self.entry_edit_pwd = tk.Entry(edit_pwd_frame, show='*',
                                       font=('微软雅黑', 10), width=20)
        self.entry_edit_pwd.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        self.edit_pwd_visible = False
        self.btn_show_edit_pwd = tk.Button(edit_pwd_frame, text="👁",
                                           command=self._toggle_edit_pwd_visibility,
                                           bg='#f0f0f0', fg='#333',
                                           font=('微软雅黑', 9), width=3)
        self.btn_show_edit_pwd.pack(side=tk.RIGHT, padx=2)

        allowed_frame = tk.Frame(self.select_frame, bg='#f0f0f0')
        allowed_frame.pack(fill=tk.X, padx=10, pady=3)
        self.allowed_var = tk.BooleanVar(value=True)
        self.chk_allowed = tk.Checkbutton(allowed_frame, text="允许使用",
                                          variable=self.allowed_var,
                                          bg='#f0f0f0',
                                          font=('微软雅黑', 10))
        self.chk_allowed.pack(side=tk.LEFT)
        self.chk_allowed_widget = self.chk_allowed

        self.usage_label = tk.Label(allowed_frame, text="最近4小时使用: -- 次",
                                    bg='#f0f0f0',
                                    font=('微软雅黑', 9), fg='#666')
        self.usage_label.pack(side=tk.RIGHT, padx=5)

        btn_row = tk.Frame(self.select_frame, bg='#f0f0f0')
        btn_row.pack(fill=tk.X, padx=10, pady=8)
        self.btn_save_all = tk.Button(btn_row, text="保存所有修改",
                                      command=self._save_all_edits,
                                      bg='#2c3e50', fg='white',
                                      font=('微软雅黑', 10), width=16)
        self.btn_save_all.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        self.btn_delete = tk.Button(btn_row, text="删除密钥",
                                    command=self._delete_key,
                                    bg='#c0392b', fg='white',
                                    font=('微软雅黑', 10), width=16)
        self.btn_delete.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # ============== UID 查询区（含读卡查询） ==============
        search_frame = tk.LabelFrame(right_frame, text="UID 查询",
                                     bg='#f0f0f0', font=('微软雅黑', 10))
        search_frame.pack(fill=tk.X, pady=5)

        search_ui_row = tk.Frame(search_frame, bg='#f0f0f0')
        search_ui_row.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(search_ui_row, text="UID:", bg='#f0f0f0',
                 font=('微软雅黑', 9)).pack(side=tk.LEFT)
        self.entry_search_uid = tk.Entry(search_ui_row,
                                         font=('微软雅黑', 10), width=20)
        self.entry_search_uid.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        self.btn_search_read_card = tk.Button(
            search_ui_row, text="读卡查询",
            command=self._read_card_and_search,
            bg='#16a085', fg='white',
            font=('微软雅黑', 9), width=8)
        self.btn_search_read_card.pack(side=tk.RIGHT, padx=2)

        self.btn_search_uid = tk.Button(
            search_ui_row, text="查询",
            command=self._search_and_select_uid,
            bg='#2c3e50', fg='white',
            font=('微软雅黑', 9), width=6)
        self.btn_search_uid.pack(side=tk.RIGHT, padx=2)

        self.label_search_result = tk.Label(search_frame, text="",
                                            bg='#f0f0f0',
                                            font=('微软雅黑', 9), fg='red')
        self.label_search_result.pack(fill=tk.X, padx=10, pady=(0, 5))

        # ============== 底部状态栏 ==============
        self.status_frame = tk.Frame(self, bg='#d9d9d9', height=28)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_label = tk.Label(self.status_frame, text="就绪",
                                     font=('微软雅黑', 9),
                                     bg='#d9d9d9', anchor='w')
        self.status_label.pack(side=tk.LEFT, padx=10, fill=tk.X)

        self.entry_uid.bind('<Return>', lambda e: self._add_key())
        self.entry_name.bind('<Return>', lambda e: self._add_key())
        self.entry_add_pwd.bind('<Return>', lambda e: self._add_key())
        self.entry_search_uid.bind('<Return>', lambda e: self._search_and_select_uid())

    # ================== 应急挂失模式 ==================
    def _apply_emergency_mode(self):
        self.status_label.config(
            text="⚠️ 当前处于应急挂失模式：只能禁用密钥，无法新增/编辑/删除/启用。",
            fg='#c0392b')

        for w in self.add_frame.winfo_children():
            try:
                w.configure(state='disabled')
            except Exception:
                pass
            try:
                for sub in w.winfo_children():
                    try:
                        sub.configure(state='disabled')
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            self.btn_delete.configure(state='disabled')
        except Exception:
            pass

        for w in (self.entry_edit_name, self.combo_edit_permission,
                  self.entry_edit_uid, self.entry_edit_pwd,
                  self.btn_read_uid, self.btn_show_edit_pwd):
            try:
                w.configure(state='disabled')
            except Exception:
                pass

        # 保存逻辑替换为应急保存
        self._save_all_edits = self._emergency_save
        self.selected_label.config(text="应急模式：仅可禁用【启用中】的密钥")

    def _emergency_save(self):
        if not self._selected_uid:
            messagebox.showwarning("提示", "请先选中一个条目", parent=self)
            return
        key_data = self.manager.get_key_by_uid(self._selected_uid)
        if not key_data or key_data.get('is_special', False):
            messagebox.showwarning(
                "提示",
                "应急模式下只能操作普通物理密钥的【允许使用】状态。",
                parent=self)
            return

        old_enabled = self.manager.key_status.get(self._selected_uid, {}).get('enabled', True)
        if not old_enabled:
            # 已禁用 → 禁止操作，也禁止保存
            messagebox.showwarning(
                "提示", "该密钥已处于禁用状态，不能再操作。", parent=self)
            try:
                self.chk_allowed_widget.config(state='disabled')
            except Exception:
                pass
            self.allowed_var.set(False)
            return

        new_enabled = self.allowed_var.get()
        if new_enabled:
            # 启用中 → 应急模式下不允许重新启用
            messagebox.showwarning(
                "提示", "应急模式下只允许禁用密钥，不允许重新启用。", parent=self)
            self.allowed_var.set(False)
            return

        # 从启用 → 禁用（唯一允许的路径）
        self.manager.set_enabled(self._selected_uid, False)
        self.manager.log_action(
            "应急模式-禁用密钥",
            f"UID: {self._selected_uid}")
        self.status_label.config(text="✅ 密钥已禁用")
        try:
            self.chk_allowed_widget.config(state='disabled')
        except Exception:
            pass
        self._refresh_list()
        self._reselect_item(self._selected_uid)

    # ================== 小工具 ==================
    def _toggle_add_pwd_visibility(self):
        self.add_pwd_visible = not self.add_pwd_visible
        self.entry_add_pwd.config(show='' if self.add_pwd_visible else '*')

    def _toggle_edit_pwd_visibility(self):
        self.edit_pwd_visible = not self.edit_pwd_visible
        self.entry_edit_pwd.config(show='' if self.edit_pwd_visible else '*')

    def _ensure_reader(self):
        """兼容旧调用：委托给 _ensure_pn532_connected。"""
        return self._ensure_pn532_connected()

    def _read_card(self):
        if self.emergency_mode:
            messagebox.showwarning("提示", "应急模式下禁止读卡新增", parent=self)
            return
        if self._reading:
            return
        if not self._ensure_reader():
            return

        self._reading = True
        self.entry_uid.delete(0, tk.END)
        self.entry_uid.insert(0, "读取中...")
        self.status_label.config(text="正在读取卡片...")

        def do_read():
            try:
                uid = None
                uid_len = None
                for _ in range(5):
                    uid, uid_len = self.pn532.read_ntag_uid(retry=3)
                    if uid and uid_len == 7:
                        break
                    time.sleep(0.3)
                if not uid:
                    for _ in range(5):
                        uid, uid_len = self.pn532.read_m1_uid()
                        if uid and uid_len == 4:
                            break
                        time.sleep(0.2)
                if uid:
                    self.after(0, lambda: self._on_card_read(uid, uid_len))
                else:
                    self.after(0, lambda: self._on_card_read_failed())
            except Exception as e:
                err = str(e)[:30]
                log_error(f"读卡异常: {err}")
                self.after(0, lambda: self._on_card_read_error(err))
            finally:
                self._reading = False

        threading.Thread(target=do_read, daemon=True).start()

    def _read_card_for_edit_uid(self):
        if self.emergency_mode:
            messagebox.showwarning("提示", "应急模式下禁止读卡修改 UID", parent=self)
            return
        if self._reading:
            return
        if not self._ensure_reader():
            return
        if not self._selected_uid:
            messagebox.showwarning("提示", "请先选中一个密钥", parent=self)
            return

        self._reading = True
        self.entry_edit_uid.delete(0, tk.END)
        self.entry_edit_uid.insert(0, "读取中...")
        self.status_label.config(text="正在读取新卡...")

        def do_read():
            try:
                uid = None
                uid_len = None
                for _ in range(5):
                    uid, uid_len = self.pn532.read_ntag_uid(retry=3)
                    if uid and uid_len == 7:
                        break
                    time.sleep(0.3)
                if not uid:
                    for _ in range(5):
                        uid, uid_len = self.pn532.read_m1_uid()
                        if uid and uid_len == 4:
                            break
                        time.sleep(0.2)
                if uid:
                    self.after(0, lambda: self._on_card_read_for_edit(uid))
                else:
                    self.after(0, lambda: self._on_card_read_failed())
            except Exception as e:
                err = str(e)[:30]
                log_error(f"读卡异常: {err}")
                self.after(0, lambda: self._on_card_read_error(err))
            finally:
                self._reading = False

        threading.Thread(target=do_read, daemon=True).start()

    def _on_card_read(self, uid, uid_len):
        self.entry_uid.delete(0, tk.END)
        self.entry_uid.insert(0, uid)
        if uid_len == 7:
            self.combo_permission.set("ROOT")
        elif uid_len == 4:
            self.combo_permission.set("Administrator")
        self.status_label.config(text=f"读取成功: {uid}")

    def _on_card_read_for_edit(self, uid):
        self.entry_edit_uid.delete(0, tk.END)
        self.entry_edit_uid.insert(0, uid)
        self.status_label.config(text=f"读取成功: {uid}")

    def _on_card_read_failed(self):
        self.entry_uid.delete(0, tk.END)
        self.status_label.config(text="读取失败，未检测到卡片")

    def _on_card_read_error(self, error):
        self.entry_uid.delete(0, tk.END)
        self.status_label.config(text=f"读取错误: {error}")

    def _get_password_display(self, uid):
        if uid == 'ADMIN_GENERAL':
            return '******' if self.manager.config.get('admin_password_hash', '') else '未设置'
        if uid == 'ROOT_GENERAL':
            return '******' if self.manager.config.get('root_password_hash', '') else '未设置'
        if uid and uid in self.manager.key_status:
            if self.manager.key_status[uid].get('permission') == 'Developer':
                return '******' if self.manager.uid_passwords.get(uid, '') else '未设置'
        return '******' if self.manager.uid_passwords.get(uid, '') else '未设置'

    def _refresh_list(self):
        for key in list(self._hide_timers.keys()):
            if self._hide_timers[key]:
                try:
                    self.after_cancel(self._hide_timers[key])
                except Exception:
                    pass
        self._hide_timers.clear()
        self._display_state.clear()

        for item in self.tree.get_children():
            self.tree.delete(item)

        keys = self.manager.get_all_keys()
        if not keys:
            self.tree.insert('', 'end', values=('', '暂无密钥', '', '', '', '', ''))
            self.status_label.config(text="暂无密钥")
            return

        def sort_key(key):
            if key.get('is_special', False):
                if key.get('is_developer', False):
                    return -1
                if key['uid'] == 'ROOT_GENERAL':
                    return -3
                if key['uid'] == 'ADMIN_GENERAL':
                    return -2
            return {'Both': 0, 'Administrator': 1, 'ROOT': 2, 'Developer': 3}.get(
                key['permission'], 4)

        for idx, key in enumerate(sorted(keys, key=sort_key), 1):
            is_special = key.get('is_special', False)
            is_developer = key.get('is_developer', False)

            if is_special and is_developer:
                item_id = self.tree.insert('', 'end', values=(
                    str(idx), key['uid'], '--', 'Developer',
                    key['name'], self._get_password_display(key['uid']),
                    '是' if key['enabled'] else '否'))
                self.tree.item(item_id, tags=(key['uid'], True, 'developer'))
            elif is_special:
                item_id = self.tree.insert('', 'end', values=(
                    str(idx), '--', '--', key['permission'],
                    key['name'], self._get_password_display(key['uid']), '是'))
                tag_type = 'admin' if key['uid'] == 'ADMIN_GENERAL' else 'root'
                self.tree.item(item_id, tags=(key['uid'], True, tag_type))
            else:
                disp_perm = 'Administrator & ROOT' if key['permission'] == 'Both' else key['permission']
                item_id = self.tree.insert('', 'end', values=(
                    str(idx), '******', key['card_type'], disp_perm,
                    key['name'], self._get_password_display(key['uid']),
                    '是' if key['enabled'] else '否'))
                self.tree.item(item_id, tags=(key['uid'], False, 'normal'))

        self.status_label.config(text=f"共 {len(keys)} 个条目")
        self.selected_label.config(text="未选中任何条目")
        self._selected_uid = None
        self.entry_edit_name.delete(0, tk.END)
        self.entry_edit_pwd.delete(0, tk.END)
        self.entry_edit_uid.delete(0, tk.END)
        self.combo_edit_permission.set('Administrator')
        self.allowed_var.set(True)
        if hasattr(self, 'chk_allowed_widget'):
            self.chk_allowed_widget.config(state='normal')

    def _on_select(self, event):
        selection = self.tree.selection()
        if not selection:
            self.selected_label.config(text="未选中任何条目")
            self._selected_uid = None
            self.entry_edit_name.config(state='normal')
            self.combo_edit_permission.config(state='readonly')
            if hasattr(self, 'chk_allowed_widget'):
                self.chk_allowed_widget.config(state='normal')
            self.entry_edit_uid.config(state='normal')
            self.usage_label.config(text="最近4小时使用: -- 次")
            return

        item = selection[0]
        tags = self.tree.item(item, 'tags')
        if tags and len(tags) > 0:
            uid = tags[0]
        else:
            values = self.tree.item(item, 'values')
            uid = values[1] if values and len(values) > 1 else None
            if uid in ('******', '--'):
                uid = None

        if not uid:
            self.selected_label.config(text="未选中任何条目")
            self._selected_uid = None
            self.usage_label.config(text="最近4小时使用: -- 次")
            return

        key_data = self.manager.get_key_by_uid(uid)
        if not key_data:
            self.selected_label.config(text="未选中任何条目")
            self._selected_uid = None
            self.usage_label.config(text="最近4小时使用: -- 次")
            return

        is_special = key_data.get('is_special', False)
        is_developer = key_data.get('is_developer', False)

        def update_usage():
            count = self.manager._get_log_usage_count(uid, hours=4)
            display_text = ("最近4小时使用: -- 次" if count < 0
                            else f"最近4小时使用: {count} 次")
            self.after(0, lambda: self.usage_label.config(text=display_text))
        threading.Thread(target=update_usage, daemon=True).start()

        self.entry_edit_pwd.delete(0, tk.END)
        self._selected_uid = uid

        if is_special and is_developer:
            self.selected_label.config(text=f"选中: {uid} (开发者)")
            self.entry_edit_name.config(state='normal')
            self.entry_edit_name.delete(0, tk.END)
            self.entry_edit_name.insert(0, key_data['name'])
            self.combo_edit_permission.config(state='readonly')
            self.combo_edit_permission.set('Developer')
            if hasattr(self, 'chk_allowed_widget'):
                self.chk_allowed_widget.config(state='normal')
            self.allowed_var.set(key_data['enabled'])
            self.entry_edit_uid.config(state='normal')
            self.entry_edit_uid.delete(0, tk.END)
            self.entry_edit_uid.insert(0, uid)
        elif is_special:
            self.selected_label.config(text=f"选中: {key_data['name']} (通用密码)")
            self.entry_edit_name.config(state='normal')
            self.entry_edit_name.delete(0, tk.END)
            self.entry_edit_name.insert(0, key_data['name'])
            self.entry_edit_name.config(state='readonly')
            self.combo_edit_permission.config(state='disabled')
            self.combo_edit_permission.set(key_data['permission'])
            if hasattr(self, 'chk_allowed_widget'):
                self.chk_allowed_widget.config(state='disabled')
            self.allowed_var.set(True)
            self.entry_edit_uid.config(state='normal')
            self.entry_edit_uid.delete(0, tk.END)
            self.entry_edit_uid.insert(0, '--')
            self.entry_edit_uid.config(state='readonly')
        else:
            self.selected_label.config(
                text=f"选中: {uid} ({key_data['name'] or '无名称'})")
            self.entry_edit_name.config(state='normal')
            self.entry_edit_name.delete(0, tk.END)
            self.entry_edit_name.insert(0, key_data['name'])
            self.combo_edit_permission.config(state='readonly')
            self.combo_edit_permission.set(key_data['permission'])
            if hasattr(self, 'chk_allowed_widget'):
                self.chk_allowed_widget.config(state='normal')
            self.allowed_var.set(key_data['enabled'])
            self.entry_edit_uid.config(state='normal')
            self.entry_edit_uid.delete(0, tk.END)

        if self.emergency_mode:
            self._apply_emergency_mode()
            if not is_special:
                if key_data.get('enabled', True):
                    try:
                        self.chk_allowed_widget.config(state='normal')
                    except Exception:
                        pass
                    self.allowed_var.set(True)
                else:
                    try:
                        self.chk_allowed_widget.config(state='disabled')
                    except Exception:
                        pass
                    self.allowed_var.set(False)

    # ================== 右键菜单 ==================
    def _show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        col = self.tree.identify_column(event.x)
        col_idx = int(col.replace('#', '')) - 1

        self.tree.selection_set(item)
        self._on_select(None)

        tags = self.tree.item(item, 'tags')
        if not tags or len(tags) < 1:
            return
        uid = tags[0]
        entry_type = tags[2] if len(tags) > 2 else 'normal'
        is_special = entry_type in ('developer', 'admin', 'root')

        if is_special:
            if col_idx == 1 and entry_type == 'developer':
                self._show_developer_uid_context_menu(event, item, uid)
            elif col_idx == 5:
                self._show_special_pwd_context_menu(event, item)
            return
        if col_idx == 1:
            self._show_uid_context_menu(event, item, uid)
        elif col_idx == 5:
            self._show_pwd_context_menu(event, item, uid)

    def _show_developer_uid_context_menu(self, event, item, uid):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label=f"用户名: {uid}", state='disabled')
        menu.add_separator()
        menu.add_command(label="复制用户名", command=lambda: self._copy_to_clipboard(uid))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        self.manager.log_action("右键菜单-用户名列", f"用户名: {uid}")

    def _show_special_pwd_context_menu(self, event, item):
        state_key = (item, 'pwd')
        is_visible = self._display_state.get(state_key, {}).get('visible', False)

        tags = self.tree.item(item, 'tags')
        if not tags or len(tags) < 1:
            return
        uid = tags[0]
        entry_type = tags[2] if len(tags) > 2 else ''

        if entry_type == 'developer':
            has_pwd = bool(self.manager.uid_passwords.get(uid, ''))
        elif uid == 'ADMIN_GENERAL':
            has_pwd = bool(self.manager.config.get('admin_password_hash', ''))
        elif uid == 'ROOT_GENERAL':
            has_pwd = bool(self.manager.config.get('root_password_hash', ''))
        else:
            return

        menu = tk.Menu(self, tearoff=0)
        if not is_visible:
            if has_pwd:
                menu.add_command(label="显示密码",
                                 command=lambda: self._reveal_special_pwd(item))
            else:
                menu.add_command(label="未设置密码", state='disabled')
        else:
            menu.add_command(label="取消显示密码",
                             command=lambda: self._hide_special_pwd(item))
            if has_pwd:
                if entry_type == 'developer':
                    pwd = self.manager.get_password(uid)
                    menu.add_command(label="复制密码",
                                     command=lambda: self._copy_to_clipboard(pwd or "未设置"))
                else:
                    menu.add_command(label="复制密码（哈希）",
                                     command=lambda: self._copy_to_clipboard("哈希存储不可逆"))
            else:
                menu.add_command(label="未设置密码", state='disabled')
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _reveal_special_pwd(self, item):
        state_key = (item, 'pwd')
        if state_key in self._hide_timers:
            try:
                self.after_cancel(self._hide_timers[state_key])
            except Exception:
                pass
            del self._hide_timers[state_key]

        tags = self.tree.item(item, 'tags')
        if not tags or len(tags) < 1:
            return
        uid = tags[0]
        entry_type = tags[2] if len(tags) > 2 else ''

        if entry_type == 'developer':
            pwd = self.manager.get_password(uid)
            display_text = pwd if pwd else "未设置密码"
        elif uid == 'ADMIN_GENERAL':
            display_text = ("已设置密码"
                            if self.manager.config.get('admin_password_hash', '')
                            else "未设置密码")
        elif uid == 'ROOT_GENERAL':
            display_text = ("已设置密码"
                            if self.manager.config.get('root_password_hash', '')
                            else "未设置密码")
        else:
            return

        values = list(self.tree.item(item, 'values'))
        values[5] = display_text
        self.tree.item(item, values=values)
        self._display_state[state_key] = {'visible': True}
        self._hide_timers[state_key] = self.after(
            5000, lambda: self._hide_special_pwd(item))

        self.manager.log_action(
            "右键-显示特殊密码",
            f"条目: {uid}, 类型: {entry_type or 'general'}, 结果: {display_text}")

    def _hide_special_pwd(self, item):
        state_key = (item, 'pwd')
        if state_key in self._hide_timers:
            try:
                self.after_cancel(self._hide_timers[state_key])
            except Exception:
                pass
            del self._hide_timers[state_key]
        tags = self.tree.item(item, 'tags')
        if not tags or len(tags) < 1:
            return
        uid = tags[0]
        values = list(self.tree.item(item, 'values'))
        values[5] = self._get_password_display(uid)
        self.tree.item(item, values=values)
        self._display_state[state_key] = {'visible': False}

        self.manager.log_action("右键-隐藏特殊密码", f"条目: {uid}")

    def _show_uid_context_menu(self, event, item, uid):
        state_key = (item, 'uid')
        is_visible = self._display_state.get(state_key, {}).get('visible', False)
        menu = tk.Menu(self, tearoff=0)
        if not is_visible:
            menu.add_command(label="显示 UID",
                             command=lambda: self._reveal_uid(item, uid))
        else:
            menu.add_command(label="取消显示 UID",
                             command=lambda: self._hide_uid(item))
            menu.add_command(label="复制 UID",
                             command=lambda: self._copy_to_clipboard(uid))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

        self.manager.log_action(
            "右键菜单-UID列",
            f"UID: {uid}, 当前状态: {'可见' if is_visible else '隐藏'}")

    def _show_pwd_context_menu(self, event, item, uid):
        state_key = (item, 'pwd')
        is_visible = self._display_state.get(state_key, {}).get('visible', False)
        has_pwd = bool(self.manager.uid_passwords.get(uid, ''))
        menu = tk.Menu(self, tearoff=0)
        if not is_visible:
            if has_pwd:
                menu.add_command(label="显示对应密码",
                                 command=lambda: self._reveal_pwd(item, uid))
            else:
                menu.add_command(label="未设置密码", state='disabled')
        else:
            menu.add_command(label="取消显示密码",
                             command=lambda: self._hide_pwd(item))
            if has_pwd:
                pwd = self.manager.get_password(uid)
                menu.add_command(label="复制密码",
                                 command=lambda: self._copy_to_clipboard(pwd or "未设置"))
            else:
                menu.add_command(label="未设置密码", state='disabled')
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

        self.manager.log_action(
            "右键菜单-密码列",
            f"UID: {uid}, 当前状态: {'可见' if is_visible else '隐藏'}, 是否已设置: {has_pwd}")

    def _reveal_uid(self, item, uid):
        state_key = (item, 'uid')
        if state_key in self._hide_timers:
            try:
                self.after_cancel(self._hide_timers[state_key])
            except Exception:
                pass
            del self._hide_timers[state_key]
        values = list(self.tree.item(item, 'values'))
        values[1] = uid
        self.tree.item(item, values=values)
        self._display_state[state_key] = {'visible': True}
        self._hide_timers[state_key] = self.after(
            5000, lambda: self._hide_uid(item))

        self.manager.log_action("右键-显示UID", f"UID: {uid}")

    def _reveal_pwd(self, item, uid):
        state_key = (item, 'pwd')
        if state_key in self._hide_timers:
            try:
                self.after_cancel(self._hide_timers[state_key])
            except Exception:
                pass
            del self._hide_timers[state_key]
        pwd = self.manager.get_password(uid)
        values = list(self.tree.item(item, 'values'))
        values[5] = pwd if pwd else "未设置密码"
        self.tree.item(item, values=values)
        self._display_state[state_key] = {'visible': True}
        self._hide_timers[state_key] = self.after(
            5000, lambda: self._hide_pwd(item))

        self.manager.log_action(
            "右键-显示专属密码",
            f"UID: {uid}, 结果: {'成功' if pwd else '未设置'}")

    def _hide_uid(self, item):
        state_key = (item, 'uid')
        if state_key in self._hide_timers:
            try:
                self.after_cancel(self._hide_timers[state_key])
            except Exception:
                pass
            del self._hide_timers[state_key]
        values = list(self.tree.item(item, 'values'))
        values[1] = '******'
        self.tree.item(item, values=values)
        self._display_state[state_key] = {'visible': False}

        tags = self.tree.item(item, 'tags')
        uid_for_log = tags[0] if tags else ''
        self.manager.log_action("右键-隐藏UID", f"UID: {uid_for_log}")

    def _hide_pwd(self, item):
        state_key = (item, 'pwd')
        if state_key in self._hide_timers:
            try:
                self.after_cancel(self._hide_timers[state_key])
            except Exception:
                pass
            del self._hide_timers[state_key]
        tags = self.tree.item(item, 'tags')
        uid = tags[0] if tags else None
        values = list(self.tree.item(item, 'values'))
        values[5] = self._get_password_display(uid) if uid else '******'
        self.tree.item(item, values=values)
        self._display_state[state_key] = {'visible': False}

        self.manager.log_action("右键-隐藏专属密码", f"UID: {uid or '未知'}")

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        self.status_label.config(text=f"已复制: {text}")
        self.manager.log_action(
            "复制到剪贴板",
            f"内容: {text if text else '(空)'}")

    def _connect_pn532(self):
        """标题栏【连接PN532】按钮：走统一的选择逻辑"""
        ok = self._connect_pn532_with_selection(
            silent_on_success=False, silent_if_no_port=False)
        try:
            if ok and self.pn532 and self.pn532.is_connected():
                port = (self.pn532.port or '').strip()
                self.status_label.config(text=f"读卡器已连接（{port}）")
            else:
                self.status_label.config(text="读卡器未连接")
        except Exception:
            pass

    # ================== 增删改操作 ==================
    def _add_key(self):
        if self.emergency_mode:
            messagebox.showwarning("提示", "应急模式下禁止新增密钥", parent=self)
            return
        permission = self.combo_permission.get()
        name = self.entry_name.get().strip()
        password = self.entry_add_pwd.get().strip()

        # ===== 开发者：用户名 + 密码 =====
        if permission == 'Developer':
            username = self.entry_uid.get().strip() or name
            if not username:
                messagebox.showwarning("提示", "开发者必须输入用户名", parent=self)
                return
            if not re.match(r'^[\u4e00-\u9fa5A-Za-z0-9_\- ]{1,32}$', username):
                messagebox.showerror(
                    "错误",
                    "用户名只能包含中文、字母、数字、下划线、空格、短横线，长度 1～32",
                    parent=self)
                return
            if username in self.manager.key_status:
                messagebox.showerror("错误", f"用户名 {username} 已存在", parent=self)
                return
            if password and len(password) < 4:
                messagebox.showwarning("提示", "密码至少4位，已忽略", parent=self)
                password = ''
            success, msg = self.manager.add_key(
                username, permission, "Developer", username, password)
            if success:
                self.manager.log_action(
                    "新增密钥", f"用户名: {username}, 权限: Developer")
                messagebox.showinfo("成功", f"已添加开发者: {username}", parent=self)
                self.entry_uid.delete(0, tk.END)
                self.entry_name.delete(0, tk.END)
                self.entry_add_pwd.delete(0, tk.END)
                self._refresh_list()
            else:
                messagebox.showerror("错误", msg, parent=self)
            return

        # ===== 普通物理密钥 =====
        uid = self.entry_uid.get().strip().upper()
        if not uid:
            messagebox.showwarning("提示", "非开发者权限必须输入 UID 或点击读卡", parent=self)
            return
        if not re.match(r'^[0-9A-F]+$', uid):
            messagebox.showerror("错误", "UID 只能包含十六进制字符 (0-9, A-F)", parent=self)
            return
        if len(uid) not in (8, 14):
            messagebox.showerror(
                "错误",
                f"UID 长度必须是 8 位(M1) 或 14 位(NTAG)，当前: {len(uid)}",
                parent=self)
            return

        card_type = "NTAG" if len(uid) == 14 else "M1"
        if password and len(password) < 4:
            messagebox.showwarning("提示", "密码至少4位，已忽略", parent=self)
            password = ''

        success, msg = self.manager.add_key(uid, permission, card_type, name, password)
        if success:
            self.manager.log_action(
                "新增密钥",
                f"UID: {uid}, 权限: {permission}, 名称: {name or '无'}")
            messagebox.showinfo("成功", msg, parent=self)
            self.entry_uid.delete(0, tk.END)
            self.entry_name.delete(0, tk.END)
            self.entry_add_pwd.delete(0, tk.END)
            self._refresh_list()
        else:
            messagebox.showerror("错误", msg, parent=self)

    def _delete_key(self):
        if self.emergency_mode:
            messagebox.showwarning("提示", "应急模式下禁止删除密钥", parent=self)
            return
        if not self._selected_uid:
            messagebox.showwarning("提示", "请先选中一个密钥", parent=self)
            return
        if messagebox.askyesno("确认删除", f"确认删除 {self._selected_uid}？", parent=self):
            success, msg = self.manager.delete_key(self._selected_uid)
            if success:
                self.manager.log_action("删除密钥", f"UID: {self._selected_uid}")
                messagebox.showinfo("成功", msg, parent=self)
                self._refresh_list()
            else:
                messagebox.showerror("错误", msg, parent=self)

    def _save_all_edits(self):
        if not self._selected_uid:
            messagebox.showwarning("提示", "请先选中一个条目", parent=self)
            return
        uid = self._selected_uid
        key_data = self.manager.get_key_by_uid(uid)
        if not key_data:
            messagebox.showerror("错误", "未找到该条目", parent=self)
            return

        is_special = key_data.get('is_special', False)
        is_developer = key_data.get('is_developer', False)

        # ========== 开发者账号：用户名 + 密码 + 启用 ==========
        if is_special and is_developer:
            new_username = self.entry_edit_uid.get().strip()
            new_password = self.entry_edit_pwd.get().strip()
            new_enabled = self.allowed_var.get()
            changes, errors, need_save = [], [], False

            if new_username and new_username != uid:
                if not re.match(r'^[\u4e00-\u9fa5A-Za-z0-9_\- ]{1,32}$', new_username):
                    errors.append("用户名只能包含中文、字母、数字、下划线、空格、短横线，长度 1～32")
                elif new_username in self.manager.key_status:
                    errors.append(f"用户名 {new_username} 已存在")
                else:
                    success, msg = self.manager.update_key_uid(uid, new_username)
                    if success:
                        changes.append(f"用户名: {uid} -> {new_username}")
                        self._selected_uid = new_username
                        need_save = True
                    else:
                        errors.append(f"用户名: {msg}")

            if new_password:
                if len(new_password) < 4:
                    errors.append("密码长度至少4位")
                else:
                    target_uid = self._selected_uid
                    success, msg = self.manager.set_password(target_uid, new_password)
                    if success:
                        changes.append("密码已更新")
                        need_save = True
                    else:
                        errors.append(f"密码: {msg}")

            old_enabled = self.manager.key_status.get(self._selected_uid, {}).get('enabled', True)
            if new_enabled != old_enabled:
                success, msg = self.manager.set_enabled(self._selected_uid, new_enabled)
                if success:
                    changes.append(
                        f"状态: {'启用' if old_enabled else '禁用'} -> "
                        f"{'启用' if new_enabled else '禁用'}")
                    need_save = True
                else:
                    errors.append(f"状态: {msg}")

            if need_save:
                self.manager.save_all()
                self.manager.log_action("修改开发者", f"用户: {self._selected_uid}, {', '.join(changes)}")
            if changes:
                self.status_label.config(text=f"✅ 已保存: {', '.join(changes)}")
            if errors:
                messagebox.showerror("错误", "\n".join(errors), parent=self)
            self._refresh_list()
            if self._selected_uid:
                self._reselect_item(self._selected_uid)
            return

        # ========== 通用密码（ADMIN_GENERAL / ROOT_GENERAL） ==========
        if is_special:
            new_password = self.entry_edit_pwd.get().strip()
            if new_password and len(new_password) < 4:
                messagebox.showerror("错误", "密码长度至少4位", parent=self)
                return
            if uid == 'ADMIN_GENERAL':
                pwd_type = 'admin'
            elif uid == 'ROOT_GENERAL':
                pwd_type = 'root'
            else:
                messagebox.showerror("错误", "未知的特殊条目", parent=self)
                return
            if new_password:
                success, msg = self.manager.set_general_password(pwd_type, new_password)
                if success:
                    self.manager.log_action("设置通用密码", f"类型: {pwd_type}")
                    self.status_label.config(text=f"✅ {msg}")
                    self._refresh_list()
                    self._reselect_item(uid)
                else:
                    messagebox.showerror("错误", msg, parent=self)
            else:
                self.status_label.config(text="密码未更改")
            return

        # ========== 普通物理密钥 ==========
        new_name = self.entry_edit_name.get().strip()
        new_permission = self.combo_edit_permission.get()
        new_uid = self.entry_edit_uid.get().strip().upper()
        new_password = self.entry_edit_pwd.get().strip()
        new_enabled = self.allowed_var.get()
        changes, errors, need_save = [], [], False

        old_name = self.manager.key_status[uid]['name']
        if new_name != old_name:
            success, msg = self.manager.update_name(uid, new_name)
            if success:
                changes.append(f"名称: {old_name} -> {new_name}")
                need_save = True
            else:
                errors.append(f"名称: {msg}")

        old_permission = self.manager.key_status[uid]['permission']
        if new_permission != old_permission:
            success, msg = self.manager.update_permission(uid, new_permission)
            if success:
                changes.append(f"权限: {old_permission} -> {new_permission}")
                need_save = True
            else:
                errors.append(f"权限: {msg}")

        if new_uid and new_uid != uid and new_uid != '--':
            if not re.match(r'^[0-9A-F]+$', new_uid):
                errors.append("新UID只能包含十六进制字符")
            elif len(new_uid) not in (8, 14):
                errors.append("UID长度必须是8位(M1)或14位(NTAG)")
            else:
                success, msg = self.manager.update_key_uid(uid, new_uid)
                if success:
                    changes.append(f"UID: {uid} -> {new_uid}")
                    self._selected_uid = new_uid
                    need_save = True
                else:
                    errors.append(f"UID: {msg}")

        if new_password:
            if len(new_password) < 4:
                errors.append("密码长度至少4位")
            else:
                old_pwd = self.manager.get_password(uid)
                if new_password != old_pwd:
                    success, msg = self.manager.set_password(uid, new_password)
                    if success:
                        changes.append("密码已更新")
                        need_save = True
                    else:
                        errors.append(f"密码: {msg}")

        old_enabled = self.manager.key_status[uid]['enabled']
        if new_enabled != old_enabled:
            success, msg = self.manager.set_enabled(uid, new_enabled)
            if success:
                changes.append(
                    f"状态: {'启用' if old_enabled else '禁用'} -> "
                    f"{'启用' if new_enabled else '禁用'}")
                need_save = True
            else:
                errors.append(f"状态: {msg}")

        if need_save:
            self.manager.save_all()
            self.manager.log_action("修改密钥", f"UID: {uid}, {', '.join(changes)}")
        if changes:
            self.status_label.config(text=f"✅ 已保存: {', '.join(changes)}")
        if errors:
            messagebox.showerror("错误", "\n".join(errors), parent=self)

        self._refresh_list()
        if self._selected_uid:
            self._reselect_item(self._selected_uid)

    def _reselect_item(self, uid):
        for item in self.tree.get_children():
            tags = self.tree.item(item, 'tags')
            if tags and tags[0] == uid:
                self.tree.selection_set(item)
                self._on_select(None)
                break

    def _search_and_select_uid(self):
        self.label_search_result.config(text="")
        uid = self.entry_search_uid.get().strip().upper()
        if not uid:
            self.label_search_result.config(text="⚠ 请输入 UID", fg='red')
            self.manager.log_action("搜索UID", "结果: 空输入")
            return
        if not re.match(r'^[0-9A-F]+$', uid):
            self.label_search_result.config(text="⚠ UID 只能包含十六进制字符", fg='red')
            self.manager.log_action("搜索UID", f"结果: 非法格式, 输入: {uid}")
            return
        for item in self.tree.get_children():
            tags = self.tree.item(item, 'tags')
            if tags and tags[0] == uid:
                self.tree.selection_set(item)
                self.tree.see(item)
                self._on_select(None)
                self.label_search_result.config(text="✓ 找到", fg='green')
                self.manager.log_action("搜索UID", f"UID: {uid}, 结果: 找到")
                return
        self.label_search_result.config(text="✗ 未找到", fg='red')
        self.manager.log_action("搜索UID", f"UID: {uid}, 结果: 未找到")

    def _read_card_and_search(self):
        """读卡 → 自动填入 UID 查询框 → 自动触发查询"""
        if self._reading:
            self.label_search_result.config(text="⚠ 正在读卡，请稍候...", fg='#e67e22')
            return

        if not self._ensure_reader():
            self.label_search_result.config(text="✗ 读卡器未就绪", fg='red')
            return

        self._reading = True
        self.label_search_result.config(
            text="⏳ 请刷卡（15 秒超时）...", fg='#2980b9')
        try:
            self.btn_search_read_card.config(state='disabled')
        except Exception:
            pass

        def do_read():
            uid = None
            try:
                deadline = time.time() + 15
                while time.time() < deadline:
                    u1, _ = self.pn532.read_ntag_uid(retry=1)
                    if not u1:
                        u2, _ = self.pn532.read_m1_uid()
                        u1 = u2
                    if u1:
                        uid = u1.upper()
                        break
                    time.sleep(0.2)
            except Exception as e:
                log_error(f"读卡查询-读取异常: {e}")
            finally:
                self._reading = False
                self.after(0, lambda u=uid: self._on_read_card_search_done(u))

        threading.Thread(target=do_read, daemon=True).start()

    def _on_read_card_search_done(self, uid):
        try:
            if self.btn_search_read_card.winfo_exists():
                self.btn_search_read_card.config(state='normal')
        except Exception:
            pass

        if not uid:
            self.label_search_result.config(
                text="✗ 读卡超时或未检测到卡片", fg='red')
            self.manager.log_action("读卡查询", "结果: 读卡超时")
            return

        self.entry_search_uid.delete(0, tk.END)
        self.entry_search_uid.insert(0, uid)
        self.manager.log_action("读卡查询", f"读到 UID: {uid}")

        self._search_and_select_uid()


if __name__ == "__main__":
    app = MainWindow()
    app.mainloop()