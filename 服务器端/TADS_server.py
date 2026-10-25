# -*- coding: utf-8 -*
"""
TADS 列车数据与查询服务系统服务器端
作者：Jason Michael

================================================================================
【核心功能】
================================================================================

一、列车数据管理
    - 车次增删改查：支持新增、删除车次，自动分配 train_id
    - 停站录入删除：为车次添加/删除经停站，自动维护始发站/终点站
    - 合并车次组管理：自动识别复车次（如 K973/K976），合并显示为 K973/K976
    - 数据持久化：JSON 格式存储，支持手动备份与还原点恢复

二、实时正晚点查询（V2 接口）
    - 调用 V2 接口获取列车实时正晚点数据
    - 显示晚点/提前分钟数，标注是否已过该站
    - 支持显示"预计正点"、"预计晚点"等预测状态

三、车站大屏（V2 接口）
    - 实时获取车站大屏数据（出发/到达）
    - 显示车次、始发站、终点站、图定时间、大屏状态
    - 显示检票口/出站口信息
    - 显示晚点/提前附加信息

四、车次详情页
    - 显示列车完整信息：车次、类型、复车次、路局、车型、配属、担当、运行时长
    - 显示完整停站列表：站名、到达、出发、跨天
    - 显示本站车次、站台、检票口、出站口（实时查询）
    - 正晚点状态（实时查询）
    - 列车组图片展示（双击放大）

五、查询中心（本地模式 + API 模式一键切换）
    - 车次停站数量：快速查看车次停靠站数
    - 车次全部经停详情：完整显示所有停站及正晚点
    - 某站经过的所有车次：查询经过某站的所有车次（含合并组）
    - 站点时刻表：显示当前时间、上一班/下一班、所有经过车次
    - 车次/站点匹配校验：验证车次是否经停某站
    - 全局搜索引擎：关键词搜索车次/车站
    - 车次当前理论位置：基于实际时刻表定位列车当前位置
    - 两站间今日列车运行：查询两站间所有车次及运行状态
    - 车站↔车次双向查询（含始发车次查询、站到站查询）

六、管理员/ROOT 编辑功能
    - 新增车次
    - 删除车次
    - 录入停站
    - 删除停站
    - 批量导入/更新车次（V1/V2 接口抓取）

七、还原点系统
    - 添加还原点（上限3个）
    - 从还原点恢复
    - 删除还原点
    - 格式化所有还原点

八、操作日志
    - 记录所有操作日志
    - 支持导出 CSV 格式

九、物理密钥认证系统（PN532 NFC 读卡器）
    - 管理员 M1 卡（4字节 UID）验证
    - ROOT NTAG215 卡（7字节 UID）验证
    - 物理密钥名单管理（增删改）
    - 支持 M1 卡和 NTAG215 卡
    - 成熟的完全自研PN532驱动

十、权限体系
    - ROOT：全权（所有功能）
    - 管理员：固定权限（新增车次、录入停站、添加还原点、导出日志、查看配置、更改管理员密码、更新数据），不含任何删除、更改配置操作
    - 开发者：保留用于身份辨识
    - 普通用户：仅查询功能

十一、API 服务（Flask）
    - 为客户端提供完整的 HTTP API 接口
    - 内置 V1/V2 接口代理（避免客户端跨域问题）
    - 支持客户端本地模式和 API 模式切换

================================================================================
【技术架构】
================================================================================

- Python 3.8+
- Tkinter（GUI 界面）
- Flask（API 服务）
- requests（HTTP 客户端）
- PySerial（串口通信）
- cryptography（Ed25519 签名）
- PN532（NFC 读写）

================================================================================
【数据存储】
================================================================================

- 主数据："Dirve所在磁盘":\数据库\TADS_Data\主数据\data.json
- 配置文件："Dirve所在磁盘":\数据库\TADS_Data\主数据\config\config.json
- 环境变量："Dirve所在磁盘":\数据库\TADS_Data\主数据\config\.env
- 日志文件："Dirve所在磁盘":\数据库\TADS_Data\log\operations.log
- 还原点："Dirve所在磁盘":\数据库\TADS_Data\还原点

================================================================================
【安全机制】
================================================================================

- 管理员认证：密码 + M1 卡物理密钥双重验证
- ROOT 认证：密码 + NTAG215 卡物理密钥 + Ed25519 签名验证
- 管理员权限硬编码（不可修改）
- ROOT 拥有全部权限
- 所有硬件操作本地完成，不通过 API 暴露
"""

# ============================================================================
# TADS_Server 兼容层 —— 仅做 CPU 二次检测与启动提示
# 不修改任何业务 import，不修改程序入口
# 弹窗全部使用 Windows 原生 API，绝对不碰 Tkinter，避免干扰主窗口
# ============================================================================
import os
import sys
import ctypes
import threading
import traceback


# ---------------------------------------------------------------------------
# 二级 CPU 检测（与运行时钩子形成双重保险）
# ---------------------------------------------------------------------------
def _compat_probe():
    """返回 dict：各特性 + ProbeOK。任何异常都归为 False。"""
    def _q(code):
        try:
            return ctypes.windll.kernel32.IsProcessorFeaturePresent(code) != 0
        except Exception:
            return False

    try:
        f = {
            'SSE3':        _q(13),
            'AVX':         _q(40),
            'AVX2':        _q(41),
            'AVX512F':     _q(42),
            'AVX512_VBMI': _q(43),
            'FMA':         _q(45),
        }
        f['ProbeOK'] = True
        return f
    except Exception:
        return {
            'SSE3': False, 'AVX': False, 'AVX2': False,
            'AVX512F': False, 'AVX512_VBMI': False, 'FMA': False,
            'ProbeOK': False,
        }


def _compat_apply(features):
    """
    与钩子相同的分档策略，双保险。
    返回人类可读的启动方式字符串。
    """
    _DIS_AVX512 = (
        "AVX512F,AVX512CD,AVX512_SKX,AVX512_CLX,"
        "AVX512_CNL,AVX512_ICL,AVX512_VBMI,AVX512_VBMI2"
    )
    _DIS_AVX2 = _DIS_AVX512 + ",AVX2,FMA3,F16C"
    _DIS_AVX  = _DIS_AVX2 + ",AVX"

    if not features['ProbeOK']:
        os.environ["OPENBLAS_CORETYPE"] = "ATOM"
        os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX
        return "最保守兼容模式（CPU 探针失效）"

    if features['AVX512F']:
        return "原生高性能模式（AVX-512）"

    if features['AVX2']:
        return "原生高性能模式（AVX2）"

    if features['AVX']:
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX2
        return "兼容模式（仅支持 AVX，已禁用 AVX2+）"

    if features['SSE3']:
        os.environ["OPENBLAS_CORETYPE"] = "ATOM"
        os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
        os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX
        return "老 CPU 兼容模式（不支持 AVX）"

    os.environ["OPENBLAS_CORETYPE"] = "ATOM"
    os.environ["MKL_DEBUG_CPU_TYPE"] = "5"
    os.environ["NPY_DISABLE_CPU_FEATURES"] = _DIS_AVX
    return "极老 CPU 最保守兼容模式（不支持 SSE3）"


# ---------------------------------------------------------------------------
# 弹窗 —— 启动提示（Windows 原生 API，5 秒自动关，完全不碰 Tkinter）
# ---------------------------------------------------------------------------
def _compat_toast(message, duration=5):
    """
    使用 Windows 原生 MessageBoxTimeoutW 显示启动提示。
    - 不创建 tk.Tk()，绝对不干扰主窗口的 Tk 状态
    - duration 秒后自动关闭
    - 模态但极短，用户不点也会自动消失
    - 兼容 Win7 及以上
    """
    try:
        # MB_ICONINFORMATION = 0x40
        # MessageBoxTimeoutW：未公开但稳定，所有 Windows NT 6.0+ 都支持
        ctypes.windll.user32.MessageBoxTimeoutW(
            0,                              # hWnd = NULL
            str(message),                   # 内容
            "TADS_Server 启动信息",          # 标题
            0x40,                           # 图标：信息
            0,                              # 语言 ID
            int(duration * 1000)            # 超时毫秒数
        )
    except Exception:
        # 万一 MessageBoxTimeoutW 不可用（极罕见），
        # 用普通 MessageBoxW，放到后台线程以免阻塞主程序
        try:
            threading.Thread(
                target=lambda: ctypes.windll.user32.MessageBoxW(
                    0, str(message), "TADS_Server 启动信息", 0x40
                ),
                daemon=True
            ).start()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 弹窗 —— 错误（Windows 原生 API，模态，不自动关，不碰 Tkinter）
# ---------------------------------------------------------------------------
def _compat_error(error_text):
    """
    使用 Windows 原生 MessageBoxW 显示错误信息。
    - 模态：用户必须手动关闭
    - 不自动关闭
    - 完全不碰 Tkinter
    """
    try:
        ctypes.windll.user32.MessageBoxW(
            0,                              # hWnd = NULL
            str(error_text),                # 内容
            "TADS_Server 启动错误",          # 标题
            0x10                            # 图标：错误
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 执行兼容层（自包含，不触碰业务代码）
# ---------------------------------------------------------------------------
_COMPAT_MODE = None  # 保存启动方式字符串，供 TADSApp 初始化后写入启动日志

try:
    _feat = _compat_probe()
    _mode = _compat_apply(_feat)
    _COMPAT_MODE = _mode
    # 不再弹窗提示，改为在 TADSApp 初始化后写入启动日志（标注"仅供参考"）
except Exception:
    _compat_error(
        "兼容层初始化过程中发生未处理异常：\n\n" + traceback.format_exc()
    )

import os
import sys
import json
import base64
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import datetime
import socket
import subprocess
import re
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Listbox, EXTENDED, filedialog, simpledialog
import ctypes
import serial
import serial.tools.list_ports
import csv
import io
import requests
import pygame
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
# ====== AES 加解密支持 ======
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from flask import Flask, request, jsonify, send_file, g, has_request_context
from functools import wraps
from typing import Dict, Optional, List, Any

# ================== 全局配置（占位，实际从配置文件加载） ==================
ADMIN_PASSWORD_HASH = ""
ROOT_PASSWORD_HASH = ""
DEVELOPER_PASSWORD_HASH = ""

# ================== 路径定义 ==================
# 配置文件存储于 AppData
APP_CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'TADS', 'Server', 'config')
CONFIG_FILE = os.path.join(APP_CONFIG_DIR, 'config.json')
ENV_FILE = os.path.join(APP_CONFIG_DIR, '.env')
KEY_STATUS_FILE = os.path.join(APP_CONFIG_DIR, "key_status.env")

# 数据路径默认值（可被 paths 覆盖）
DEFAULT_DATA_ROOT = r"E:\数据库\TADS_Data"
DEFAULT_LOG_DIR = os.path.join(DEFAULT_DATA_ROOT, "log")
DEFAULT_MAIN_DATA_DIR = os.path.join(DEFAULT_DATA_ROOT, "主数据")
DEFAULT_RESTORE_DIR = os.path.join(DEFAULT_DATA_ROOT, "还原点")

# 运行时使用的路径（会被 ConfigManager 更新）
DATA_ROOT = DEFAULT_DATA_ROOT
LOG_DIR = DEFAULT_LOG_DIR
MAIN_DATA_DIR = DEFAULT_MAIN_DATA_DIR
RESTORE_DIR = DEFAULT_RESTORE_DIR
DATA_FILE = os.path.join(MAIN_DATA_DIR, "data.json")
LOG_FILE = os.path.join(LOG_DIR, "operations.log")
ERROR_LOG = os.path.join(LOG_DIR, "error.log")

RAIL_RHYTHM_ROOT = r"E:\数据库\TADS_Data\分数据\RailRhythm12306"
CONVERT_SCRIPT = os.path.join(RAIL_RHYTHM_ROOT, "convert_to_tads.py")
AUTO_UPDATE_SCRIPT = os.path.join(RAIL_RHYTHM_ROOT, "auto_update.py")
TRAIN_DATA_DIR = os.path.join(RAIL_RHYTHM_ROOT, "train_data")

# ================== 工具函数 ==================
def verify_password(input_pwd, stored_hash_b64):
    if not stored_hash_b64:
        return False
    try:
        combined = base64.b64decode(stored_hash_b64)
        if len(combined) != 48:
            return False
        salt = combined[:16]
        stored_hash = combined[16:]
        pwd_bytes = input_pwd.encode('utf-8')
        salted = pwd_bytes + salt
        computed = hashlib.sha256(salted).digest()
        return computed == stored_hash
    except:
        return False

def find_pn532_port(baudrate=115200, timeout=0.5):
    """
    自动扫描并返回 PN532 设备所在的串口号。
    :param baudrate: 波特率
    :param timeout: 每个端口的超时时间
    :return: 找到的端口名称（如 'COM3'）或 None
    """
    ports = serial.tools.list_ports.comports()
    for port in ports:
        device = port.device
        try:
            ser = serial.Serial(device, baudrate, timeout=timeout)
            # 发送唤醒命令（与 PN532._wake() 相同）
            wake = b'\x55\x55\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\x03\xfd\xd4\x14\x01\x17\x00'
            ser.write(wake)
            time.sleep(0.1)
            ser.reset_input_buffer()
            # 发送 SAM_CONFIG 命令 (0x14 0x01) 并检查响应
            test_cmd = b'\x00\x00\xff\x04\xfc\xd4\x14\x01\xe7'  # SAM_CONFIG
            ser.write(test_cmd)
            time.sleep(0.1)
            # 读取响应头（5字节）
            header = ser.read(5)
            if len(header) == 5 and header[0:3] == b'\x00\x00\xff':
                ser.close()
                return device
            ser.close()
        except:
            continue
    return None

def hash_password(password):
    salt = os.urandom(16)
    pwd_bytes = password.encode('utf-8')
    salted = pwd_bytes + salt
    computed = hashlib.sha256(salted).digest()
    combined = salt + computed
    return base64.b64encode(combined).decode('utf-8')

def test_port_silent(host='localhost', port=10045, timeout=0.2):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def _get_local_ip():
    """获取本机对外 IP（基于 UDP 路由探测，不发送数据）"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return '127.0.0.1'

# ================== DPAPI 加密（Windows 原生，无需额外依赖） ==================
import ctypes
from ctypes import wintypes as _wintypes

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ('cbData', _wintypes.DWORD),
        ('pbData', ctypes.POINTER(ctypes.c_char)),
    ]

_CRYPTPROTECT_UI_FORBIDDEN = 0x01

def dpapi_encrypt(data_bytes: bytes) -> bytes:
    """用 Windows DPAPI 加密（当前用户作用域）；非 Windows 或失败时返回 b''"""
    if os.name != 'nt':
        return b''
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data_bytes, len(data_bytes))
        blob_in = _DATA_BLOB(len(data_bytes), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _DATA_BLOB()
        ok = crypt32.CryptProtectData(
            ctypes.byref(blob_in), None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)
        )
        if not ok:
            return b''
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return b''

def dpapi_decrypt(data_bytes: bytes) -> bytes:
    """用 Windows DPAPI 解密；失败返回 b''"""
    if os.name != 'nt' or not data_bytes:
        return b''
    try:
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_string_buffer(data_bytes, len(data_bytes))
        blob_in = _DATA_BLOB(len(data_bytes), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        blob_out = _DATA_BLOB()
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None,
            _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(blob_out)
        )
        if not ok:
            return b''
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            kernel32.LocalFree(blob_out.pbData)
    except Exception:
        return b''

def get_hub_count(port=10045):
    try:
        output = subprocess.check_output("netstat -an", shell=True, encoding='gbk')
        return len([line for line in output.splitlines() if f':{port}' in line])
    except:
        return 0

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def run_as_admin():
    try:
        script = sys.executable
        params = ' '.join(sys.argv[1:])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
        return True
    except:
        return False

def convert_to_old_format(railgo_data: Dict, train_number: str) -> Optional[Dict]:
    """
    将 RailGo API 或 V2 API 返回的数据转换为内部格式。
    兼容多种字段名：timetable / trainStops / stops
    """
    # 尝试多种可能的停站字段名
    timetable = railgo_data.get("timetable")
    if not timetable:
        timetable = railgo_data.get("trainStops")
    if not timetable:
        timetable = railgo_data.get("stops")
    if not timetable:
        return None

    if not isinstance(timetable, list) or len(timetable) < 2:
        return None

    stops = []
    total = len(timetable)
    for idx, stop in enumerate(timetable):
        # 兼容字段名：station / stationName
        station_name = stop.get("station") or stop.get("stationName") or ""
        station_name = station_name.strip()
        if not station_name:
            continue

        arrive = stop.get("arrive") or stop.get("arrival") or ""
        depart = stop.get("depart") or stop.get("departure") or ""
        day_offset = stop.get("day") or stop.get("dayOffset") or 0

        if arrive == "----":
            arrive = None
        if depart == "----":
            depart = None
        if idx == 0:
            arrive = None
        elif idx == total - 1:
            depart = None

        stops.append({
            "station_name": station_name,
            "arrive": arrive,
            "depart": depart,
            "day_offset": day_offset,
        })

    if len(stops) < 2:
        return None

    # 兼容 type / numberKind / trainType
    train_type = railgo_data.get("type") or railgo_data.get("numberKind") or railgo_data.get("trainType") or "未知"
    return {
        "base_number": train_number,
        "type": train_type,
        "stops": stops,
    }

def derive_aes_key_from_root_hash(root_hash: str) -> bytes:
    """从 ROOT 密码哈希派生 AES 密钥"""
    AES_SALT = b"TADS_UID_PASSWORD_SALT_v1"
    return hashlib.pbkdf2_hmac('sha256', root_hash.encode('utf-8'), AES_SALT, 100000, 32)

def decrypt_password(encrypted_data: str, aes_key: bytes) -> str:
    if not encrypted_data:
        return ""
    try:
        combined = base64.b64decode(encrypted_data)
        iv = combined[:16]
        ciphertext = combined[16:]
        cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_data) + unpadder.finalize()
        return plaintext.decode('utf-8')
    except Exception as e:
        # 抛出异常，让上层捕获
        raise ValueError(f"解密失败: {e}")

# ================== PN532 读卡器驱动（稳定版，基于 deploy_key.py） ==================
class PN532Reader:
    """
    基于 PN532 的 NFC 读写器，通过串口通信
    完全复制 deploy_key.py 中已验证的通信逻辑
    支持读取 M1 卡 UID 和 NTAG215 UID
    """
    def __init__(self, port="COM4", baudrate=115200, auto=False):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._lock = threading.Lock()
        self._connected = False

        # auto 模式：延迟连接。端口选择与连接由 UI 层统一负责
        # （启动时/点击"连接PN532"时通过 MainWindow._connect_pn532_with_selection 处理）
        if auto or port is None or (isinstance(port, str) and port.lower() == "auto"):
            if not port or (isinstance(port, str) and port.lower() == "auto"):
                self.port = "auto"
            return

        # 显式指定端口：立即尝试连接
        self._init_reader()

    def _init_reader(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.5,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=8
            )
            self._wake()
            self.ser.reset_input_buffer()
            self._init_rf()
            self._connected = True
        except Exception as e:
            print(f"PN532 初始化失败: {e}")
            self._connected = False

    def _wake(self):
        wake = b'\x55\x55\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\x03\xfd\xd4\x14\x01\x17\x00'
        self.ser.write(wake)
        time.sleep(0.1)

    def _send_command(self, cmd, params=b'', timeout=0.05):
        data = b'\xd4' + bytes([cmd]) + params
        length = len(data)
        lcs = (0x100 - length) & 0xFF
        frame = b'\x00\x00\xff' + bytes([length, lcs]) + data
        dcs = (0x100 - (sum(data) & 0xFF)) & 0xFF
        frame += bytes([dcs])

        with self._lock:
            self.ser.write(frame)
            time.sleep(timeout)
            ack = self.ser.read(6)
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

    def _init_rf(self):
        self._send_command(0x14, b'\x01')
        time.sleep(0.05)
        self._send_command(0x32, b'\x01\x01')
        time.sleep(0.05)

    def reset(self):
        self.ser.reset_input_buffer()
        self._wake()
        self._init_rf()

    def read_card_uid(self):
        resp = self._send_command(0x4A, b'\x01\x00', timeout=0.1)
        if not resp:
            return None, None
        if resp[0] == 0xD5:
            resp = resp[1:]
        if len(resp) < 7 or resp[0] != 0x4B:
            return None, None
        nbtg = resp[1]
        if nbtg == 0:
            return None, None
        uid_len = resp[6]
        if uid_len == 0 or len(resp) < 7 + uid_len:
            return None, None
        uid = resp[7:7+uid_len]
        return uid.hex().upper(), uid_len

    def wait_for_card_removed(self, timeout_sec=2.0):
        start = time.time()
        while time.time() - start < timeout_sec:
            if not self.read_card_uid()[0]:
                return True
            time.sleep(0.1)
        return False

    def wait_for_card(self):
        self.reset()
        last_uid = None
        consecutive_none = 0

        while True:
            result = self.read_card_uid()
            if result[0]:
                uid_hex, uid_len = result
                consecutive_none = 0
                if uid_hex != last_uid:
                    last_uid = uid_hex
                    if self.wait_for_card_removed():
                        self.reset()
                        time.sleep(0.2)
                        uid_hex2, uid_len2 = self.read_card_uid()
                        if uid_hex2 == uid_hex:
                            return uid_hex, uid_len
                        else:
                            continue
                    else:
                        self.reset()
                        continue
            else:
                consecutive_none += 1
                if consecutive_none > 50:
                    self.reset()
                    consecutive_none = 0
            time.sleep(0.1)

    def is_connected(self):
        return self._connected

    def reconnect(self, port=None, baudrate=None):
        """按指定端口重连 PN532（不再自动扫描；端口选择由 UI 层负责）"""
        if port:
            self.port = port
        if baudrate:
            self.baudrate = baudrate
        if not self.port or (isinstance(self.port, str) and self.port.lower() == "auto"):
            return False
        self._init_reader()
        return self._connected

    def list_ports(self):
        return [port.device for port in serial.tools.list_ports.comports()]

    def check_connection(self):
        """独立检测设备连接状态，通过发送空命令测试"""
        try:
            if not self.ser or not self.ser.is_open:
                return False
            # 发送一个简单的命令测试设备是否响应
            import time
            self.ser.write(b'')
            self.ser.timeout = 0.1
            # 尝试读取，如果串口已断开会抛出异常
            self.ser.read(1)
            return True
        except Exception as e:
            print(f"PN532连接检测失败: {e}")
            try:
                self.ser.close()
            except:
                pass
            self._connected = False
            return False

    # 以下两个方法是为了兼容原有接口（系统里可能没有调用，但保留以免报错）
    def read_ntag_uid_and_signature(self):
        return None, None

    def write_ntag_signature(self, signature_bytes):
        return False

# ================== 配置管理器 ==================
class ConfigManager:
    def __init__(self):
        self._lock = threading.Lock()
        if not os.path.exists(APP_CONFIG_DIR):
            os.makedirs(APP_CONFIG_DIR)
        self.config = {}
        self.env = {}
        self._private_key = None
        self._public_key = None
        self.load()

    def _ensure_dirs(self):
        for d in [APP_CONFIG_DIR, LOG_DIR, MAIN_DATA_DIR, RESTORE_DIR]:
            if not os.path.exists(d):
                os.makedirs(d)

    def load(self):
        global ADMIN_PASSWORD_HASH, ROOT_PASSWORD_HASH, DEVELOPER_PASSWORD_HASH
        
        with self._lock:
            if os.path.exists(CONFIG_FILE):
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        self.config = json.load(f)
                except:
                    self.config = {}
            else:
                self.config = {}

            if os.path.exists(ENV_FILE):
                try:
                    with open(ENV_FILE, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, val = line.split('=', 1)
                                self.env[key.strip()] = val.strip()
                except:
                    self.env = {}
            else:
                self.env = {}

            # 从 config.json 读取密码哈希
            ADMIN_PASSWORD_HASH = self.config.get('admin_password_hash', '')
            ROOT_PASSWORD_HASH = self.config.get('root_password_hash', '')
            DEVELOPER_PASSWORD_HASH = self.config.get('developer_password_hash', '')

            self._ensure_defaults()
            self._load_key_pair()

    def _ensure_defaults(self):
        if 'admin_password_hash' not in self.config or not self.config['admin_password_hash']:
            self.config['admin_password_hash'] = ""
        if 'root_password_hash' not in self.config or not self.config['root_password_hash']:
            self.config['root_password_hash'] = ""
        # 新增：开发者密码哈希
        if 'developer_password_hash' not in self.config or not self.config['developer_password_hash']:
            self.config['developer_password_hash'] = ""
        if 'physical_keys' not in self.config:
            self.config['physical_keys'] = []
        if 'com_port' not in self.config:
            self.config['com_port'] = "COM4"
        if 'baudrate' not in self.config:
            self.config['baudrate'] = 115200
        if 'api_port' not in self.config:
            self.config['api_port'] = 10076
        if 'paths' not in self.config:
            self.config['paths'] = {
                'data_root': DEFAULT_DATA_ROOT,
                'log_dir': DEFAULT_LOG_DIR,
                'main_data_dir': DEFAULT_MAIN_DATA_DIR,
                'restore_dir': DEFAULT_RESTORE_DIR
            }
        if 'monitor' not in self.config:
            self.config['monitor'] = {
                'enabled': True,
                'port': 10045,
                'display_name': '中枢站'
            }
        if 'api' not in self.config:
            self.config['api'] = {
                'v1_base': 'https://data.railgo.zenglingkun.cn/api',
                'v2_base': 'https://rg-api.zenglingkun.cn/api/v2',
                'emu_base': 'https://emu.railgo.zenglingkun.cn'  # 新增 EMU API 地址
            }

        # 保留但不使用
        full_permissions = {
            "key_add": {"name": "添加物理密钥", "description": "允许添加新的物理密钥令牌"},
            "key_delete": {"name": "删除物理密钥", "description": "允许删除现有的物理密钥令牌"},
            "key_manage": {"name": "完全管理密钥", "description": "允许添加和删除物理密钥令牌"},
            "export_logs": {"name": "导出日志", "description": "允许导出操作日志为CSV"},
            "change_admin_pwd": {"name": "更改管理员密码", "description": "允许更改管理员密码"},
            "view_config": {"name": "查看配置", "description": "允许查看系统配置"},
            "edit_config": {"name": "编辑配置", "description": "允许修改系统配置（如COM口）"},
            "change_root_pwd": {"name": "更改ROOT密码", "description": "允许更改ROOT密码"},
            "add_train": {"name": "新增车次", "description": "允许新增车次"},
            "delete_train": {"name": "删除车次", "description": "允许删除车次"},
            "add_stop": {"name": "录入停站", "description": "允许录入停站"},
            "delete_stop": {"name": "删除停站", "description": "允许删除停站"},
            "add_restore": {"name": "添加还原点", "description": "允许添加还原点"},
            "restore_apply": {"name": "从还原点恢复", "description": "允许从还原点恢复"},
            "restore_delete": {"name": "删除还原点", "description": "允许删除还原点"},
            "restore_format": {"name": "格式化还原点", "description": "允许格式化所有还原点"},
            "update_data": {"name": "更新列车数据", "description": "允许从RailRhythm更新数据"},
        }

        if 'permissions_definition' not in self.config:
            self.config['permissions_definition'] = {}

        for key, value in full_permissions.items():
            if key not in self.config['permissions_definition']:
                self.config['permissions_definition'][key] = value

        self.save()

    def _load_key_pair(self):
        private_key_b64 = self.env.get('ROOT_PRIVATE_KEY')
        public_key_b64 = self.env.get('ROOT_PUBLIC_KEY')
        if private_key_b64 and public_key_b64:
            try:
                private_bytes = base64.b64decode(private_key_b64)
                public_bytes = base64.b64decode(public_key_b64)
                self._private_key = Ed25519PrivateKey.from_private_bytes(private_bytes)
                self._public_key = Ed25519PublicKey.from_public_bytes(public_bytes)
                return
            except:
                pass
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        private_bytes = self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_bytes = self._public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        self.env['ROOT_PRIVATE_KEY'] = base64.b64encode(private_bytes).decode('utf-8')
        self.env['ROOT_PUBLIC_KEY'] = base64.b64encode(public_bytes).decode('utf-8')
        self._save_env()

    def get_public_key_b64(self):
        return self.env.get('ROOT_PUBLIC_KEY', '')

    def sign_data(self, data):
        return self._private_key.sign(data.encode('utf-8'))

    def verify_signature(self, data, signature):
        try:
            self._public_key.verify(signature, data.encode('utf-8'))
            return True
        except InvalidSignature:
            return False

    def save(self):
        global ADMIN_PASSWORD_HASH, ROOT_PASSWORD_HASH
        self.config['admin_password_hash'] = ADMIN_PASSWORD_HASH
        self.config['root_password_hash'] = ROOT_PASSWORD_HASH
        
        lock_file = CONFIG_FILE + ".lock"
        lock_fd = None
        
        # 尝试获取文件锁（最多等待 3 秒）
        for attempt in range(30):
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock_fd = open(lock_file, 'w')
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    lock_fd = open(lock_file, 'w')
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (IOError, OSError, PermissionError):
                if lock_fd:
                    try:
                        lock_fd.close()
                    except:
                        pass
                    lock_fd = None
                time.sleep(0.1)
                continue
        
        if lock_fd is None:
            print(f"保存配置失败：获取文件锁超时（3秒）")
            return
        
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
        finally:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except:
                pass
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
            except:
                pass
        
        # 保存后重新加载全局变量
        self._reload_password_hashes()

    def _reload_password_hashes(self):
        """重新加载 config.json 中的密码哈希到全局变量"""
        global ADMIN_PASSWORD_HASH, ROOT_PASSWORD_HASH
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                ADMIN_PASSWORD_HASH = config.get('admin_password_hash', '')
                ROOT_PASSWORD_HASH = config.get('root_password_hash', '')
        except Exception as e:
            print(f"重新加载密码哈希失败: {e}")

    def _save_env(self):
        try:
            with open(ENV_FILE, 'w', encoding='utf-8') as f:
                for key, val in self.env.items():
                    f.write(f"{key}={val}\n")
        except Exception as e:
            print(f"保存环境变量失败: {e}")

    def get(self, key, default=None):
        with self._lock:
            return self.config.get(key, default)

    def set(self, key, value):
        with self._lock:
            self.config[key] = value
            self.save()

    def get_physical_keys(self):
        with self._lock:
            return self.config.get('physical_keys', [])

    def add_physical_key(self, key_data):
        with self._lock:
            if 'physical_keys' not in self.config:
                self.config['physical_keys'] = []
            for k in self.config['physical_keys']:
                if k.get('uid') == key_data.get('uid'):
                    return False
            # 移除权限字段（如果有）
            if 'permissions' in key_data:
                del key_data['permissions']
            self.config['physical_keys'].append(key_data)
            self.save()
            return True

    def delete_physical_key(self, uid):
        with self._lock:
            if 'physical_keys' not in self.config:
                return False
            original_len = len(self.config['physical_keys'])
            self.config['physical_keys'] = [k for k in self.config['physical_keys'] if k.get('uid') != uid]
            if len(self.config['physical_keys']) < original_len:
                self.save()
                return True
            return False

    def update_physical_key(self, uid, new_data, new_uid=None):
        """
        更新物理密钥信息。
        :param uid: 当前密钥的 UID（用于查找）
        :param new_data: 要更新的字段（如 person, type 等），不包含 uid
        :param new_uid: 新的 UID，如果提供则替换原有 UID
        :return: True 成功，False 失败
        """
        with self._lock:
            if 'physical_keys' not in self.config:
                return False
            # 查找要更新的条目
            target_index = None
            target = None
            for i, k in enumerate(self.config['physical_keys']):
                if k.get('uid') == uid:
                    target_index = i
                    target = k
                    break
            if target_index is None:
                return False

            # 准备新数据
            updated = target.copy()
            # 如果提供了 new_uid，且与当前不同，检查唯一性
            if new_uid is not None and new_uid != uid:
                # 检查新 UID 是否已被其他密钥使用
                for k in self.config['physical_keys']:
                    if k.get('uid') == new_uid and k.get('uid') != uid:
                        return False
                updated['uid'] = new_uid
            # 更新其他字段
            for key, value in new_data.items():
                if key != 'uid':  # 防止意外覆盖
                    updated[key] = value
            # 保存
            self.config['physical_keys'][target_index] = updated
            self.save()
            return True

    def get_permissions_definition(self):
        with self._lock:
            return self.config.get('permissions_definition', {})

# ================== TADS 应用核心 ==================
class TADSApp:
    # 管理员固定权限（硬编码，不可更改）
    ADMIN_FIXED_PERMISSIONS = [
        "add_train",      # 新增车次
        "add_stop",       # 录入停站
        "add_restore",    # 添加还原点
        "export_logs",    # 导出日志
        "view_config",    # 查看配置
        "change_admin_pwd", # 更改管理员密码
        "update_data",    # 更新列车数据
    ]

    def __init__(self):
        self.config = ConfigManager()
        
        # 获取或生成固定 UID 加密密钥（与 ROOT 密码无关）
        self.uid_encryption_key = self._get_uid_encryption_key()
        
        self._apply_paths_from_config()

        self.pn532 = PN532Reader(
            port=self.config.get('com_port', 'COM3'),
            baudrate=self.config.get('baudrate', 115200),
            auto=True
        )

        self.current_identity = "普通用户"
        self.is_admin = False
        self.is_developer = False
        self.is_root = False

        # ===== API Token（用于 Flask 请求级认证） =====
        # 只有提权成功后才签发；退出登录/身份变化时吊销
        self.api_token = None
        self.api_token_expire = 0.0
        self.api_token_identity = None
        self.api_token_ttl = 8 * 3600   # 8 小时，可按需调整

        # ===== 客户端 Token（持久化到 config.json） =====
        # 结构：{token_str: {'identity':..., 'permissions':[...], 'expire':ts, 'issued_at':ts, 'source':'client'}}
        self.client_tokens = {}
        self.client_token_ttl = 8 * 3600
        self._load_tokens_from_config()

        self.data = None
        self.restore_points = []
        self.stats = None
        self.current_page = "主界面"
        self._physical_key_present = False
        self._physical_key_update_stop = False

        self.load_data()
        # 从 .env 读取多个 ADMIN UID（逗号分隔）
        admin_uid_str = self.config.env.get('ADMIN_UID', '')
        if admin_uid_str:
            self.ADMIN_UIDS = [uid.strip() for uid in admin_uid_str.split(',') if uid.strip()]
        else:
            self.ADMIN_UIDS = []
        
        # 从 .env 读取多个 ROOT UID（逗号分隔）
        root_uid_str = self.config.env.get('ROOT_UID', '')
        if root_uid_str:
            self.ROOT_UIDS = [uid.strip() for uid in root_uid_str.split(',') if uid.strip()]
        else:
            self.ROOT_UIDS = []
        
        self.update_restore_points()
        self.update_stats()
        self.update_identity()
        self.log_action("服务器端系统启动", f"当前身份：{self.current_identity}")
        # 写入 CPU 兼容层启动方式（仅供参考）
        try:
            if _COMPAT_MODE:
                self.log_action("系统兼容层", f"已使用启动方式：{_COMPAT_MODE}（仅供参考）")
        except Exception:
            pass

        threading.Thread(target=self._physical_key_updater, daemon=True).start()

        self.current_permissions = []   # 存储当前管理员/ROOT的权限列表
        self.current_uid = None         # 存储当前提权的物理密钥UID

        # 合并组缓存
        self.merged_groups = self._compute_merged_groups()
        # 电报码映射缓存
        self._telecode_cache = {}   # 站名 -> 电报码
        self._telecode_loaded = False
        # 在后台加载电报码
        threading.Thread(target=self._load_telecode_map, daemon=True).start()

        self._v2_cache = {}  # {train_number: (data, timestamp)}

        # ====== API查询开关 ======
        self.use_api_query = True # 默认开启，使用API实时数据

        # ====== 新增：自动更新配置 ======
        self.auto_update_on_query = self.config.get('auto_update_on_query', False)
        self.main_window = None

        # ====== 配置版本监控初始化 ======
        self.config_version_at_login = None
        self._version_monitor_thread = None
        self._version_monitor_stop = False
        # 注意：版本监控在 set_main_window 之后才会真正启动

        # 启动配置版本监控
        self._start_config_version_monitor()

        # ★★★ 新增：记录启动时的配置版本，用于后续动态比对
        self._last_known_config_version = self._get_config_version()

    def _check_config_version_and_revoke(self):
        """如果发现配置文件版本已变，立刻撤销所有 Token"""
        current_version = self._get_config_version()
        if current_version != self._last_known_config_version:
            self._last_known_config_version = current_version
            # 清理所有客户端 Token
            self.client_tokens.clear()
            self._save_tokens_to_config()
            # 清理 GUI Token
            self._revoke_api_token()
            # 通知服务器端 GUI 降级
            if self.is_admin or self.is_root or self.is_developer:
                self.is_admin = False
                self.is_root = False
                self.is_developer = False
                self.current_identity = "普通用户"
                if self.main_window:
                    self.main_window.after(0, self._force_logout)
            return True
        return False

    def set_main_window(self, window):
        """设置主窗口引用，用于临时消息回调"""
        self.main_window = window

    def _load_tokens_from_config(self):
        """启动时加载 token；优先读加密字段，读不到时尝试旧版明文并自动迁移"""
        try:
            cfg = self.config.config
            now = time.time()

            # ----- 1. 加载 client_tokens -----
            loaded_ct = {}
            raw_enc = cfg.get('client_tokens_enc', '') or ''
            if raw_enc:
                try:
                    blob = base64.b64decode(raw_enc)
                    plain = dpapi_decrypt(blob)
                    if plain:
                        loaded_ct = json.loads(plain.decode('utf-8')) or {}
                except Exception:
                    loaded_ct = {}

            # 迁移：如果加密字段为空但存在旧版明文
            if not raw_enc:
                legacy = cfg.get('client_tokens', {}) or {}
                if isinstance(legacy, dict) and legacy:
                    loaded_ct = legacy
                    cfg.pop('client_tokens', None)

            # 清理过期
            if isinstance(loaded_ct, dict):
                loaded_ct = {t: e for t, e in loaded_ct.items()
                             if isinstance(e, dict) and e.get('expire', 0) > now}
            else:
                loaded_ct = {}
            self.client_tokens = loaded_ct

            # ----- 2. 加载 GUI api_token -----
            gui_token = ''
            gui_expire = 0.0
            gui_identity = ''
            raw_gui_enc = cfg.get('api_token_enc', '') or ''
            if raw_gui_enc:
                try:
                    blob = base64.b64decode(raw_gui_enc)
                    plain = dpapi_decrypt(blob)
                    if plain:
                        d = json.loads(plain.decode('utf-8'))
                        gui_token = d.get('token', '') or ''
                        gui_expire = float(d.get('expire', 0) or 0)
                        gui_identity = d.get('identity', '') or ''
                except Exception:
                    pass
            if not raw_gui_enc:
                # 迁移旧版明文
                legacy_token = cfg.get('api_token', '') or ''
                if legacy_token:
                    gui_token = legacy_token
                    gui_expire = float(cfg.get('api_token_expire', 0) or 0)
                    gui_identity = cfg.get('api_token_identity', '') or ''
                    cfg.pop('api_token', None)
                    cfg.pop('api_token_expire', None)
                    cfg.pop('api_token_identity', None)

            if gui_token and gui_expire > now:
                self.api_token = gui_token
                self.api_token_expire = gui_expire
                self.api_token_identity = gui_identity
            else:
                self.api_token = None
                self.api_token_expire = 0.0
                self.api_token_identity = None

            # 若有迁移动作或清理了过期项 → 立刻重新加密写盘
            if (raw_enc and loaded_ct != cfg.get('_last_saved_ct_snapshot', loaded_ct)) \
                    or (not raw_enc and self.client_tokens) \
                    or (not raw_gui_enc and self.api_token):
                self._save_tokens_to_config()

        except Exception as e:
            try:
                self.write_error_log(f"加载 client_tokens 失败: {e}")
            except Exception:
                pass
            self.client_tokens = {}

    def _save_tokens_to_config(self):
        """把 GUI api_token 和 client_tokens 加密后写回 config.json（兼容 Win7+）"""
        try:
            with self.config._lock:
                cfg = self.config.config

                # ----- 1. client_tokens 整体加密 -----
                try:
                    ct_json = json.dumps(self.client_tokens or {}, ensure_ascii=False).encode('utf-8')
                except Exception:
                    ct_json = b'{}'
                ct_enc = dpapi_encrypt(ct_json)
                if ct_enc:
                    cfg['client_tokens_enc'] = base64.b64encode(ct_enc).decode('ascii')
                    cfg.pop('client_tokens', None)
                else:
                    # 非 Windows 或 DPAPI 失败：降级为明文存储（保证可用）
                    cfg['client_tokens'] = self.client_tokens or {}
                    cfg.pop('client_tokens_enc', None)

                # ----- 2. GUI api_token 加密 -----
                gui_payload = {
                    'token': self.api_token or '',
                    'expire': self.api_token_expire or 0,
                    'identity': self.api_token_identity or '',
                }
                gui_json = json.dumps(gui_payload).encode('utf-8')
                gui_enc = dpapi_encrypt(gui_json)
                if gui_enc:
                    cfg['api_token_enc'] = base64.b64encode(gui_enc).decode('ascii')
                    cfg.pop('api_token', None)
                    cfg.pop('api_token_expire', None)
                    cfg.pop('api_token_identity', None)
                else:
                    cfg['api_token'] = self.api_token or ''
                    cfg['api_token_expire'] = self.api_token_expire
                    cfg['api_token_identity'] = self.api_token_identity or ''
                    cfg.pop('api_token_enc', None)

                self.config.save()
        except Exception as e:
            try:
                self.write_error_log(f"保存 token 失败: {e}")
            except Exception:
                pass

    def get_auto_update_setting(self):
        return self.auto_update_on_query

    def set_auto_update_setting(self, enabled):
        self.auto_update_on_query = enabled
        self.config.set('auto_update_on_query', enabled)
        self.log_action("服务器端切换自动更新", f"状态: {'开启' if enabled else '关闭'}")

    def _apply_paths_from_config(self):
        global DATA_ROOT, LOG_DIR, MAIN_DATA_DIR, RESTORE_DIR, DATA_FILE, LOG_FILE, ERROR_LOG
        paths = self.config.get('paths', {})
        DATA_ROOT = paths.get('data_root', DEFAULT_DATA_ROOT)
        LOG_DIR = paths.get('log_dir', DEFAULT_LOG_DIR)
        MAIN_DATA_DIR = paths.get('main_data_dir', DEFAULT_MAIN_DATA_DIR)
        RESTORE_DIR = paths.get('restore_dir', DEFAULT_RESTORE_DIR)
        DATA_FILE = os.path.join(MAIN_DATA_DIR, "data.json")
        LOG_FILE = os.path.join(LOG_DIR, "operations.log")
        ERROR_LOG = os.path.join(LOG_DIR, "error.log")
        
        for d in [LOG_DIR, MAIN_DATA_DIR, RESTORE_DIR]:
            if not os.path.exists(d):
                try:
                    os.makedirs(d)
                except:
                    pass

    # ====== API查询相关方法 ======
    def _load_telecode_map(self):
        """从12306官方接口加载站名-电报码映射"""
        try:
            url = "https://kyfw.12306.cn/otn/resources/js/framework/station_name.js"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                text = resp.text
                match = re.search(r"var station_names\s*=\s*'([^']+)'", text)
                if match:
                    data_str = match.group(1)
                    records = data_str.split('@')
                    for rec in records:
                        if not rec:
                            continue
                        parts = rec.split('|')
                        if len(parts) >= 3:
                            name = parts[1]
                            telecode = parts[2]
                            self._telecode_cache[name] = telecode
                    self._telecode_loaded = True
                    print(f"✅ 已加载 {len(self._telecode_cache)} 个车站电报码")
                else:
                    print("⚠️ 未找到 station_names 数据")
            else:
                print(f"⚠️ 获取电报码失败，状态码: {resp.status_code}")
        except Exception as e:
            print(f"⚠️ 加载电报码异常: {e}")

    def get_telecode(self, station_name):
        """获取站名对应的电报码，若未加载则同步加载"""
        if not self._telecode_loaded:
            self._load_telecode_map()
        return self._telecode_cache.get(station_name)

    def query_train_from_v2(self, train_number: str) -> tuple:
        """
        实时调用 V2 接口查询车次主数据。
        返回 (data, error_type, error_msg)
        data: V2 返回的原始 data 对象（含 timetable），若成功
        error_type: 'success', 'notfound', 'timeout', 'error'
        """
        # ====== 记录查询操作 ======
        self.log_action("服务器端通过V2查询车次", train_number)
        
        now = time.time()
        if train_number in self._v2_cache:
            cached_data, timestamp = self._v2_cache[train_number]
            if now - timestamp < 300:
                if cached_data is not None:
                    return cached_data, 'success', ''
                else:
                    return None, 'notfound', 'V2已重试，该车次未找到'

        try:
            data = self._get_train_main(train_number)
            if data is not None:
                self._v2_cache[train_number] = (data, now)
                return data, 'success', ''
            else:
                self._v2_cache[train_number] = (None, now)
                return None, 'notfound', 'V2已重试，该车次未找到'
        except requests.exceptions.Timeout:
            self._v2_cache[train_number] = (None, now)
            return None, 'timeout', '未找到该车次，V2未重试'
        except Exception as e:
            self._log_api_error(f"V2 查询异常 {train_number}: {e}")
            self._v2_cache[train_number] = (None, now)
            return None, 'error', '未找到该车次，V2未重试'

    def _get_train_main(self, train_num, date=None):
        """调用 V2 接口获取车次主数据"""
        api_config = self.config.get('api', {})
        api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getTrainMain"
        try:
            params = {"trainNum": train_num}
            if date:
                params["date"] = date
            resp = requests.get(api_url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data')
        except requests.exceptions.Timeout:
            self._log_api_error(f"V2 请求超时 {train_num}")
            raise
        except Exception as e:
            self._log_api_error(f"获取车次主数据失败 {train_num}: {e}")
        return None

    def _get_train_delay(self, train_num, timeout=None):
        """调用 V2 接口获取正晚点数据"""
        # ====== 记录正晚点查询 ======
        self.log_action("服务器端通过V2查询正晚点", train_num)
        
        api_config = self.config.get('api', {})
        api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getTrainDelayAll"
        try:
            params = {"trainNum": train_num}
            resp = requests.get(api_url, params=params, timeout=timeout or 10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data', [])
        except Exception as e:
            self._log_api_error(f"获取正晚点失败 {train_num}: {e}")
        return None

    def _call_v1_station_query(self, telecode: str):
        """调用 V1 车站查询接口"""
        # ====== 记录车站查询 ======
        self.log_action("服务器端通过V1查询车站", telecode)
        
        api_config = self.config.get('api', {})
        api_url = api_config.get('v1_base', 'https://data.railgo.zenglingkun.cn/api') + "/station/query"
        try:
            resp = requests.get(api_url, params={"telecode": telecode}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self._log_api_error(f"V1 车站查询失败 {telecode}: {e}")
        return None

    def _call_v1_train_query(self, train_number: str):
        """调用 V1 车次查询接口"""
        api_config = self.config.get('api', {})
        api_url = api_config.get('v1_base', 'https://data.railgo.zenglingkun.cn/api') + "/train/query"
        try:
            resp = requests.get(api_url, params={"train": train_number}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data and "timetable" in data and len(data.get("timetable", [])) >= 2:
                    return data
        except Exception as e:
            self._log_api_error(f"V1 车次查询失败 {train_number}: {e}")
        return None

    def _call_v1_sts_query(self, from_telecode: str, to_telecode: str, date: str):
        """调用 V1 站到站车次查询接口"""
        # ====== 记录站到站查询 ======
        self.log_action("服务器端通过V1站到站查询", f"{from_telecode} -> {to_telecode} ({date})")
        
        api_config = self.config.get('api', {})
        api_url = api_config.get('v1_base', 'https://data.railgo.zenglingkun.cn/api') + "/train/sts_query"
        try:
            resp = requests.get(api_url, params={"from": from_telecode, "to": to_telecode, "date": date}, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self._log_api_error(f"V1 站到站查询失败: {e}")
        return None

    def get_telecode_by_station_name(self, station_name: str):
        """通过站名获取电报码"""
        if not self._telecode_loaded:
            self._load_telecode_map()
        for name, telecode in self._telecode_cache.items():
            if name == station_name:
                return telecode
        return None

    def get_train_from_api(self, number: str):
        """从 API 获取车次数据（不经过本地）"""
        data, error_type, _ = self.query_train_from_v2(number)
        if error_type == 'success' and data is not None:
            return {
                "base_number": number,
                "type": data.get("numberKind") or data.get("type") or "未知",
                "stops": self._convert_timetable_to_stops(data.get("timetable", [])),
                "numberFull": data.get("numberFull", [number]),
                "bureau": data.get("bureauShortName", ""),
                "car": data.get("car", ""),
                "runner": data.get("runner", ""),
                "_api_data": data
            }
        return None

    def _convert_timetable_to_stops(self, timetable):
        """将 API 的 timetable 转换为内部 stops 格式"""
        if not timetable:
            return []
        stops = []
        total = len(timetable)
        for idx, stop in enumerate(timetable):
            station_name = stop.get("station", "").strip()
            if not station_name:
                continue
            arrive = stop.get("arrive", "")
            depart = stop.get("depart", "")
            day_offset = stop.get("day", 0)
            if arrive == "----":
                arrive = None
            if depart == "----":
                depart = None
            if idx == 0:
                arrive = None
            elif idx == total - 1:
                depart = None
            stops.append({
                "station_name": station_name,
                "arrive": arrive,
                "depart": depart,
                "day_offset": day_offset,
            })
        return stops

    def _physical_key_updater(self):
        while not self._physical_key_update_stop:
            try:
                self._physical_key_present = self._check_root_key()
            except:
                self._physical_key_present = False
            time.sleep(3)

    def verify_admin_card(self):
        """验证管理员 M1 卡 (4字节 UID)，持续等待直到检测到卡片"""
        uid, uid_len = self.pn532.wait_for_card()
        if uid and uid_len == 4 and uid == self.ADMIN_UID:
            return True, uid
        return False, uid

    def verify_root_card(self):
        """验证 ROOT NTAG 卡 (7字节 UID)，持续等待直到检测到卡片"""
        uid, uid_len = self.pn532.wait_for_card()
        if uid and uid_len == 7 and uid == self.ROOT_UID:
            return True, uid
        return False, uid

    def _check_root_key(self):
        uid, signature = self.pn532.read_ntag_uid_and_signature()
        if uid is None or signature is None:
            return False
        return self.config.verify_signature(uid, signature)

    def verify_admin_card(self, timeout=6):
        """
        验证管理员卡（兼容 4字节 M1 卡 和 7字节 NTAG 卡）
        持续检测直到卡片出现或超时
        返回 (是否成功, uid)
        """
        if not self.pn532:
            return False, None
        start = time.time()
        while time.time() - start < timeout:
            uid, uid_len = self.pn532.read_card_uid()
            # ===== 核心修正：取消了硬性限制 uid_len == 4，只要在名单里就通过 =====
            if uid and uid in self.ADMIN_UIDS:
                return True, uid
            time.sleep(0.2)
        return False, None

    def verify_root_card(self, timeout=6):
        """
        验证 ROOT 卡（兼容 4字节 M1 卡 和 7字节 NTAG 卡）
        持续检测直到卡片出现或超时
        返回 (是否成功, uid)
        """
        if not self.pn532:
            return False, None
        start = time.time()
        while time.time() - start < timeout:
            uid, uid_len = self.pn532.read_card_uid()
            # ===== 核心修正：取消了硬性限制 uid_len == 7，只要在名单里就通过 =====
            if uid and uid in self.ROOT_UIDS:
                return True, uid
            time.sleep(0.2)
        return False, None

    def has_permission(self, perm_key):
        """检查当前用户是否拥有指定权限"""
        if self.is_root:
            return True
        if self.is_admin:
            return perm_key in self.current_permissions
        return False

    def _get_usb_key_permissions(self):
        """保留但不使用，返回空列表"""
        return []

    def update_identity(self):
        if self.is_root:
            self.current_identity = "TADS Root"
        elif self.is_admin:
            self.current_identity = "TADS Administrator"
        elif self.is_developer:
            self.current_identity = "TADS Developer"
        else:
            self.current_identity = "普通用户"

        # ===== 身份变化 → 同步刷新 API Token =====
        if self.current_identity == "普通用户":
            # 降为普通用户：吊销 token
            if getattr(self, 'api_token', None):
                self._revoke_api_token()
        else:
            # 已提权：
            # - 身份变了（如 admin → root）→ 重新签发
            # - 身份没变但重新登录 → 续期
            if (not getattr(self, 'api_token', None)
                    or getattr(self, 'api_token_identity', None) != self.current_identity):
                self._issue_api_token()
            else:
                self.api_token_expire = time.time() + self.api_token_ttl

    def _issue_api_token(self):
        """提权成功后签发 GUI API Token，并持久化"""
        import secrets
        self.api_token = secrets.token_urlsafe(32)
        self.api_token_expire = time.time() + self.api_token_ttl
        self.api_token_identity = self.current_identity
        self._save_tokens_to_config()
        self.log_action("签发 API Token",
                        f"身份: {self.current_identity}，有效期 {self.api_token_ttl // 3600} 小时")
        return self.api_token

    def _revoke_api_token(self):
        """吊销 GUI API Token 并持久化"""
        if self.api_token:
            self.log_action("吊销 API Token", f"原身份: {self.api_token_identity}")
        self.api_token = None
        self.api_token_expire = 0.0
        self.api_token_identity = None
        self._save_tokens_to_config()

    def _issue_client_token(self, identity, permission_scope, source_ip='', card_uid=''):
        """签发客户端 Token（写入内存+config.json，并清理该 IP 下的旧 Token）"""
        import secrets
        
        # ★★★ 新增：清理同一来源 IP 的旧 Token，防止重启后堆积
        if source_ip:
            for old_token, entry in list(self.client_tokens.items()):
                if entry.get('source_ip') == source_ip:
                    self.client_tokens.pop(old_token, None)
                    
        token = secrets.token_urlsafe(32)
        now = time.time()
        self.client_tokens[token] = {
            'identity': identity,
            'permissions': list(permission_scope),
            'expire': now + self.client_token_ttl,
            'issued_at': now,
            'source': 'client',
            'source_ip': source_ip or '',
            'card_uid': (card_uid or '').upper(),
        }
        expired = [t for t, e in self.client_tokens.items() if e.get('expire', 0) <= now]
        for t in expired:
            self.client_tokens.pop(t, None)
        self._save_tokens_to_config()
        return token

    def _check_client_token(self, token):
        """校验客户端 Token，返回 entry dict 或 None"""
        if not token:
            return None
        entry = self.client_tokens.get(token)
        if not entry:
            return None
        if time.time() > entry.get('expire', 0):
            self.client_tokens.pop(token, None)
            self._save_tokens_to_config()
            return None
        return entry

    def _check_api_token(self):
        """
        校验当前请求携带的 X-TADS-Token（兼容 GUI token + 客户端 token）。
        返回 dict：
            {'identity': 'TADS Root'/'TADS Administrator'/'TADS Developer',
             'permissions': ['*'] 或 [...] 或 [],
             'source': 'gui'/'client'}
        或 None（未授权）。
        """
        import hmac

        # ★★★ 新增：任何请求先检查配置版本是否变更
        if self._check_config_version_and_revoke():
            return None

        try:
            token = request.headers.get('X-TADS-Token', '') or ''
        except Exception:
            return None
        if not token:
            return None

        try:
            token = request.headers.get('X-TADS-Token', '') or ''
        except Exception:
            return None
        if not token:
            return None

        # 1. 客户端 token（通过 /api/auth/login 签发，持久化）
        client_entry = self._check_client_token(token)
        if client_entry:
            return {
                'identity': client_entry.get('identity', 'API客户端'),
                'permissions': client_entry.get('permissions', []) or [],
                'source': 'client',
            }

        # 2. GUI token（本地提权时签发）
        if self.api_token and time.time() <= self.api_token_expire:
            try:
                if hmac.compare_digest(token, self.api_token):
                    if self.is_root:
                        return {'identity': 'TADS Root', 'permissions': ['*'], 'source': 'gui'}
                    elif self.is_admin:
                        return {'identity': 'TADS Administrator',
                                'permissions': list(self.current_permissions), 'source': 'gui'}
                    elif self.is_developer:
                        return {'identity': 'TADS Developer', 'permissions': [], 'source': 'gui'}
            except Exception:
                pass

        return None

    def verify_admin(self, password):
        """
        验证管理员身份
        流程：
        1. 先从文件读取最新的管理员密码哈希
        2. 用哈希比对是否管理员通用密码
        3. 是 → 读卡验证 UID 是否在管理员列表中
        4. 否 → 读卡获取 UID，查专属密码比对
        """
        self.write_log(f"=== 开始管理员验证 ===")
        
        # 从文件读取最新的管理员密码哈希
        admin_password_hash = self._get_admin_password_hash()
        
        # 流程 A：先判断是不是管理员通用密码
        if verify_password(password, admin_password_hash):
            self.write_log("管理员通用密码匹配，开始读卡验证 UID...")
            card_uid = self._wait_for_card_uid()
            if not card_uid:
                self.write_log("读卡失败")
                return False
            
            admin_uids = self._get_admin_uids()
            
            if card_uid in admin_uids:
                self.is_admin = True
                self.is_developer = False
                self.is_root = False
                self.current_permissions = self.ADMIN_FIXED_PERMISSIONS.copy()
                self.current_uid = card_uid
                self.update_identity()
                self.log_action("验证通过", f"管理员 (UID: {card_uid}, 通用密码)")
                self.config_version_at_login = self._get_config_version()
                self._start_config_version_monitor()
                self.write_log("✅ 管理员提权成功（通用密码）")
                return True
            else:
                self.write_log(f"❌ UID {card_uid} 不在管理员列表中")
                return False

        # 流程 B：不是管理员通用密码，尝试专属密码
        self.write_log("不是管理员通用密码，尝试专属密码...")
        card_uid = self._wait_for_card_uid()
        if not card_uid:
            self.write_log("读卡失败")
            return False

        admin_uids = self._get_admin_uids()
        if card_uid not in admin_uids:
            self.write_log(f"UID {card_uid} 不在管理员列表中")
            return False

        stored_pwd = self.get_uid_password(card_uid)
        if not stored_pwd:
            self.write_log(f"UID {card_uid} 没有设置专属密码")
            return False

        if password == stored_pwd:
            self.is_admin = True
            self.is_developer = False
            self.is_root = False
            self.current_permissions = self.ADMIN_FIXED_PERMISSIONS.copy()
            self.current_uid = card_uid
            self.update_identity()
            self.log_action("验证通过", f"管理员 (UID: {card_uid}, 专属密码)")
            self.config_version_at_login = self._get_config_version()
            self._start_config_version_monitor()
            self.write_log("✅ 管理员提权成功（专属密码）")
            return True
        else:
            self.write_log("❌ 专属密码不匹配")
            return False

    def verify_root(self, password):
        """
        验证 ROOT 身份
        流程：
        1. 先从文件读取最新的 ROOT 密码哈希
        2. 用哈希比对是否 ROOT 通用密码
        3. 是 → 读卡验证 UID 是否在 ROOT 列表中
        4. 否 → 读卡获取 UID，查专属密码比对
        """
        self.write_log(f"=== 开始 ROOT 验证 ===")
        
        # 从文件读取最新的 ROOT 密码哈希
        root_password_hash = self._get_root_password_hash()
        
        # 流程 A：先判断是不是 ROOT 通用密码
        if verify_password(password, root_password_hash):
            self.write_log("ROOT 通用密码匹配，开始读卡验证 UID...")
            card_uid = self._wait_for_card_uid()
            if not card_uid:
                self.write_log("读卡失败")
                return False
            
            root_uids = self._get_root_uids()
            
            if card_uid in root_uids:
                self.is_root = True
                self.is_admin = True
                self.is_developer = False
                self.current_permissions = []
                self.current_uid = card_uid
                self.update_identity()
                self.log_action("验证通过", f"ROOT (UID: {card_uid}, 通用密码)")
                self.config_version_at_login = self._get_config_version()
                self._start_config_version_monitor()
                self.write_log("✅ ROOT 提权成功（通用密码）")
                return True
            else:
                self.write_log(f"❌ UID {card_uid} 不在 ROOT 列表中")
                return False

        # 流程 B：不是 ROOT 通用密码，尝试专属密码
        self.write_log("不是 ROOT 通用密码，尝试专属密码...")
        card_uid = self._wait_for_card_uid()
        if not card_uid:
            self.write_log("读卡失败")
            return False

        root_uids = self._get_root_uids()
        if card_uid not in root_uids:
            self.write_log(f"UID {card_uid} 不在 ROOT 列表中")
            return False

        stored_pwd = self.get_uid_password(card_uid)
        if not stored_pwd:
            self.write_log(f"UID {card_uid} 没有设置专属密码")
            return False

        if password == stored_pwd:
            self.is_root = True
            self.is_admin = True
            self.is_developer = False
            self.current_permissions = []
            self.current_uid = card_uid
            self.update_identity()
            self.log_action("验证通过", f"ROOT (UID: {card_uid}, 专属密码)")
            self.config_version_at_login = self._get_config_version()
            self._start_config_version_monitor()
            self.write_log("✅ ROOT 提权成功（专属密码）")
            return True
        else:
            self.write_log("❌ 专属密码不匹配")
            return False

    def _get_admin_password_hash(self):
        """从 config.json 读取最新的管理员密码哈希"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('admin_password_hash', '')
        except Exception as e:
            self.write_error_log(f"读取管理员密码哈希失败: {e}")
        return ''

    def _get_root_password_hash(self):
        """从 config.json 读取最新的 ROOT 密码哈希"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('root_password_hash', '')
        except Exception as e:
            self.write_error_log(f"读取 ROOT 密码哈希失败: {e}")
        return ''

    def verify_developer(self, password, username):
        """
        开发者身份验证（新机制）：
        - 只允许开发者账号 + 专属密码
        - 用户名即 key_status.env 中的 UID（permission=Developer）
        - 通用密码（developer_password_hash）路径已废弃，不再使用
        - 成功日志带用户名原文，用于统计最近4小时使用
        """
        self.write_log(f"=== 开始开发者验证 ===")
        self.write_log(f"用户名: {username}")

        username = (username or "").strip()
        if not username:
            self.write_log("❌ 用户名为空")
            return False

        try:
            key_status = {}
            if os.path.exists(KEY_STATUS_FILE):
                with open(KEY_STATUS_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split('|')
                        if len(parts) >= 5:
                            uid = parts[0].strip()
                            permission = parts[2].strip()
                            enabled = parts[4].strip().upper() == 'TRUE'
                            key_status[uid] = {
                                'permission': permission,
                                'enabled': enabled
                            }
            else:
                self.write_log("❌ key_status.env 不存在")
                return False

            info = key_status.get(username)
            if not info:
                self.write_log(f"❌ 用户名 {username} 未注册")
                return False
            if info['permission'] != 'Developer':
                self.write_log(f"❌ 用户名 {username} 不是开发者账号")
                return False
            if not info['enabled']:
                self.write_log(f"❌ 开发者账号 {username} 已被禁用")
                return False

            if not os.path.exists(CONFIG_FILE):
                self.write_log("❌ config.json 不存在")
                return False

            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            uid_passwords = config.get('uid_passwords', {})
            encrypted_pwd = uid_passwords.get(username)
            if not encrypted_pwd:
                self.write_log(f"❌ 开发者 {username} 未设置专属密码")
                return False

            decrypted = decrypt_password(encrypted_pwd, self.uid_encryption_key)
            if decrypted and password == decrypted:
                self.is_developer = True
                self.is_admin = False
                self.is_root = False
                self.current_permissions = []
                self.current_uid = username
                self.update_identity()
                self.log_action("验证通过", f"开发者 (用户名: {username}, 专属密码)")
                self.config_version_at_login = self._get_config_version()
                self._start_config_version_monitor()
                self.write_log(f"✅ 开发者提权成功：{username}")
                return True
            else:
                self.write_log(f"❌ 密码错误")
                return False
        except Exception as e:
            self.write_error_log(f"开发者验证失败: {e}")
            self.write_log(f"异常: {e}")
            return False

    def _get_developer_password_hash(self):
        """从 config.json 读取最新的开发者密码哈希"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('developer_password_hash', '')
        except Exception as e:
            self.write_error_log(f"读取开发者密码哈希失败: {e}")
        return ''

    def _get_uid_encryption_key(self):
        """从 config.json 获取或生成固定的 UID 加密密钥（Base64 编码的 32 字节密钥）"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                key_b64 = config.get('uid_encryption_key', '')
                if key_b64:
                    return base64.b64decode(key_b64)
        except Exception as e:
            self.write_error_log(f"读取 uid_encryption_key 失败: {e}")

        # 生成新密钥
        new_key = os.urandom(32)
        key_b64 = base64.b64encode(new_key).decode('utf-8')

        # 直接修改 config.json，递增 config_version
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            else:
                config = {}
            
            config['uid_encryption_key'] = key_b64
            # 递增版本号（新增加密密钥属于物理密钥相关变更）
            config['config_version'] = config.get('config_version', 0) + 1
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.write_error_log(f"保存 uid_encryption_key 失败: {e}")
            raise

        self.write_log("已生成新的固定 UID 加密密钥")
        return new_key

    def get_uid_password(self, uid):
        """从 config.json 获取 UID 对应的密码（使用固定密钥解密）"""
        uid = uid.upper()
        try:
            if not os.path.exists(CONFIG_FILE):
                self.write_log(f"get_uid_password: 配置文件不存在 {CONFIG_FILE}")
                return None

            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)

            encrypted = config.get('uid_passwords', {}).get(uid, '')

            if not encrypted:
                return None

            # 输出密钥的 Base64 值，方便对比
            key_b64 = base64.b64encode(self.uid_encryption_key).decode('utf-8')

            # 使用固定密钥解密
            plain = decrypt_password(encrypted, self.uid_encryption_key)
            return plain

        except ValueError as e:
            self.write_error_log(f"解密失败 {uid}: {e}")
            self.write_log(f"解密失败 {uid}: {e}")
            return None
        except Exception as e:
            self.write_error_log(f"获取 UID 密码失败 {uid}: {e}")
            self.write_log(f"get_uid_password 异常: {e}")
            return None

    def get_uid_permission(self, uid):
        """从 key_status.env 获取 UID 的权限等级"""
        uid = uid.upper()
        try:
            if not os.path.exists(KEY_STATUS_FILE):
                return None
            
            with open(KEY_STATUS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('|')
                    if len(parts) >= 3 and parts[0].strip().upper() == uid:
                        return parts[2].strip()
        except Exception as e:
            self.write_error_log(f"获取 UID 权限失败 {uid}: {e}")
        return None

    def _get_current_card_uid(self):
        """获取当前刷卡读取到的 UID"""
        try:
            uid, uid_len = self.pn532.read_card_uid()
            if uid:
                return uid.upper()
        except Exception as e:
            self.write_error_log(f"读取当前物理密钥 UID 失败: {e}")
        return None

    def _start_config_version_monitor(self):
        self.write_log(f"=== 启动配置版本监控 ===")
        self.write_log(f"身份: {'管理员' if self.is_admin else '普通'}, ROOT: {self.is_root}")
        
        # 不管线程是否存在，都重新启动
        self._version_monitor_stop = True
        if self._version_monitor_thread is not None:
            try:
                self._version_monitor_thread.join(timeout=0.5)
            except:
                pass
            self._version_monitor_thread = None
        
        # 只有管理员或 ROOT 才启动监控
        if not (self.is_admin or self.is_root):
            self.write_log("配置版本监控未启动：当前不是管理员或ROOT")
            return
        
        self.config_version_at_login = self._get_config_version()
        self._version_monitor_stop = False
        self._version_monitor_thread = threading.Thread(
            target=self._monitor_config_version,
            daemon=True
        )
        self._version_monitor_thread.start()
        self.write_log(f"配置版本监控已启动，当前版本: {self.config_version_at_login}")

    def _get_config_version(self):
        """读取 config.json 中的 config_version"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('config_version', 0)
        except Exception as e:
            self.write_error_log(f"读取 config_version 失败: {e}")
        return 0

    def _monitor_config_version(self):
        self.write_log("=== 版本监控线程已启动 ===")
        while not self._version_monitor_stop:
            time.sleep(5)
            try:
                if not (self.is_admin or self.is_root):
                    continue
                current_version = self._get_config_version()
                if current_version != self.config_version_at_login:
                    self.write_log(f"检测到版本变化: {self.config_version_at_login} -> {current_version}")
                    if self.main_window:
                        self.main_window.after(0, self._force_logout)
                    break
            except Exception as e:
                self.write_error_log(f"版本号监控异常: {e}")
                time.sleep(5)
            
    def _force_logout(self):
        """强制退出登录（由版本号变更触发）"""
        self.write_log("=== 强制退出登录 ===")
        
        # 停止监控线程
        self._version_monitor_stop = True
        if self._version_monitor_thread:
            try:
                self._version_monitor_thread.join(timeout=0.5)
            except:
                pass
            self._version_monitor_thread = None
        
        # 重置身份
        self.is_admin = False
        self.is_developer = False
        self.is_root = False
        self.current_identity = "普通用户"
        self.current_permissions = []
        self.current_uid = None
        self.config_version_at_login = None
        self.update_identity()
        
        self.log_action("强制退出登录", "检测到配置版本变更")
        
        if self.main_window:
            self.main_window.refresh_status()
            self.main_window.update_edit_permission()
            self.main_window.show_temp_message("⚠️ 登录过期，请重新登录", 5000)
            
            # 需要关闭的标签页关键词列表
            close_keywords = ["编辑", "设置", "日志", "还原点"]
            
            tabs_to_close = []
            for tid, data in self.main_window.tabs.items():
                title = data['title']
                # 检查标题是否包含任一关键词
                should_close = False
                for keyword in close_keywords:
                    if keyword in title:
                        should_close = True
                        break
                if should_close:
                    tabs_to_close.append(tid)
            
            for tid in tabs_to_close:
                self.main_window.close_tab(tid)
            
            messagebox.showwarning(
                "登录过期", 
                "您的登录状态已过期。\n请重新登录以继续操作。",
                parent=self.main_window
            )

    # ====== 数据管理 ======
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                return
            except json.JSONDecodeError as e:
                self.write_error_log(f"data.json 损坏: {e}")
                # 备份损坏文件
                corrupt_path = DATA_FILE + ".corrupt"
                try:
                    os.rename(DATA_FILE, corrupt_path)
                except:
                    pass
                # 弹窗提示（如果有GUI）
                try:
                    messagebox.showerror(
                        "数据文件损坏",
                        f"data.json 已损坏，已备份为 {corrupt_path}\n"
                        "请从还原点恢复数据后重新启动程序。"
                    )
                except:
                    pass
                self.data = None
                return
            except Exception as e:
                self.write_error_log(f"加载 data.json 失败: {e}")
                self.data = None
                return
        # 只有文件不存在时才创建新数据
        self.data = {
            "version": "1.0",
            "last_updated": datetime.datetime.now().isoformat(),
            "stations": [],
            "trains": []
        }
        self.save_data()

    def _verify_usb_key(self):
        # 不再用于权限分配，保留空实现
        return False

    def save_data(self):
        """保存数据到文件（带文件锁，防止并发写入损坏）"""
        if not self.data:
            return False
        
        temp_file = DATA_FILE + ".tmp"
        lock_file = DATA_FILE + ".lock"
        lock_fd = None
        
        # 尝试获取文件锁（最多等待 3 秒）
        for attempt in range(30):
            try:
                if os.name == 'nt':
                    import msvcrt
                    lock_fd = open(lock_file, 'w')
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    lock_fd = open(lock_file, 'w')
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break  # 获得锁，跳出循环
            except (IOError, OSError, PermissionError):
                # 锁被占用，等待 0.1 秒后重试
                if lock_fd:
                    try:
                        lock_fd.close()
                    except:
                        pass
                    lock_fd = None
                time.sleep(0.1)
                continue
        
        if lock_fd is None:
            self.write_error_log("保存数据失败：获取文件锁超时（3秒）")
            return False
        
        try:
            # 写入临时文件
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            
            # 验证写入是否有效
            with open(temp_file, 'r', encoding='utf-8') as f:
                json.load(f)
            
            # 原子替换
            os.replace(temp_file, DATA_FILE)
            return True
            
        except Exception as e:
            self.write_error_log(f"保存数据失败: {e}")
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            return False
            
        finally:
            # 释放锁
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
            except:
                pass
            try:
                if os.path.exists(lock_file):
                    os.remove(lock_file)
            except:
                pass

    def update_restore_points(self):
        if not os.path.exists(RESTORE_DIR):
            os.makedirs(RESTORE_DIR)
        self.restore_points = [os.path.splitext(f)[0] for f in os.listdir(RESTORE_DIR) if f.endswith('.json')]

    def update_stats(self):
        try:
            if not self.data or 'stations' not in self.data or 'trains' not in self.data:
                self.stats = None
                return
            station_count = len(self.data['stations'])
            train_count = len(self.data['trains'])
            total_stops = 0
            station_freq = {}
            for train in self.data['trains']:
                stops = train.get('stops', [])
                if stops:
                    total_stops += len(stops)
                    for stop in stops:
                        sid = stop['station_id']
                        station_freq[sid] = station_freq.get(sid, 0) + 1
            avg_stops = round(total_stops / train_count, 1) if train_count else 0
            busy_id = None
            busy_count = 0
            for sid, cnt in station_freq.items():
                if cnt > busy_count:
                    busy_count = cnt
                    busy_id = sid
            busy_name = self.get_station_name_by_id(busy_id) if busy_id else None
            self.stats = {
                'station_count': station_count,
                'train_count': train_count,
                'avg_stops': avg_stops,
                'busy_station_name': busy_name,
                'busy_station_count': busy_count
            }
        except Exception as e:
            self.write_error_log(f"更新统计信息失败: {e}")
            self.stats = None

    # ====== 合并组管理 ======
    def _compute_merged_groups(self):
        """
        计算所有合并组。
        返回列表，每个元素为：
            {
                'display_name': 'A/B/C',
                'numbers': ['A', 'B', 'C'],
                'representative': 代表车次的 train 字典,
                'stops': 停站列表,
                'train_ids': [id1, id2, ...]
            }
        """
        groups = {}
        for train in self.data.get('trains', []):
            stops = train.get('stops', [])
            # 生成签名（包含关键字段）
            sig = json.dumps([
                (s['station_id'], s.get('arrive'), s.get('depart'), s.get('day_offset', 0))
                for s in stops
            ], sort_keys=False)
            groups.setdefault(sig, []).append(train)

        merged = []
        for sig, trains in groups.items():
            if not trains:
                continue
            # 按车次号排序
            trains_sorted = sorted(trains, key=lambda t: t['base_number'])
            numbers = [t['base_number'] for t in trains_sorted]
            display_name = '/'.join(numbers) if len(numbers) > 1 else numbers[0]
            representative = trains_sorted[0]  # 代表车次
            merged.append({
                'display_name': display_name,
                'numbers': numbers,
                'representative': representative,
                'stops': representative['stops'],
                'train_ids': [t['train_id'] for t in trains_sorted]
            })
        return merged

    def get_merged_by_number(self, number, use_api=None):
        if use_api is None:
            use_api = self.use_api_query

        # 1. 先查本地合并组
        for group in self.merged_groups:
            if number in group['numbers']:
                return group

        # 2. 如果开启了 API 查询，从 API 获取合并组
        if use_api:
            api_train = self.get_train_from_api(number)
            if api_train:
                return {
                    'display_name': '/'.join(api_train.get('numberFull', [number])),
                    'numbers': api_train.get('numberFull', [number]),
                    'representative': api_train,
                    'stops': api_train.get('stops', []),
                    'train_ids': []
                }

        # 3. 本地没有，使用合并逻辑（不调用 get_merged_by_number）
        merged = self.get_train_with_merge(number, use_api=use_api)
        if merged:
            return merged

        # 4. 兜底：通过 get_train 获取单列车（本地或V2）
        train = self.get_train(number, use_api=use_api)
        if train:
            return {
                'display_name': number,
                'numbers': [number],
                'representative': train,
                'stops': train.get('stops', []),
                'train_ids': [train.get('train_id', 0)]
            }
        return None

    def get_all_train_displays(self):
        """返回所有展示项（包括合并组和单组），用于列表显示"""
        return self.merged_groups  # 已经包含了单组

    # ====== 车次操作 ======
    def add_train(self, number):
        if not number or re.search(r'[<>:"/\\|?*]', number):
            return False
        if any(t['base_number'] == number for t in self.data.get('trains', [])):
            return False
        new_id = 1
        if self.data['trains']:
            new_id = max(t['train_id'] for t in self.data['trains']) + 1
        new_train = {
            'train_id': new_id,
            'base_number': number,
            'type': "未知",
            'start_station': None,
            'end_station': None,
            'stops': []
        }
        self.data['trains'].append(new_train)
        self.save_data()
        self.update_stats()
        self.log_action("服务器端新增车次", f"{number} (编号{new_id})")
        self.merged_groups = self._compute_merged_groups()
        return True

    def delete_train(self, number):
        train = self.get_train(number)
        if not train:
            return False
        self.data['trains'] = [t for t in self.data['trains'] if t['train_id'] != train['train_id']]
        self.save_data()
        self.update_stats()
        self.log_action("服务器端删除车次", number)
        self.merged_groups = self._compute_merged_groups()
        return True

    def add_stop(self, train_number, station_name, arrive, depart, day_offset):
        train = self.get_train(train_number)
        if not train:
            return False
        sid = self.get_station_id_by_name(station_name)
        if sid is None:
            new_sid = 1
            if self.data['stations']:
                new_sid = max(s['id'] for s in self.data['stations']) + 1
            self.data['stations'].append({'id': new_sid, 'name': station_name})
            sid = new_sid
        stop = {
            'station_id': sid,
            'station_name': station_name,
            'arrive': arrive if arrive else None,
            'depart': depart if depart else None,
            'day_offset': day_offset
        }
        train['stops'].append(stop)
        if len(train['stops']) == 1:
            train['start_station'] = sid
        train['end_station'] = sid
        self.save_data()
        self.update_stats()
        self.log_action("服务器端录入经停站", f"{train_number} 添加车站 {station_name}")
        self.merged_groups = self._compute_merged_groups()
        return True

    def delete_stop(self, train_number, index):
        train = self.get_train(train_number)
        if not train:
            return False
        if index < 1 or index > len(train['stops']):
            return False
        del train['stops'][index-1]
        if train['stops']:
            train['start_station'] = train['stops'][0]['station_id']
            train['end_station'] = train['stops'][-1]['station_id']
        else:
            train['start_station'] = None
            train['end_station'] = None
        self.save_data()
        self.update_stats()
        self.log_action("服务器端删除停站", f"{train_number} 序号 {index}")
        self.merged_groups = self._compute_merged_groups()
        return True

    # ====== 还原点 ======
    def add_restore_point(self, name):
        if len(self.restore_points) >= 3:
            return False
        if not name or re.search(r'[<>:"/\\|?*]', name):
            return False
        if name in self.restore_points:
            return False
        backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
        try:
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            self.restore_points.append(name)
            self.log_action("服务器端添加还原点", name)
            return True
        except:
            return False

    def restore_from_point(self, name):
        if name not in self.restore_points:
            return False
        backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
        if not os.path.exists(backup_file):
            return False
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.data = data
            self.save_data()
            self.update_stats()
            self.log_action("服务器端从还原点恢复", name)
            self.merged_groups = self._compute_merged_groups()
            return True
        except:
            return False

    def delete_restore_point(self, name):
        if name not in self.restore_points:
            return False
        backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
        if os.path.exists(backup_file):
            os.remove(backup_file)
        self.restore_points = [p for p in self.restore_points if p != name]
        self.log_action("服务器端删除还原点", name)
        return True

    def format_restore_points(self):
        try:
            for f in os.listdir(RESTORE_DIR):
                if f.endswith('.json'):
                    os.remove(os.path.join(RESTORE_DIR, f))
            self.restore_points = []
            self.log_action("服务器端格式化所有还原点")
            self.merged_groups = self._compute_merged_groups()
            return True
        except:
            return False

    # ====== 更新数据（已移除界面入口，但保留方法以防其他地方调用） ======
    def update_train_data(self):
        if not os.path.exists(RAIL_RHYTHM_ROOT):
            return {"success": False, "error": f"RailRhythm 目录不存在: {RAIL_RHYTHM_ROOT}"}
        if not os.path.exists(AUTO_UPDATE_SCRIPT):
            return {"success": False, "error": f"auto_update.py 不存在: {AUTO_UPDATE_SCRIPT}"}
        try:
            old_cwd = os.getcwd()
            os.chdir(RAIL_RHYTHM_ROOT)
            result = subprocess.run([sys.executable, AUTO_UPDATE_SCRIPT], capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                os.chdir(old_cwd)
                return {"success": False, "error": f"自动更新脚本执行失败（退出码：{result.returncode}）", "output": result.stderr}
            if not os.path.exists(TRAIN_DATA_DIR):
                os.chdir(old_cwd)
                return {"success": False, "error": f"train_data 目录不存在: {TRAIN_DATA_DIR}"}
            result2 = subprocess.run([sys.executable, CONVERT_SCRIPT, TRAIN_DATA_DIR, DATA_FILE],
                                     capture_output=True, text=True, timeout=300)
            os.chdir(old_cwd)
            if result2.returncode != 0:
                return {"success": False, "error": "数据转换失败", "output": result2.stderr}
            self.load_data()
            self.update_stats()
            self.log_action("服务器端更新列车时刻表数据", "成功")
            return {"success": True, "message": "数据更新完成"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ====== 查询 ======
    def search(self, keyword):
        results = []
        # 1. 合并车次组匹配
        for group in self.merged_groups:
            if any(re.search(re.escape(keyword), num, re.I) for num in group['numbers']):
                results.append({
                    "type": "车次组",
                    "name": group['display_name'],
                    "detail": f"包含 {len(group['numbers'])} 个车次，停靠 {len(group['stops'])} 个站"
                })
        # 2. 车站匹配（保持不变）
        for station in self.data.get('stations', []):
            if re.search(re.escape(keyword), station['name'], re.I):
                count = sum(1 for t in self.data['trains'] if any(s['station_id'] == station['id'] for s in t.get('stops', [])))
                results.append({
                    "type": "车站",
                    "name": station['name'],
                    "detail": f"有 {count} 趟车次经过"
                })
        return results

    def get_train(self, number, use_api=None):
        if use_api is None:
            use_api = self.use_api_query

        # 1. 先查本地
        if self.data and 'trains' in self.data:
            for train in self.data['trains']:
                if train['base_number'] == number:
                    return train

        # 2. 如果开启了 API 查询，从 API 获取
        if use_api:
            try:
                api_train = self.get_train_from_api(number)
                if api_train:
                    return api_train
            except Exception as e:
                self.write_error_log(f"get_train API 查询失败 {number}: {e}")

        # 3. 本地没有，调 V2 查询
        if use_api:
            try:
                data, error_type, _ = self.query_train_from_v2(number)
                if error_type == 'success' and data is not None:
                    converted = convert_to_old_format(data, number)
                    if converted:
                        converted['train_id'] = -1
                        return converted
            except Exception as e:
                self.write_error_log(f"get_train V2 查询失败 {number}: {e}")
        return None

    def get_station_id_by_name(self, name):
        if not self.data or 'stations' not in self.data:
            return None
        for s in self.data['stations']:
            if s['name'] == name:
                return s['id']
        return None

    def get_station_name_by_id(self, sid):
        if not self.data or 'stations' not in self.data:
            return None
        for s in self.data['stations']:
            if s['id'] == sid:
                return s['name']
        return None

    # ====== 电报码映射（用于车站大屏） ======
    # 已在上方定义 _load_telecode_map 和 get_telecode

    # ====== 正晚点 API ======
    # 已在上方定义 _get_train_delay

    # ====== 日志 ======
    def log_action(self, action, detail=""):
        identity = self.current_identity
        client_ip = None
        is_api = False

        try:
            if has_request_context():
                is_api = True
                client_ip = request.remote_addr or '-'
                entry = self._check_api_token()
                if entry:
                    identity = entry.get('identity', 'API客户端')
                else:
                    identity = 'API未认证'
        except Exception:
            is_api = False

        if is_api and client_ip:
            msg = f"[{identity}] [来自客户端 {client_ip}] {action}"
        else:
            msg = f"[{identity}] {action}"

        if detail:
            msg += f" – {detail}"
        self.write_log(msg)

    def write_log(self, message):
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except:
            pass

    def _log_api_error(self, message):
        """仅在开启API实时查询时记录API相关错误到错误日志"""
        if self.use_api_query:
            self.write_error_log(message)

    def write_error_log(self, message):
        try:
            with open(ERROR_LOG, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except:
            pass

    def get_recent_logs(self, lines=30):
        try:
            if not os.path.exists(LOG_FILE):
                return "日志文件不存在"
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                if not all_lines:
                    return "日志文件为空"
                return ''.join(all_lines[-lines:])
        except Exception as e:
            return f"读取日志失败: {e}"

    def export_logs_csv(self):
        """导出全部日志为 CSV 格式（字符串）"""
        try:
            if not os.path.exists(LOG_FILE):
                return None
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["时间", "身份", "操作", "详情"])
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    match = re.match(r'\[(.*?)\]\s*\[(.*?)\]\s*(.*?)(?:\s*–\s*(.*))?$', line)
                    if match:
                        time_str, identity, action, detail = match.groups()
                        writer.writerow([time_str, identity, action, detail or ""])
                    else:
                        writer.writerow(["", "", "", line])
            return output.getvalue()
        except Exception as e:
            return None

    # ====== 车次主数据 API ======
    # 已在上方定义 _get_train_main 和 query_train_from_v2

    # ====== V1 接口调用 ======
    # 已在上方定义 _call_v1_train_query, _call_v1_station_query, _call_v1_sts_query, get_telecode_by_station_name

    # ====== 合并逻辑（V2 查询时前后5个车次合并） ======
    def get_train_with_merge(self, number: str, use_api=None):
        if use_api is None:
            use_api = self.use_api_query

        # 1. 先查本地数据（不调用 get_merged_by_number，直接查 self.data）
        if self.data and 'trains' in self.data:
            for train in self.data['trains']:
                if train['base_number'] == number:
                    return {
                        'display_name': number,
                        'numbers': [number],
                        'representative': train,
                        'stops': train.get('stops', []),
                        'train_ids': [train.get('train_id', 0)]
                    }

        # 2. 如果开启了 API 查询，从 API 获取合并组
        if use_api:
            api_train = self.get_train_from_api(number)
            if api_train:
                return {
                    'display_name': '/'.join(api_train.get('numberFull', [number])),
                    'numbers': api_train.get('numberFull', [number]),
                    'representative': api_train,
                    'stops': api_train.get('stops', []),
                    'train_ids': []
                }

        # 3. 本地没有，查询 V2 获取原始数据（仅在API开启时）
        if use_api:
            data, error_type, _ = self.query_train_from_v2(number)
            if error_type != 'success' or data is None:
                return None

            timetable = data.get('timetable', [])
            if len(timetable) < 2:
                return None

            current_signature = self._generate_timetable_signature(timetable)

            matched_numbers = [number]
            try:
                prefix = ''.join([c for c in number if not c.isdigit()])
                num_str = ''.join([c for c in number if c.isdigit()])
                if num_str:
                    base_num = int(num_str)
                    for i in range(1, 6):
                        test_num = f"{prefix}{base_num - i}"
                        if base_num - i < 0:
                            continue
                        if test_num == number:
                            continue
                        v2_data, err_type, _ = self.query_train_from_v2(test_num)
                        if err_type == 'success' and v2_data:
                            test_timetable = v2_data.get('timetable', [])
                            if len(test_timetable) >= 2:
                                test_sig = self._generate_timetable_signature(test_timetable)
                                if test_sig == current_signature:
                                    matched_numbers.append(test_num)
                    for i in range(1, 6):
                        test_num = f"{prefix}{base_num + i}"
                        if test_num == number:
                            continue
                        v2_data, err_type, _ = self.query_train_from_v2(test_num)
                        if err_type == 'success' and v2_data:
                            test_timetable = v2_data.get('timetable', [])
                            if len(test_timetable) >= 2:
                                test_sig = self._generate_timetable_signature(test_timetable)
                                if test_sig == current_signature:
                                    matched_numbers.append(test_num)
            except:
                pass

            def sort_key(x):
                prefix_part = ''.join([c for c in x if not c.isdigit()])
                num_part = int(''.join([c for c in x if c.isdigit()]) or 0)
                return (prefix_part, num_part)
            matched_numbers = sorted(matched_numbers, key=sort_key)

            converted = convert_to_old_format(data, number)
            if not converted:
                return None

            display_name = '/'.join(matched_numbers) if len(matched_numbers) > 1 else matched_numbers[0]
            return {
                'display_name': display_name,
                'numbers': matched_numbers,
                'representative': converted,
                'stops': converted.get('stops', []),
                'train_ids': []
            }

        return None

    def _generate_timetable_signature(self, timetable: List[Dict]) -> str:
        """
        生成时刻表签名，用于比较两个车次的停站是否相同
        """
        sig = []
        for stop in timetable:
            station = stop.get('station') or ''
            arrive = stop.get('arrive') or ''
            depart = stop.get('depart') or ''
            day = stop.get('day') or 0
            sig.append(f"{station}|{arrive}|{depart}|{day}")
        return '||'.join(sig)

    # ====== 批量导入/更新车次（新增） ======
    def batch_import_train(self, train_number: str, api_type: str = "V2", auto_update: bool = False) -> tuple:
        """
        从 API 抓取车次全部经停站，本地存在则更新，不存在则新增
        返回 (success, message, stop_count)
        :param auto_update: 是否为自动更新（仅影响日志描述和临时消息）
        """
        try:
            if api_type == "V1":
                data = self._call_v1_train_query(train_number)
                if not data:
                    return False, "V1接口未返回数据", 0
                timetable = data.get("timetable", [])
                if len(timetable) < 2:
                    return False, "该车次停站不足2个", 0
                stops = []
                total = len(timetable)
                for idx, stop in enumerate(timetable):
                    station_name = stop.get("station", "").strip()
                    if not station_name:
                        continue
                    arrive = stop.get("arrive", "")
                    depart = stop.get("depart", "")
                    day_offset = stop.get("day", 0)
                    if arrive == "----":
                        arrive = None
                    if depart == "----":
                        depart = None
                    if idx == 0:
                        arrive = None
                    elif idx == total - 1:
                        depart = None
                    stops.append({
                        "station_name": station_name,
                        "arrive": arrive,
                        "depart": depart,
                        "day_offset": day_offset,
                    })
                train_type = data.get("type") or data.get("numberKind") or "未知"
            else:
                v2_data, error_type, error_msg = self.query_train_from_v2(train_number)
                if error_type != 'success' or v2_data is None:
                    return False, f"V2接口错误: {error_msg}", 0
                timetable = v2_data.get("timetable", [])
                if len(timetable) < 2:
                    return False, "该车次停站不足2个", 0
                stops = []
                total = len(timetable)
                for idx, stop in enumerate(timetable):
                    station_name = stop.get("station", "").strip()
                    if not station_name:
                        continue
                    arrive = stop.get("arrive", "")
                    depart = stop.get("depart", "")
                    day_offset = stop.get("day", 0)
                    if arrive == "----":
                        arrive = None
                    if depart == "----":
                        depart = None
                    if idx == 0:
                        arrive = None
                    elif idx == total - 1:
                        depart = None
                    stops.append({
                        "station_name": station_name,
                        "arrive": arrive,
                        "depart": depart,
                        "day_offset": day_offset,
                    })
                train_type = v2_data.get("numberKind") or v2_data.get("type") or "未知"

            if not stops:
                return False, "未解析到有效停站", 0

            # ====== 验证数据完整性：停站数至少2个 ======
            if len(stops) < 2:
                return False, "停站数据不完整（少于2站），拒绝保存", 0

            existing_train = None
            for t in self.data['trains']:
                if t['base_number'] == train_number:
                    existing_train = t
                    break

            station_ids = {}
            for stop in stops:
                name = stop["station_name"]
                if name not in station_ids:
                    sid = self.get_station_id_by_name(name)
                    if sid is None:
                        new_sid = 1
                        if self.data['stations']:
                            new_sid = max(s['id'] for s in self.data['stations']) + 1
                        self.data['stations'].append({'id': new_sid, 'name': name})
                        sid = new_sid
                    station_ids[name] = sid

            stops_with_id = []
            for stop in stops:
                sid = station_ids[stop["station_name"]]
                stops_with_id.append({
                    "station_id": sid,
                    "station_name": stop["station_name"],
                    "arrive": stop["arrive"],
                    "depart": stop["depart"],
                    "day_offset": stop["day_offset"],
                })

            # ====== 再次验证：转换后停站数至少2个 ======
            if len(stops_with_id) < 2:
                return False, "停站数据不完整（少于2站），拒绝保存", 0

            if existing_train:
                existing_train['stops'] = stops_with_id
                existing_train['type'] = train_type
                if stops_with_id:
                    existing_train['start_station'] = stops_with_id[0]['station_id']
                    existing_train['end_station'] = stops_with_id[-1]['station_id']
                else:
                    existing_train['start_station'] = None
                    existing_train['end_station'] = None
                # ====== 验证数据完整性：确保有始发和终点 ======
                if existing_train['start_station'] is None or existing_train['end_station'] is None:
                    return False, "始发站或终点站为空，拒绝保存", 0
                action = "自动更新车次" if auto_update else "批量更新车次"
                self.log_action(action, f"{train_number} (从{api_type}接口)")
                self.save_data()
                self.update_stats()
                self.merged_groups = self._compute_merged_groups()
                action_msg = f"已更新车次 {train_number}，共 {len(stops_with_id)} 个停站"
                if auto_update and self.main_window:
                    self.main_window.after(0, lambda: self.main_window.show_temp_message(f"{train_number} 已更新至本地数据库"))
                return True, action_msg, len(stops_with_id)
            else:
                new_id = 1
                if self.data['trains']:
                    new_id = max(t['train_id'] for t in self.data['trains']) + 1
                new_train = {
                    'train_id': new_id,
                    'base_number': train_number,
                    'type': train_type,
                    'start_station': stops_with_id[0]['station_id'] if stops_with_id else None,
                    'end_station': stops_with_id[-1]['station_id'] if stops_with_id else None,
                    'stops': stops_with_id
                }
                # ====== 验证数据完整性：确保有始发和终点 ======
                if new_train['start_station'] is None or new_train['end_station'] is None:
                    return False, "始发站或终点站为空，拒绝保存", 0
                self.data['trains'].append(new_train)
                action = "自动新增车次" if auto_update else "批量新增车次"
                self.log_action(action, f"{train_number} (从{api_type}接口)")
                self.save_data()
                self.update_stats()
                self.merged_groups = self._compute_merged_groups()
                action_msg = f"已新增车次 {train_number}，共 {len(stops_with_id)} 个停站"
                if auto_update and self.main_window:
                    self.main_window.after(0, lambda: self.main_window.show_temp_message(f"{train_number} 已更新至本地数据库"))
                return True, action_msg, len(stops_with_id)

        except Exception as e:
            self.write_error_log(f"批量导入失败 {train_number}: {e}")
            return False, f"导入失败: {str(e)}", 0

    def _get_train_exit(self, train_num: str, station_telecode: str, date: str = None) -> dict:
        """
        调用 V2 接口获取车次在指定车站的检票口、站台、出站口信息
        返回: {"entrance": [...], "exit": [...], "platform": "7"} 或 None
        """
        # ====== 记录检票口查询 ======
        self.log_action("服务器端通过V2查询检票口", f"{train_num} @ {station_telecode}")
        
        api_config = self.config.get('api', {})
        api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getExit"
        try:
            params = {
                "trainNum": train_num,
                "stationTelecode": station_telecode
            }
            if date:
                params["date"] = date
            
            if hasattr(self, 'scraper') and self.scraper:
                resp = self.scraper.get(api_url, params=params, timeout=10)
            else:
                resp = requests.get(api_url, params=params, timeout=10)
                
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data', {})
        except Exception as e:
            self._log_api_error(f"获取检票口失败 {train_num} {station_telecode}: {e}")
        return None

    def _get_coach_pic(self, train_num: str) -> Optional[Dict]:
        """
        调用 V2 接口获取列车车厢图数据
        返回: API 返回的 data 字段内容，或 None
        """
        # ====== 记录车厢图查询 ======
        self.log_action("服务器端通过V2查询车厢图", train_num)
        
        api_config = self.config.get('api', {})
        api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getCoachPic"
        try:
            resp = requests.get(api_url, params={"train": train_num}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data')
        except Exception as e:
            self._log_api_error(f"获取列车车厢图失败 {train_num}: {e}")
        return None

    def _get_emu_running(self, keyword: str) -> tuple:
        """查询动车组运行信息，返回 (data, error_msg)"""
        self.log_action("服务器端通过EMU API查询动车组运行", keyword)
        
        api_config = self.config.get('api', {})
        emu_base = api_config.get('emu_base', 'https://emu.railgo.zenglingkun.cn')
        api_url = emu_base + "/api/query"
        try:
            # 超时时间限制为 15 秒
            resp = requests.get(api_url, params={"keyword": keyword}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data', []), None
                else:
                    return None, data.get('message', '外部接口返回未知错误')
            elif resp.status_code == 524:
                return None, "数据源服务器响应超时 (524)，请稍后再试"
            else:
                return None, f"数据源接口异常，状态码: {resp.status_code}"
        except requests.exceptions.Timeout:
            # 超时异常写入 error.log
            self._log_api_error(f"获取动车组运行信息超时(15s) {keyword}")
            return None, "数据源服务器响应超时，请稍后再试"
        except Exception as e:
            # 其他网络异常写入 error.log
            self._log_api_error(f"获取动车组运行信息失败 {keyword}: {e}")
            return None, f"网络连接异常: {str(e)}"

    def _get_car_info(self, car_id: str) -> Optional[Dict]:
        """
        调用配属详细信息API查询车组详细信息
        返回: data对象，包含 bureau, model, depot, trainset_manufacturer 等
        """
        self.log_action("服务器端通过EMU API查询配属详细信息", car_id)
        
        api_config = self.config.get('api', {})
        emu_base = api_config.get('emu_base', 'https://emu.railgo.zenglingkun.cn')
        api_url = emu_base + "/api/car/info"
        try:
            resp = requests.get(api_url, params={"id": car_id}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data', {})
            return None
        except Exception as e:
            self._log_api_error(f"获取配属详细信息失败 {car_id}: {e}")
            return None

    def check_pn532_connection(self):
        """独立检测PN532连接状态"""
        if not self.pn532:
            return False
        try:
            return self.pn532.check_connection()
        except:
            return False

    def get_recent_error_logs(self, lines=300):
        try:
            if not os.path.exists(ERROR_LOG):
                return "错误日志文件不存在"
            with open(ERROR_LOG, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
                if not all_lines:
                    return "错误日志文件为空"
                return ''.join(all_lines[-lines:])
        except Exception as e:
            return f"读取错误日志失败: {e}"

    def _wait_for_card_uid(self, timeout=8.0):
        """等待卡片出现并返回 UID，超时返回 None（不加 reset 避免串口假死）"""
        if not self.pn532 or not self.pn532.ser:
            self.write_log("PN532 未连接，无法读卡")
            return None
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                uid, _ = self.pn532.read_card_uid()
                if uid:
                    return uid.upper()
            except Exception as e:
                self.write_error_log(f"读卡异常: {e}")
                time.sleep(0.1)
                continue
            time.sleep(0.1)
        self.write_log(f"读卡超时 ({timeout}秒)")
        return None

    def _get_admin_uids(self):
        """从 .env 读取管理员 UID 列表"""
        admin_uids = []
        try:
            if os.path.exists(ENV_FILE):
                with open(ENV_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('ADMIN_UID='):
                            val = line.split('=', 1)[1].strip()
                            if val:
                                admin_uids = [uid.strip().upper() for uid in val.split(',') if uid.strip()]
                            break
        except Exception as e:
            self.write_error_log(f"读取 ADMIN_UID 失败: {e}")
        return admin_uids

    def _get_root_uids(self):
        """从 .env 读取 ROOT UID 列表"""
        root_uids = []
        try:
            if os.path.exists(ENV_FILE):
                with open(ENV_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('ROOT_UID='):
                            val = line.split('=', 1)[1].strip()
                            if val:
                                root_uids = [uid.strip().upper() for uid in val.split(',') if uid.strip()]
                            break
        except Exception as e:
            self.write_error_log(f"读取 ROOT_UID 失败: {e}")
        return root_uids

# ================== 密钥派生函数 ==================
def _derive_network_key():
    """基于 root_password_hash 派生网络通信 AES 密钥（带缓存）"""
    # 利用 Flask 的 app 全局变量缓存
    if hasattr(app, '_cached_network_key') and app._cached_network_key:
        return app._cached_network_key

    root_hash = tads_app.config.get('root_password_hash', '')
    if not root_hash:
        return None
        
    salt = b"TADS_NETWORK_SALT_v1"
    app._cached_network_key = hashlib.pbkdf2_hmac('sha256', root_hash.encode('utf-8'), salt, 100000, 32)
    return app._cached_network_key

# ================== Flask API 服务 ==================
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

tads_app = None

import io
from werkzeug.datastructures import ImmutableMultiDict

@app.before_request
def decrypt_request_payload():
    """自动解密客户端发来的加密请求体（底层无缝替换，业务代码无需修改）"""
    if request.method in ['POST', 'PUT', 'DELETE'] and request.is_json:
        data = request.get_json(silent=True)
        if isinstance(data, dict) and 'encrypted_payload' in data:
            key = _derive_network_key()
            if key:
                try:
                    encrypted_data = base64.b64decode(data['encrypted_payload'])
                    nonce = encrypted_data[:12]
                    ciphertext = encrypted_data[12:]
                    aesgcm = AESGCM(key)
                    decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                    
                    # ====== 核心：把明文写回请求流，实现完美篡改 ======
                    # 1. 覆盖底层的流数据
                    request.environ['wsgi.input'] = io.BytesIO(decrypted_bytes)
                    request.environ['CONTENT_LENGTH'] = str(len(decrypted_bytes))
                    
                    # 2. 清除 Flask/Werkzeug 关于 body 的缓存，逼迫它重新读取
                    if hasattr(request, '_cached_data'):
                        delattr(request, '_cached_data')
                    if hasattr(request, '_cached_json'):
                        request._cached_json = (None, None)  # 清空缓存
                        
                except Exception as e:
                    return jsonify({"error": "解密失败，非法请求"}), 400
            else:
                return jsonify({"error": "服务器密钥未初始化"}), 500

@app.after_request
def encrypt_response_payload(response):
    """自动加密响应体"""
    if response.is_json:
        data = response.get_json()
        # 排除 client_config 接口，因为客户端需要它来推导密钥
        if data is not None and not response.direct_passthrough and request.path != '/api/client_config':
            key = _derive_network_key()
            if key:
                try:
                    plaintext = json.dumps(data).encode('utf-8')
                    aesgcm = AESGCM(key)
                    nonce = os.urandom(12)
                    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
                    encrypted_b64 = base64.b64encode(nonce + ciphertext).decode('utf-8')
                    response.set_data(json.dumps({"encrypted_payload": encrypted_b64}))
                except Exception:
                    pass
    return response


def require_permission(perm_key):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token_entry = tads_app._check_api_token()
            if not token_entry:
                return jsonify({
                    "error": "未授权",
                    "detail": "缺少或无效的 X-TADS-Token 请求头"
                }), 401

            ident = token_entry.get('identity', '')
            perms = token_entry.get('permissions', []) or []

            if ident == "TADS Root" or '*' in perms:
                return f(*args, **kwargs)
            if ident == "TADS Administrator" and perm_key in perms:
                return f(*args, **kwargs)

            return jsonify({"error": "权限不足，您没有执行此操作的权限"}), 403
        return decorated_function
    return decorator

@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """
    客户端独立认证入口。
    请求体：{"password": "...", "card_uid": "..." 或 "username": "..." }
      - card_uid 有值：管理员/ROOT 刷卡认证
      - username 有值：开发者账号认证（不刷卡）
    """
    data = request.get_json() or {}
    password = data.get('password', '') or ''
    card_uid = (data.get('card_uid', '') or '').upper().strip()
    username = (data.get('username', '') or '').strip()

    if not password:
        return jsonify({"success": False, "error": "缺少密码"}), 400

    client_ip = request.remote_addr or '-'

    # ========== 开发者：用户名 + 密码 ==========
    if username:
        try:
            key_status = {}
            if os.path.exists(KEY_STATUS_FILE):
                with open(KEY_STATUS_FILE, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split('|')
                        if len(parts) >= 5:
                            uid = parts[0].strip()
                            permission = parts[2].strip()
                            enabled = parts[4].strip().upper() == 'TRUE'
                            key_status[uid] = {'permission': permission, 'enabled': enabled}

            info = key_status.get(username)
            if not info or info['permission'] != 'Developer' or not info['enabled']:
                tads_app.write_log(
                    f"[API认证] [来自客户端 {client_ip}] 开发者登录失败：用户名 {username} 无效或已禁用")
                return jsonify({"success": False, "error": "用户名或密码错误"}), 403

            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                uid_passwords = config.get('uid_passwords', {})
                encrypted = uid_passwords.get(username, '')
                if encrypted:
                    decrypted = decrypt_password(encrypted, tads_app.uid_encryption_key)
                    if decrypted and password == decrypted:
                        token = tads_app._issue_client_token(
                            "TADS Developer", [], client_ip, username)
                        tads_app.write_log(
                            f"[API认证] [来自客户端 {client_ip}] TADS Developer 登录成功（用户名: {username}, 专属密码）")
                        return jsonify({
                            "success": True, "token": token,
                            "identity": "TADS Developer", "username": username
                        })
        except Exception as e:
            tads_app.write_error_log(f"[API认证] 开发者认证异常: {e}")

        tads_app.write_log(
            f"[API认证] [来自客户端 {client_ip}] 开发者登录失败：用户名或密码错误")
        return jsonify({"success": False, "error": "用户名或密码错误"}), 403

    # ========== 管理员 / ROOT：刷卡 + 密码 ==========
    root_uids = tads_app._get_root_uids()
    admin_uids = tads_app._get_admin_uids()

    if card_uid:
        if card_uid in root_uids:
            root_hash = tads_app._get_root_password_hash()
            if verify_password(password, root_hash):
                token = tads_app._issue_client_token("TADS Root", ['*'], client_ip, card_uid)
                tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] TADS Root 登录成功（通用密码, UID={card_uid}）")
                return jsonify({"success": True, "token": token, "identity": "TADS Root"})
            stored_pwd = tads_app.get_uid_password(card_uid)
            if stored_pwd and password == stored_pwd:
                token = tads_app._issue_client_token("TADS Root", ['*'], client_ip, card_uid)
                tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] TADS Root 登录成功（专属密码, UID={card_uid}）")
                return jsonify({"success": True, "token": token, "identity": "TADS Root"})
            tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] TADS Root 登录失败（密码错误, UID={card_uid}）")
            return jsonify({"success": False, "error": "ROOT 认证失败"}), 403

        if card_uid in admin_uids:
            admin_hash = tads_app._get_admin_password_hash()
            if verify_password(password, admin_hash):
                token = tads_app._issue_client_token(
                    "TADS Administrator", tads_app.ADMIN_FIXED_PERMISSIONS, client_ip, card_uid)
                tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] TADS Administrator 登录成功（通用密码, UID={card_uid}）")
                return jsonify({"success": True, "token": token, "identity": "TADS Administrator"})
            stored_pwd = tads_app.get_uid_password(card_uid)
            if stored_pwd and password == stored_pwd:
                token = tads_app._issue_client_token(
                    "TADS Administrator", tads_app.ADMIN_FIXED_PERMISSIONS, client_ip, card_uid)
                tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] TADS Administrator 登录成功（专属密码, UID={card_uid}）")
                return jsonify({"success": True, "token": token, "identity": "TADS Administrator"})
            tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] TADS Administrator 登录失败（密码错误, UID={card_uid}）")
            return jsonify({"success": False, "error": "管理员认证失败"}), 403

        tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] 登录失败（UID={card_uid} 不在名单）")
        return jsonify({"success": False, "error": "该卡不在授权名单中"}), 403

    tads_app.write_log(f"[API认证] [来自客户端 {client_ip}] 登录失败（缺少 card_uid 或 username）")
    return jsonify({"success": False, "error": "认证失败"}), 403

@app.route('/api/admin/tokens/list', methods=['GET'])
@require_permission('view_config')
def api_tokens_list():
    """列出所有客户端 Token（需要 token 认证 + view_config 权限）"""
    now = time.time()
    out = []
    for tok, entry in list(tads_app.client_tokens.items()):
        if not isinstance(entry, dict):
            continue
        if entry.get('expire', 0) <= now:
            continue
        out.append({
            "token_preview": tok[:8] + "..." + tok[-4:],
            "identity": entry.get('identity', ''),
            "issued_at": entry.get('issued_at', 0),
            "expire": entry.get('expire', 0),
            "source_ip": entry.get('source_ip', ''),
            "card_uid": entry.get('card_uid', ''),
        })
    out.sort(key=lambda x: x.get('issued_at', 0), reverse=True)
    return jsonify({"success": True, "tokens": out})


@app.route('/api/admin/tokens/revoke', methods=['POST'])
@require_permission('view_config')
def api_tokens_revoke():
    """撤销一个或多个客户端 Token（需要 token 认证 + view_config 权限）"""
    data = request.get_json() or {}
    previews = data.get('token_previews', []) or []
    if not isinstance(previews, list) or not previews:
        return jsonify({"success": False, "error": "缺少 token_previews"}), 400

    revoked = 0
    for tok in list(tads_app.client_tokens.keys()):
        pv = tok[:8] + "..." + tok[-4:]
        if pv in previews:
            tads_app.client_tokens.pop(tok, None)
            revoked += 1
    if revoked:
        tads_app._save_tokens_to_config()
        tads_app.log_action("撤销客户端 Token", f"数量: {revoked}")
    return jsonify({"success": True, "revoked": revoked})

@app.route('/')
def index():
    return jsonify({
        "service": "TADS API",
        "version": "2.0",
        "status": "running",
        "endpoints": {
            "GET /api/health": "健康检查",
            "GET /api/stats": "统计信息",
            "GET /api/trains": "所有车次（精简）",
            "GET /api/train/<number>": "车次详情",
            "GET /api/stations": "所有车站",
            "GET /api/station/<name>/trains": "经过某站的车次",
            "GET /api/search?q=<keyword>": "全局搜索",
            "GET /api/logs": "最近日志（需管理员密码）",
            "GET /api/export_logs": "导出日志CSV（需管理员密码）",
            "POST /api/admin/add_train": "新增车次",
            "POST /api/admin/delete_train": "删除车次",
            "POST /api/admin/add_stop": "录入停站",
            "POST /api/admin/delete_stop": "删除停站",
            "POST /api/admin/restore/add": "添加还原点",
            "POST /api/admin/restore/apply": "从还原点恢复",
            "POST /api/admin/restore/delete": "删除还原点",
            "POST /api/admin/restore/format": "格式化所有还原点",
            "POST /api/admin/change_admin_pwd": "更改管理员密码",
            "POST /api/admin/change_root_pwd": "更改ROOT密码（需ROOT）",
            "GET /api/admin/physical_keys": "获取物理密钥名单",
            "POST /api/admin/physical_keys/add": "添加物理密钥",
            "POST /api/admin/physical_keys/delete": "删除物理密钥",
            "POST /api/admin/physical_keys/update": "更新物理密钥权限",
            "GET /api/client_config": "获取客户端配置",
            "GET /api/emu/query": "动车组运行查询",
            "GET /api/emu/car/info": "配属详细信息查询"
        }
    })

@app.route('/api/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.datetime.now().isoformat()})

@app.route('/api/stats')
def stats():
    stats = tads_app.stats
    if stats:
        return jsonify(stats)
    return jsonify({"error": "统计数据不可用"}), 500

@app.route('/api/trains')
def list_trains():
    displays = tads_app.get_all_train_displays()
    result = [{"number": d['display_name'], "stops": len(d['stops'])} for d in displays]
    return jsonify(result)

@app.route('/api/train/<string:number>')
def train_detail(number):
    source = request.args.get('source', '')
    use_api = (source == 'api') if source else tads_app.use_api_query

    tads_app.log_action("客户端通过内网API查询车次", number)

    # 1. 先查找本地合并组
    group = tads_app.get_merged_by_number(number, use_api=use_api)
    if group:
        if tads_app.auto_update_on_query and (tads_app.is_admin or tads_app.is_root):
            def do_auto_update():
                try:
                    success, msg, _ = tads_app.batch_import_train(number, "V2", auto_update=True)
                    if success and tads_app.main_window:
                        tads_app.main_window.after(0, lambda: tads_app.main_window.show_temp_message(f"{number} 已更新至本地数据库"))
                except Exception as e:
                    tads_app.write_error_log(f"API自动更新异常 {number}: {e}")
            threading.Thread(target=do_auto_update, daemon=True).start()
        return jsonify({
            "display_name": group['display_name'],
            "numbers": group['numbers'],
            "stops": group['stops']
        })

    # 2. 本地没有 → 如果 use_api，走 V2 实时查询
    if use_api:
        data, error_type, error_msg = tads_app.query_train_from_v2(number)
        if error_type == 'success':
            if tads_app.auto_update_on_query and (tads_app.is_admin or tads_app.is_root):
                def do_auto_update():
                    try:
                        success, msg, _ = tads_app.batch_import_train(number, "V2", auto_update=True)
                        if success and tads_app.main_window:
                            tads_app.main_window.after(0, lambda: tads_app.main_window.show_temp_message(f"{number} 已更新至本地数据库"))
                    except Exception as e:
                        tads_app.write_error_log(f"API自动更新异常 {number}: {e}")
                threading.Thread(target=do_auto_update, daemon=True).start()
            return jsonify({
                "display_name": number,
                "numbers": [number],
                "data": data
            })
        else:
            return jsonify({
                "error": error_msg,
                "error_type": error_type
            }), 404
    else:
        return jsonify({"error": "未找到该车次"}), 404

@app.route('/api/stations')
def list_stations():
    return jsonify(tads_app.data.get('stations', []))

@app.route('/api/station/<string:name>/trains')
def station_trains(name):
    source = request.args.get('source', '')
    use_api = (source == 'api') if source else tads_app.use_api_query

    tads_app.log_action("客户端通过内网API查询车站车次", name)

    # ====== API 实时查询模式 ======
    if use_api:
        telecode = tads_app.get_telecode(name)
        if not telecode:
            return jsonify({"error": f"未找到车站 '{name}' 的电报码"}), 404

        station_data = tads_app._call_v1_station_query(telecode)
        if not station_data or 'trains' not in station_data:
            return jsonify({"error": "获取车站数据失败"}), 500

        trains = station_data.get('trains', [])
        result = []
        for train in trains:
            result.append({
                "train": train.get('number', ''),
                "arrive": train.get('arrive', ''),
                "depart": train.get('depart', ''),
                "day_offset": 0,
                "type": train.get('type', ''),
                "numberFull": train.get('numberFull', [])
            })
        return jsonify(result)

    # ====== 本地模式 ======
    sid = tads_app.get_station_id_by_name(name)
    if sid is None:
        return jsonify({"error": "车站不存在"}), 404
    result = []
    for train in tads_app.data.get('trains', []):
        for stop in train.get('stops', []):
            if stop['station_id'] == sid:
                result.append({
                    "train": train['base_number'],
                    "arrive": stop.get('arrive'),
                    "depart": stop.get('depart'),
                    "day_offset": stop.get('day_offset', 0)
                })
                break
    return jsonify(result)

@app.route('/api/search')
def search():
    keyword = request.args.get('q', '')
    if not keyword:
        return jsonify({"error": "缺少 q 参数"}), 400
    tads_app.log_action("客户端通过内网API进行全局搜索", keyword)
    results = tads_app.search(keyword)
    return jsonify(results)

@app.route('/api/logs')
@require_permission('export_logs')
def get_logs():
    lines = int(request.args.get('lines', 30))
    logs = tads_app.get_recent_logs(lines)
    return jsonify({"logs": logs})

@app.route('/api/export_logs')
@require_permission('export_logs')
def export_logs():
    csv_data = tads_app.export_logs_csv()
    if csv_data is None:
        return jsonify({"error": "导出日志失败"}), 500
    return send_file(
        io.BytesIO(csv_data.encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"TADS_logs_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

@app.route('/api/error_logs')
@require_permission('export_logs')
def get_error_logs():
    lines = int(request.args.get('lines', 300))
    logs = tads_app.get_recent_error_logs(lines)
    return jsonify({"logs": logs})


@app.route('/api/latest_error')
def api_latest_error():
    try:
        if not os.path.exists(ERROR_LOG):
            return jsonify({"error": ""})
        with open(ERROR_LOG, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if not lines:
            return jsonify({"error": ""})
        last = lines[-1].strip()
        if re.search(r'U盘序列号|检查路径|文件存在', last):
            return jsonify({"error": ""})
        return jsonify({"error": last})
    except Exception:
        return jsonify({"error": ""})


@app.route('/api/admin/logs/clear', methods=['POST'])
def api_clear_logs():
    token_entry = tads_app._check_api_token()
    if not token_entry:
        return jsonify({"error": "未授权"}), 401
    ident = token_entry.get('identity', '')
    if ident != "TADS Root":
        return jsonify({"error": "仅ROOT可清空日志"}), 403
    
    # ★ 直接从 URL 的参数里拿，无视 JSON 加密体
    log_type = request.args.get('log_type', '')
    
    if log_type == 'normal':
        log_file = LOG_FILE
        log_name = "普通日志"
    elif log_type == 'error':
        log_file = ERROR_LOG
        log_name = "报错日志"
    else:
        return jsonify({"success": False, "error": f"无效的参数 [{log_type}]，拒绝操作"}), 400
    
    try:
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("")
            
        tads_app.log_action("清空日志", f"类型: {log_name}")
        return jsonify({"success": True, "message": f"{log_name}已清空"})
    except PermissionError:
        return jsonify({"success": False, "error": "文件被占用，请关闭正在查看该日志的编辑器后重试"}), 500
    except Exception as e:
        tads_app.write_error_log(f"清空日志失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/logs/save', methods=['POST'])
def api_save_logs():
    token_entry = tads_app._check_api_token()
    if not token_entry:
        return jsonify({"error": "未授权"}), 401
    ident = token_entry.get('identity', '')
    if ident != "TADS Root":
        return jsonify({"error": "仅ROOT可保存日志"}), 403
    
    data = request.get_json() or {}
    log_type = data.get('log_type', 'normal')
    content = data.get('content', '')
    log_file = LOG_FILE if log_type == 'normal' else ERROR_LOG
    
    try:
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(content)
            
        tads_app.log_action("保存日志", f"类型: {log_type}")
        return jsonify({"success": True, "message": "日志已保存"})
    except PermissionError:
        return jsonify({"success": False, "error": "文件被占用，请关闭正在查看该日志的编辑器后重试"}), 500
    except Exception as e:
        tads_app.write_error_log(f"保存日志失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/add_train', methods=['POST'])
@require_permission('add_train')
def api_add_train():
    data = request.get_json()
    if not data or 'number' not in data:
        return jsonify({"error": "缺少 number 字段"}), 400
    if tads_app.add_train(data['number']):
        return jsonify({"success": True, "message": f"车次 {data['number']} 已添加"})
    return jsonify({"success": False, "error": "添加失败，可能车次已存在或名称非法"}), 400

@app.route('/api/admin/delete_train', methods=['POST'])
@require_permission('delete_train')
def api_delete_train():
    data = request.get_json()
    if not data or 'number' not in data:
        return jsonify({"error": "缺少 number 字段"}), 400
    if tads_app.delete_train(data['number']):
        return jsonify({"success": True, "message": f"车次 {data['number']} 已删除"})
    return jsonify({"success": False, "error": "删除失败，车次不存在"}), 404

@app.route('/api/admin/add_stop', methods=['POST'])
@require_permission('add_stop')
def api_add_stop():
    data = request.get_json()
    required = ['train_number', 'station_name', 'arrive', 'depart', 'day_offset']
    if not data or any(k not in data for k in required):
        return jsonify({"error": f"缺少必要字段，需要 {required}"}), 400
    if tads_app.add_stop(data['train_number'], data['station_name'], data['arrive'], data['depart'], int(data['day_offset'])):
        return jsonify({"success": True, "message": f"已为 {data['train_number']} 添加停站 {data['station_name']}"})
    return jsonify({"success": False, "error": "添加停站失败，请检查车次号"}), 400

@app.route('/api/admin/delete_stop', methods=['POST'])
@require_permission('delete_stop')
def api_delete_stop():
    data = request.get_json()
    required = ['train_number', 'index']
    if not data or any(k not in data for k in required):
        return jsonify({"error": f"缺少必要字段，需要 {required}"}), 400
    if tads_app.delete_stop(data['train_number'], int(data['index'])):
        return jsonify({"success": True, "message": f"已删除 {data['train_number']} 的序号 {data['index']} 停站"})
    return jsonify({"success": False, "error": "删除失败，请检查车次号和序号"}), 400

@app.route('/api/admin/restore/add', methods=['POST'])
@require_permission('add_restore')
def api_add_restore():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "缺少 name 字段"}), 400
    if tads_app.add_restore_point(data['name']):
        return jsonify({"success": True, "message": f"还原点 {data['name']} 已添加"})
    return jsonify({"success": False, "error": "添加失败，可能已达上限、名称已存在或非法"}), 400

@app.route('/api/admin/restore/apply', methods=['POST'])
@require_permission('restore_apply')
def api_restore_apply():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "缺少 name 字段"}), 400
    if tads_app.restore_from_point(data['name']):
        return jsonify({"success": True, "message": f"已从 {data['name']} 恢复"})
    return jsonify({"success": False, "error": "恢复失败，请检查还原点名称"}), 400

@app.route('/api/admin/restore/delete', methods=['POST'])
@require_permission('restore_delete')
def api_delete_restore():
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "缺少 name 字段"}), 400
    if tads_app.delete_restore_point(data['name']):
        return jsonify({"success": True, "message": f"已删除还原点 {data['name']}"})
    return jsonify({"success": False, "error": "删除失败，还原点不存在"}), 400

@app.route('/api/admin/restore/format', methods=['POST'])
@require_permission('restore_format')
def api_format_restore():
    if tads_app.format_restore_points():
        return jsonify({"success": True, "message": "所有还原点已清空"})
    return jsonify({"success": False, "error": "格式化失败"}), 500

@app.route('/api/admin/update_data', methods=['POST'])
@require_permission('update_data')
def api_update_data():
    result = tads_app.update_train_data()
    return jsonify(result)

@app.route('/api/admin/restore/list', methods=['GET'])
@require_permission('view_config')
def api_restore_list():
    return jsonify(tads_app.restore_points)

@app.route('/api/admin/change_admin_pwd', methods=['POST'])
@require_permission('change_admin_pwd')
def api_change_admin_pwd():
    data = request.get_json()
    if not data or 'new_password' not in data:
        return jsonify({"error": "缺少 new_password 字段"}), 400
    global ADMIN_PASSWORD_HASH
    ADMIN_PASSWORD_HASH = hash_password(data['new_password'])
    tads_app.config.save()
    tads_app._increment_config_version() # ★ 新增
    tads_app.log_action("客户端通过内网API更改管理员密码", "密码已更新")
    return jsonify({"success": True, "message": "管理员密码已更改"})

@app.route('/api/admin/change_root_pwd', methods=['POST'])
@require_permission('change_root_pwd')
def api_change_root_pwd():
    data = request.get_json()
    if not data or 'new_password' not in data:
        return jsonify({"error": "缺少 new_password 字段"}), 400
    global ROOT_PASSWORD_HASH
    ROOT_PASSWORD_HASH = hash_password(data['new_password'])
    tads_app.config.save()
    tads_app._increment_config_version() # ★ 新增
    tads_app.log_action("客户端通过内网API更改ROOT密码", "密码已更新")
    return jsonify({"success": True, "message": "ROOT密码已更改"})

@app.route('/api/admin/physical_keys', methods=['GET'])
@require_permission('view_config')
def api_get_physical_keys():
    keys = tads_app.config.get_physical_keys()
    sanitized = []
    for k in keys:
        item = {key: val for key, val in k.items() if key != 'signature'}
        sanitized.append(item)
    return jsonify(sanitized)

@app.route('/api/admin/physical_keys/add', methods=['POST'])
@require_permission('key_add')
def api_add_physical_key():
    data = request.get_json()
    if not data or 'uid' not in data or 'type' not in data:
        return jsonify({"error": "缺少 uid 或 type 字段"}), 400
    key_data = {
        "uid": data['uid'],
        "type": data['type'],
        "person": data.get('person', '')
    }
    if data['type'] == 'ntag' and 'signature' in data:
        key_data['signature'] = data['signature']
    if tads_app.config.add_physical_key(key_data):
        tads_app.log_action("客户端通过内网API添加物理密钥", f"UID: {data['uid']}, 人员: {data.get('person', '')}")
        return jsonify({"success": True, "message": "物理密钥已添加"})
    return jsonify({"success": False, "error": "添加失败，可能UID已存在"}), 400
    tads_app._increment_config_version() # ★ 新增

@app.route('/api/admin/physical_keys/delete', methods=['POST'])
@require_permission('key_delete')
def api_delete_physical_key():
    data = request.get_json()
    if not data or 'uid' not in data:
        return jsonify({"error": "缺少 uid 字段"}), 400
    if tads_app.config.delete_physical_key(data['uid']):
        tads_app.log_action("客户端通过内网API删除物理密钥", f"UID: {data['uid']}")
        return jsonify({"success": True, "message": "物理密钥已删除"})
    return jsonify({"success": False, "error": "删除失败，UID不存在"}), 404
    tads_app._increment_config_version() # ★ 新增

@app.route('/api/admin/physical_keys/update', methods=['POST'])
@require_permission('key_manage')
def api_update_physical_key():
    data = request.get_json()
    if not data or 'uid' not in data:
        return jsonify({"error": "缺少 uid 字段"}), 400
    new_data = {k: v for k, v in data.items() if k != 'uid'}
    if tads_app.config.update_physical_key(data['uid'], new_data):
        tads_app.log_action("客户端通过内网API更新物理密钥", f"UID: {data['uid']}")
        return jsonify({"success": True, "message": "物理密钥已更新"})
    return jsonify({"success": False, "error": "更新失败，UID不存在"}), 404
    tads_app._increment_config_version() # ★ 新增

@app.route('/api/admin/get_uid_password', methods=['GET'])
def api_get_uid_password():
    """
    获取指定 UID 的专属密码（需要 token 认证 + 管理员/ROOT 权限）
    """
    uid = request.args.get('uid', '').strip().upper()
    if not uid:
        return jsonify({"error": "缺少 uid 参数"}), 400

    token_entry = tads_app._check_api_token()
    if not token_entry:
        return jsonify({"error": "未授权，缺少或无效的 X-TADS-Token"}), 401

    ident = token_entry.get('identity', '')
    perms = token_entry.get('permissions', []) or []
    if not (ident == "TADS Root" or '*' in perms
            or (ident == "TADS Administrator" and 'view_config' in perms)):
        return jsonify({"error": "权限不足，您没有执行此操作的权限"}), 403

    pwd = tads_app.get_uid_password(uid)
    if pwd is not None:
        return jsonify({"password": pwd})
    return jsonify({"password": ""})

@app.route('/api/admin/get_developer_uids', methods=['GET'])
def api_get_developer_uids():
    """
    获取所有开发者 UID 列表（需要 token 认证 + 管理员/ROOT 权限）
    """
    token_entry = tads_app._check_api_token()
    if not token_entry:
        return jsonify({"error": "未授权，缺少或无效的 X-TADS-Token"}), 401

    ident = token_entry.get('identity', '')
    perms = token_entry.get('permissions', []) or []
    if not (ident == "TADS Root" or '*' in perms
            or (ident == "TADS Administrator" and 'view_config' in perms)):
        return jsonify({"error": "权限不足，您没有执行此操作的权限"}), 403

    uids = []
    try:
        if os.path.exists(KEY_STATUS_FILE):
            with open(KEY_STATUS_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('|')
                    if len(parts) >= 3:
                        permission = parts[2].strip()
                        if permission == 'Developer':
                            uids.append(parts[0].strip().upper())
    except Exception as e:
        tads_app.write_error_log(f"获取开发者 UID 列表失败: {e}")
        return jsonify({"error": str(e)}), 500

    return jsonify({"uids": uids})

@app.route('/api/client_config', methods=['GET'])
def client_config():
    """
    获取客户端配置（包含 config_version）
    """
    # 获取所有管理员 UID 列表
    admin_uids = []
    admin_uid_str = tads_app.config.env.get('ADMIN_UID', '')
    if admin_uid_str:
        admin_uids = [uid.strip() for uid in admin_uid_str.split(',') if uid.strip()]
    
    # 获取所有 ROOT UID 列表
    root_uids = []
    root_uid_str = tads_app.config.env.get('ROOT_UID', '')
    if root_uid_str:
        root_uids = [uid.strip() for uid in root_uid_str.split(',') if uid.strip()]
    
    # 获取 config_version
    config_version = 0
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                config_version = config.get('config_version', 0)
    except:
        pass
    
    return jsonify({
        "com_port": tads_app.config.get('com_port', 'COM4'),
        "baudrate": tads_app.config.get('baudrate', 115200),
        "root_public_key": tads_app.config.get_public_key_b64(),
        "admin_uids": admin_uids,
        "root_uids": root_uids,
        "admin_password_hash": ADMIN_PASSWORD_HASH,
        "root_password_hash": ROOT_PASSWORD_HASH,
        "config_version": config_version
    })

# ================== V1 接口代理 ==================
@app.route('/api/v1/train/query')
def v1_train_query():
    """代理 V1 车次查询接口"""
    train = request.args.get('train')
    if not train:
        return jsonify({"error": "缺少 train 参数"}), 400
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v1_base', 'https://data.railgo.zenglingkun.cn/api') + "/train/query"
    try:
        resp = requests.get(api_url, params={"train": train}, timeout=10)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/station/query')
def v1_station_query():
    """代理 V1 车站查询接口"""
    telecode = request.args.get('telecode')
    if not telecode:
        return jsonify({"error": "缺少 telecode 参数"}), 400
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v1_base', 'https://data.railgo.zenglingkun.cn/api') + "/station/query"
    try:
        resp = requests.get(api_url, params={"telecode": telecode}, timeout=10)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/train/sts_query')
def v1_sts_query():
    """代理 V1 站到站车次查询接口"""
    from_telecode = request.args.get('from')
    to_telecode = request.args.get('to')
    date = request.args.get('date')
    if not from_telecode or not to_telecode or not date:
        return jsonify({"error": "缺少 from/to/date 参数"}), 400
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v1_base', 'https://data.railgo.zenglingkun.cn/api') + "/train/sts_query"
    try:
        resp = requests.get(api_url, params={"from": from_telecode, "to": to_telecode, "date": date}, timeout=15)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/station/telecode')
def v1_station_telecode():
    """通过站名获取电报码"""
    name = request.args.get('name')
    if not name:
        return jsonify({"error": "缺少 name 参数"}), 400
    telecode = tads_app.get_telecode_by_station_name(name)
    if telecode:
        return jsonify({"telecode": telecode})
    return jsonify({"error": "未找到电报码"}), 404


# ================== V2 接口代理 ==================
@app.route('/api/v2/getTrainMain')
def v2_get_train_main():
    """代理车次主数据查询"""
    train_num = request.args.get('trainNum')
    date = request.args.get('date')
    if not train_num:
        return jsonify({"error": "缺少 trainNum"}), 400
    tads_app.log_action("客户端通过内网API代理V2查询-车次主数据", train_num)
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getTrainMain"
    try:
        resp = requests.get(api_url, params={"trainNum": train_num, "date": date} if date else {"trainNum": train_num}, timeout=10)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"success": False, "error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/v2/getTrainDelayAll')
def v2_get_train_delay_all():
    """代理正晚点数据查询"""
    train_num = request.args.get('trainNum')
    if not train_num:
        return jsonify({"error": "缺少 trainNum"}), 400
    tads_app.log_action("客户端通过内网API代理V2查询-正晚点", train_num)
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getTrainDelayAll"
    try:
        resp = requests.get(api_url, params={"trainNum": train_num}, timeout=10)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"success": False, "error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/v2/getStationBigScreen')
def v2_get_station_big_screen():
    """代理车站大屏数据"""
    telecode = request.args.get('stationTelecode')
    kind = request.args.get('kind', 'departure')
    if not telecode:
        return jsonify({"error": "缺少 stationTelecode"}), 400

    kind_str = "出发" if kind == 'departure' else "到达"
    tads_app.log_action("客户端通过内网API代理V2查询-车站大屏", f"电报码: {telecode}, 方向: {kind_str}")
    
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getStationBigScreen"
    try:
        resp = requests.get(api_url, params={"stationTelecode": telecode, "kind": kind}, timeout=5)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"success": False, "error": f"外网请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/v2/getExit')
def v2_get_exit():
    """代理获取检票口/站台/出站口信息"""
    train_num = request.args.get('trainNum')
    station_telecode = request.args.get('stationTelecode')
    date = request.args.get('date')
    if not train_num or not station_telecode:
        return jsonify({"error": "缺少 trainNum 或 stationTelecode"}), 400
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getExit"
    try:
        params = {"trainNum": train_num, "stationTelecode": station_telecode}
        if date:
            params["date"] = date
        resp = requests.get(api_url, params=params, timeout=10)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"success": False, "error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/v2/getCoachPic')
def v2_get_coach_pic():
    """代理获取列车车厢图"""
    train_num = request.args.get('train')
    if not train_num:
        return jsonify({"error": "缺少 train 参数"}), 400
    api_config = tads_app.config.get('api', {})
    api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getCoachPic"
    try:
        resp = requests.get(api_url, params={"train": train_num}, timeout=10)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"success": False, "error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/station_info/<string:name>')
def station_info(name):
    source = request.args.get('source', '')
    use_api = (source == 'api') if source else tads_app.use_api_query

    tads_app.log_action("客户端通过内网API查询车站信息", name)

    if use_api:
        telecode = tads_app.get_telecode(name)
        if telecode:
            result = tads_app._call_v1_station_query(telecode)
            if result and 'data' in result:
                return jsonify(result['data'])
        return jsonify({"name": name, "error": "未找到详细信息"}), 404
    else:
        return jsonify({"name": name})

@app.route('/api/admin/batch_import', methods=['POST'])
@require_permission('add_train')
def api_batch_import():
    """批量导入/更新车次（从API抓取）"""
    data = request.get_json()
    train_number = data.get('train_number')
    api_type = data.get('api_type', 'V2')
    auto_update = data.get('auto_update', False)
    if not train_number:
        return jsonify({"success": False, "error": "缺少 train_number"}), 400
    success, msg, count = tads_app.batch_import_train(train_number, api_type, auto_update=auto_update)
    return jsonify({"success": success, "message": msg, "stop_count": count})

# ================== EMU API 代理 ==================
@app.route('/api/emu/query')
def emu_query():
    """代理动车组运行查询API"""
    keyword = request.args.get('keyword')
    if not keyword:
        return jsonify({"error": "缺少 keyword 参数"}), 400
    
    # 调用上面修改的 15 秒超时方法
    data, err_msg = tads_app._get_emu_running(keyword)
    
    if data is not None:
        return jsonify({"success": True, "data": data})
    else:
        return jsonify({"success": False, "error": err_msg}), 500


@app.route('/api/emu/car/info')
def emu_car_info():
    """代理配属详细信息查询API"""
    car_id = request.args.get('id')
    if not car_id:
        return jsonify({"error": "缺少 id 参数"}), 400
    
    tads_app.log_action("客户端通过内网API代理EMU查询-配属详细信息", car_id)
    
    api_config = tads_app.config.get('api', {})
    emu_base = api_config.get('emu_base', 'https://emu.railgo.zenglingkun.cn')
    api_url = emu_base + "/api/car/info"
    try:
        resp = requests.get(api_url, params={"id": car_id}, timeout=10)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"success": False, "error": f"请求失败 {resp.status_code}"}), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500



# ================== GUI 主窗口 ==================
class MainWindow(tk.Tk):
    def resource_path(self, relative_path):
        """获取打包后内部资源的绝对路径，脱离外部的原目录依赖"""
        import sys
        import os
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    def __init__(self):
        from tkinter import ttk
        super().__init__()

        # ===== tads_app 全局引用 =====
        global tads_app
        if tads_app is None:
            tads_app = TADSApp()
        self.app = tads_app
        self.app.set_main_window(self)

        # ===== 获取系统 DPI 缩放系数（Tkinter 基准为 72 DPI） =====
        try:
            import ctypes
            hwnd = self.winfo_id()
            dpi = None
            try:
                dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
            except Exception:
                pass
            if not dpi or dpi <= 0:
                try:
                    hdc = ctypes.windll.user32.GetDC(0)
                    dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
                    ctypes.windll.user32.ReleaseDC(0, hdc)
                except Exception:
                    pass
            self.scale_factor = dpi / 72.0 if (dpi and dpi > 0) else 1.0
        except Exception:
            self.scale_factor = 1.0

        try:
            self.tk.call('tk', 'scaling', self.scale_factor)
        except Exception:
            pass

        base_w, base_h = 1000, 600
        min_w, min_h = 900, 500
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        win_w = min(int(base_w * self.scale_factor), int(sw * 0.9))
        win_h = min(int(base_h * self.scale_factor), int(sh * 0.9))
        self.geometry(f"{win_w}x{win_h}")
        self.minsize(int(min_w * self.scale_factor), int(min_h * self.scale_factor))

        self.title(" TADS 列车数据与查询服务系统 · QS Studio      v26.9.9")
        self.configure(bg='#f0f0f0')
        self.is_fullscreen = False

        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11), rowheight=30)
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))

        try:
            self.iconbitmap(self.resource_path('ic_directions_train_128_28252.ico'))
        except Exception:
            pass

        import tkinter as tk
        original_toplevel_init = tk.Toplevel.__init__
        def new_toplevel_init(self_t, master=None, cnf={}, **kw):
            original_toplevel_init(self_t, master, cnf, **kw)
            try:
                if master and hasattr(master, 'resource_path'):
                    self_t.iconbitmap(master.resource_path('ic_directions_train_128_28252.ico'))
            except Exception:
                pass
        tk.Toplevel.__init__ = new_toplevel_init

        try:
            pygame.mixer.init()
        except Exception:
            pass
        self.beep_file = self.resource_path("ding.mp3")

        self._api_status_label = None

        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="全屏", command=self.toggle_fullscreen)
        menubar.add_cascade(label="视图", menu=view_menu)
        menubar.add_command(label="连接PN532", command=self._connect_pn532_menu)
        menubar.add_command(label="显示当前API Token", command=self._show_api_token)
        menubar.add_command(label="显示服务器信息", command=self._show_server_info)
        menubar.add_separator()
        menubar.add_command(label="退出登录", command=self._logout)
        self.config(menu=menubar)

        # ===== 状态栏 =====
        self.status_frame = tk.Frame(self, bg='#d9d9d9', height=30)
        self.status_frame.pack(side=tk.TOP, fill=tk.X)

        self.temp_msg_label = tk.Label(self.status_frame, text="", font=('微软雅黑', 9), bg='#d9d9d9', fg='green', anchor='e', width=39)
        self.temp_msg_label.pack(side=tk.RIGHT, padx=5)

        self.separator = ttk.Separator(self.status_frame, orient='vertical')
        self.separator.pack(side=tk.RIGHT, fill=tk.Y, padx=2)

        self.status_label = tk.Label(self.status_frame, text="", font=('微软雅黑', 9), bg='#d9d9d9', anchor='w')
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.full_status_text = ""
        self.scroll_offset = 0
        self.scroll_after_id = None
        self._temp_msg_after_id = None
        self.api_status = "正常运行"

        # ===== 主面板 =====
        main_panel = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED,
                                     sashwidth=5, bg='#f0f0f0')
        main_panel.pack(fill=tk.BOTH, expand=True)

        nav_w = int(180 * self.scale_factor)
        nav_min = int(180 * self.scale_factor)
        self.left_nav = tk.Frame(main_panel, bg='#2c3e50', width=nav_w)
        main_panel.add(self.left_nav, width=nav_w, minsize=nav_min)

        # ===== 左侧顶部 LOGO + T A D S =====
        header_frame = tk.Frame(self.left_nav, bg='#2c3e50',
                                 height=int(46 * self.scale_factor))
        header_frame.pack(fill=tk.X, pady=(8, 4))
        header_frame.pack_propagate(False)

        logo_inner = tk.Frame(header_frame, bg='#2c3e50')
        logo_inner.place(relx=0.5, rely=0.5, anchor='center')

        try:
            from PIL import Image, ImageTk
            icon_path = self.resource_path('ic_directions_train_128_28252.ico')
            if os.path.exists(icon_path):
                _img = Image.open(icon_path)
                # 图标缩得更小，例如 20 像素
                icon_sz = int(20 * self.scale_factor)
                _img = _img.resize((icon_sz, icon_sz), Image.Resampling.LANCZOS)
                self._nav_logo_img = ImageTk.PhotoImage(_img)
                tk.Label(logo_inner, image=self._nav_logo_img, bg='#2c3e50').pack(side=tk.LEFT, padx=(0, 6))
        except Exception:
            pass

        # 字体也相应改小，例如 13
        tk.Label(logo_inner, text="T A D S", font=('微软雅黑', int(13 * self.scale_factor), 'bold'),
                 bg='#2c3e50', fg='white').pack(side=tk.LEFT)

        ttk.Separator(self.left_nav, orient='horizontal').pack(
            fill=tk.X, padx=8, pady=(0, 4))

        nav_buttons = [
            ("主页", self.open_home_tab),
            ("编辑", self.open_edit_tab),
            ("查看", self.open_view_tab),
            ("查询", self.open_query_tab),
            ("提权", self.open_privilege_tab),
            ("设置", self.open_settings_tab),
            ("日志", self.open_log_tab),
            ("还原点", self.open_restore_tab),
            ("车站大屏", self.open_station_screen_tab)
        ]
        for text, cmd in nav_buttons:
            btn = tk.Button(self.left_nav, text=text, command=cmd,
                            font=('微软雅黑', 11), bg='#34495e', fg='white',
                            activebackground='#1abc9c', activeforeground='white',
                            relief=tk.FLAT, bd=0, anchor='w', padx=20, pady=12)
            btn.pack(fill=tk.X, pady=2)

        tk.Frame(self.left_nav, bg='#2c3e50').pack(fill=tk.BOTH, expand=True)

        # ===== 右侧内容区 =====
        right_w = int(1000 * self.scale_factor)
        right_min = int(800 * self.scale_factor)
        self.right_container = tk.Frame(main_panel, bg='#f0f0f0')
        main_panel.add(self.right_container, width=right_w, minsize=right_min)

        tab_bar_frame = tk.Frame(self.right_container, bg='#d0d0d0', height=45)
        tab_bar_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 2))
        tab_bar_frame.pack_propagate(False)
        self.tab_bar_frame = tab_bar_frame
        self.tab_container = tk.Frame(tab_bar_frame, bg='#d0d0d0')
        self.tab_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tab_container.bind("<Configure>", self._on_tab_container_resize)

        self.content_area = tk.Frame(self.right_container, bg='#f0f0f0')
        self.content_area.pack(fill=tk.BOTH, expand=True)

        self.tabs = {}
        self.tab_counter = 0
        self.current_tab_id = None

        self._current_query_context = None
        self._current_query_frame = None

        self.open_home_tab()
        self.after(5000, self.refresh_status)
        self.after(1000, lambda: threading.Thread(target=self.start_api_server, daemon=True).start())
        self.after(300, self._initial_pn532_connect)

        self.after(1000, self._poll_error_log)

        self.app.log_action("系统启动", "服务器端主界面已加载")
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self._start_udp_discovery_service()

    def _start_udp_discovery_service(self):
        """后台开启 UDP 广播监听，供客户端自动发现服务器 IP"""
        def udp_listener():
            udp_port = 10077
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                # 绑定所有网卡的 10077 端口
                sock.bind(('', udp_port))
            except Exception as e:
                self.app.write_error_log(f"UDP 广播服务启动失败: {e}")
                return
                
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    if data == b'TADS_DISCOVER':
                        # 获取当前机器在内网的 IP
                        local_ip = _get_local_ip()
                        api_port = self.app.config.get('api_port', 10076)
                        # 拼接回复内容：TADS_SERVER|IP|端口
                        response = f"TADS_SERVER|{local_ip}|{api_port}".encode('utf-8')
                        sock.sendto(response, addr)
                except Exception:
                    pass

        threading.Thread(target=udp_listener, daemon=True).start()

    def _on_window_close(self):
        try:
            self.app.log_action("系统关闭", "服务器端主界面已关闭")
        except Exception:
            pass
        self.destroy()

    def _manage_tokens(self):
        """活跃 Token 管理（仅 ROOT 可见完整功能）"""
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return

        top = tk.Toplevel(self)
        top.title("活跃 Token 管理")
        top.geometry("1500x500")
        top.transient(self)
        top.grab_set()

        cols = ('身份', '签发时间', '过期时间', '来源IP', '卡UID', 'Token')
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 10))
        style.configure("Treeview.Heading", font=('微软雅黑', 10, 'bold'))
        tree = ttk.Treeview(top, columns=cols, show='headings', selectmode='extended')
        widths = (160, 150, 150, 120, 130, 120)
        for c, w in zip(cols, widths):
            tree.heading(c, text=c)
            tree.column(c, anchor='center', width=w)
        vsb = ttk.Scrollbar(top, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        vsb.pack(side=tk.LEFT, fill=tk.Y, pady=10)

        status_label = tk.Label(top, text="", font=('微软雅黑', 9), fg='blue')
        status_label.pack(side=tk.BOTTOM, pady=4)

        def fmt_ts(ts):
            try:
                return datetime.datetime.fromtimestamp(float(ts)).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return '-'

        def refresh():
            for i in tree.get_children():
                tree.delete(i)
            status_label.config(text="正在加载...", fg='blue')
            def do():
                try:
                    resp = requests.get(
                        f"http://127.0.0.1:{self.app.config.get('api_port', 10076)}/api/admin/tokens/list",
                        headers={'X-TADS-Token': self.app.api_token or ''},
                        timeout=5
                    )
                    if resp.status_code != 200:
                        self.after(0, lambda: status_label.config(
                            text=f"加载失败: HTTP {resp.status_code}", fg='red'))
                        return
                    data = resp.json()
                    tokens = data.get('tokens', [])
                    def render():
                        for t in tokens:
                            tree.insert('', 'end', values=(
                                t.get('identity', ''),
                                fmt_ts(t.get('issued_at', 0)),
                                fmt_ts(t.get('expire', 0)),
                                t.get('source_ip', ''),
                                t.get('card_uid', ''),
                                t.get('token_preview', ''),
                            ))
                        status_label.config(text=f"共 {len(tokens)} 个活跃 Token", fg='green')
                    self.after(0, render)
                except Exception as e:
                    self.after(0, lambda: status_label.config(text=f"异常: {e}", fg='red'))
            threading.Thread(target=do, daemon=True).start()

        def revoke_selected():
            if not (self.app.is_root or self.app.is_admin):
                messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=top)
                return
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "请先选择要撤销的 Token", parent=top)
                return
            previews = []
            for iid in sel:
                vals = tree.item(iid, 'values')
                if len(vals) >= 6 and vals[5]:
                    previews.append(vals[5])
            if not previews:
                return
            if not messagebox.askyesno("确认撤销",
                                       f"确认撤销 {len(previews)} 个 Token？\n被撤销的客户端会立即失效，需重新提权。",
                                       parent=top):
                return
            def do():
                try:
                    resp = requests.post(
                        f"http://127.0.0.1:{self.app.config.get('api_port', 10076)}/api/admin/tokens/revoke",
                        json={"token_previews": previews},
                        headers={'X-TADS-Token': self.app.api_token or ''},
                        timeout=5
                    )
                    if resp.status_code == 200:
                        self.after(0, refresh)
                    else:
                        self.after(0, lambda: status_label.config(
                            text=f"撤销失败: HTTP {resp.status_code}", fg='red'))
                except Exception as e:
                    self.after(0, lambda: status_label.config(text=f"异常: {e}", fg='red'))
            threading.Thread(target=do, daemon=True).start()

        bar = tk.Frame(top)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=6)
        tk.Button(bar, text="刷新", command=refresh, width=10).pack(side=tk.LEFT, padx=4)
        if self.app.is_root or self.app.is_admin:
            tk.Button(bar, text="撤销选中", command=revoke_selected, width=12).pack(side=tk.LEFT, padx=4)
        tk.Button(bar, text="关闭", command=top.destroy, width=10).pack(side=tk.LEFT, padx=4)

        refresh()

    def _show_port_selection_dialog(self, ports):
        """显示串口选择对话框，返回选择的端口名或 None"""
        result = {"port": None}

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
                        getattr(p, 'description', '') or '')
            )
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
                result["port"] = values[0]
            top.destroy()

        def on_cancel():
            result["port"] = None
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
        return result["port"]

    def _connect_pn532_with_selection(self, silent_on_success=False, silent_if_no_port=False):
        """
        统一的 PN532 连接流程：
          - 枚举所有串口
          - 0 个：silent_if_no_port=True 时静默失败，否则报错
          - 1 个：直接使用
          - 多个：弹框让用户鼠标选择
        - 选择后把 com_port 写回配置文件
        - silent_on_success=True 时成功不弹提示（启动流程用）
        """
        try:
            ports = list(serial.tools.list_ports.comports())
        except Exception as e:
            self.app.write_error_log(f"枚举串口失败: {e}")
            if not silent_if_no_port:
                messagebox.showerror("错误", f"枚举串口失败: {e}", parent=self)
            return False

        if not ports:
            self.app.write_error_log("PN532 连接：系统未检测到任何串口设备")
            if not silent_if_no_port:
                messagebox.showerror(
                    "错误", "系统未检测到任何串口设备，请检查 PN532 是否已连接", parent=self
                )
            return False

        # 选择端口
        if len(ports) == 1:
            selected_port = ports[0].device
            self.app.log_action("PN532 连接", f"仅检测到 1 个串口 {selected_port}，直接使用")
        else:
            selected_port = self._show_port_selection_dialog(ports)
            if selected_port is None:
                self.app.log_action("PN532 连接", "用户取消端口选择")
                return False
            self.app.log_action("PN532 连接", f"用户手动选择串口 {selected_port}")

        # 写入配置
        try:
            self.app.config.set('com_port', selected_port)
        except Exception as e:
            self.app.write_error_log(f"保存 com_port 到配置文件失败: {e}")

        # 执行连接
        try:
            self.app.pn532.port = selected_port
            self.app.pn532.baudrate = self.app.config.get('baudrate', 115200)
            self.app.pn532._init_reader()
        except Exception as e:
            self.app.write_error_log(f"PN532 连接失败 {selected_port}: {e}")
            if not silent_if_no_port:
                messagebox.showerror("错误", f"PN532 连接失败: {e}", parent=self)
            return False

        if self.app.pn532.is_connected():
            self.app.log_action("PN532 连接", f"已连接 {selected_port}")
            if not silent_on_success:
                messagebox.showinfo("成功", f"PN532 已连接（{selected_port}）", parent=self)
            try:
                self.refresh_status()
            except Exception:
                pass
            return True
        else:
            self.app.write_error_log(f"PN532 端口 {selected_port} 打开失败或初始化失败")
            if not silent_if_no_port:
                messagebox.showerror(
                    "错误", f"端口 {selected_port} 连接失败，请检查设备", parent=self
                )
            return False

    def _ensure_pn532_connected(self):
        """
        确保 PN532 已连接。
        - 已连接：直接返回 True
        - 未连接：用配置里上次手动选择的 com_port 直接连接，不弹选择框
        - 配置端口不可用：提示用户点击"连接PN532"重新选择
        """
        try:
            if (self.app.pn532 and self.app.pn532.is_connected()
                    and self.app.pn532.ser and self.app.pn532.ser.is_open):
                return True
        except Exception:
            pass

        if not self.app.pn532:
            messagebox.showerror("错误", "PN532 读卡器未初始化", parent=self)
            return False

        # 读取上次手动选择的端口
        saved_port = ""
        try:
            saved_port = (self.app.config.get('com_port', '') or '').strip()
        except Exception:
            saved_port = ""

        if not saved_port or saved_port.lower() == "auto":
            messagebox.showerror(
                "错误",
                "尚未选择 PN532 串口。\n请先点击「连接PN532」选择端口后再提权。",
                parent=self
            )
            return False

        # 检查该端口当前是否还存在（给出更准确的错误提示）
        try:
            current_ports = {p.device.upper() for p in serial.tools.list_ports.comports()}
            if saved_port.upper() not in current_ports:
                messagebox.showerror(
                    "错误",
                    f"上次选择的串口 {saved_port} 当前不存在。\n"
                    f"请点击「连接PN532」重新选择端口后再提权。",
                    parent=self
                )
                return False
        except Exception as e:
            self.app.write_error_log(f"检查端口列表失败: {e}")

        # 直接用上次选择的端口连接
        try:
            self.app.pn532.port = saved_port
            self.app.pn532.baudrate = self.app.config.get('baudrate', 115200)
            self.app.pn532._init_reader()
        except Exception as e:
            self.app.write_error_log(f"使用上次端口 {saved_port} 连接 PN532 失败: {e}")
            messagebox.showerror(
                "错误",
                f"使用上次选择的串口 {saved_port} 连接 PN532 失败。\n"
                f"请点击「连接PN532」重新选择端口后再提权。",
                parent=self
            )
            return False

        if not self.app.pn532.is_connected():
            self.app.write_error_log(f"PN532 端口 {saved_port} 打开失败或初始化失败")
            messagebox.showerror(
                "错误",
                f"串口 {saved_port} 连接 PN532 失败。\n"
                f"请点击「连接PN532」重新选择端口后再提权。",
                parent=self
            )
            return False

        self.app.log_action("PN532 连接", f"提权时复用上次选择的串口 {saved_port}")
        return True

    def _initial_pn532_connect(self):
        """启动时连接 PN532：多端口弹选择；单端口直连；无端口静默"""
        try:
            self._connect_pn532_with_selection(
                silent_on_success=True,
                silent_if_no_port=True
            )
        except Exception as e:
            self.app.write_error_log(f"启动时连接 PN532 失败: {e}")

    def _play_ding(self):
        """播放 ding.mp3 提示音"""
        try:
            if not os.path.exists(self.beep_file):
                return
            pygame.mixer.music.load(self.beep_file)
            pygame.mixer.music.play()
        except:
            pass

    def _show_offline_message(self, parent_frame):
        """在指定容器中显示离线模式提示"""
        tk.Label(
            parent_frame,
            text="当前为离线模式，请开启“使用API实时查询”后再尝试查询本项。",
            font=('微软雅黑', 12), bg='#f0f0f0', fg='#2980b9',
            wraplength=520, justify='center'
        ).pack(pady=40, padx=20, expand=True)

    def _toggle_auto_update(self):
        """切换自动更新开关"""
        current = self.app.auto_update_on_query
        new_state = not current
        # 直接修改属性并保存配置
        self.app.auto_update_on_query = new_state
        self.app.config.set('auto_update_on_query', new_state)
        # 更新按钮文本
        self.auto_update_btn.config(
            text="关闭查询时自动更新该车次" if new_state else "开启查询时自动更新该车次"
        )
        # 显示临时消息
        self.temp_msg_label.config(text=f"自动更新已{'开启' if new_state else '关闭'}")
        self.after(3000, lambda: self.temp_msg_label.config(text=""))
        # 记录日志
        self.app.log_action("切换自动更新", f"状态: {'开启' if new_state else '关闭'}")

    def _start_scroll(self):
        """流水屏滚动显示长文本（避免闪烁）"""
        if self.scroll_after_id:
            self.after_cancel(self.scroll_after_id)
            self.scroll_after_id = None

        self.update_idletasks()
        label_width = self.status_label.winfo_width()
        if label_width < 10:
            self.scroll_after_id = self.after(200, self._start_scroll)
            return

        import tkinter.font as tkFont
        font = tkFont.Font(font=self.status_label['font'])
        max_width = label_width - 10
        full = self.full_status_text
        if not full:
            self.status_label.config(text="")
            return

        # 如果全部文本宽度小于可用宽度，直接显示全部，停止滚动
        if font.measure(full) <= max_width:
            current_text = self.status_label.cget('text')
            if current_text != full:
                self.status_label.config(text=full)
            self.scroll_offset = 0
            self.scroll_after_id = self.after(3000, self._start_scroll)
            return

        # 滚动显示，只更新变化的部分
        display_text = full[self.scroll_offset:] + "   " + full[:self.scroll_offset]
        max_chars = 0
        for i in range(1, len(display_text) + 1):
            if font.measure(display_text[:i]) <= max_width:
                max_chars = i
            else:
                break
        if max_chars == 0:
            max_chars = 1
        
        new_display = display_text[:max_chars]
        current_display = self.status_label.cget('text')
        # 只有内容变化时才更新
        if current_display != new_display:
            self.status_label.config(text=new_display)
        
        self.scroll_offset += 1
        if self.scroll_offset >= len(full):
            self.scroll_offset = 0
        self.scroll_after_id = self.after(200, self._start_scroll)

    def show_temp_message(self, text, duration=3000):
        """显示临时消息（右侧），3秒后消失"""
        # 取消之前的定时器（安全处理 None 和无效 id）
        if hasattr(self, '_temp_msg_after_id'):
            try:
                if self._temp_msg_after_id is not None:
                    self.after_cancel(self._temp_msg_after_id)
            except:
                pass
        self.temp_msg_label.config(text=text)
        self._temp_msg_after_id = self.after(duration, lambda: self.temp_msg_label.config(text=""))

    def _connect_pn532(self):
        if not (self.app.is_root or self.app.is_admin):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return

        self._connect_pn532_with_selection(silent_on_success=False, silent_if_no_port=False)
        self.refresh_status()

    def _logout(self):
        """退出登录，重置为普通用户"""
        # 显示确认弹窗
        if not messagebox.askyesno("确认退出", "确定要退出当前登录吗？\n退出后将回退到普通用户权限。", parent=self):
            return
        
        # 重置身份
        self.app.is_admin = False
        self.app.is_developer = False
        self.app.is_root = False
        self.app.current_identity = "普通用户"
        self.app.current_permissions = []
        self.app.current_uid = None
        self.app.log_action("退出登录", "已回退到普通用户")
        
        # 刷新状态栏
        self.refresh_status()
        
        # 更新编辑标签页权限状态
        self.update_edit_permission()
        
        # 显示临时消息
        self.show_temp_message("已退出登录，当前为普通用户", 2000)
        
        # 刷新欢迎页
        self.display_welcome()
        
        # ====== 关闭需要关闭的标签页 ======
        close_keywords = ["编辑", "设置", "日志", "还原点"]
        
        tabs_to_close = []
        for tid, data in self.tabs.items():
            title = data['title']
            should_close = False
            for keyword in close_keywords:
                if keyword in title:
                    should_close = True
                    break
            if should_close:
                tabs_to_close.append(tid)
        
        for tid in tabs_to_close:
            self.close_tab(tid)

    def _connect_pn532_menu(self):
        """菜单栏连接PN532（无权限检查）"""
        self._connect_pn532_with_selection(silent_on_success=False, silent_if_no_port=False)
        self.refresh_status()

    def _open_train_detail_tab(self, train_number: str):
        """打开一个车次详情标签页（含列车信息 + 停站 + 本站车次/站台/检票口/出站口 + 正晚点）"""
        # 检查是否已存在该车次的标签页
        for tid, data in self.tabs.items():
            if data['title'] == f"车次-{train_number}":
                self.switch_tab(tid)
                return

        # 创建新标签页的框架
        frame = ttk.Frame(self.content_area, padding=10)

        # 标题
        tk.Label(frame, text=f"车次 {train_number} 详情", font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=5)

        # ---- 列车信息框架 ----
        info_frame = tk.Frame(frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
        info_frame.pack(fill=tk.X, pady=5, padx=5)
        info_label = tk.Label(info_frame, text="正在加载列车信息...", font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
        info_label.pack(fill=tk.X, padx=10, pady=5)

        # ---- 列车组图片按钮和动车组运行查询按钮 ----
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=5, padx=5)
        
        coach_pic_btn = tk.Button(btn_frame, text="查看列车组图片",
                                  command=lambda: self._show_coach_pic(train_number),
                                  width=20, font=('微软雅黑', 10))
        coach_pic_btn.pack(side=tk.LEFT, padx=5)

        emu_running_btn = tk.Button(btn_frame, text="查询动车组运行",
                                    command=lambda: self._open_emu_running_tab(train_number),
                                    width=20, font=('微软雅黑', 10))
        emu_running_btn.pack(side=tk.LEFT, padx=5)

        # ---- 停站表格 ----
        tree_frame = tk.Frame(frame, bg='#f0f0f0')
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ['序号', '站名', '到达', '出发', '本站车次', '站台', '检票口', '出站口', '正晚点状态']
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=100)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ---- 绑定双击事件到"站名"列 ----
        def on_station_double_click(event):
            """双击站名打开车站详情"""
            item = tree.identify_row(event.y)
            if not item:
                return
            col = tree.identify_column(event.x)
            if col == '#2':  # 站名列
                values = tree.item(item, 'values')
                if values and len(values) > 1:
                    station_name = values[1]
                    if station_name:
                        self._open_station_detail_tab(station_name)
        
        tree.bind("<Double-1>", on_station_double_click)

        # 状态标签
        status_label = tk.Label(frame, text="正在加载数据...", font=('微软雅黑', 9), bg='#f0f0f0', fg='blue')
        status_label.pack(pady=5)

        # 添加标签页
        self.add_tab(f"车次-{train_number}", frame, closable=True)

        # 异步加载数据
        def load_data():
            import concurrent.futures

            try:
                use_api = self.app.use_api_query

                if use_api:
                    # ---- API 模式：获取 V2 车次主数据 ----
                    v2_data, error_type, _ = self.app.query_train_from_v2(train_number)
                    if error_type != 'success' or not v2_data:
                        self.after(0, lambda: status_label.config(text="❌ 未找到该车次", fg='red'))
                        return

                    group = self.app.get_merged_by_number(train_number)
                    display_name = group['display_name'] if group else train_number

                    timetable = v2_data.get('timetable', [])
                    if not timetable:
                        self.after(0, lambda: status_label.config(text="⚠️ 该车次没有停站数据", fg='orange'))
                        return

                    # 构建列车信息（API版本）
                    info_parts = [f"车次: {display_name}"]
                    number_kind = v2_data.get('numberKind', '')
                    if number_kind:
                        info_parts.append(f"类型: {number_kind}")
                    number_full = v2_data.get('numberFull', [])
                    if number_full and len(number_full) > 1:
                        info_parts.append(f"复车次: {', '.join(number_full)}")
                    bureau = v2_data.get('bureauShortName', '') or v2_data.get('bureau', '')
                    if bureau:
                        info_parts.append(f"路局: {bureau}")
                    car = v2_data.get('car', '')
                    if car:
                        info_parts.append(f"车型: {car}")
                    car_owner = v2_data.get('carOwner', '')
                    if car_owner:
                        info_parts.append(f"配属: {car_owner}")
                    runner = v2_data.get('runner', '')
                    if runner:
                        info_parts.append(f"担当: {runner}")
                    spend = v2_data.get('spend', 0)
                    if spend:
                        hours = spend // 60
                        minutes = spend % 60
                        if hours > 0:
                            info_parts.append(f"运行时长: {hours}时{minutes}分")
                        else:
                            info_parts.append(f"运行时长: {minutes}分")
                    info_text = " | ".join(info_parts)

                    # 统一 timetable 结构
                    unified_timetable = []
                    for stop in timetable:
                        unified_timetable.append({
                            'station': stop.get('station', ''),
                            'arrive': stop.get('arrive', '') or '',
                            'depart': stop.get('depart', '') or '',
                            'day': stop.get('day', 0),
                            'trainCode': stop.get('trainCode', ''),
                            'stationTelecode': stop.get('stationTelecode', ''),
                        })
                else:
                    # ---- 本地模式：使用本地数据库 ----
                    group = self.app.get_merged_by_number(train_number)
                    if not group:
                        self.after(0, lambda: status_label.config(
                            text="❌ 本地数据中未找到该车次\n可开启“使用API实时查询”后再试", fg='red'))
                        return

                    display_name = group['display_name']
                    stops = group.get('stops', [])
                    if not stops:
                        self.after(0, lambda: status_label.config(text="⚠️ 该车次没有停站数据", fg='orange'))
                        return

                    info_parts = [f"车次: {display_name}"]
                    rep = group.get('representative', {}) or {}
                    if rep.get('type') and rep.get('type') != '未知':
                        info_parts.append(f"类型: {rep['type']}")
                    info_parts.append("数据来源: 本地数据库")
                    info_text = " | ".join(info_parts)

                    # 统一 timetable 结构
                    unified_timetable = []
                    for stop in stops:
                        name = stop.get('station_name') or self.app.get_station_name_by_id(stop.get('station_id')) or ''
                        unified_timetable.append({
                            'station': name,
                            'arrive': stop.get('arrive') or '',
                            'depart': stop.get('depart') or '',
                            'day': stop.get('day_offset', 0),
                            'trainCode': train_number,
                            'stationTelecode': '',
                        })

                # 显示列车信息
                self.after(0, lambda: info_label.config(text=info_text))

                # 插入表格行
                placeholder = "查询中..." if use_api else ""
                for i, stop in enumerate(unified_timetable):
                    values = (
                        str(i + 1),
                        stop['station'],
                        stop['arrive'],
                        stop['depart'],
                        stop['trainCode'],
                        placeholder, placeholder, placeholder, placeholder
                    )
                    self.after(0, lambda v=values: tree.insert('', 'end', values=v))

                if not use_api:
                    # 离线模式：跳过正晚点/检票口查询
                    self.after(0, lambda: status_label.config(text="✅ 数据加载完成（离线模式）", fg='green'))
                    return

                self.after(0, lambda: status_label.config(text="正在获取正晚点和检票口信息...", fg='blue'))

                # ---- 并发获取正晚点和检票口信息 ----
                stations_to_query = []
                for stop in unified_timetable:
                    if stop['stationTelecode']:
                        stations_to_query.append({
                            'name': stop['station'],
                            'telecode': stop['stationTelecode'],
                            'train_code': stop['trainCode'] or train_number
                        })

                exit_data_map = {}
                if stations_to_query:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                        future_to_station = {}
                        for station in stations_to_query:
                            future = executor.submit(
                                self.app._get_train_exit,
                                station['train_code'],
                                station['telecode']
                            )
                            future_to_station[future] = station['name']

                        for future in concurrent.futures.as_completed(future_to_station):
                            station_name = future_to_station[future]
                            try:
                                exit_info = future.result(timeout=30)
                                if exit_info:
                                    exit_data_map[station_name] = exit_info
                            except Exception as e:
                                self.app._log_api_error(f"获取检票口失败 {station_name}: {e}")

                delay_data = self.app._get_train_delay(train_number, timeout=30)

                if delay_data:
                    delay_map = {}
                    for item in delay_data:
                        station = item.get('stationName')
                        if station:
                            delay_map[station] = item

                    now = datetime.datetime.now()
                    today = now.date()
                    children = tree.get_children()
                    for i, stop in enumerate(unified_timetable):
                        if i >= len(children):
                            break
                        station_name = stop['station']
                        station_train_code = stop['trainCode']

                        time_str = stop['depart'] or stop['arrive']
                        is_passed = False
                        if time_str:
                            try:
                                dt = datetime.datetime.strptime(time_str, '%H:%M')
                                station_dt = datetime.datetime.combine(today, dt.time())
                                if now > station_dt:
                                    is_passed = True
                            except:
                                pass

                        status = '未维护'
                        if station_name in delay_map:
                            item = delay_map[station_name]
                            code = item.get('delayStatusCode')
                            time_val = item.get('delayTime', 0)
                            if code in ('ON_TIME', 'ON_TIME_PREDICTION'):
                                status = '正点'
                            elif code in ('DELAY', 'DELAY_PREDICTION'):
                                status = f'晚点{time_val}分钟'
                            elif code in ('EARLY', 'EARLY_PREDICTION'):
                                status = f'提前{time_val}分钟'
                            else:
                                status = '未维护'
                            if not is_passed and status not in ('未维护', ''):
                                status = f'预计{status}'

                        platform = entrance = exit_str = ''
                        if station_name in exit_data_map:
                            exit_info = exit_data_map[station_name]
                            platform = exit_info.get('platform', '')
                            entrance = '/'.join(exit_info.get('entrance', [])) if exit_info.get('entrance') else ''
                            exit_str = '/'.join(exit_info.get('exit', [])) if exit_info.get('exit') else ''

                        col_map = {
                            '本站车次': station_train_code,
                            '站台': platform,
                            '检票口': entrance,
                            '出站口': exit_str,
                            '正晚点状态': status
                        }
                        for col_name, value in col_map.items():
                            self.after(0, lambda idx=i, col=col_name, val=value:
                                       tree.set(tree.get_children()[idx], column=col, value=val))

                    self.after(0, lambda: status_label.config(text="✅ 数据加载完成", fg='green'))
                else:
                    self.after(0, lambda: status_label.config(text="⚠️ 未获取到正晚点数据", fg='orange'))

                # ====== 自动更新本地数据库（异步执行，不阻塞查询结果） ======
                if self.app.auto_update_on_query:
                    if self.app.is_admin or self.app.is_root:
                        def do_auto_update():
                            try:
                                success, msg, _ = self.app.batch_import_train(train_number, "V2", auto_update=True)
                                if success:
                                    self.show_temp_message(f"{train_number} 已更新至本地数据库")
                                    self.app.log_action("自动更新车次", f"{train_number} 成功")
                                else:
                                    self.app.log_action("自动更新车次失败", f"{train_number}: {msg}")
                            except Exception as e:
                                self.app.log_action("自动更新车次异常", f"{train_number}: {str(e)}")
                        threading.Thread(target=do_auto_update, daemon=True).start()
                    else:
                        self.app.log_action("自动更新车次失败", f"{train_number}: 无管理员权限")

            except Exception as e:
                self.app.write_error_log(f"加载车次详情失败 {train_number}: {e}")
                self.after(0, lambda: status_label.config(text=f"❌ 加载失败: {str(e)[:50]}", fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _open_station_detail_tab(self, station_name: str):
        """打开车站详情标签页（含基本信息 + 时刻表）"""
        # 检查是否已存在该车站的标签页
        for tid, data in self.tabs.items():
            if data['title'] == f"车站-{station_name}":
                self.switch_tab(tid)
                return

        # 创建新标签页的框架
        frame = ttk.Frame(self.content_area, padding=10)

        tk.Label(frame, text=f"车站 {station_name} 详情", font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=5)

        # ---- 车站信息框架 ----
        info_frame = tk.Frame(frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
        info_frame.pack(fill=tk.X, pady=5, padx=5)
        info_label = tk.Label(info_frame, text="正在加载车站信息...", font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
        info_label.pack(fill=tk.X, padx=10, pady=5)

        # ---- 时刻表标题 ----
        tk.Label(frame, text="经过该站的车次", font=('微软雅黑', 12, 'bold'), bg='#f0f0f0').pack(pady=5)

        # ---- 时刻表表格 ----
        tree_frame = tk.Frame(frame, bg='#f0f0f0')
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ['序号', '车次', '始发站', '终点站', '到达', '出发', '跨天']
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=120)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ---- 双击车次打开车次详情 ----
        tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))

        status_label = tk.Label(frame, text="正在加载数据...", font=('微软雅黑', 9), bg='#f0f0f0', fg='blue')
        status_label.pack(pady=5)

        self.add_tab(f"车站-{station_name}", frame, closable=True)

        # ---- 异步加载数据 ----
        def load_data():
            try:
                # ============ 1. 获取车站信息 ============
                station_info = None
                raw_trains_api = []
                if self.app.use_api_query:
                    telecode = self.app.get_telecode(station_name)
                    if telecode:
                        station_data = self.app._call_v1_station_query(telecode)
                        if station_data:
                            if 'data' in station_data:
                                station_info = station_data['data']
                            raw_trains_api = station_data.get('trains', []) or []

                # ---- 构建车站信息显示 ----
                info_text = ""
                if station_info:
                    info_parts = []
                    info_parts.append(f"车站: {station_info.get('name', station_name)}")
                    if station_info.get('telecode'):
                        info_parts.append(f"电报码: {station_info['telecode']}")
                    if station_info.get('pinyin'):
                        info_parts.append(f"拼音: {station_info['pinyin']}")
                    if station_info.get('pinyinTriple'):
                        info_parts.append(f"三字码: {station_info['pinyinTriple']}")
                    if station_info.get('belong'):
                        info_parts.append(f"所属: {station_info['belong']}")
                    if station_info.get('bureau'):
                        info_parts.append(f"路局: {station_info['bureau']}")
                    if station_info.get('province'):
                        info_parts.append(f"省份: {station_info['province']}")
                    if station_info.get('city'):
                        info_parts.append(f"城市: {station_info['city']}")
                    if station_info.get('level'):
                        info_parts.append(f"等级: {station_info['level']}")
                    info_text = " | ".join(info_parts)
                else:
                    info_text = f"车站: {station_name}"

                self.after(0, lambda: info_label.config(text=info_text))

                # ============ 2. 渲染时刻表 ============
                if self.app.use_api_query:
                    # ---- API 模式：使用 V1 返回的车次直接构建（不依赖本地数据） ----
                    if not raw_trains_api:
                        self.after(0, lambda: status_label.config(text="该站暂无车次数据", fg='orange'))
                        return

                    merged_api = {}
                    for train in raw_trains_api:
                        number_full = train.get('numberFull', []) or []
                        if not number_full:
                            n = train.get('number', '')
                            if n:
                                number_full = [n]
                        if not number_full:
                            continue
                        key = '/'.join(number_full)
                        if key in merged_api:
                            continue
                        timetable = train.get('timetable', []) or []
                        from_station = train.get('fromStation') or {}
                        to_station = train.get('toStation') or {}
                        start_st = from_station.get('station', '') if isinstance(from_station, dict) else ''
                        end_st = to_station.get('station', '') if isinstance(to_station, dict) else ''
                        if not start_st and timetable:
                            start_st = timetable[0].get('station', '')
                        if not end_st and timetable:
                            end_st = timetable[-1].get('station', '')
                        merged_api[key] = {
                            'numbers': number_full,
                            'start': start_st,
                            'end': end_st,
                            'arrive': train.get('arrive', '') or '',
                            'depart': train.get('depart', '') or '',
                            'day_offset': 0
                        }

                    def sort_key_api(item):
                        info = item[1]
                        t = info.get('depart') or info.get('arrive')
                        if t:
                            try:
                                return datetime.datetime.strptime(t, '%H:%M').time()
                            except:
                                pass
                        return datetime.time(23, 59, 59)

                    idx = 1
                    for display_name_full, info in sorted(merged_api.items(), key=sort_key_api):
                        numbers = info.get('numbers', [display_name_full])
                        display = '/'.join(numbers) if len(numbers) > 1 else display_name_full
                        start_st = info.get('start', '')
                        end_st = info.get('end', '')
                        arrive = info.get('arrive') or ''
                        depart = info.get('depart') or ''
                        day_off = info.get('day_offset', 0)
                        day_info = "次日" if day_off == 1 else "当日"
                        self.after(0, lambda v=(str(idx), display, start_st, end_st, arrive, depart, day_info): tree.insert('', 'end', values=v))
                        idx += 1

                    self.after(0, lambda: status_label.config(text=f"共 {len(merged_api)} 趟车次经过", fg='green'))
                    return

                # ---- 本地模式：从本地数据库查询 ----
                sid = self.app.get_station_id_by_name(station_name)
                station_trains = []
                if sid is not None:
                    for train in self.app.data.get('trains', []):
                        for stop in train.get('stops', []):
                            if stop['station_id'] == sid:
                                station_trains.append({
                                    'train': train['base_number'],
                                    'arrive': stop.get('arrive'),
                                    'depart': stop.get('depart'),
                                    'day_offset': stop.get('day_offset', 0)
                                })
                                break

                if not station_trains:
                    self.after(0, lambda: status_label.config(text="该站暂无车次数据", fg='orange'))
                    return

                import concurrent.futures
                train_info = {}
                def fetch_train_info(train_num):
                    group = self.app.get_merged_by_number(train_num)
                    if group:
                        stops = group.get('stops', [])
                        start_station = ''
                        end_station = ''
                        if stops:
                            start_station = stops[0].get('station_name', '')
                            end_station = stops[-1].get('station_name', '')
                        return train_num, group['display_name'], group['numbers'], start_station, end_station
                    train = self.app.get_train(train_num)
                    if train:
                        stops = train.get('stops', [])
                        start_station = ''
                        end_station = ''
                        if stops:
                            start_station = stops[0].get('station_name', '')
                            end_station = stops[-1].get('station_name', '')
                        return train_num, train_num, [train_num], start_station, end_station
                    return train_num, train_num, [train_num], '', ''

                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(fetch_train_info, item['train']) for item in station_trains]
                    for future in concurrent.futures.as_completed(futures):
                        num, display, numbers, start_st, end_st = future.result()
                        train_info[num] = {'display': display, 'numbers': numbers, 'start': start_st, 'end': end_st}

                merged_results = {}
                for item in station_trains:
                    train_num = item['train']
                    info = train_info.get(train_num, {'display': train_num, 'numbers': [train_num], 'start': '', 'end': ''})
                    display_name_full = info['display']
                    numbers = info['numbers']
                    start_st = info['start']
                    end_st = info['end']

                    if display_name_full not in merged_results:
                        merged_results[display_name_full] = {
                            'numbers': numbers,
                            'start': start_st,
                            'end': end_st,
                            'arrive': item.get('arrive') or '',
                            'depart': item.get('depart') or '',
                            'day_offset': item.get('day_offset', 0)
                        }

                # ====== 按发车时间排序 ======
                def sort_key(item):
                    info = item[1]
                    time_str = info.get('depart') or info.get('arrive')
                    if time_str:
                        try:
                            return datetime.datetime.strptime(time_str, '%H:%M').time()
                        except:
                            pass
                    return datetime.time(23, 59, 59)

                idx = 1
                for display_name_full, info in sorted(merged_results.items(), key=sort_key):
                    numbers = info.get('numbers', [display_name_full])
                    display = '/'.join(numbers) if len(numbers) > 1 else display_name_full
                    start_st = info.get('start', '')
                    end_st = info.get('end', '')
                    arrive = info.get('arrive') or ''
                    depart = info.get('depart') or ''
                    day_off = info.get('day_offset', 0)
                    day_info = "次日" if day_off == 1 else "当日"
                    self.after(0, lambda v=(str(idx), display, start_st, end_st, arrive, depart, day_info): tree.insert('', 'end', values=v))
                    idx += 1

                self.after(0, lambda: status_label.config(text=f"共 {len(merged_results)} 趟车次经过", fg='green'))

            except Exception as e:
                self.app.write_error_log(f"加载车站详情失败 {station_name}: {e}")
                self.after(0, lambda: status_label.config(text=f"加载失败: {str(e)[:50]}", fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _show_coach_pic(self, train_num: str):
        """显示列车车厢图，在新建标签页中展示"""
        import concurrent.futures
        from PIL import Image, ImageTk
        import requests
        from io import BytesIO

        # 获取合并组
        group = self.app.get_merged_by_number(train_num)
        candidates = group['numbers'] if group else [train_num]
        display_name = group['display_name'] if group else train_num

        # 检查是否已存在该车次的图片标签页
        tab_title = f"车厢图-{display_name}"
        for tid, data in self.tabs.items():
            if data['title'] == tab_title:
                self.switch_tab(tid)
                return

        # 创建新标签页的框架
        frame = ttk.Frame(self.content_area, padding=10)

        # 标题
        tk.Label(frame, text=f"列车组图片 - {display_name}", 
                 font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=5)

        # ===== 离线模式检查 =====
        if not self.app.use_api_query:
            self.add_tab(tab_title, frame, closable=True)
            self._show_offline_message(frame)
            return

        # 加载状态标签
        status_label = tk.Label(frame, text="正在加载数据...", 
                                font=('微软雅黑', 10), bg='#f0f0f0', fg='blue')
        status_label.pack(pady=5)

        # 主框架
        main_frame = tk.Frame(frame, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧：车厢网格
        left_frame = tk.Frame(main_frame, bg='#f0f0f0')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        # 滚动区域
        canvas_frame = tk.Frame(left_frame, bg='#f0f0f0')
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, bg='#f0f0f0', highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#f0f0f0')

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 右侧：列车参数
        right_frame = tk.Frame(main_frame, bg='#f0f0f0', width=300)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)
        right_frame.pack_propagate(False)

        tk.Label(right_frame, text="列车参数",
                 font=('微软雅黑', 12, 'bold'), bg='#f0f0f0').pack(pady=5)

        param_canvas = tk.Canvas(right_frame, bg='#f0f0f0', highlightthickness=0)
        param_scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=param_canvas.yview)
        param_frame = tk.Frame(param_canvas, bg='#f0f0f0')

        param_frame.bind(
            "<Configure>",
            lambda e: param_canvas.configure(scrollregion=param_canvas.bbox("all"))
        )
        param_canvas.create_window((0, 0), window=param_frame, anchor="nw")
        param_canvas.configure(yscrollcommand=param_scrollbar.set)

        param_canvas.pack(side="left", fill="both", expand=True)
        param_scrollbar.pack(side="right", fill="y")

        # 添加标签页
        self.add_tab(tab_title, frame, closable=True)

        # 异步加载数据
        def load_data():
            data = None
            for num in candidates:
                data = self.app._get_coach_pic(num)
                if data:
                    break

            if not data:
                self.after(0, lambda: status_label.config(
                    text=f"❌ 未获取到车次组 {display_name} 的车厢图数据", fg='red'))
                return

            self.after(0, lambda: status_label.config(text="✅ 数据加载完成", fg='green'))

            # 显示列车基础信息
            car_type = data.get('carType', '未知车型')
            train_style = data.get('trainStyle', '')
            car_code = data.get('carCode', '')
            info_text = f"车型: {car_type}"
            if train_style:
                info_text += f"  ({train_style})"
            if car_code:
                info_text += f"  |  车号: {car_code}"
            self.after(0, lambda: tk.Label(left_frame, text=info_text,
                     font=('微软雅黑', 12, 'bold'), bg='#f0f0f0').pack(pady=5))

            # 车厢图片
            coach_pic_list = data.get('coachPicList', [])
            load_tasks = []

            if coach_pic_list:
                sorted_pics = sorted(coach_pic_list, key=lambda x: x.get('picOrder', 0))
                row_num = 0

                for pic in sorted_pics:
                    name = pic.get('pictureName', '')
                    url = pic.get('pictureUrl', '')

                    cell_frame = tk.Frame(scrollable_frame, bg='#ffffff', relief=tk.RAISED, bd=2)
                    cell_frame.grid(row=row_num, column=0, padx=5, pady=5, sticky='ew')
                    cell_frame.grid_columnconfigure(0, weight=1)

                    label = tk.Label(cell_frame, text=name, bg='#f0f0f0',
                                     font=('微软雅黑', 10, 'bold'), anchor='center')
                    label.pack(fill=tk.X, pady=2)

                    img_label = tk.Label(cell_frame, text="等待加载...",
                                         bg='#e8e8e8', width=770, height=135,
                                         relief=tk.SUNKEN, bd=1)
                    img_label.pack(padx=5, pady=5, fill=tk.X)
                    img_label.bind("<Double-1>", lambda e, u=url, n=name: self._show_large_pic(u, n))

                    if url:
                        load_tasks.append((url, img_label))

                    row_num += 1

                scrollable_frame.grid_columnconfigure(0, weight=1)

            # 列车参数
            car_info = data.get('carInfo', [])
            if car_info:
                for info in car_info:
                    name = info.get('pictureName', '')
                    value = info.get('pictureValue', '')

                    param_item = tk.Frame(param_frame, bg='#f0f0f0')
                    param_item.pack(fill=tk.X, pady=3, padx=5)

                    tk.Label(param_item, text=f"{name}:", bg='#f0f0f0',
                             font=('微软雅黑', 10, 'bold')).pack(side=tk.LEFT)
                    tk.Label(param_item, text=value, bg='#f0f0f0',
                             font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)

            # 加载图片
            if load_tasks:
                executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
                frame._executor = executor

                for url, img_label in load_tasks:
                    self.after(0, lambda lbl=img_label: lbl.config(text="加载中..."))
                    executor.submit(self._load_thumbnail_with_executor, url, img_label)

        threading.Thread(target=load_data, daemon=True).start()

    def _open_emu_running_tab(self, keyword: str):
        """打开动车组运行查询标签页"""
        if not keyword:
            messagebox.showwarning("提示", "请先输入车次或车组号", parent=self)
            return

        tab_title = f"动车组-{keyword}"
        for tid, data in self.tabs.items():
            if data['title'] == tab_title:
                self.switch_tab(tid)
                return

        frame = ttk.Frame(self.content_area, padding=10)

        tk.Label(frame, text=f"动车组运行查询 - {keyword}",
                 font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=5)

        if not self.app.use_api_query:
            self.add_tab(tab_title, frame, closable=True)
            self._show_offline_message(frame)
            return

        status_label = tk.Label(frame, text="正在查询数据，可能需要等待几秒...",
                                font=('微软雅黑', 10), bg='#f0f0f0', fg='blue', wraplength=600)
        status_label.pack(pady=5)

        tree_frame = tk.Frame(frame, bg='#f0f0f0')
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ['运行日期', '车次', '车组号', '是否重联']
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        
        tree = ttk.Treeview(tree_frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=150)
            
        v_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.add_tab(tab_title, frame, closable=True)

        def on_double_click(event):
            selected = tree.selection()
            if not selected:
                return
            item = selected[0]
            values = tree.item(item, 'values')
            if not values or len(values) < 3:
                return
            code_str = values[2]
            if not code_str:
                return
            car_id = code_str.split('/')[0].strip()
            if car_id:
                self._open_car_detail_tab(car_id)
        tree.bind("<Double-1>", on_double_click)

        def load_data():
            try:
                data, err_msg = self.app._get_emu_running(keyword)
                
                if not data:
                    display_msg = f"❌ {err_msg}" if err_msg else f"❌ 未找到 {keyword} 的运行信息"
                    self.after(0, lambda m=display_msg: status_label.config(text=m, fg='red'))
                    return

                rows_to_insert = []
                for item in data:
                    run_date = item.get('runDate', '')
                    train_num = item.get('trainNum', '')
                    train_codes = item.get('trainCode', [])
                    code_str = '/'.join(train_codes) if train_codes else ''
                    coupling = '是' if item.get('coupling', False) else '否'
                    rows_to_insert.append((run_date, train_num, code_str, coupling))

                def update_ui():
                    if not frame.winfo_exists():
                        return
                    for row in rows_to_insert:
                        tree.insert('', 'end', values=row)
                    status_label.config(text=f"✅ 共找到 {len(rows_to_insert)} 条记录", fg='green')
                
                self.after(0, update_ui)

            except Exception as e:
                self.app.write_error_log(f"动车组运行查询UI异常 {keyword}: {e}")
                err_text = f"❌ 查询异常: {str(e)[:50]}"
                self.after(0, lambda m=err_text: status_label.config(text=m, fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _open_emu_running_from_entry(self, entry):
        """从输入框获取车次号并查询动车组运行"""
        keyword = entry.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请先输入车次或车组号", parent=self)
            return
        self._open_emu_running_tab(keyword)

    def _open_car_detail_tab(self, car_id: str):
        """打开车组详细信息标签页（美化版）"""
        if not car_id:
            return

        # 检查是否已存在该车组的标签页
        tab_title = f"车组-{car_id}"
        for tid, data in self.tabs.items():
            if data['title'] == tab_title:
                self.switch_tab(tid)
                return

        # 创建新标签页
        frame = ttk.Frame(self.content_area, padding=10)

        # 标题区域
        title_frame = tk.Frame(frame, bg='#2c3e50', height=80)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text=f"车组详细信息", 
                 font=('微软雅黑', 18, 'bold'), bg='#2c3e50', fg='white').pack(side=tk.LEFT, padx=20, pady=20)
        tk.Label(title_frame, text=car_id, 
                 font=('微软雅黑', 14), bg='#2c3e50', fg='#3498db').pack(side=tk.LEFT, padx=10, pady=20)

        # ===== 离线模式检查 =====
        if not self.app.use_api_query:
            self.add_tab(tab_title, frame, closable=True)
            self._show_offline_message(frame)
            return

        # 状态标签
        status_label = tk.Label(frame, text="⏳ 正在加载详细信息...",
                                font=('微软雅黑', 10), bg='#f0f0f0', fg='blue')
        status_label.pack(pady=5)

        # 创建滚动区域
        canvas_frame = tk.Frame(frame, bg='#f0f0f0')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        canvas = tk.Canvas(canvas_frame, bg='#f0f0f0', highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#f0f0f0')

        # 用 canvas 内嵌窗口
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def on_scrollable_configure(event=None):
            # 内容变化时，重新计算滚动区域
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            # canvas 尺寸变化时，让内嵌窗口宽度跟随
            canvas.itemconfig(canvas_window, width=event.width)

        scrollable_frame.bind("<Configure>", on_scrollable_configure)
        canvas.bind("<Configure>", on_canvas_configure)

        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 添加标签页
        self.add_tab(tab_title, frame, closable=True)

        # 异步加载数据
        def load_data():
            try:
                data = self.app._get_car_info(car_id)
                if not data:
                    self.after(0, lambda: status_label.config(
                        text=f"❌ 未找到车组 {car_id} 的详细信息", fg='red'))
                    return

                self.after(0, lambda: status_label.config(
                    text=f"✅ 车组 {car_id} 详细信息加载完成", fg='green'))

                # 构建美观的卡片式显示
                self.after(0, lambda: self._build_car_detail_cards(scrollable_frame, data))

            except Exception as e:
                self.after(0, lambda: status_label.config(
                    text=f"❌ 加载失败: {str(e)[:50]}", fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _build_car_detail_cards(self, parent, data):
        """构建车组详细信息的卡片式布局（所有卡片占满整行）"""
        # 定义颜色方案
        colors = {
            'card_bg': '#ffffff',
            'header_bg': '#34495e',
            'header_text': '#ffffff',
            'label_color': '#7f8c8d',
            'value_color': '#2c3e50',
            'border': '#ecf0f1',
            'section_bg': '#f8f9fa'
        }

        # 注意：parent 已经由 canvas.create_window 管理，不要再 pack
        # 只设置列权重让卡片占满整行
        parent.grid_columnconfigure(0, weight=1)

        # ---- 基本信息卡片（占满整行） ----
        card1 = tk.Frame(parent, bg=colors['card_bg'], relief=tk.RIDGE, bd=1)
        card1.grid(row=0, column=0, sticky='ew', pady=8, padx=10)
        card1.grid_columnconfigure(0, weight=1)

        header1 = tk.Frame(card1, bg=colors['header_bg'], height=40)
        header1.grid(row=0, column=0, sticky='ew')
        header1.grid_columnconfigure(0, weight=1)
        header1.pack_propagate(False)
        tk.Label(header1, text="基本信息", font=('微软雅黑', 13, 'bold'),
                 bg=colors['header_bg'], fg=colors['header_text']).pack(side=tk.LEFT, padx=15)

        body1 = tk.Frame(card1, bg=colors['card_bg'], padx=25, pady=18)
        body1.grid(row=1, column=0, sticky='ew')
        body1.grid_columnconfigure(0, weight=1)
        body1.grid_columnconfigure(1, weight=1)
        body1.grid_columnconfigure(2, weight=1)

        info_items1 = [
            ("车组号", data.get('id', '未知')),
            ("车型", data.get('model', '未知')),
            ("子型号", data.get('sub_model', '未知')),
            ("自定义类型", data.get('custom_type', '未知')),
            ("生产时间", data.get('manufacture_month', '未知'))
        ]

        self._render_info_items(body1, info_items1, colors)

        # ---- 配属信息卡片（占满整行） ----
        card2 = tk.Frame(parent, bg=colors['card_bg'], relief=tk.RIDGE, bd=1)
        card2.grid(row=1, column=0, sticky='ew', pady=8, padx=10)
        card2.grid_columnconfigure(0, weight=1)

        header2 = tk.Frame(card2, bg=colors['header_bg'], height=40)
        header2.grid(row=0, column=0, sticky='ew')
        header2.grid_columnconfigure(0, weight=1)
        header2.pack_propagate(False)
        tk.Label(header2, text="配属信息", font=('微软雅黑', 13, 'bold'),
                 bg=colors['header_bg'], fg=colors['header_text']).pack(side=tk.LEFT, padx=15)

        body2 = tk.Frame(card2, bg=colors['card_bg'], padx=25, pady=18)
        body2.grid(row=1, column=0, sticky='ew')
        body2.grid_columnconfigure(0, weight=1)
        body2.grid_columnconfigure(1, weight=1)
        body2.grid_columnconfigure(2, weight=1)

        info_items2 = [
            ("所属局", data.get('bureau', '未知')),
            ("所属段", data.get('depot', '未知')),
            ("所属客车段", data.get('train_depot', '未知')),
            ("动车制造商", data.get('trainset_manufacturer', '未知')),
            ("拖车制造商", data.get('trailer_manufacturer', '未知'))
        ]

        self._render_info_items(body2, info_items2, colors)

        # ---- 设施信息卡片（占满整行） ----
        card3 = tk.Frame(parent, bg=colors['card_bg'], relief=tk.RIDGE, bd=1)
        card3.grid(row=2, column=0, sticky='ew', pady=8, padx=10)
        card3.grid_columnconfigure(0, weight=1)

        header3 = tk.Frame(card3, bg=colors['header_bg'], height=40)
        header3.grid(row=0, column=0, sticky='ew')
        header3.grid_columnconfigure(0, weight=1)
        header3.pack_propagate(False)
        tk.Label(header3, text="设施信息", font=('微软雅黑', 13, 'bold'),
                 bg=colors['header_bg'], fg=colors['header_text']).pack(side=tk.LEFT, padx=15)

        body3 = tk.Frame(card3, bg=colors['card_bg'], padx=25, pady=18)
        body3.grid(row=1, column=0, sticky='ew')
        body3.grid_columnconfigure(0, weight=1)
        body3.grid_columnconfigure(1, weight=1)
        body3.grid_columnconfigure(2, weight=1)

        # 处理布尔值显示
        def bool_text(val):
            return "✅ 是" if val else "❌ 否"

        info_items3 = [
            ("商务座类型", data.get('business_seat_type', '未知')),
            ("一等座电动腿托", bool_text(data.get('first_class_power_legrest', False))),
            ("电源位置", data.get('socket_location', '未知')),
            ("厕所类型", data.get('toilet_status', '未知')),
            ("是否对外运营", bool_text(data.get('is_public', False))),
            ("铁路畅行扫码", bool_text(data.get('railway_travel_code_enabled', False)))
        ]

        self._render_info_items(body3, info_items3, colors)

        # ---- 备注信息卡片（占满整行） ----
        remark = data.get('remark', {})
        if remark:
            card4 = tk.Frame(parent, bg=colors['card_bg'], relief=tk.RIDGE, bd=1)
            card4.grid(row=3, column=0, sticky='ew', pady=8, padx=10)
            card4.grid_columnconfigure(0, weight=1)

            header4 = tk.Frame(card4, bg=colors['header_bg'], height=40)
            header4.grid(row=0, column=0, sticky='ew')
            header4.grid_columnconfigure(0, weight=1)
            header4.pack_propagate(False)
            tk.Label(header4, text="备注信息", font=('微软雅黑', 13, 'bold'),
                     bg=colors['header_bg'], fg=colors['header_text']).pack(side=tk.LEFT, padx=15)

            body4 = tk.Frame(card4, bg=colors['card_bg'], padx=25, pady=18)
            body4.grid(row=1, column=0, sticky='ew')
            body4.grid_columnconfigure(0, weight=1)

            if isinstance(remark, dict):
                model_remark = remark.get('model', '')
                if model_remark:
                    row_frame = tk.Frame(body4, bg=colors['card_bg'])
                    row_frame.pack(fill=tk.X, pady=6)
                    label_widget = tk.Label(row_frame, text="车型备注：", font=('微软雅黑', 12),
                                            bg=colors['card_bg'], fg=colors['label_color'])
                    label_widget.pack(side=tk.LEFT)
                    text_widget = tk.Text(row_frame, height=2, font=('微软雅黑', 12),
                                          bg='#fff8e1', fg='#795548', relief=tk.FLAT, wrap=tk.WORD)
                    text_widget.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
                    text_widget.insert(tk.END, model_remark)
                    text_widget.config(state='disabled')

                car_remark = remark.get('car', {})
                if isinstance(car_remark, dict):
                    note = car_remark.get('note', '')
                    if note:
                        row_frame = tk.Frame(body4, bg=colors['card_bg'])
                        row_frame.pack(fill=tk.X, pady=6)
                        label_widget = tk.Label(row_frame, text="车辆备注：", font=('微软雅黑', 12),
                                                bg=colors['card_bg'], fg=colors['label_color'])
                        label_widget.pack(side=tk.LEFT)
                        text_widget = tk.Text(row_frame, height=2, font=('微软雅黑', 12),
                                              bg='#e8f5e9', fg='#2e7d32', relief=tk.FLAT, wrap=tk.WORD)
                        text_widget.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
                        text_widget.insert(tk.END, note)
                        text_widget.config(state='disabled')

                    tags = car_remark.get('tags', '')
                    if tags:
                        row_frame = tk.Frame(body4, bg=colors['card_bg'])
                        row_frame.pack(fill=tk.X, pady=6)
                        label_widget = tk.Label(row_frame, text="标签：", font=('微软雅黑', 12),
                                                bg=colors['card_bg'], fg=colors['label_color'])
                        label_widget.pack(side=tk.LEFT)
                        tag_frame = tk.Frame(row_frame, bg=colors['card_bg'])
                        tag_frame.pack(side=tk.LEFT, padx=5)
                        try:
                            import ast
                            tag_list = ast.literal_eval(tags) if tags else []
                            for tag in tag_list:
                                tag_label = tk.Label(tag_frame, text=tag, font=('微软雅黑', 11),
                                                     bg='#3498db', fg='white', padx=12, pady=4,
                                                     relief=tk.RAISED, bd=1)
                                tag_label.pack(side=tk.LEFT, padx=4)
                        except:
                            value_widget = tk.Label(row_frame, text=tags, font=('微软雅黑', 12),
                                                    bg=colors['card_bg'], fg=colors['value_color'])
                            value_widget.pack(side=tk.LEFT, padx=5)

        # ---- 底部提示 ----
        footer_frame = tk.Frame(parent, bg='#f0f0f0')
        footer_frame.grid(row=4, column=0, sticky='ew', pady=10)
        tk.Label(footer_frame, text="💡 数据来源: RailGo EMU API | 仅供参考", 
                 font=('微软雅黑', 10), bg='#f0f0f0', fg='#95a5a6').pack()

        # ---- 关键：布局完成后，强制更新滚动区域 ----
        def _update_scrollregion():
            try:
                parent.update_idletasks()
                canvas = parent.master
                if isinstance(canvas, tk.Canvas):
                    canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass

        # 立即执行一次，再在下一帧执行一次（应对字体异步加载等导致的尺寸变化）
        _update_scrollregion()
        parent.after(50, _update_scrollregion)
        parent.after(200, _update_scrollregion)

    def _render_info_items(self, parent, items, colors):
        """
        渲染信息项，自动适配长文本
        - 短文本：3列显示
        - 长文本（超过20个字符）：独占一行，占满整行
        """
        # 先分类短文本和长文本
        short_items = []
        long_items = []
        
        for label, value in items:
            value_str = str(value)
            # 如果值超过20个字符，或者包含中文标点（可能是长描述），标记为长文本
            if len(value_str) > 20 or '；' in value_str or '，' in value_str:
                long_items.append((label, value_str))
            else:
                short_items.append((label, value_str))
        
        row_idx = 0
        
        # 先渲染长文本（独占一行，占满整行）
        for label, value in long_items:
            # 创建一个容器，占满3列
            container = tk.Frame(parent, bg=colors['card_bg'])
            container.grid(row=row_idx, column=0, columnspan=3, sticky='ew', padx=10, pady=6)
            # 让容器占满整行
            container.grid_columnconfigure(0, weight=0)  # 标签列，不扩展
            container.grid_columnconfigure(1, weight=1)  # 值列，占满剩余空间
            
            label_widget = tk.Label(container, text=label + "：", font=('微软雅黑', 12),
                                    bg=colors['card_bg'], fg=colors['label_color'])
            label_widget.grid(row=0, column=0, sticky='w')
            
            # 值使用Label，wraplength设为较大值，自动换行
            value_widget = tk.Label(container, text=value, font=('微软雅黑', 12, 'bold'),
                                    bg=colors['card_bg'], fg=colors['value_color'],
                                    wraplength=1000, justify='left')
            value_widget.grid(row=0, column=1, sticky='w', padx=(5, 0))
            
            row_idx += 1
        
        # 再渲染短文本（3列）
        col = 0
        for label, value in short_items:
            container = tk.Frame(parent, bg=colors['card_bg'])
            container.grid(row=row_idx, column=col, sticky='w', padx=10, pady=6)
            
            label_widget = tk.Label(container, text=label + "：", font=('微软雅黑', 12),
                                    bg=colors['card_bg'], fg=colors['label_color'])
            label_widget.grid(row=0, column=0, sticky='w')
            
            value_widget = tk.Label(container, text=value, font=('微软雅黑', 12, 'bold'),
                                    bg=colors['card_bg'], fg=colors['value_color'])
            value_widget.grid(row=0, column=1, sticky='w', padx=(5, 0))
            
            col += 1
            if col >= 3:
                col = 0
                row_idx += 1
        
        # 如果最后一行没有占满，增加一行空白占位
        if col != 0:
            row_idx += 1

    def _show_coach_pic_from_entry(self, entry):
        """从输入框获取车次号并显示列车组图片"""
        train_num = entry.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请先输入车次号", parent=self)
            return
        self._show_coach_pic(train_num)

    def _load_thumbnail_with_executor(self, url, img_label):
        """配合线程池加载缩略图（最大并发4）"""
        try:
            from PIL import Image, ImageTk
            import requests
            from io import BytesIO
            
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content))
                max_size = (866, 450)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                self.after(0, lambda: self._update_image_label(img_label, photo))
            else:
                self.after(0, lambda: img_label.config(text="加载失败", bg='#ffcccc'))
        except Exception as e:
            self.after(0, lambda: img_label.config(text="加载失败", bg='#ffcccc'))
            self.app.write_error_log(f"加载车厢图失败 {url}: {e}")

    def _load_thumbnail_async(self, url, img_label, parent_frame):
        """异步加载缩略图"""
        try:
            from PIL import Image, ImageTk
            import requests
            from io import BytesIO
            
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content))
                # 缩放到适合格子的大小（保持比例）
                max_size = (180, 100)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                # 在主线程更新UI
                self.after(0, lambda: self._update_image_label(img_label, photo))
        except Exception as e:
            self.after(0, lambda: img_label.config(text="加载失败", bg='#ffcccc'))
            self.app.write_error_log(f"加载车厢图失败 {url}: {e}")

    def _show_large_pic(self, url, name):
        """双击车厢图时打开大图窗口"""
        if not url:
            messagebox.showinfo("提示", "该车厢没有图片", parent=self)
            return
        
        # 创建大图窗口
        top = tk.Toplevel(self)
        top.title(f"车厢图 - {name}")
        top.geometry("800x600")
        top.minsize(600, 400)
        top.configure(bg='#f0f0f0')
        
        tk.Label(top, text=name, font=('微软雅黑', 12, 'bold'), 
                 bg='#f0f0f0').pack(pady=10)
        
        # 图片显示区域
        img_frame = tk.Frame(top, bg='#f0f0f0')
        img_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        img_label = tk.Label(img_frame, text="加载中...", bg='#e8e8e8')
        img_label.pack(fill=tk.BOTH, expand=True)
        
        # 底部关闭按钮
        btn_frame = tk.Frame(top, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=10)
        tk.Button(btn_frame, text="关闭", command=top.destroy, 
                  width=15, font=('微软雅黑', 10)).pack()
        
        # 异步加载大图
        threading.Thread(target=self._load_large_pic_async, 
                       args=(url, img_label, top), daemon=True).start()
    
    def _load_large_pic_async(self, url, img_label, window):
        """异步加载大图"""
        try:
            from PIL import Image, ImageTk
            import requests
            from io import BytesIO
            
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                img = Image.open(BytesIO(resp.content))
                
                # 获取窗口大小，自适应缩放
                window.update_idletasks()
                max_width = window.winfo_width() - 40
                max_height = window.winfo_height() - 120
                
                if max_width > 100 and max_height > 100:
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(img)
                self.after(0, lambda: self._update_image_label(img_label, photo))
            else:
                self.after(0, lambda: img_label.config(text="加载失败", bg='#ffcccc'))
        except Exception as e:
            self.after(0, lambda: img_label.config(text=f"加载失败: {str(e)[:30]}", bg='#ffcccc'))
            self.app.write_error_log(f"加载大图失败 {url}: {e}")
    
    def _update_image_label(self, img_label, photo):
        """更新图片标签"""
        img_label.config(image=photo, text='')
        img_label.image = photo  # 保持引用

    def _on_train_row_double_click(self, event, tree):
        """双击表格行，打开车次详情标签页"""
        selection = tree.selection()
        if not selection:
            return
        item = selection[0]
        values = tree.item(item, 'values')
        if not values or len(values) < 2:
            return
        train_display = values[1]  # 第二列是车次（可能是合并显示名）
        # 取第一个车次号
        train_num = train_display.split('/')[0]
        self._open_train_detail_tab(train_num)

    def _fetch_delays_concurrent(self, train_numbers, timeout=120, max_workers=4):
        """并发获取多个车次的正晚点数据（调整至4并发），增加超时到120秒"""
        import concurrent.futures
        delay_map = {}
        if not train_numbers:
            return delay_map
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_num = {executor.submit(self.app._get_train_delay, num, timeout): num for num in train_numbers}
            for future in concurrent.futures.as_completed(future_to_num):
                num = future_to_num[future]
                try:
                    data = future.result(timeout=timeout)
                    if data and len(data) > 0:
                        delay_map[num] = data
                except concurrent.futures.TimeoutError:
                    self.app.write_error_log(f"正晚点查询超时 {num}")
                except Exception as e:
                    self.app.write_error_log(f"并发获取正晚点失败 {num}: {e}")
        return delay_map

    def start_api_server(self):
        # 从配置读取端口
        api_port = self.app.config.get('api_port', 10076)
        # 检查端口是否被占用
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('0.0.0.0', api_port))
            sock.close()
        except OSError:
            self.api_status = f"端口 {api_port} 被占用"
            return
        app.run(host='0.0.0.0', port=api_port, debug=False, use_reloader=False, threaded=True)

    # ====== 辅助方法 ======
    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes('-fullscreen', self.is_fullscreen)

    def update_status(self):
        now = datetime.datetime.now().strftime("%Y/%m/%d-%H:%M")
        identity = self.app.current_identity
        server_ip = _get_local_ip()
        base_text = (
            f"当前页面：{self.app.current_page} | 身份：{identity} | "
            f"系统时间：{now} | 服务器IP：{server_ip}"
        )

        pn532_ok = self.app.check_pn532_connection()
        pn532_status = "已连接" if pn532_ok else "未连接"

        pn532_port = ""
        try:
            if self.app.pn532:
                pv = (self.app.pn532.port or "").strip()
                if pv and pv.lower() != "auto":
                    pn532_port = pv
        except Exception:
            pn532_port = ""
        port_display = f"（{pn532_port}）" if pn532_port else "（未选择端口）"

        def async_hub():
            full_text = base_text + f" | PN532：{pn532_status}{port_display}"

            monitor = self.app.config.get(
                'monitor', {'enabled': True, 'port': 10045, 'display_name': '中枢站'})
            if monitor.get('enabled', True):
                port = monitor.get('port', 10045)
                display_name = monitor.get('display_name', '中枢站')
                hub_open = test_port_silent(port=port)
                hub_status = "运行中" if hub_open else "未运行"
                hub_count = get_hub_count(port=port) if hub_open else 0
                full_text += f" | {display_name}：{hub_status} | 访问人数：{hub_count}人"

            full_text += f" | API服务：{self.api_status}"

            if self.full_status_text != full_text:
                self.full_status_text = full_text
                self.after(0, self._start_scroll)

        threading.Thread(target=async_hub, daemon=True).start()

    def _poll_error_log(self):
        """轮询 ERROR_LOG 检查是否有新报错"""
        if not hasattr(self, '_last_error_size'):
            self._last_error_size = 0
            if os.path.exists(ERROR_LOG):
                self._last_error_size = os.path.getsize(ERROR_LOG)

        if os.path.exists(ERROR_LOG):
            current_size = os.path.getsize(ERROR_LOG)
            if current_size > self._last_error_size:
                try:
                    with open(ERROR_LOG, 'r', encoding='utf-8') as f:
                        f.seek(self._last_error_size)
                        new_lines = f.readlines()
                        if new_lines:
                            last_err = new_lines[-1].strip()
                            if not re.search(r'U盘序列号|检查路径|文件存在', last_err):
                                self._show_cinematic_error("系统运行异常", last_err)
                except Exception:
                    pass
                self._last_error_size = current_size
            elif current_size < self._last_error_size:
                # 文件被清空
                self._last_error_size = current_size

        self.after(3000, self._poll_error_log)

    def _show_cinematic_error(self, title, message):
        """电影级超宽比例报错弹窗"""
        # 如果弹窗已存在，只更新文字，不重复弹
        if hasattr(self, '_error_popup') and self._error_popup and self._error_popup.winfo_exists():
            try:
                self._error_text_var.set(message)
                self._error_popup.lift()
                return
            except Exception:
                pass

        self._error_popup = tk.Toplevel(self)
        self._error_popup.overrideredirect(True)  # 去除系统标题栏
        self._error_popup.attributes('-topmost', True) # 置顶
        
        # 宽长比：约 800x150
        w, h = 800, 150
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self._error_popup.geometry(f"{w}x{h}+{x}+{y}")
        self._error_popup.configure(bg='#111111')

        # 红色外边框
        border = tk.Frame(self._error_popup, bg='#e74c3c', padx=2, pady=2)
        border.pack(fill=tk.BOTH, expand=True)
        
        inner = tk.Frame(border, bg='#111111')
        inner.pack(fill=tk.BOTH, expand=True)

        # 顶部标题
        top_bar = tk.Frame(inner, bg='#e74c3c', height=30)
        top_bar.pack(fill=tk.X)
        top_bar.pack_propagate(False)
        tk.Label(top_bar, text=f" ⚠️ 系统警告 - {title}", font=('微软雅黑', 10, 'bold'), 
                 bg='#e74c3c', fg='white').pack(side=tk.LEFT, padx=10)
                 
        # 关闭按钮
        tk.Button(top_bar, text="×", command=self._error_popup.destroy, 
                  bg='#e74c3c', fg='white', relief=tk.FLAT, 
                  font=('微软雅黑', 12, 'bold'), bd=0).pack(side=tk.RIGHT, padx=10)

        # 报错内容区
        content = tk.Frame(inner, bg='#111111')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self._error_text_var = tk.StringVar(value=message)
        err_lbl = tk.Label(content, textvariable=self._error_text_var, 
                           font=('Consolas', 11), bg='#111111', fg='#ff9999',
                           justify='left', anchor='w', wraplength=740)
        err_lbl.pack(fill=tk.BOTH, expand=True)

        # 底部按钮
        tk.Button(inner, text="Dismiss / 确认", command=self._error_popup.destroy,
                  bg='#333333', fg='white', font=('微软雅黑', 9),
                  relief=tk.FLAT, width=15).pack(pady=(0, 10))

        # 允许拖动
        top_bar.bind("<Button-1>", lambda e: self._error_popup.geometry(f"+{e.x_root - 400}+{e.y_root - 15}"))
        top_bar.bind("<B1-Motion>", lambda e: self._error_popup.geometry(f"+{e.x_root - 400}+{e.y_root - 15}"))

    def refresh_status(self):
        self.update_status()
        self.after(3000, self.refresh_status)

    def show_placeholder(self):
        if hasattr(self, 'tab_bar_frame'):
            self.tab_bar_frame.pack_forget()
        for widget in self.content_area.winfo_children():
            widget.destroy()
        container = tk.Frame(self.content_area, bg='#f0f0f0')
        container.pack(fill=tk.BOTH, expand=True)
        big_font = ('微软雅黑', 28, 'bold')
        title_label = tk.Label(container, text="\n\n欢 迎 使 用\nT A D S 列 车 数 据 与 查 询 服 务 系 统",
                               font=big_font, bg='#f0f0f0', justify='center')
        title_label.pack(expand=True, pady=(50, 0))
        small_font = ('微软雅黑', 10)
        small_text = (
            "© 2026 QS Studio\n"
            "开发者/负责人：Jason Michael (linchenlang)\n"
            "linchenlang@outlook.com\n\n"
            "版本  v26.9.9\n\n\n"
            "RailGo 提供数据支持"
        )
        small_label = tk.Label(container, text=small_text, font=small_font,
                               bg='#f0f0f0', justify='center')
        small_label.pack(expand=True, pady=(20, 50))
        self.placeholder_container = container

    def hide_placeholder(self):
        if hasattr(self, 'placeholder_container') and self.placeholder_container:
            self.placeholder_container.destroy()
            delattr(self, 'placeholder_container')
        if hasattr(self, 'tab_bar_frame'):
            self.tab_bar_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 2), before=self.content_area)
            self.tab_bar_frame.update_idletasks()

    def add_tab(self, title, content_frame, closable=True):
        self.hide_placeholder()
        tab_id = self.tab_counter
        self.tab_counter += 1
        DEFAULT_WIDTH = 160
        font = ('微软雅黑', 10)
        temp_label = tk.Label(self.tab_container, text=title, font=font)
        text_width = temp_label.winfo_reqwidth()
        temp_label.destroy()
        padding = 20
        close_btn_width = 20 if closable else 0
        required_width = text_width + padding + close_btn_width
        preferred_width = max(DEFAULT_WIDTH, required_width)
        preferred_width = min(preferred_width, 220)

        card_height = int(40 * getattr(self, 'scale_factor', 1.0))
        tab_card = tk.Frame(self.tab_container, bg='#e0e0e0', relief=tk.RAISED, bd=1,
                            width=preferred_width, height=card_height)
        tab_card.pack_propagate(False)

        title_label = tk.Label(tab_card, text=title, font=font, bg='#e0e0e0', anchor='w')
        title_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 2), pady=2)

        if closable:
            close_btn = tk.Button(tab_card, text="×", font=('微软雅黑', 10, 'bold'),
                                  bg='#e0e0e0', fg='#666', relief=tk.FLAT,
                                  command=lambda tid=tab_id: self.close_tab(tid),
                                  width=2, height=1)
            close_btn.place(relx=1.0, x=-4, y=1, anchor='ne')
        else:
            close_btn = None

        new_data = {
            'title': title,
            'content_frame': content_frame,
            'tab_card': tab_card,
            'title_label': title_label,
            'close_btn': close_btn,
            'preferred_width': preferred_width
        }

        # 插入逻辑
        current_id = self.current_tab_id
        if current_id is not None and current_id in self.tabs:
            new_tabs = {}
            for tid, data in self.tabs.items():
                new_tabs[tid] = data
                if tid == current_id:
                    new_tabs[tab_id] = new_data
            self.tabs = new_tabs
        else:
            self.tabs[tab_id] = new_data

        # 重新 pack
        for t_data in self.tabs.values():
            t_data['tab_card'].pack_forget()
        for t_data in self.tabs.values():
            t_data['tab_card'].pack(side=tk.LEFT, fill=tk.NONE, expand=False, padx=1, pady=2)

        content_frame.place(in_=self.content_area, x=0, y=0, relwidth=1, relheight=1)
        content_frame.place_forget()

        def on_click(event, tid=tab_id):
            self.switch_tab(tid)
        tab_card.bind("<Button-1>", on_click)
        title_label.bind("<Button-1>", on_click)

        self.switch_tab(tab_id)
        self.reflow_tabs()
        content_frame.tab_id = tab_id
        self.app.current_page = title
        self.update_status()
        return content_frame

    def reflow_tabs(self, event=None):
        container_width = self.tab_container.winfo_width()
        if container_width <= 10:
            return
        tab_cards = []
        preferred_widths = []
        min_widths = []
        for tid, data in self.tabs.items():
            tab_cards.append(data['tab_card'])
            preferred_widths.append(data.get('preferred_width', 160))
            min_widths.append(100)
        if not tab_cards:
            return
        padding = 2
        total_preferred = sum(preferred_widths) + padding * (len(tab_cards) - 1)
        available_width = container_width
        if total_preferred <= available_width:
            for card, pref in zip(tab_cards, preferred_widths):
                card.config(width=pref)
        else:
            total_available = available_width - padding * (len(tab_cards) - 1)
            total_min = sum(min_widths)
            if total_available < total_min:
                for card, min_w in zip(tab_cards, min_widths):
                    card.config(width=min_w)
                self.tab_container.update_idletasks()
                return
            factor = total_available / total_preferred
            new_widths = []
            for pref, min_w in zip(preferred_widths, min_widths):
                w = int(pref * factor)
                if w < min_w:
                    w = min_w
                new_widths.append(w)
            total_new = sum(new_widths) + padding * (len(tab_cards) - 1)
            if total_new > available_width:
                avg_width = (available_width - padding * (len(tab_cards) - 1)) // len(tab_cards)
                for card in tab_cards:
                    card.config(width=max(avg_width, 100))
            else:
                for card, w in zip(tab_cards, new_widths):
                    card.config(width=w)
        self.tab_container.update_idletasks()

    def _on_tab_container_resize(self, event):
        if hasattr(self, '_resize_after_id'):
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(100, self.reflow_tabs)

    def update_tab_title(self, tab_id, new_title):
        if tab_id in self.tabs:
            data = self.tabs[tab_id]
            data['title'] = new_title
            data['title_label'].config(text=new_title)
            font = ('微软雅黑', 10)
            temp_label = tk.Label(self.tab_container, text=new_title, font=font)
            text_width = temp_label.winfo_reqwidth() + 20
            temp_label.destroy()
            close_width = 20 if data['close_btn'] else 0
            new_preferred = text_width + close_width
            new_preferred = max(new_preferred, 80)
            new_preferred = min(new_preferred, 220)
            data['preferred_width'] = new_preferred
            self.reflow_tabs()
            if self.current_tab_id == tab_id:
                self.app.current_page = new_title
                self.update_status()

    def switch_tab(self, tab_id):
        if tab_id not in self.tabs:
            return
        for tid, data in self.tabs.items():
            data['content_frame'].place_forget()
            card = data['tab_card']
            card.configure(bg='#e0e0e0')
            if data['title_label']:
                data['title_label'].configure(bg='#e0e0e0')
            if data['close_btn']:
                data['close_btn'].configure(bg='#e0e0e0')
        current = self.tabs[tab_id]
        current['content_frame'].place(in_=self.content_area, x=0, y=0, relwidth=1, relheight=1)
        current['tab_card'].configure(bg='#ffffff')
        if current['title_label']:
            current['title_label'].configure(bg='#ffffff')
        if current['close_btn']:
            current['close_btn'].configure(bg='#ffffff')
        self.current_tab_id = tab_id
        self.app.current_page = current['title']
        self.update_status()

    def close_tab(self, tab_id):
        if tab_id not in self.tabs:
            return
            
        tab_keys = list(self.tabs.keys())
        idx = tab_keys.index(tab_id)
        is_current = (self.current_tab_id == tab_id)
        
        data = self.tabs[tab_id]
        data['tab_card'].destroy()
        data['content_frame'].destroy()
        del self.tabs[tab_id]
        
        self.reflow_tabs()
        
        if self.tabs:
            if is_current:
                prev_id = None
                for i in range(idx - 1, -1, -1):
                    if tab_keys[i] in self.tabs:
                        prev_id = tab_keys[i]
                        break
                if prev_id is None:
                    prev_id = next(iter(self.tabs))
                self.switch_tab(prev_id)
        else:
            self.show_placeholder()
            self.current_tab_id = None
            self.app.current_page = "无标签"
            self.update_status()
            
        self.update_status()

    def _get_display_train_name(self, train_num):
        """获取车次的合并显示名，若属于合并组则返回合并名，否则返回原车次号"""
        group = self.app.get_merged_by_number(train_num)
        if group:
            return group['display_name']
        return train_num

    # ====== 构建各标签页 ======
    def build_home_frame(self):
        # 外层容器，填满整个 content_area
        outer_frame = tk.Frame(self.content_area, bg='#f0f0f0')
        outer_frame.pack(fill=tk.BOTH, expand=True)

        # 内层容器，用于居中放置内容（标题 + 文本控件）
        content_container = tk.Frame(outer_frame, bg='#f0f0f0')
        content_container.place(relx=0.5, rely=0.5, anchor='center')

        # ===== 恢复标题标签 =====
        tk.Label(
            content_container,
            text="欢迎使用 TADS 列车数据与查询服务系统\n",
            font=('微软雅黑', 25, 'bold'),
            bg='#f0f0f0'
        ).pack(pady=10)

        # 文本控件（用于显示数据库统计信息）
        home_text = scrolledtext.ScrolledText(
            content_container,
            font=('Consolas', 12),
            wrap=tk.NONE,          # 不自动换行，保持原有空格布局
            bg='white',
            height=20,
            width=80
        )
        home_text.pack(padx=10, pady=10)

        # 禁用编辑
        home_text.config(state='disabled')
        outer_frame.home_text = home_text

        # 填充内容
        self._display_welcome_to_text(home_text)

        return outer_frame

    def _display_welcome_to_text(self, text_widget):
        text_widget.config(state='normal')
        text_widget.delete(1.0, tk.END)
        last_write = ""
        if os.path.exists(DATA_FILE):
            mtime = os.path.getmtime(DATA_FILE)
            last_write = datetime.datetime.fromtimestamp(mtime).strftime("%Y/%m/%d-%H:%M")
        else:
            last_write = "无数据文件"
        info = f"""\n\n\n\n
                 T A D S  列  车  数  据  与  查  询  服  务  系  统
                      TADS Train Data & Query Service System
                                       T A D S
  
                      · 数据库最后修改日期：{last_write}
"""
        if self.app.stats:
            s = self.app.stats
            info += f"                      · 数据库记录车站数：{s['station_count']} 个\n"
            info += f"                      · 数据库记录车次数：{s['train_count']} 个\n"
            if s['train_count'] > 0:
                info += f"                        平均每趟车停靠 {s['avg_stops']} 个站\n"
            if s.get('busy_station_name'):
                info += f"                        经过列车最多的车站：{s['busy_station_name']} ({s['busy_station_count']}趟)\n"
        else:
            info += "                      · 数据库尚未加载或数据为空。\n"
        text_widget.insert(tk.END, info)
        text_widget.config(state='disabled')

    def display_welcome(self):
        for tid, data in self.tabs.items():
            if data['title'] == "主页":
                frame = data['content_frame']
                if hasattr(frame, 'home_text'):
                    text_widget = frame.home_text
                    text_widget.config(state='normal')
                    text_widget.delete(1.0, tk.END)
                    text_widget.insert(tk.END, "正在加载数据...\n")
                    text_widget.config(state='disabled')
        def async_update():
            self.app.update_stats()
            self.after(0, self._do_display_welcome)
        threading.Thread(target=async_update, daemon=True).start()

    def _do_display_welcome(self):
        for tid, data in self.tabs.items():
            if data['title'] == "主页":
                frame = data['content_frame']
                if hasattr(frame, 'home_text'):
                    self._display_welcome_to_text(frame.home_text)

    def build_edit_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        status_label = tk.Label(frame, text="当前身份：管理员（可编辑）" if (self.app.is_admin or self.app.is_root) else "当前身份：普通用户（需要管理员权限）",
                                font=('微软雅黑', 10), bg='#f0f0f0')
        status_label.pack(pady=5)

        op_frame = tk.Frame(frame, bg='#f0f0f0')
        op_frame.pack(fill=tk.X, pady=10)

        tk.Label(op_frame, text="新增车次:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=0, column=0, padx=5, pady=3, sticky='e')
        entry_new_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_new_train.grid(row=0, column=1, padx=5, pady=3)
        def add_train_wrapper():
            self._add_train(entry_new_train)
        tk.Button(op_frame, text="确认新增", command=add_train_wrapper, width=12).grid(row=0, column=2, padx=5, pady=3)

        tk.Label(op_frame, text="删除车次:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=1, column=0, padx=5, pady=3, sticky='e')
        entry_del_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_del_train.grid(row=1, column=1, padx=5, pady=3)
        def del_train_wrapper():
            self._del_train(entry_del_train)
        tk.Button(op_frame, text="确认删除", command=del_train_wrapper, width=12).grid(row=1, column=2, padx=5, pady=3)

        tk.Label(op_frame, text="录入停站(车次):", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=2, column=0, padx=5, pady=3, sticky='e')
        entry_add_stop_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_add_stop_train.grid(row=2, column=1, padx=5, pady=3)
        def show_add_stop_wrapper():
            self._show_add_stop_form(frame, entry_add_stop_train)
        tk.Button(op_frame, text="显示录入表单", command=show_add_stop_wrapper, width=14).grid(row=2, column=2, padx=5, pady=3)

        tk.Label(op_frame, text="删除停站(车次):", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=3, column=0, padx=5, pady=3, sticky='e')
        entry_del_stop_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_del_stop_train.grid(row=3, column=1, padx=5, pady=3)
        def show_del_stop_wrapper():
            self._show_del_stop_form(frame, entry_del_stop_train)
        tk.Button(op_frame, text="显示删除列表", command=show_del_stop_wrapper, width=14).grid(row=3, column=2, padx=5, pady=3)

        stop_form_frame = tk.Frame(frame, bg='#f0f0f0')
        stop_form_frame.pack(fill=tk.X, pady=5)
        frame.stop_form_frame = stop_form_frame

        # ---- 批量导入车次（API抓取） ----
        batch_frame = tk.LabelFrame(frame, text="批量导入/更新车次（API抓取）", bg='#f0f0f0', font=('微软雅黑', 10))
        batch_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(batch_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=0, column=0, padx=5, pady=5, sticky='e')
        entry_batch_train = tk.Entry(batch_frame, font=('微软雅黑', 10), width=15)
        entry_batch_train.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(batch_frame, text="接口:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=0, column=2, padx=5, pady=5, sticky='e')
        batch_api_var = tk.StringVar(value="V2")
        combo_batch_api = ttk.Combobox(batch_frame, textvariable=batch_api_var, values=["V1", "V2"], width=8, state="readonly")
        combo_batch_api.grid(row=0, column=3, padx=5, pady=5)

        # 保存按钮引用和状态标签到实例变量
        self.batch_import_btn = tk.Button(batch_frame, text="抓取并导入全部经停站",
                                          command=lambda: self._batch_import_train(entry_batch_train, batch_api_var),
                                          width=20)
        self.batch_import_btn.grid(row=0, column=4, padx=5, pady=5)

        self.batch_status_label = tk.Label(batch_frame, text="", bg='#f0f0f0', font=('微软雅黑', 9), fg='blue')
        self.batch_status_label.grid(row=1, column=0, columnspan=5, padx=5, pady=2)
        frame.batch_status = self.batch_status_label

        # ====== 新增：车站抓取（抓取该站所有车次） ======
        station_crawl_frame = tk.LabelFrame(frame, text="车站抓取（抓取该站所有车次）", bg='#f0f0f0', font=('微软雅黑', 10))
        station_crawl_frame.pack(fill=tk.X, pady=10, padx=5)

        tk.Label(station_crawl_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=0, column=0, padx=5, pady=5, sticky='e')
        entry_crawl_station = tk.Entry(station_crawl_frame, font=('微软雅黑', 10), width=15)
        entry_crawl_station.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(station_crawl_frame, text="接口:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=0, column=2, padx=5, pady=5, sticky='e')
        crawl_api_var = tk.StringVar(value="V1")
        combo_crawl_api = ttk.Combobox(station_crawl_frame, textvariable=crawl_api_var, values=["V1", "V2"], width=8, state="readonly")
        combo_crawl_api.grid(row=0, column=3, padx=5, pady=5)

        # crawl_status 定义移到按钮之前
        crawl_status = tk.Label(station_crawl_frame, text="", bg='#f0f0f0', font=('微软雅黑', 9), fg='blue')
        crawl_status.grid(row=1, column=0, columnspan=5, padx=5, pady=2)
        frame.crawl_status = crawl_status

        btn_crawl_station = tk.Button(station_crawl_frame, text="抓取该站所有车次",
                                       command=lambda: self._crawl_station_trains(entry_crawl_station, crawl_api_var, crawl_status),
                                       width=20)
        btn_crawl_station.grid(row=0, column=4, padx=5, pady=5)

        edit_display = scrolledtext.ScrolledText(frame, font=('Consolas', 11), wrap=tk.WORD, bg='white', height=10)
        edit_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        edit_display.config(state='disabled')
        frame.edit_display = edit_display

        frame.status_label = status_label
        frame.entry_new_train = entry_new_train
        frame.entry_del_train = entry_del_train
        frame.entry_add_stop_train = entry_add_stop_train
        frame.entry_del_stop_train = entry_del_stop_train
        frame.entry_batch_train = entry_batch_train
        frame.batch_api_var = batch_api_var
        frame.entry_crawl_station = entry_crawl_station
        frame.crawl_api_var = crawl_api_var
        return frame

    # ====== 编辑功能实现 ======
    def _add_train(self, entry):
        if not self._check_permission("add_train"):
            return
        number = entry.get().strip()
        if not number:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        if re.search(r'[<>:"/\\|?*]', number):
            messagebox.showerror("错误", "车次号包含非法字符", parent=self)
            return
        if any(t['base_number'] == number for t in self.app.data['trains']):
            messagebox.showinfo("提示", "该车次已存在", parent=self)
            return
        new_id = 1
        if self.app.data['trains']:
            new_id = max(t['train_id'] for t in self.app.data['trains']) + 1
        new_train = {
            'train_id': new_id,
            'base_number': number,
            'type': "未知",
            'start_station': None,
            'end_station': None,
            'stops': []
        }
        self.app.data['trains'].append(new_train)
        self.app.log_action("新增车次", f"{number} (编号{new_id})")
        def async_save():
            self.app.save_data()
            self.app.update_stats()
            self.after(0, self.display_welcome)
        threading.Thread(target=async_save, daemon=True).start()
        messagebox.showinfo("成功", "已录入数据库", parent=self)
        entry.delete(0, tk.END)

    def _del_train(self, entry):
        if not self._check_permission("delete_train"):
            return
        number = entry.get().strip()
        if not number:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        train = self.app.get_train(number)
        if not train:
            messagebox.showerror("错误", "未找到该车次", parent=self)
            return
        def do_remove():
            if not messagebox.askyesno("确认", f"确认删除 {number} 及其所有停站？", parent=self):
                return
            self.app.data['trains'] = [t for t in self.app.data['trains'] if t['train_id'] != train['train_id']]
            self.app.log_action("删除车次", number)
            def async_save():
                self.app.save_data()
                self.app.update_stats()
                self.after(0, self.display_welcome)
            threading.Thread(target=async_save, daemon=True).start()
            messagebox.showinfo("成功", f"{number} 的所有停站数据已从数据库抹除", parent=self)
            entry.delete(0, tk.END)
        do_remove()

    def _show_add_stop_form(self, parent_frame, entry_train):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        train_num = entry_train.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        train = self.app.get_train(train_num)
        if not train:
            messagebox.showerror("错误", "未找到该车次", parent=self)
            return
        for widget in parent_frame.stop_form_frame.winfo_children():
            widget.destroy()
        tk.Label(parent_frame.stop_form_frame, text=f"为 {train_num} 录入停站", bg='#f0f0f0', font=('微软雅黑', 11)).pack(pady=5)
        row_frame = tk.Frame(parent_frame.stop_form_frame, bg='#f0f0f0')
        row_frame.pack(fill=tk.X, pady=2)
        tk.Label(row_frame, text="站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_station = tk.Entry(row_frame, font=('微软雅黑', 10), width=12)
        entry_station.pack(side=tk.LEFT, padx=5)
        tk.Label(row_frame, text="到达:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_arrive = tk.Entry(row_frame, font=('微软雅黑', 10), width=8)
        entry_arrive.pack(side=tk.LEFT, padx=5)
        tk.Label(row_frame, text="出发:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_depart = tk.Entry(row_frame, font=('微软雅黑', 10), width=8)
        entry_depart.pack(side=tk.LEFT, padx=5)
        tk.Label(row_frame, text="跨天(0/1):", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_day = tk.Entry(row_frame, font=('微软雅黑', 10), width=4)
        entry_day.pack(side=tk.LEFT, padx=5)

        def confirm_add():
            if not self._check_permission("add_stop"):
                return
            station = entry_station.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入站名", parent=self)
                return
            arrive = entry_arrive.get().strip() or None
            depart = entry_depart.get().strip() or None
            day_str = entry_day.get().strip()
            day_offset = int(day_str) if day_str.isdigit() else 0
            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                new_sid = 1
                if self.app.data['stations']:
                    new_sid = max(s['id'] for s in self.app.data['stations']) + 1
                self.app.data['stations'].append({'id': new_sid, 'name': station})
                sid = new_sid
            stop = {
                'station_id': sid,
                'station_name': station,
                'arrive': arrive,
                'depart': depart,
                'day_offset': day_offset
            }
            train['stops'].append(stop)
            if len(train['stops']) == 1:
                train['start_station'] = sid
            train['end_station'] = sid
            self.app.log_action("录入经停站", f"{train_num} 添加车站 {station}")
            def async_save():
                self.app.save_data()
                self.app.update_stats()
                self.after(0, self.display_welcome)
            threading.Thread(target=async_save, daemon=True).start()
            messagebox.showinfo("成功", "已录入", parent=self)
            for widget in parent_frame.stop_form_frame.winfo_children():
                widget.destroy()
        tk.Button(row_frame, text="确认录入", command=confirm_add, width=12).pack(side=tk.LEFT, padx=5)

    def _show_del_stop_form(self, parent_frame, entry_train):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        train_num = entry_train.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        train = self.app.get_train(train_num)
        if not train:
            messagebox.showerror("错误", "未找到该车次", parent=self)
            return
        if not train['stops']:
            messagebox.showinfo("提示", "该车次没有停站", parent=self)
            return
        display = parent_frame.edit_display
        display.config(state='normal')
        display.delete(1.0, tk.END)
        display.insert(tk.END, "选择要删除的停站（输入序号）:\n")
        for i, stop in enumerate(train['stops']):
            name = self.app.get_station_name_by_id(stop['station_id'])
            display.insert(tk.END, f"{i+1}. {name}  {stop.get('arrive','')}->{stop.get('depart','')} (跨{stop.get('day_offset',0)})\n")
        display.config(state='disabled')

        def remove_by_index():
            if not self._check_permission("delete_stop"):
                return
            try:
                idx = int(tk.simpledialog.askstring("删除", "请输入要删除的序号:", parent=self))
                if idx is None:
                    return
                if idx < 1 or idx > len(train['stops']):
                    messagebox.showerror("错误", "序号无效", parent=self)
                    return
                if messagebox.askyesno("确认删除", f"确认删除序号 {idx} 的停站？", parent=self):
                    del train['stops'][idx-1]
                    if train['stops']:
                        train['start_station'] = train['stops'][0]['station_id']
                        train['end_station'] = train['stops'][-1]['station_id']
                    else:
                        train['start_station'] = None
                        train['end_station'] = None
                    self.app.log_action("删除停站", train_num)
                    def async_save():
                        self.app.save_data()
                        self.app.update_stats()
                        self.after(0, self.display_welcome)
                    threading.Thread(target=async_save, daemon=True).start()
                    messagebox.showinfo("成功", "已删除停站", parent=self)
                    self._show_del_stop_form(parent_frame, entry_train)
            except:
                pass
        tk.Button(parent_frame.stop_form_frame, text="确认删除", command=remove_by_index, width=12).pack(pady=5)

    # ====== 批量导入功能 ======
    def _batch_import_train(self, entry_train, api_var):
        """批量导入/更新车次：从 API 抓取全部经停站，本地存在则更新，不存在则新增"""
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return

        train_num = entry_train.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return

        # 直接使用实例变量 self.batch_status_label
        if hasattr(self, 'batch_status_label') and self.batch_status_label:
            self.batch_status_label.config(text="正在抓取数据，请稍候...", fg='blue')
            self.batch_status_label.update()

        # 禁用按钮
        if hasattr(self, 'batch_import_btn') and self.batch_import_btn:
            self.batch_import_btn.config(state='disabled')

        def do_import():
            try:
                api_type = api_var.get()
                success, msg, count = self.app.batch_import_train(train_num, api_type)
                # ★★★ 修正：传递正确的参数，不传 status_label 和 btn_widget ★★★
                self.after(0, lambda: self._batch_import_result(success, msg, count, train_num))
            except Exception as e:
                self.after(0, lambda: self._batch_import_result(False, f"异常: {str(e)}", 0, train_num))

        threading.Thread(target=do_import, daemon=True).start()

    def _batch_import_result(self, success, msg, count, train_num, status_label=None, btn_widget=None):
        """批量导入结果回调（兼容旧参数）"""
        # 优先使用实例变量，如果没有则使用传入的参数
        target_label = self.batch_status_label if hasattr(self, 'batch_status_label') and self.batch_status_label else status_label
        target_btn = self.batch_import_btn if hasattr(self, 'batch_import_btn') and self.batch_import_btn else btn_widget

        if target_label:
            if success:
                target_label.config(text=f"✅ {msg}", fg='green')
                messagebox.showinfo("导入成功", f"{msg}", parent=self)
                self.display_welcome()
                self.app.update_stats()
                self.after(1000, lambda: self.refresh_status())
            else:
                target_label.config(text=f"❌ {msg}", fg='red')
                messagebox.showerror("导入失败", msg, parent=self)

        if target_btn and target_btn.winfo_exists():
            target_btn.config(state='normal')

    def _crawl_station_trains(self, entry_station, api_var, status_label):
        """抓取该站所有车次"""
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return

        station = entry_station.get().strip()
        if not station:
            messagebox.showwarning("提示", "请输入车站名", parent=self)
            return

        # 重置状态
        status_label.config(text="正在获取车站车次列表...", fg='blue')
        status_label.update()

        # 禁用按钮
        btn_widget = None
        parent_frame = entry_station.master
        for child in parent_frame.winfo_children():
            if isinstance(child, tk.Button):
                btn_widget = child
                btn_widget.config(state='disabled')
                break

        def do_crawl():
            try:
                # 1. 获取电报码
                telecode = self.app.get_telecode(station)
                if not telecode:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, f"未找到车站 '{station}' 的电报码", []))
                    return

                # 2. 调用 V1 接口获取车站车次列表
                station_data = self.app._call_v1_station_query(telecode)
                if not station_data or 'trains' not in station_data:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, "获取车站数据失败，请检查网络连接", []))
                    return

                trains = station_data.get('trains', [])
                if not trains:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, f"没有车次经过 '{station}'", []))
                    return

                # 3. 提取车次号（取 numberFull 第一个，或 number）
                train_numbers = []
                for train in trains:
                    number_full = train.get('numberFull', [])
                    if number_full:
                        train_numbers.append(number_full[0])
                    else:
                        num = train.get('number')
                        if num:
                            train_numbers.append(num)

                # 去重
                train_numbers = list(dict.fromkeys(train_numbers))

                if not train_numbers:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, "未解析到有效车次号", []))
                    return

                total = len(train_numbers)
                self.after(0, lambda: status_label.config(
                    text=f"找到 {total} 个车次，开始抓取（每秒4个）...", fg='blue'))

                # 4. 逐个抓取（每秒最多4个）
                success_list = []
                failed_list = []
                api_type = api_var.get()

                for idx, train_num in enumerate(train_numbers):
                    try:
                        # 更新进度
                        progress = f"({idx+1}/{total})"
                        self.after(0, lambda p=progress, t=train_num: status_label.config(
                            text=f"正在抓取 {t} {p}...", fg='blue'))

                        # 调用批量导入
                        success, msg, _ = self.app.batch_import_train(train_num, api_type)

                        if success:
                            success_list.append(train_num)
                        else:
                            failed_list.append((train_num, msg))

                        # 每秒最多4个（每个间隔250ms）
                        if (idx + 1) < total:
                            time.sleep(0.25)

                    except Exception as e:
                        failed_list.append((train_num, str(e)))

                # 5. 显示结果
                result_msg = f"抓取完成！成功: {len(success_list)} 个，失败: {len(failed_list)} 个"
                self.after(0, lambda: self._crawl_station_result(
                    status_label, btn_widget, True, result_msg, success_list, failed_list))

                # 如果有失败的车次，弹出详细列表
                if failed_list:
                    failed_detail = "\n".join([f"{num}: {msg}" for num, msg in failed_list[:20]])
                    if len(failed_list) > 20:
                        failed_detail += f"\n... 共 {len(failed_list)} 个失败"
                    self.after(0, lambda: messagebox.showwarning(
                        "部分失败", f"以下车次抓取失败：\n{failed_detail}", parent=self))

                # 刷新数据显示
                self.after(0, self.display_welcome)
                self.after(0, self.app.update_stats)

            except Exception as e:
                self.after(0, lambda: self._crawl_station_result(
                    status_label, btn_widget, False, f"异常: {str(e)}", []))

        threading.Thread(target=do_crawl, daemon=True).start()

    def _crawl_station_result(self, status_label, btn_widget, success, msg, success_list=None, failed_list=None):
        """车站抓取结果回调"""
        if status_label:
            if success:
                status_label.config(text=f"✅ {msg}", fg='green')
            else:
                status_label.config(text=f"❌ {msg}", fg='red')
        if btn_widget:
            btn_widget.config(state='normal')

    # ====== 查看框架 ======
    def build_view_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        # 左侧按钮区
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        def make_view_callback(cmd, frame, suffix):
            def callback():
                cmd(frame)
                if self.current_tab_id is not None:
                    self.update_tab_title(self.current_tab_id, f"查看-{suffix}")
            return callback

        tk.Button(btn_frame, text="车次排行榜（停站数）",
                  command=make_view_callback(self._view_rank, frame, "车次排行榜"),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="查看车次所有经停站",
                  command=make_view_callback(self._view_train_stops, frame, "查看车次所有经停站"),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="查看所有车次时刻表（需管理员）",
                  command=make_view_callback(self._view_all_trains, frame, "查看所有车次时刻表"),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)

        # 右侧表格显示区
        tree_frame = tk.Frame(frame, bg='#f0f0f0')
        tree_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.tree_frame = tree_frame
        return frame

    def _set_view_table(self, frame, columns, rows):
        for widget in frame.tree_frame.winfo_children():
            widget.destroy()
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        tree = ttk.Treeview(frame.tree_frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=120)
        scrollbar = ttk.Scrollbar(frame.tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for row in rows:
            tree.insert('', 'end', values=row)

    def _view_rank(self, frame):
        displays = self.app.get_all_train_displays()
        ranked = sorted(displays, key=lambda d: len(d['stops']), reverse=True)[:20]
        rows = [(str(i+1), d['display_name'], str(len(d['stops']))) for i, d in enumerate(ranked)]
        self._set_view_table(frame, ['名次', '车次', '停站数'], rows)

    def _view_train_stops(self, frame):
        for widget in frame.tree_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.tree_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="输入车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(f, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_view():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            group = self.app.get_merged_by_number(number)
            if group:
                # 使用合并组
                columns = ['序号', '站名', '到达', '出发', '跨天']
                rows = []
                for i, stop in enumerate(group['stops']):
                    name = self.app.get_station_name_by_id(stop['station_id'])
                    rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or '', str(stop.get('day_offset', 0))))
                self._set_view_table(frame, columns, rows)
                return
            # 否则按单列车
            train = self.app.get_train(number)
            if not train:
                self._set_view_table(frame, ['序号', '站名', '到达', '出发', '跨天'], [])
                return
            columns = ['序号', '站名', '到达', '出发', '跨天']
            rows = []
            for i, stop in enumerate(train['stops']):
                name = self.app.get_station_name_by_id(stop['station_id'])
                rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or '', str(stop.get('day_offset', 0))))
            self._set_view_table(frame, columns, rows)
        entry.bind('<Return>', lambda e: do_view())
        tk.Button(f, text="查看", command=do_view, width=12).pack(side=tk.LEFT, padx=5)

    def _view_all_trains(self, frame):
        if not self._check_permission("view_config"):
            return
        displays = self.app.get_all_train_displays()
        rows = [(d['display_name'], d['representative'].get('type', '未知'), str(len(d['stops']))) for d in displays]
        self._set_view_table(frame, ['车次', '类型', '停站数'], rows)

    # ====== 查询框架 ======
    def build_query_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)

        # ---- API 查询开关 ----
        top_control_frame = tk.Frame(frame, bg='#f0f0f0')
        top_control_frame.pack(fill=tk.X, pady=(0, 5))

        # 每个 frame 独立保存自己的 API 状态
        frame._api_query_state = tk.BooleanVar(value=self.app.use_api_query)

        def on_api_toggle(*args):
            new_state = frame._api_query_state.get()
            self.app.use_api_query = new_state
            self.app.log_action("切换API查询", f"状态: {new_state}")

            if hasattr(frame, 'status_api_label') and frame.status_api_label:
                if new_state:
                    frame.status_api_label.config(text="当前: API实时查询", fg='green')
                else:
                    frame.status_api_label.config(text="当前: 本地数据", fg='blue')

            if hasattr(self, '_api_status_label') and self._api_status_label:
                if new_state:
                    self._api_status_label.config(text="当前: API实时查询", fg='green')
                else:
                    self._api_status_label.config(text="当前: 本地数据", fg='blue')

            if self._current_query_context is not None:
                ctx = self._current_query_context
                frm = ctx.get('frame')
                try:
                    if frm and frm.winfo_exists():
                        saved_entry_values = {}
                        if frm:
                            def find_entries(widget):
                                if isinstance(widget, tk.Entry):
                                    saved_entry_values[id(widget)] = widget.get()
                                try:
                                    for child in widget.winfo_children():
                                        find_entries(child)
                                except:
                                    pass
                            find_entries(frm)

                        if ctx['type'] == 'station_trains':
                            self._q_station_trains(ctx['frame'])
                        elif ctx['type'] == 'station_schedule':
                            self._q_station_schedule(ctx['frame'])
                        elif ctx['type'] == 'station_to_station':
                            self._q_station_to_station(ctx['frame'])
                        elif ctx['type'] == 'stop_count':
                            self._q_stop_count(ctx['frame'])
                        elif ctx['type'] == 'train_detail':
                            self._q_train_detail(ctx['frame'])
                        elif ctx['type'] == 'match':
                            self._q_match(ctx['frame'])
                        elif ctx['type'] == 'search':
                            self._q_search(ctx['frame'])
                        elif ctx['type'] == 'current_position':
                            self._q_current_position(ctx['frame'])
                        elif ctx['type'] == 'bidirectional':
                            self._q_bidirectional(ctx['frame'])
                        elif ctx['type'] == 'emu_car':
                            self._q_emu_car(ctx['frame'])

                        def restore_entries():
                            if frm:
                                def find_and_restore(widget):
                                    if isinstance(widget, tk.Entry):
                                        if id(widget) in saved_entry_values:
                                            widget.delete(0, tk.END)
                                            widget.insert(0, saved_entry_values[id(widget)])
                                    try:
                                        for child in widget.winfo_children():
                                            find_and_restore(child)
                                    except:
                                        pass
                                find_and_restore(frm)
                        self.after(50, restore_entries)
                except (tk.TclError, AttributeError):
                    pass

        frame._api_query_state.trace_add('write', on_api_toggle)

        chk_api = tk.Checkbutton(
            top_control_frame,
            text="使用API实时查询（开启后所有查询从API获取）",
            variable=frame._api_query_state,
            bg='#f0f0f0',
            font=('微软雅黑', 10)
        )
        chk_api.pack(side=tk.LEFT, padx=10)

        status_api_label = tk.Label(
            top_control_frame,
            text="当前: API实时查询" if self.app.use_api_query else "当前: 本地数据",
            bg='#f0f0f0',
            font=('微软雅黑', 9),
            fg='green' if self.app.use_api_query else 'blue'
        )
        status_api_label.pack(side=tk.LEFT, padx=10)
        frame.status_api_label = status_api_label
        self._api_status_label = status_api_label

        # ---- 左侧按钮列表 ----
        sub_frame = tk.Frame(frame, bg='#f0f0f0')
        sub_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        btn_list = [
            ("车次停站数量", self._q_stop_count, 'stop_count'),
            ("车次全部经停详情", self._q_train_detail, 'train_detail'),
            ("某站经过的所有车次", self._q_station_trains, 'station_trains'),
            ("站点时刻表（含上一/下一班）", self._q_station_schedule, 'station_schedule'),
            ("车次/站点匹配校验", self._q_match, 'match'),
            ("全局搜索引擎", self._q_search, 'search'),
            ("车次当前理论位置", self._q_current_position, 'current_position'),
            ("两站间今日列车运行", self._q_station_to_station, 'station_to_station'),
            ("车站↔车次查询（含子功能）", self._q_bidirectional, 'bidirectional'),
            ("动车组运行查询", self._q_emu_running, 'emu_running'),
            ("动车组配属查询", self._q_emu_car, 'emu_car')
        ]

        for text, cmd, ctx_type in btn_list:
            def make_callback(cmd, frame, title_suffix, ctx_type):
                def callback():
                    if hasattr(frame, 'display_frame'):
                        for widget in frame.display_frame.winfo_children():
                            widget.destroy()

                    self._current_query_context = {
                        'type': ctx_type,
                        'frame': frame
                    }
                    cmd(frame)
                    if self.current_tab_id is not None:
                        self.update_tab_title(self.current_tab_id, f"查询-{title_suffix}")
                return callback
            btn = tk.Button(
                sub_frame,
                text=text,
                command=make_callback(cmd, frame, text, ctx_type),
                font=('微软雅黑', 10),
                bg='#ecf0f1',
                relief=tk.RAISED,
                bd=1,
                width=26,
                anchor='w',
                padx=5
            )
            btn.pack(anchor='w', pady=2)

        # ---- 右侧显示区域 ----
        display_frame = tk.Frame(frame, bg='#f0f0f0')
        display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.display_frame = display_frame
        self._set_query_content(frame, "请从左侧选择查询功能")
        return frame

    def _toggle_api_query(self):
        """切换API查询模式"""
        new_state = self.api_query_var.get()
        self.app.use_api_query = new_state
        self.app.log_action("切换API查询", f"状态: {new_state}")
        
        # 更新状态标签
        for tid, data in self.tabs.items():
            if data['title'] == "查询":
                frame = data['content_frame']
                if hasattr(frame, 'status_api_label'):
                    if new_state:
                        frame.status_api_label.config(text="当前: API实时查询", fg='green')
                    else:
                        frame.status_api_label.config(text="当前: 本地数据", fg='blue')
                break
        
        # 如果有当前查询标签页，清空显示区域，让用户知道已切换
        if self.current_tab_id is not None:
            current_tab = self.tabs.get(self.current_tab_id)
            if current_tab and current_tab['title'] == "查询":
                frame = current_tab['content_frame']
                if hasattr(frame, 'display_frame'):
                    # 清空显示区域，显示提示
                    for widget in frame.display_frame.winfo_children():
                        widget.destroy()
                    lbl = tk.Label(frame.display_frame, text="已切换查询模式，请重新选择查询功能", 
                                   font=('微软雅黑', 12), bg='#f0f0f0', fg='blue')
                    lbl.pack(pady=20)

    def _set_query_content(self, frame, text):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        lbl = tk.Label(frame.display_frame, text=text, font=('微软雅黑', 12), bg='#f0f0f0')
        lbl.pack(pady=20)

    def _set_query_table(self, frame, columns, rows):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        tree = ttk.Treeview(frame.display_frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=120)
        scrollbar = ttk.Scrollbar(frame.display_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for row in rows:
            tree.insert('', 'end', values=row)

    def _set_query_scrolledtext(self, frame, text):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        st = scrolledtext.ScrolledText(frame.display_frame, font=('Consolas', 11), wrap=tk.WORD, bg='white')
        st.pack(fill=tk.BOTH, expand=True)
        st.insert(tk.END, text)
        st.config(state='disabled')

    # ====== 辅助：时间调整 ======
    def _adjust_time_str(self, time_str, minutes):
        """将时间字符串 'HH:MM' 调整 minutes 分钟，返回新字符串"""
        try:
            dt = datetime.datetime.strptime(time_str, '%H:%M')
            dt = dt + datetime.timedelta(minutes=minutes)
            return dt.strftime('%H:%M')
        except:
            return time_str

    # ====== 查询子功能 ======
    def _q_stop_count(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            group = self.app.get_merged_by_number(number)
            if group:
                for widget in result_frame.winfo_children():
                    widget.destroy()
                tk.Label(result_frame, text=f"车次组 {group['display_name']} 停靠 {len(group['stops'])} 个站",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            train = self.app.get_train(number)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not train:
                tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            tk.Label(result_frame, text=f"车次 {number} 停靠 {len(train.get('stops', []))} 个站",
                     font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_train_detail(self, frame):
        if self.app.use_api_query:
            self._q_train_detail_api(frame)
            return

        """本地模式：车次全部经停详情（纯本地数据，完全不联网）"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        train_info_var = tk.BooleanVar(value=False)
        chk_info = tk.Checkbutton(top_frame, text="显示列车信息", variable=train_info_var, bg='#f0f0f0')
        chk_info.pack(side=tk.LEFT, padx=20)

        # ---- 列车组图片按钮和动车组运行查询按钮 ----
        coach_pic_btn = tk.Button(top_frame, text="查看列车组图片",
                                  command=lambda: self._show_coach_pic_from_entry(entry),
                                  width=16, font=('微软雅黑', 9))
        coach_pic_btn.pack(side=tk.LEFT, padx=10)

        emu_running_btn = tk.Button(top_frame, text="查询动车组运行",
                                    command=lambda: self._open_emu_running_from_entry(entry),
                                    width=16, font=('微软雅黑', 9))
        emu_running_btn.pack(side=tk.LEFT, padx=10)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return

            for widget in result_frame.winfo_children():
                widget.destroy()

            # ---- 本地模式：从本地数据库读取（不联网） ----
            group = self.app.get_merged_by_number(number)
            if not group:
                tk.Label(result_frame, text=f"本地数据库未找到车次 {number}",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            display_name = group['display_name']
            stops = group.get('stops', [])
            if not stops:
                tk.Label(result_frame, text="该车次没有停站数据",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 构建列车信息 ----
            info_parts = [f"车次: {display_name}"]
            rep = group.get('representative', {}) or {}
            if rep.get('type') and rep.get('type') != '未知':
                info_parts.append(f"类型: {rep['type']}")
            info_parts.append("数据来源: 本地数据库")
            info_text = " | ".join(info_parts)

            # ---- 显示列车信息 ----
            if train_info_var.get():
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                info_label = tk.Label(info_frame, text=info_text,
                                      font=('微软雅黑', 10), bg='#f0f0f0',
                                      anchor='w', justify='left')
                info_label.pack(fill=tk.X, padx=10, pady=5)

            title_label = tk.Label(result_frame, text=f"车次 {display_name} 经停详情",
                                   font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
            title_label.pack(pady=5)

            # ---- 表格 ----
            table_frame = tk.Frame(result_frame, bg='#f0f0f0')
            table_frame.pack(fill=tk.BOTH, expand=True)

            columns = ['序号', '站名', '到达', '出发']
            style = ttk.Style()
            style.configure("Treeview", font=('微软雅黑', 11))
            style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
            tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode='browse')
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, anchor='center', width=150)
            scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            # ---- 双击站名 → 打开车站详情 ----
            def on_station_double_click(event):
                item = tree.identify_row(event.y)
                if not item:
                    return
                col = tree.identify_column(event.x)
                if col == '#2':  # 站名列
                    values = tree.item(item, 'values')
                    if values and len(values) > 1:
                        station_name = values[1]
                        if station_name:
                            self._open_station_detail_tab(station_name)

            tree.bind("<Double-1>", on_station_double_click)

            for i, stop in enumerate(stops):
                station_name = stop.get('station_name') or self.app.get_station_name_by_id(stop.get('station_id')) or ''
                arrive = stop.get('arrive') or ''
                depart = stop.get('depart') or ''
                tree.insert('', 'end', values=(str(i + 1), station_name, arrive, depart))

            # ---- 离线模式提示 ----
            tk.Label(result_frame,
                     text="当前为离线模式，未显示正晚点、检票口、站台等信息。",
                     font=('微软雅黑', 9), bg='#f0f0f0', fg='#e67e22').pack(pady=2)

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_train_detail_api(self, frame):
        """API 模式：车次全部经停详情（含检票口、站台、本站车次）"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        delay_var = tk.BooleanVar(value=True)
        chk_delay = tk.Checkbutton(top_frame, text="显示正晚点", variable=delay_var, bg='#f0f0f0')
        chk_delay.pack(side=tk.LEFT, padx=20)

        train_info_var = tk.BooleanVar(value=True)
        chk_info = tk.Checkbutton(top_frame, text="显示列车信息", variable=train_info_var, bg='#f0f0f0')
        chk_info.pack(side=tk.LEFT, padx=20)

        # ---- 新增：列车组图片按钮和动车组运行查询按钮 ----
        coach_pic_btn = tk.Button(top_frame, text="查看列车组图片",
                                  command=lambda: self._show_coach_pic_from_entry(entry),
                                  width=16, font=('微软雅黑', 9))
        coach_pic_btn.pack(side=tk.LEFT, padx=10)

        emu_running_btn = tk.Button(top_frame, text="查询动车组运行",
                                    command=lambda: self._open_emu_running_from_entry(entry),
                                    width=16, font=('微软雅黑', 9))
        emu_running_btn.pack(side=tk.LEFT, padx=10)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return

            for widget in result_frame.winfo_children():
                widget.destroy()

            # ---- 获取 V2 车次主数据（包含 timetable 和 trainCode） ----
            v2_data, error_type, _ = self.app.query_train_from_v2(number)
            if error_type != 'success' or not v2_data:
                tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # 获取合并组信息
            group = self.app.get_merged_by_number(number)
            display_name = group['display_name'] if group else number

            # ---- 从 V2 数据中提取 timetable ----
            timetable = v2_data.get('timetable', [])
            if not timetable:
                tk.Label(result_frame, text="该车次没有停站数据", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 构建列车信息 ----
            info_parts = []
            info_parts.append(f"车次: {display_name}")

            number_kind = v2_data.get('numberKind', '')
            if number_kind:
                info_parts.append(f"类型: {number_kind}")

            number_full = v2_data.get('numberFull', [])
            if number_full and len(number_full) > 1:
                info_parts.append(f"复车次: {', '.join(number_full)}")

            bureau = v2_data.get('bureauShortName', '') or v2_data.get('bureau', '')
            if bureau:
                info_parts.append(f"路局: {bureau}")

            car = v2_data.get('car', '')
            if car:
                info_parts.append(f"车型: {car}")

            car_owner = v2_data.get('carOwner', '')
            if car_owner:
                info_parts.append(f"配属: {car_owner}")

            runner = v2_data.get('runner', '')
            if runner:
                info_parts.append(f"担当: {runner}")

            spend = v2_data.get('spend', 0)
            if spend:
                hours = spend // 60
                minutes = spend % 60
                if hours > 0:
                    info_parts.append(f"运行时长: {hours}时{minutes}分")
                else:
                    info_parts.append(f"运行时长: {minutes}分")

            info_text = " | ".join(info_parts)

            # ---- 显示列车信息 ----
            if train_info_var.get():
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                info_label = tk.Label(info_frame, text=info_text, font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
                info_label.pack(fill=tk.X, padx=10, pady=5)

            # ---- 渲染停站表格 ----
            def render_table(delay_data, exit_data_map=None):
                for widget in result_frame.winfo_children():
                    widget.destroy()

                if train_info_var.get():
                    info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                    info_frame.pack(fill=tk.X, pady=5, padx=5)
                    info_label = tk.Label(info_frame, text=info_text, font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
                    info_label.pack(fill=tk.X, padx=10, pady=5)

                title_label = tk.Label(result_frame, text=f"车次 {display_name} 经停详情", font=('微软雅黑', 12, 'bold'), bg='#f0f0f0')
                title_label.pack(pady=5)

                columns = ['序号', '站名', '到达', '出发', '本站车次', '站台', '检票口', '出站口']
                if delay_data is not None:
                    columns.append('正晚点状态')

                style = ttk.Style()
                style.configure("Treeview", font=('微软雅黑', 11))
                style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
                tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, anchor='center', width=100)
                scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                # ---- 绑定双击事件到"站名"列 ----
                def on_station_double_click(event):
                    """双击站名打开车站详情"""
                    item = tree.identify_row(event.y)
                    if not item:
                        return
                    col = tree.identify_column(event.x)
                    if col == '#2':  # 站名列
                        values = tree.item(item, 'values')
                        if values and len(values) > 1:
                            station_name = values[1]
                            if station_name:
                                self._open_station_detail_tab(station_name)
                
                tree.bind("<Double-1>", on_station_double_click)

                delay_map = {}
                if delay_data:
                    for item in delay_data:
                        station = item.get('stationName')
                        if station:
                            delay_map[station] = item

                now = datetime.datetime.now()
                today = now.date()

                for i, stop in enumerate(timetable):
                    station_name = stop.get('station', '')
                    station_train_code = stop.get('trainCode', '')
                    arrive = stop.get('arrive', '')
                    depart = stop.get('depart', '')
                    
                    # 判断是否已过该站
                    time_str = depart or arrive
                    is_passed = False
                    if time_str:
                        try:
                            dt = datetime.datetime.strptime(time_str, '%H:%M')
                            station_dt = datetime.datetime.combine(today, dt.time())
                            if now > station_dt:
                                is_passed = True
                        except:
                            pass
                    
                    status = ''
                    if delay_map and station_name in delay_map:
                        item = delay_map[station_name]
                        code = item.get('delayStatusCode')
                        time_val = item.get('delayTime', 0)
                        if code in ('ON_TIME', 'ON_TIME_PREDICTION'):
                            status = '正点'
                        elif code in ('DELAY', 'DELAY_PREDICTION'):
                            status = f'晚点{time_val}分钟'
                        elif code in ('EARLY', 'EARLY_PREDICTION'):
                            status = f'提前{time_val}分钟'
                        else:
                            status = '未维护'
                        
                        if not is_passed and status not in ('未维护', ''):
                            status = f'预计{status}'
                    
                    platform = ''
                    entrance = ''
                    exit_str = ''
                    if exit_data_map and station_name in exit_data_map:
                        exit_info = exit_data_map[station_name]
                        platform = exit_info.get('platform', '')
                        entrance = '/'.join(exit_info.get('entrance', [])) if exit_info.get('entrance') else ''
                        exit_str = '/'.join(exit_info.get('exit', [])) if exit_info.get('exit') else ''
                    
                    row = (str(i+1), station_name, arrive, depart, station_train_code, platform, entrance, exit_str)
                    if delay_data is not None:
                        row = row + (status,)
                    tree.insert('', 'end', values=row)

                # ====== 自动更新本地数据库（异步执行，不阻塞查询结果） ======
                if self.app.auto_update_on_query:
                    if self.app.is_admin or self.app.is_root:
                        def do_auto_update():
                            try:
                                success, msg, _ = self.app.batch_import_train(number, "V2", auto_update=True)
                                if success:
                                    self.show_temp_message(f"{number} 已更新至本地数据库")
                                    self.app.log_action("自动更新车次", f"{number} 成功")
                                else:
                                    self.app.log_action("自动更新车次失败", f"{number}: {msg}")
                            except Exception as e:
                                self.app.log_action("自动更新车次异常", f"{number}: {str(e)}")
                        threading.Thread(target=do_auto_update, daemon=True).start()
                    else:
                        self.app.log_action("自动更新车次失败", f"{number}: 无管理员权限")

            # ---- 获取正晚点和检票口信息 ----
            loading_label = tk.Label(result_frame, text="正在获取数据，请稍候...", font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
            loading_label.pack(pady=20)
            btn.config(state='disabled')
            entry.config(state='disabled')

            def fetch_all():
                import concurrent.futures
                
                delay_data = None
                if delay_var.get():
                    delay_data = self.app._get_train_delay(number, timeout=5)
                
                # ---- 4并发获取检票口/站台信息 ----
                exit_data_map = {}
                
                stations_to_query = []
                for stop in timetable:
                    station_name = stop.get('station', '')
                    station_telecode = stop.get('stationTelecode', '')
                    train_code = stop.get('trainCode', number)
                    if station_telecode:
                        stations_to_query.append({
                            'name': station_name,
                            'telecode': station_telecode,
                            'train_code': train_code
                        })
                
                if stations_to_query:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                        future_to_station = {}
                        for station in stations_to_query:
                            future = executor.submit(
                                self.app._get_train_exit, 
                                station['train_code'], 
                                station['telecode']
                            )
                            future_to_station[future] = station['name']
                        
                        for future in concurrent.futures.as_completed(future_to_station):
                            station_name = future_to_station[future]
                            try:
                                exit_info = future.result(timeout=30)
                                if exit_info:
                                    exit_data_map[station_name] = exit_info
                            except Exception as e:
                                self.app.write_error_log(f"获取检票口失败 {station_name}: {e}")
                
                self.after(0, lambda: after_fetch(delay_data, exit_data_map))

            def after_fetch(delay_data, exit_data_map):
                loading_label.destroy()
                btn.config(state='normal')
                entry.config(state='normal')
                if delay_data is None and delay_var.get():
                    messagebox.showwarning("提示", f"获取 {display_name} 正晚点数据失败", parent=self)
                render_table(delay_data, exit_data_map)

            threading.Thread(target=fetch_all, daemon=True).start()

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_station_trains(self, frame):
        """本地模式：某站经过的所有车次（含合并，按时间排序）"""
        if self.app.use_api_query:
            self._q_station_trains_api(frame)
            return

        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return

            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                tk.Label(result_frame, text="未找到车站", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 获取车站信息（从V1接口获取补充信息） ----
            station_info = None
            telecode = self.app.get_telecode(station)
            if telecode:
                station_data = self.app._call_v1_station_query(telecode)
                if station_data and 'data' in station_data:
                    station_info = station_data['data']

            # ---- 获取经过该站的所有车次号 ----
            train_numbers = []
            for train in self.app.data.get('trains', []):
                for stop in train.get('stops', []):
                    if stop['station_id'] == sid:
                        train_numbers.append(train['base_number'])
                        break
            if not train_numbers:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 使用合并组去重并获取始发/终点 ----
            merged_results = {}
            processed = set()
            for number in train_numbers:
                if number in processed:
                    continue
                group = self.app.get_merged_by_number(number)
                if group:
                    display_name = group['display_name']
                    if display_name not in merged_results:
                        stops = group.get('stops', [])
                        start_station = stops[0].get('station_name', '') if stops else ''
                        end_station = stops[-1].get('station_name', '') if stops else ''
                        
                        # 提取经过当前站的时间
                        t_arrive, t_depart = '', ''
                        for s in stops:
                            if s.get('station_name') == station or s.get('station_id') == sid:
                                t_arrive = s.get('arrive') or ''
                                t_depart = s.get('depart') or ''
                                break

                        merged_results[display_name] = {
                            'numbers': group['numbers'],
                            'stops': group['stops'],
                            'representative': group['representative'],
                            'start': start_station,
                            'end': end_station,
                            'arrive': t_arrive,
                            'depart': t_depart
                        }
                        for n in group['numbers']:
                            processed.add(n)
                else:
                    if number not in merged_results:
                        train = self.app.get_train(number)
                        stops = train.get('stops', []) if train else []
                        start_station = stops[0].get('station_name', '') if stops else ''
                        end_station = stops[-1].get('station_name', '') if stops else ''
                        
                        t_arrive, t_depart = '', ''
                        for s in stops:
                            if s.get('station_name') == station or s.get('station_id') == sid:
                                t_arrive = s.get('arrive') or ''
                                t_depart = s.get('depart') or ''
                                break

                        merged_results[number] = {
                            'numbers': [number],
                            'stops': [],
                            'representative': {},
                            'start': start_station,
                            'end': end_station,
                            'arrive': t_arrive,
                            'depart': t_depart
                        }
                    processed.add(number)

            # ---- 直接渲染 ----
            for widget in result_frame.winfo_children():
                widget.destroy()

            # ---- 显示车站信息 ----
            if station_info:
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                d = station_info
                info_parts = [f"车站: {d.get('name', station)}"]
                if d.get('telecode'): info_parts.append(f"电报码: {d['telecode']}")
                if d.get('bureau'): info_parts.append(f"路局: {d['bureau']}")
                if d.get('city'): info_parts.append(f"城市: {d['city']}")
                info_text = " | ".join(info_parts)
                info_label = tk.Label(info_frame, text=info_text, font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
                info_label.pack(fill=tk.X, padx=10, pady=5)

            columns = ['序号', '车次', '始发站', '终点站', '到达', '出发', '停站数']
            style = ttk.Style()
            style.configure("Treeview", font=('微软雅黑', 11))
            style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
            tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, anchor='center', width=120)
            scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))

            # 按时间排序
            def time_key(item):
                info = item[1]
                t = info.get('depart') or info.get('arrive')
                if t:
                    try:
                        return datetime.datetime.strptime(t, '%H:%M').time()
                    except:
                        pass
                return datetime.time(23, 59, 59)

            idx = 1
            for display_name, info in sorted(merged_results.items(), key=time_key):
                numbers = info.get('numbers', [display_name])
                display = '/'.join(numbers)
                start_st = info.get('start', '')
                end_st = info.get('end', '')
                arrive = info.get('arrive') or ''
                depart = info.get('depart') or ''
                day_off = info.get('day_offset', 0)
                day_info = "次日" if day_off == 1 else "当日"
                tree.insert('', 'end', values=(str(idx), display, start_st, end_st, arrive, depart, day_info))
                idx += 1

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_station_trains_api(self, frame):
        """API 模式：某站经过的所有车次（按时间排序）"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return

            telecode = self.app.get_telecode(station)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not telecode:
                tk.Label(result_frame, text=f"未找到车站 '{station}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            station_data = self.app._call_v1_station_query(telecode)
            if not station_data:
                tk.Label(result_frame, text="获取车站数据失败，请检查网络连接", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            trains = station_data.get('trains', [])
            if not trains:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            if 'data' in station_data:
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                d = station_data['data']
                info_parts = [f"车站: {d.get('name', station)}"]
                if d.get('telecode'): info_parts.append(f"电报码: {d['telecode']}")
                if d.get('bureau'): info_parts.append(f"路局: {d['bureau']}")
                if d.get('city'): info_parts.append(f"城市: {d['city']}")
                tk.Label(info_frame, text=" | ".join(info_parts), font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left').pack(fill=tk.X, padx=10, pady=5)

            merged = {}
            for train in trains:
                number_full = train.get('numberFull', [])
                if not number_full:
                    n = train.get('number', '')
                    if n: number_full = [n]
                if not number_full: continue
                
                key = '/'.join(number_full)
                if key in merged: continue
                
                timetable = train.get('timetable', [])
                start_st = train.get('fromStation', {}).get('station', '')
                end_st = train.get('toStation', {}).get('station', '')
                if not start_st and timetable: start_st = timetable[0].get('station', '')
                if not end_st and timetable: end_st = timetable[-1].get('station', '')
                
                merged[key] = {
                    'display': key,
                    'start': start_st,
                    'end': end_st,
                    'arrive': train.get('arrive', ''),
                    'depart': train.get('depart', ''),
                    'stop_count': len(timetable) if timetable else 0,
                }

            columns = ['序号', '车次', '始发站', '终点站', '到达', '出发', '停站数']
            style = ttk.Style()
            style.configure("Treeview", font=('微软雅黑', 11))
            style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
            tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, anchor='center', width=120)
            scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))

            # 按时间排序
            def time_key(item):
                info = item[1]
                t = info.get('depart') or info.get('arrive')
                if t:
                    try:
                        return datetime.datetime.strptime(t, '%H:%M').time()
                    except:
                        pass
                return datetime.time(23, 59, 59)

            idx = 1
            for key, info in sorted(merged.items(), key=time_key):
                tree.insert('', 'end', values=(
                    str(idx), info['display'], info['start'], info['end'],
                    info['arrive'], info['depart'], str(info['stop_count'])
                ))
                idx += 1

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_station_schedule(self, frame):
        """本地模式：站点时刻表（含上一班/下一班）"""
        if self.app.use_api_query:
            self._q_station_schedule_api(frame)
            return

        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return

            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                tk.Label(result_frame, text="未找到车站", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 获取车站信息 ----
            station_info = None
            telecode = self.app.get_telecode(station)
            if telecode:
                station_data = self.app._call_v1_station_query(telecode)
                if station_data and 'data' in station_data:
                    station_info = station_data['data']

            # 获取经过该站的所有车次号
            train_numbers = []
            for train in self.app.data.get('trains', []):
                for stop in train.get('stops', []):
                    if stop['station_id'] == sid:
                        train_numbers.append(train['base_number'])
                        break
            if not train_numbers:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 合并处理 ----
            merged_results = {}
            processed = set()
            for number in train_numbers:
                if number in processed:
                    continue
                group = self.app.get_merged_by_number(number)
                if group:
                    display_name = group['display_name']
                    if display_name not in merged_results:
                        stops = group.get('stops', [])
                        start_station = stops[0].get('station_name', '') if stops else ''
                        end_station = stops[-1].get('station_name', '') if stops else ''
                        merged_results[display_name] = {
                            'numbers': group['numbers'],
                            'stops': group['stops'],
                            'representative': group['representative'],
                            'start': start_station,
                            'end': end_station
                        }
                        for n in group['numbers']:
                            processed.add(n)
                else:
                    if number not in merged_results:
                        train = self.app.get_train(number)
                        stops = train.get('stops', []) if train else []
                        start_station = stops[0].get('station_name', '') if stops else ''
                        end_station = stops[-1].get('station_name', '') if stops else ''
                        merged_results[number] = {
                            'numbers': [number],
                            'stops': [],
                            'representative': {},
                            'start': start_station,
                            'end': end_station
                        }
                    processed.add(number)

            # ---- 构建列表（只取该站的时间） ----
            merged_list = []
            for display_name, info in merged_results.items():
                stops = info.get('stops', [])
                for stop in stops:
                    if stop.get('station_name') == station or stop.get('station_id') == sid:
                        time_str = stop.get('depart') or stop.get('arrive')
                        if time_str:
                            merged_list.append({
                                'display_name': display_name,
                                'numbers': info.get('numbers', [display_name]),
                                'start': info.get('start', ''),
                                'end': info.get('end', ''),
                                'time': time_str,
                                'day_offset': stop.get('day_offset', 0),
                                'arrive': stop.get('arrive'),
                                'depart': stop.get('depart')
                            })
                        break

            if not merged_list:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 直接渲染 ----
            for widget in result_frame.winfo_children():
                widget.destroy()

            # ---- 显示车站信息 ----
            if station_info:
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                d = station_info
                info_parts = [f"车站: {d.get('name', station)}"]
                if d.get('telecode'): info_parts.append(f"电报码: {d['telecode']}")
                if d.get('bureau'): info_parts.append(f"路局: {d['bureau']}")
                info_text = " | ".join(info_parts)
                info_label = tk.Label(info_frame, text=info_text, font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
                info_label.pack(fill=tk.X, padx=10, pady=5)

            now = datetime.datetime.now()
            today = now.date()

            # 计算上一班/下一班
            stops_with_time = []
            for item in merged_list:
                t = item.get('time')
                if not t: continue
                try:
                    time_obj = datetime.datetime.strptime(t, '%H:%M').time()
                    day_off = item.get('day_offset', 0)
                    abs_date = today + datetime.timedelta(days=day_off)
                    abs_dt = datetime.datetime.combine(abs_date, time_obj)
                    stops_with_time.append((item, abs_dt))
                except:
                    continue

            stops_with_time.sort(key=lambda x: x[1])
            prev_item = None
            next_item = None
            for item, abs_dt in stops_with_time:
                if abs_dt < now:
                    prev_item = (item, abs_dt)
                else:
                    next_item = (item, abs_dt)
                    break

            header = f"当前时间: {now.strftime('%H:%M')}\n"
            if prev_item:
                item, abs_dt = prev_item
                display_name = item.get('display_name')
                t = item.get('time')
                if abs_dt.date() < now.date(): date_mark = "（昨日）"
                elif abs_dt.date() > now.date(): date_mark = "（次日）"
                else: date_mark = ""
                header += f"上一班车: {display_name}  {t}{date_mark}\n"
            else:
                header += "上一班车: 无\n"

            if next_item:
                item, abs_dt = next_item
                display_name = item.get('display_name')
                t = item.get('time')
                if abs_dt.date() < now.date(): date_mark = "（昨日）"
                elif abs_dt.date() > now.date(): date_mark = "（次日）"
                else: date_mark = ""
                header += f"下一班车: {display_name}  {t}{date_mark}\n"
            else:
                header += "下一班车: 无\n"

            header += "=" * 50 + "\n所有经过该站的车次:\n"
            tk.Label(result_frame, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT).pack(fill=tk.X, padx=5, pady=2)

            columns = ['序号', '车次', '始发站', '终点站', '到达', '出发', '跨天']
            style = ttk.Style()
            style.configure("Treeview", font=('微软雅黑', 11))
            style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
            tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, anchor='center', width=100)
            scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

            tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))

            def sort_key(item):
                t = item.get('time')
                if t:
                    try:
                        dt = datetime.datetime.strptime(t, '%H:%M')
                        dt = dt.replace(day=dt.day + item.get('day_offset', 0))
                        return dt
                    except:
                        pass
                return datetime.datetime.max

            idx = 1
            for item in sorted(merged_list, key=sort_key):
                display_name = item.get('display_name')
                start_st = item.get('start', '')
                end_st = item.get('end', '')
                arrive = item.get('arrive') or ''
                depart = item.get('depart') or ''
                day_off = item.get('day_offset', 0)
                day_info = "次日" if day_off == 1 else "当日"
                tree.insert('', 'end', values=(str(idx), display_name, start_st, end_st, arrive, depart, day_info))
                idx += 1

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_station_schedule_api(self, frame):
        """API 模式：站点时刻表（含合并组 + 上一班/下一班）"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return

            telecode = self.app.get_telecode(station)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not telecode:
                tk.Label(result_frame, text=f"未找到车站 '{station}' 的电报码",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            station_data = self.app._call_v1_station_query(telecode)
            if not station_data:
                tk.Label(result_frame, text="获取车站数据失败，请检查网络连接",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            trains = station_data.get('trains', [])
            if not trains:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # 合并去重
            merged = {}
            for train in trains:
                number_full = train.get('numberFull', [])
                if not number_full:
                    n = train.get('number', '')
                    if n:
                        number_full = [n]
                if not number_full:
                    continue
                key = '/'.join(number_full)
                if key in merged:
                    continue
                timetable = train.get('timetable', [])
                start_st = train.get('fromStation', {}).get('station', '')
                end_st = train.get('toStation', {}).get('station', '')
                if not start_st and timetable:
                    start_st = timetable[0].get('station', '')
                if not end_st and timetable:
                    end_st = timetable[-1].get('station', '')
                merged[key] = {
                    'display': key,
                    'start': start_st,
                    'end': end_st,
                    'arrive': train.get('arrive', ''),
                    'depart': train.get('depart', ''),
                }

            merged_list = list(merged.values())

            # 车站信息
            if 'data' in station_data:
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                d = station_data['data']
                info_parts = [f"车站: {d.get('name', station)}"]
                for key, label in [('telecode', '电报码'), ('pinyin', '拼音'),
                                    ('pinyinTriple', '三字码'), ('belong', '所属'),
                                    ('bureau', '路局'), ('province', '省份'),
                                    ('city', '城市'), ('level', '等级')]:
                    if d.get(key):
                        info_parts.append(f"{label}: {d[key]}")
                tk.Label(info_frame, text=" | ".join(info_parts), font=('微软雅黑', 10),
                         bg='#f0f0f0', anchor='w', justify='left').pack(fill=tk.X, padx=10, pady=5)

            now = datetime.datetime.now()
            today = now.date()

            # 上一班 / 下一班
            stops_with_time = []
            for item in merged_list:
                t = item.get('depart') or item.get('arrive')
                if not t:
                    continue
                try:
                    time_obj = datetime.datetime.strptime(t, '%H:%M').time()
                    abs_dt = datetime.datetime.combine(today, time_obj)
                    stops_with_time.append((item, abs_dt))
                except:
                    continue

            stops_with_time.sort(key=lambda x: x[1])
            prev_item = None
            next_item = None
            for item, abs_dt in stops_with_time:
                if abs_dt < now:
                    prev_item = (item, abs_dt)
                else:
                    next_item = (item, abs_dt)
                    break

            header = f"当前时间: {now.strftime('%H:%M')}\n"
            if prev_item:
                item, _ = prev_item
                t = item.get('depart') or item.get('arrive')
                header += f"上一班车: {item['display']}  {t}\n"
            else:
                header += "上一班车: 无\n"
            if next_item:
                item, _ = next_item
                t = item.get('depart') or item.get('arrive')
                header += f"下一班车: {item['display']}  {t}\n"
            else:
                header += "下一班车: 无\n"
            header += "=" * 50 + "\n所有经过该站的车次:\n"
            tk.Label(result_frame, text=header, font=('微软雅黑', 10),
                     bg='#f0f0f0', justify=tk.LEFT).pack(fill=tk.X, padx=5, pady=2)

            columns = ['序号', '车次', '始发站', '终点站', '到达', '出发', '跨天']
            style = ttk.Style()
            style.configure("Treeview", font=('微软雅黑', 11))
            style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
            tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, anchor='center', width=100)
            scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))

            def sort_key(item):
                t = item.get('depart') or item.get('arrive')
                if t:
                    try:
                        return datetime.datetime.strptime(t, '%H:%M')
                    except:
                        pass
                return datetime.datetime.max

            idx = 1
            for item in sorted(merged_list, key=sort_key):
                tree.insert('', 'end', values=(
                    str(idx), item['display'], item['start'], item['end'],
                    item.get('arrive', ''), item.get('depart', ''), '当日'
                ))
                idx += 1

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_station_to_station(self, frame):
        # 如果开启了 API 查询，使用 API 数据
        if self.app.use_api_query:
            self._q_station_to_station_api(frame)
            return

        # 原有本地查询逻辑
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_start = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_start.pack(side=tk.LEFT, padx=5)
        tk.Label(top_frame, text="终止站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_end = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_end.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        delay_var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(top_frame, text="显示正晚点", variable=delay_var, bg='#f0f0f0')
        chk.pack(side=tk.LEFT, padx=20)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            start = entry_start.get().strip()
            end = entry_end.get().strip()
            if not start or not end:
                messagebox.showwarning("提示", "请输入起始站和终止站", parent=self)
                return
            start_id = self.app.get_station_id_by_name(start)
            end_id = self.app.get_station_id_by_name(end)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if start_id is None or end_id is None:
                tk.Label(result_frame, text="未找到车站", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            candidates = []
            for train in self.app.data['trains']:
                stops = train['stops']
                start_idx = -1
                end_idx = -1
                for i, s in enumerate(stops):
                    if s['station_id'] == start_id:
                        start_idx = i
                    if s['station_id'] == end_id:
                        end_idx = i
                if start_idx >= 0 and end_idx > start_idx:
                    start_stop = stops[start_idx]
                    end_stop = stops[end_idx]
                    if start_stop.get('depart') and end_stop.get('arrive'):
                        candidates.append((train, start_stop, end_stop))
            if not candidates:
                tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 方向的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            def render_table(delay_map):
                for widget in result_frame.winfo_children():
                    widget.destroy()
                # 去重
                dedup_dict = {}
                for train, s_stop, e_stop in candidates:
                    display_name = self._get_display_train_name(train['base_number'])
                    if display_name not in dedup_dict:
                        dedup_dict[display_name] = (train, s_stop, e_stop)
                dedup_candidates = list(dedup_dict.values())

                now = datetime.datetime.now()
                today = now.date()
                results = []
                for train, s_stop, e_stop in dedup_candidates:
                    first_stop = train['stops'][0]
                    first_depart_raw = first_stop.get('depart') or first_stop.get('arrive')
                    first_depart = None
                    if first_depart_raw:
                        try:
                            first_depart = datetime.datetime.combine(today, datetime.datetime.strptime(first_depart_raw, '%H:%M').time()) + datetime.timedelta(days=first_stop.get('day_offset', 0))
                        except:
                            pass
                    today_departed = first_depart and first_depart <= now
                    base_date = today
                    date_label = "今天"
                    if not today_departed:
                        yesterday = today - datetime.timedelta(days=1)
                        y_first = None
                        if first_depart_raw:
                            try:
                                y_first = datetime.datetime.combine(yesterday, datetime.datetime.strptime(first_depart_raw, '%H:%M').time()) + datetime.timedelta(days=first_stop.get('day_offset', 0))
                            except:
                                pass
                        if y_first:
                            last_stop = train['stops'][-1]
                            last_time_raw = last_stop.get('arrive') or last_stop.get('depart')
                            y_last = None
                            if last_time_raw:
                                try:
                                    y_last = datetime.datetime.combine(yesterday, datetime.datetime.strptime(last_time_raw, '%H:%M').time()) + datetime.timedelta(days=last_stop.get('day_offset', 0))
                                except:
                                    pass
                            if y_last and y_last >= now:
                                base_date = yesterday
                                date_label = "昨天"

                    def get_abs_time(stop, base):
                        t = stop.get('depart') or stop.get('arrive')
                        if not t:
                            return None
                        try:
                            dt = datetime.datetime.combine(base, datetime.datetime.strptime(t, '%H:%M').time()) + datetime.timedelta(days=stop.get('day_offset', 0))
                            return dt
                        except:
                            return None
                    start_abs = get_abs_time(s_stop, base_date)
                    end_abs = get_abs_time(e_stop, base_date)
                    if not start_abs or not end_abs:
                        continue
                    if now < start_abs:
                        status = f"未到达 {start}"
                    elif start_abs <= now < end_abs:
                        status = f"正在 {start}->{end} 运行"
                    else:
                        status = f"已到达 {end}"
                    results.append({
                        'train': train['base_number'],
                        'start_time': start_abs,
                        'end_time': end_abs,
                        'status': status,
                        'date_label': date_label,
                        'train_obj': train,
                        'start_stop': s_stop,
                        'end_stop': e_stop
                    })
                results.sort(key=lambda x: x['start_time'])

                # ---- 新增序号列 ----
                columns = ['序号', '车次', f'{start}发车', f'{end}到达', '状态']
                if delay_map:
                    columns.append('正晚点状态')

                just_passed = None
                coming_soon = None
                min_past_diff = None
                min_future_diff = None
                for r in results:
                    if r['status'].startswith("已到达"):
                        diff = (now - r['end_time']).total_seconds()
                        if diff >= 0:
                            if min_past_diff is None or diff < min_past_diff:
                                min_past_diff = diff
                                just_passed = r
                    elif r['status'].startswith("未到达"):
                        diff = (r['start_time'] - now).total_seconds()
                        if diff >= 0:
                            if min_future_diff is None or diff < min_future_diff:
                                min_future_diff = diff
                                coming_soon = r

                header = f"经过 '{start}' -> '{end}' 区间的车次 (共 {len(results)} 趟)\n"
                if just_passed:
                    train_display = self._get_display_train_name(just_passed['train'])
                    t = just_passed['end_time'].strftime('%H:%M')
                    if just_passed['date_label'] == "昨天":
                        t += "(昨)"
                    header += f"刚过掉: {train_display}（{t} 到达 {end}）"
                else:
                    header += "刚过掉: 无"
                if coming_soon:
                    train_display = self._get_display_train_name(coming_soon['train'])
                    t = coming_soon['start_time'].strftime('%H:%M')
                    if coming_soon['date_label'] == "昨天":
                        t += "(昨)"
                    header += f"\n马上进入: {train_display}（{t} 从 {start} 发车）"
                else:
                    header += "\n马上进入: 无"
                tk.Label(result_frame, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT).pack(fill=tk.X, padx=5, pady=2)

                style = ttk.Style()
                style.configure("Treeview", font=('微软雅黑', 11))
                style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
                tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, anchor='center', width=120)
                scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                idx = 1
                for r in results:
                    train_display = self._get_display_train_name(r['train'])
                    s_str = r['start_time'].strftime('%H:%M')
                    e_str = r['end_time'].strftime('%H:%M')
                    if r['date_label'] == "昨天":
                        s_str += "(昨)"
                        e_str += "(昨)"
                    row = (str(idx), train_display, s_str, e_str, r['status'])
                    if delay_map:
                        train_num = r['train']
                        station_delay = delay_map.get(train_num, {})
                        status_delay = ''
                        if station_delay:
                            for st in [start, end]:
                                if st in station_delay:
                                    item = station_delay[st]
                                    code = item.get('delayStatusCode')
                                    time_val = item.get('delayTime', 0)
                                    if code in ('ON_TIME', 'ON_TIME_PREDICTION'):
                                        status_delay = '正点'
                                    elif code in ('DELAY', 'DELAY_PREDICTION'):
                                        status_delay = f'晚点{time_val}分钟'
                                    elif code in ('EARLY', 'EARLY_PREDICTION'):
                                        status_delay = f'提前{time_val}分钟'
                                    else:
                                        status_delay = '未维护'
                                    break
                        row = row + (status_delay,)
                    tree.insert('', 'end', values=row)
                    idx += 1

            if delay_var.get():
                loading_label = tk.Label(result_frame, text="正在获取所有车次正晚点数据，请稍候...", font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
                loading_label.pack(pady=20)
                btn.config(state='disabled')
                entry_start.config(state='disabled')
                entry_end.config(state='disabled')

                def fetch_all():
                    delay_map = {}
                    # 去重后获取
                    dedup_dict = {}
                    for train, _, _ in candidates:
                        display_name = self._get_display_train_name(train['base_number'])
                        if display_name not in dedup_dict:
                            dedup_dict[display_name] = train
                    for train in dedup_dict.values():
                        train_num = train['base_number']
                        delay_data = self.app._get_train_delay(train_num)
                        if delay_data:
                            station_delay = {}
                            for item in delay_data:
                                st = item.get('stationName')
                                if st:
                                    station_delay[st] = item
                            delay_map[train_num] = station_delay
                    self.after(0, lambda: after_fetch(delay_map))

                def after_fetch(delay_map):
                    loading_label.destroy()
                    btn.config(state='normal')
                    entry_start.config(state='normal')
                    entry_end.config(state='normal')
                    render_table(delay_map)

                threading.Thread(target=fetch_all, daemon=True).start()
            else:
                render_table({})

        btn.config(command=do_query)
        entry_start.bind('<Return>', lambda e: do_query())
        entry_end.bind('<Return>', lambda e: do_query())

    def _q_match(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_train = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_train.pack(side=tk.LEFT, padx=5)
        tk.Label(top_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_station = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_station.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="匹配", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            number = entry_train.get().strip()
            station = entry_station.get().strip()
            if not number or not station:
                messagebox.showwarning("提示", "请输入车次和车站", parent=self)
                return
            train = self.app.get_train(number)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not train:
                tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            # 直接通过站名匹配
            match = any(stop.get('station_name') == station for stop in train.get('stops', []))
            result_text = f"{number} {'经停' if match else '不经停'} {station}"
            tk.Label(result_frame, text=result_text, font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)

        btn.config(command=do_query)
        entry_train.bind('<Return>', lambda e: do_query())
        entry_station.bind('<Return>', lambda e: do_query())

    def _q_search(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="关键词:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=20)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="搜索", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            keyword = entry.get().strip()
            if not keyword:
                messagebox.showwarning("提示", "请输入关键词", parent=self)
                return
            results = self.app.search(keyword)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not results:
                tk.Label(result_frame, text="未找到匹配项", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            columns = ['类型', '名称', '详情']
            style = ttk.Style()
            style.configure("Treeview", font=('微软雅黑', 11))
            style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
            tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, anchor='center', width=150)
            scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            for r in results:
                tree.insert('', 'end', values=(r['type'], r['name'], r['detail']))

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_current_position(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not train:
                display_name = self._get_display_train_name(number)
                tk.Label(result_frame, text=f"未找到车次 {display_name}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            stops = train['stops']
            if len(stops) < 2:
                tk.Label(result_frame, text="该车次停站不足，无法判断区间", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # 获取正晚点数据（异步）
            loading_label = tk.Label(result_frame, text="正在获取正晚点数据，请稍候...", font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
            loading_label.pack(pady=20)
            btn.config(state='disabled')
            entry.config(state='disabled')

            def fetch_and_calc():
                delay_data = self.app._get_train_delay(number)
                self.after(0, lambda: after_fetch(delay_data))

            def after_fetch(delay_data):
                loading_label.destroy()
                btn.config(state='normal')
                entry.config(state='normal')
                # 构建延迟映射（站名 -> 延迟信息）
                delay_map = {}
                if delay_data:
                    for item in delay_data:
                        station = item.get('stationName')
                        if station:
                            delay_map[station] = item
                # 生成结果
                display_name = self._get_display_train_name(number)
                self._render_current_position(result_frame, train, display_name, delay_map)

            threading.Thread(target=fetch_and_calc, daemon=True).start()

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _render_current_position(self, result_frame, train, display_name, delay_map):
        """根据实际时刻表渲染当前位置 - 适配缩放"""
        for widget in result_frame.winfo_children():
            widget.destroy()

        result_frame.configure(bg='#f0f4f8')
        stops = train['stops']
        now = datetime.datetime.now()
        today = now.date()

        def parse_time(time_str, base_date, day_offset):
            if not time_str:
                return None
            try:
                dt = datetime.datetime.strptime(time_str, '%H:%M')
                return datetime.datetime.combine(base_date, dt.time()) + datetime.timedelta(days=day_offset)
            except:
                return None

        def build_actual_table(base_date):
            table = []
            last_time = None
            for stop in stops:
                # 兼容本地格式(station_name) 与 V2 格式(station)
                station_name = stop.get('station_name') or stop.get('station')
                if not station_name:
                    sid = stop.get('station_id')
                    if sid is not None:
                        station_name = self.app.get_station_name_by_id(sid)
                    else:
                        station_name = ''
                arrive_raw = stop.get('arrive')
                depart_raw = stop.get('depart')
                day_off = stop.get('day_offset', stop.get('day', 0))

                delay_info = delay_map.get(station_name, {})
                code = delay_info.get('delayStatusCode', '')
                delta = delay_info.get('delayTime', 0)
                offset = 0
                if code in ('DELAY', 'DELAY_PREDICTION'):
                    offset = delta
                elif code in ('EARLY', 'EARLY_PREDICTION'):
                    offset = -delta

                arrive_dt = parse_time(arrive_raw, base_date, day_off)
                depart_dt = parse_time(depart_raw, base_date, day_off)

                if arrive_dt:
                    arrive_dt += datetime.timedelta(minutes=offset)
                if depart_dt:
                    depart_dt += datetime.timedelta(minutes=offset)

                current = arrive_dt or depart_dt
                if last_time and current and current < last_time:
                    if arrive_dt:
                        arrive_dt += datetime.timedelta(days=1)
                    if depart_dt:
                        depart_dt += datetime.timedelta(days=1)
                if arrive_dt:
                    last_time = arrive_dt
                elif depart_dt:
                    last_time = depart_dt

                table.append({
                    'station_name': station_name,
                    'arrive': arrive_dt,
                    'depart': depart_dt,
                    'raw_arrive': arrive_raw,
                    'raw_depart': depart_raw,
                    'offset': offset
                })
            return table

        times_today = build_actual_table(today)
        first_depart = times_today[0]['depart'] or times_today[0]['arrive']
        last_arrive = times_today[-1]['arrive'] or times_today[-1]['depart']
        today_running = first_depart and last_arrive and first_depart <= now <= last_arrive

        yesterday = today - datetime.timedelta(days=1)
        times_yesterday = build_actual_table(yesterday)
        first_depart_y = times_yesterday[0]['depart'] or times_yesterday[0]['arrive']
        last_arrive_y = times_yesterday[-1]['arrive'] or times_yesterday[-1]['depart']
        yesterday_running = first_depart_y and last_arrive_y and first_depart_y <= now <= last_arrive_y

        if yesterday_running:
            times = times_yesterday
            date_label = "昨天"
        elif today_running:
            times = times_today
            date_label = "今天"
        else:
            times = times_today
            date_label = "今天（未校准，仅供参考）"

        # ---- 主容器 ----
        main_container = tk.Frame(result_frame, bg='#f0f4f8')
        main_container.pack(fill=tk.BOTH, expand=True)

        # ---- 1. 标题卡片 ----
        header_frame = tk.Frame(main_container, bg='#2c3e50', height=70)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        header_frame.pack_propagate(False)

        tk.Label(header_frame, text=f" {display_name} 当前位置",
                 font=('微软雅黑', 18, 'bold'), bg='#2c3e50', fg='white').pack(side=tk.LEFT, padx=20, pady=15)

        date_color = '#3498db' if '今天' in date_label else '#e67e22'
        tk.Label(header_frame, text=date_label,
                 font=('微软雅黑', 12), bg='#2c3e50', fg=date_color).pack(side=tk.LEFT, padx=15)

        train_type = train.get('type', '未知')
        type_colors = {'高铁': '#e74c3c', '动车': '#3498db', '普速': '#2ecc71', '未知': '#95a5a6'}
        tc = type_colors.get(train_type, '#95a5a6')
        tk.Label(header_frame, text=train_type,
                 font=('微软雅黑', 11), bg='#2c3e50', fg=tc).pack(side=tk.RIGHT, padx=20)

        # ---- 2. 定位信息 ----
        position_info = {
            'status': 'unknown',
            'current_station': None,
            'next_station': None,
            'prev_station': None,
            'arrive_time': None,
            'depart_time': None,
            'wait_minutes': None,
            'arrive_minutes': None,
            'offset': 0,
            'is_passed': False,
            'progress_ratio': 0.0
        }

        for st in times:
            if st['arrive'] and st['depart'] and st['arrive'] <= now <= st['depart']:
                position_info['status'] = 'stopping'
                position_info['current_station'] = st['station_name']
                position_info['arrive_time'] = st['arrive']
                position_info['depart_time'] = st['depart']
                position_info['offset'] = st['offset']
                wait = int((st['depart'] - now).total_seconds() // 60)
                position_info['wait_minutes'] = wait if wait > 0 else 0
                position_info['progress_ratio'] = 1.0
                break

        if position_info['status'] == 'unknown':
            for i in range(len(times)-1):
                cur = times[i]
                nxt = times[i+1]
                depart_cur = cur['depart'] or cur['arrive']
                arrive_next = nxt['arrive'] or nxt['depart']
                if depart_cur and arrive_next and depart_cur <= now < arrive_next:
                    position_info['status'] = 'running'
                    position_info['prev_station'] = cur['station_name']
                    position_info['next_station'] = nxt['station_name']
                    position_info['arrive_time'] = arrive_next
                    position_info['offset'] = nxt['offset']
                    delta = int((arrive_next - now).total_seconds() // 60)
                    position_info['arrive_minutes'] = delta if delta > 0 else 0
                    total_seconds = (arrive_next - depart_cur).total_seconds()
                    elapsed_seconds = (now - depart_cur).total_seconds()
                    if total_seconds > 0:
                        position_info['progress_ratio'] = min(1.0, max(0.0, elapsed_seconds / total_seconds))
                    else:
                        position_info['progress_ratio'] = 0.5
                    break

        if position_info['status'] == 'unknown':
            first = times[0]
            if first['depart'] and now < first['depart']:
                position_info['status'] = 'not_departed'
                position_info['current_station'] = first['station_name']
                position_info['depart_time'] = first['depart']
                position_info['offset'] = first['offset']
                wait = int((first['depart'] - now).total_seconds() // 60)
                position_info['wait_minutes'] = wait if wait > 0 else 0
                position_info['progress_ratio'] = 0.0

        if position_info['status'] == 'unknown':
            last = times[-1]
            if last['arrive'] and now >= last['arrive']:
                position_info['status'] = 'arrived'
                position_info['current_station'] = last['station_name']
                position_info['arrive_time'] = last['arrive']
                position_info['offset'] = last['offset']
                position_info['is_passed'] = True
                position_info['progress_ratio'] = 1.0

        # ---- 3. 状态卡片 ----
        status_card = tk.Frame(main_container, bg='white', relief=tk.RIDGE, bd=1)
        status_card.pack(fill=tk.X, pady=5, padx=10)

        status_text, status_color = self._get_status_display(position_info, now)
        tk.Label(status_card, text=status_text,
                 font=('微软雅黑', 14, 'bold'), bg='white', fg=status_color).pack(pady=10)

        extra = self._get_extra_info(position_info)
        if extra:
            tk.Label(status_card, text=extra,
                     font=('微软雅黑', 11), bg='white', fg='#2c3e50').pack(pady=(0, 10))

        # ---- 4. 线路图（自适应缩放） ----
        line_frame = tk.Frame(main_container, bg='white', relief=tk.RIDGE, bd=1)
        line_frame.pack(fill=tk.X, pady=5, padx=10)

        tk.Label(line_frame, text="运行线路",
                 font=('微软雅黑', 12, 'bold'), bg='white', fg='#2c3e50').pack(pady=(10, 5), padx=15, anchor='w')

        canvas_container = tk.Frame(line_frame, bg='white')
        canvas_container.pack(fill=tk.X, pady=10, padx=15)

        display_stations = times
        sf = getattr(self, 'scale_factor', 1.0)
        draw_height = int(140 * sf)
        parent_width = main_container.winfo_width()
        if parent_width < 100:
            parent_width = 800
        margin = int(30 * sf)
        total = len(display_stations)
        if total > 1:
            spacing = max(int(80 * sf), (parent_width - 2*margin) / (total - 1))
        else:
            spacing = int(100 * sf)
        draw_width = int((total - 1) * spacing + 2*margin)

        scroll_canvas = tk.Canvas(canvas_container, height=draw_height + int(30*sf), bg='white', highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_container, orient=tk.HORIZONTAL, command=scroll_canvas.xview)
        scroll_canvas.configure(xscrollcommand=scrollbar.set)

        inner_canvas = tk.Canvas(scroll_canvas, height=draw_height, width=draw_width, bg='white', highlightthickness=0)
        scroll_canvas.create_window((0, 0), window=inner_canvas, anchor='nw')
        scroll_canvas.configure(scrollregion=(0, 0, draw_width, draw_height))

        scroll_canvas.pack(side=tk.TOP, fill=tk.X, expand=True)
        scrollbar.pack(side=tk.BOTTOM, fill=tk.X)

        # 获取当前站索引
        current_station = None
        if position_info['status'] == 'stopping':
            current_station = position_info['current_station']
        elif position_info['status'] == 'running':
            current_station = position_info['prev_station']
        elif position_info['status'] == 'not_departed':
            current_station = position_info['current_station']
        elif position_info['status'] == 'arrived':
            current_station = position_info['current_station']

        current_idx = -1
        for i, st in enumerate(display_stations):
            if st['station_name'] == current_station:
                current_idx = i
                break

        station_positions = []

        # 画连线
        for i in range(len(display_stations)-1):
            x1 = margin + (i / max(1, total-1)) * (draw_width - 2*margin)
            y1 = draw_height // 2
            x2 = margin + ((i+1) / max(1, total-1)) * (draw_width - 2*margin)
            y2 = draw_height // 2
            is_passed = False
            if current_idx >= 0 and i < current_idx:
                is_passed = True
            is_current_segment = False
            if position_info['status'] == 'running' and i == current_idx:
                is_current_segment = True
            color = '#2980b9' if is_current_segment else ('#2ecc71' if is_passed else '#bdc3c7')
            width = 4 if is_current_segment else (3 if is_passed else 2)
            inner_canvas.create_line(x1, y1, x2, y2, fill=color, width=width)

        # 画站点
        for i, st in enumerate(display_stations):
            x = margin + (i / max(1, total-1)) * (draw_width - 2*margin)
            y = draw_height // 2
            station_positions.append((x, y, st))

            is_current = (i == current_idx)
            is_passed = False
            if current_idx >= 0:
                is_passed = (i < current_idx)

            if is_passed:
                color = '#2ecc71'
                radius = int(7 * sf)
            elif is_current:
                if position_info['status'] == 'stopping':
                    color = '#e74c3c'
                    radius = int(10 * sf)
                elif position_info['status'] == 'running':
                    color = '#f39c12'
                    radius = int(8 * sf)
                else:
                    color = '#e74c3c'
                    radius = int(8 * sf)
            else:
                color = '#bdc3c7'
                radius = int(7 * sf)

            inner_canvas.create_oval(x-radius, y-radius, x+radius, y+radius, fill=color, outline='#2c3e50', width=1)
            if is_current and position_info['status'] == 'stopping':
                inner_canvas.create_oval(x-int(16*sf), y-int(16*sf), x+int(16*sf), y+int(16*sf), outline='#e74c3c', width=2)

            offset = st.get('offset', 0)
            if is_passed:
                text_color = '#e74c3c' if offset > 0 else ('#3498db' if offset < 0 else '#2ecc71')
            elif is_current:
                text_color = '#e74c3c' if offset > 0 else ('#3498db' if offset < 0 else '#2ecc71')
            else:
                text_color = '#95a5a6'

            station_name = st['station_name']
            if len(station_name) > 8:
                station_name = station_name[:8] + '...'

            font_weight = ('微软雅黑', int(10*sf), 'bold') if is_current else ('微软雅黑', int(9*sf))
            if i % 2 == 0:
                label_y = y + int(30*sf)
            else:
                label_y = y - int(30*sf)
                if total > 8:
                    label_y = y - int(30*sf)

            inner_canvas.create_text(x, label_y, text=station_name, font=font_weight, fill=text_color)

            if st['depart'] or st['arrive']:
                time_str = ''
                if st['depart']:
                    time_str = st['depart'].strftime('%H:%M')
                elif st['arrive']:
                    time_str = st['arrive'].strftime('%H:%M')
                if time_str:
                    time_y = y + int(50*sf) if label_y == y + int(30*sf) else y - int(50*sf)
                    inner_canvas.create_text(x, time_y, text=time_str, font=('微软雅黑', int(8*sf)), fill='#95a5a6')

        # 画移动红点
        if position_info['status'] == 'running':
            prev_idx = current_idx
            if prev_idx >= 0 and prev_idx + 1 < len(station_positions):
                x1, y1, _ = station_positions[prev_idx]
                x2, y2, _ = station_positions[prev_idx + 1]
                ratio = position_info['progress_ratio']
                pos_x = x1 + (x2 - x1) * ratio
                pos_y = y1 + (y2 - y1) * ratio
                inner_canvas.create_oval(pos_x-int(10*sf), pos_y-int(10*sf), pos_x+int(10*sf), pos_y+int(10*sf),
                                          fill='#e74c3c', outline='#c0392b', width=2)
                inner_canvas.create_oval(pos_x-int(14*sf), pos_y-int(14*sf), pos_x+int(14*sf), pos_y+int(14*sf),
                                          outline='#e74c3c', width=1)
                inner_canvas.create_oval(pos_x-int(6*sf), pos_y-int(6*sf), pos_x+int(6*sf), pos_y+int(6*sf),
                                          fill='#ff6b6b', outline='')
                scroll_ratio = pos_x / draw_width
                scroll_canvas.xview_moveto(max(0, min(1, scroll_ratio - 0.15)))

        elif position_info['status'] == 'stopping' and current_idx >= 0:
            x, y, _ = station_positions[current_idx]
            inner_canvas.create_oval(x-int(12*sf), y-int(12*sf), x+int(12*sf), y+int(12*sf),
                                      fill='#e74c3c', outline='#c0392b', width=2)
            inner_canvas.create_oval(x-int(8*sf), y-int(8*sf), x+int(8*sf), y+int(8*sf),
                                      fill='#ff6b6b', outline='')
            scroll_ratio = x / draw_width
            scroll_canvas.xview_moveto(max(0, min(1, scroll_ratio - 0.15)))

        elif position_info['status'] == 'not_departed' and current_idx >= 0:
            x, y, _ = station_positions[0]
            inner_canvas.create_oval(x-int(8*sf), y-int(8*sf), x+int(8*sf), y+int(8*sf),
                                      fill='#f39c12', outline='#e67e22', width=2)
            scroll_ratio = x / draw_width
            scroll_canvas.xview_moveto(max(0, min(1, scroll_ratio - 0.15)))

        elif position_info['status'] == 'arrived' and current_idx >= 0:
            x, y, _ = station_positions[-1]
            inner_canvas.create_oval(x-int(8*sf), y-int(8*sf), x+int(8*sf), y+int(8*sf),
                                      fill='#8e44ad', outline='#6c3483', width=2)
            scroll_ratio = x / draw_width
            scroll_canvas.xview_moveto(max(0, min(1, scroll_ratio - 0.15)))

        # ---- 5. 时刻表表格 ----
        table_frame = tk.Frame(main_container, bg='white', relief=tk.RIDGE, bd=1)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=5, padx=10)

        tk.Label(table_frame, text="时刻表",
                 font=('微软雅黑', 12, 'bold'), bg='white', fg='#2c3e50').pack(pady=(10, 5), padx=15, anchor='w')

        table_container = tk.Frame(table_frame, bg='white')
        table_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        columns = ['序号', '站名', '到达', '出发', '正晚点状态']
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11), rowheight=30)
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))

        tree = ttk.Treeview(table_container, columns=columns, show='headings', selectmode='browse')
        col_widths = [int(60*sf), int(150*sf), int(100*sf), int(100*sf), int(130*sf)]
        for col, w in zip(columns, col_widths):
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=w)

        scrollbar_v = ttk.Scrollbar(table_container, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar_v.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_v.pack(side=tk.RIGHT, fill=tk.Y)

        def on_station_double_click(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            col = tree.identify_column(event.x)
            if col == '#2':
                values = tree.item(item, 'values')
                if values and len(values) > 1:
                    station_name = values[1]
                    if station_name:
                        self._open_station_detail_tab(station_name)

        tree.bind("<Double-1>", on_station_double_click)

        current_station_name = None
        if position_info['status'] == 'stopping':
            current_station_name = position_info['current_station']
        elif position_info['status'] == 'running':
            current_station_name = position_info['next_station']
        elif position_info['status'] == 'not_departed':
            current_station_name = position_info['current_station']

        # ---- 插入时刻表行，记录"当前站"那一行的 item id ----
        current_item_id = None
        for i, st in enumerate(times):
            station_name = st['station_name']
            arrive = st['arrive'].strftime('%H:%M') if st['arrive'] else '--:--'
            depart = st['depart'].strftime('%H:%M') if st['depart'] else '--:--'

            delay_status = ''
            if st['offset'] > 0:
                delay_status = f'晚点{st["offset"]}分钟'
            elif st['offset'] < 0:
                delay_status = f'提前{-st["offset"]}分钟'
            else:
                delay_status = '正点'

            is_passed = False
            if st['arrive'] and st['arrive'] < now:
                is_passed = True
            elif st['depart'] and st['depart'] < now:
                is_passed = True

            row_tag = ''
            if station_name == current_station_name:
                row_tag = 'current'
            elif is_passed:
                row_tag = 'passed'

            item_id = tree.insert('', 'end',
                                  values=(str(i+1), station_name, arrive, depart, delay_status),
                                  tags=(row_tag,))
            if row_tag == 'current':
                current_item_id = item_id

        tree.tag_configure('current', background='#fff3cd', font=('微软雅黑', 11, 'bold'))
        tree.tag_configure('passed', background='#e8f5e9')

        # ---- 自动滚动到"当前站"（加粗高亮）那一行，与线段图红点定位一致 ----
        if current_item_id is not None:
            def _scroll_to_current():
                try:
                    children = list(tree.get_children())
                    if not children:
                        return
                    idx = children.index(current_item_id)
                    total = len(children)
                    tree.see(current_item_id)
                    tree.update_idletasks()
                    if total > 1:
                        # 让当前站出现在视图约 1/3 处
                        ratio = max(0.0, min(1.0, (idx - 1) / total))
                        tree.yview_moveto(ratio)
                except Exception:
                    pass

            tree.after(50, _scroll_to_current)
    
    def _get_status_display(self, position_info, now):
        """获取状态显示文本和颜色"""
        status = position_info['status']
        
        if status == 'stopping':
            st = position_info['current_station']
            depart = position_info['depart_time']
            wait = position_info['wait_minutes']
            text = f"🟢 正在停靠「{st}」站"
            if wait > 0:
                text += f" ｜ 预计 {depart.strftime('%H:%M')} 发车（还有 {wait} 分钟）"
            return text, '#27ae60'
        
        elif status == 'running':
            prev = position_info['prev_station']
            nxt = position_info['next_station']
            arrive = position_info['arrive_time']
            mins = position_info['arrive_minutes']
            text = f"正在从「{prev}」开往「{nxt}」"
            if mins > 0:
                text += f" ｜ 预计 {arrive.strftime('%H:%M')} 到达（还有 {mins} 分钟）"
            return text, '#2980b9'
        
        elif status == 'not_departed':
            st = position_info['current_station']
            depart = position_info['depart_time']
            wait = position_info['wait_minutes']
            text = f"⏳ 尚未从始发站「{st}」发车"
            if wait > 0:
                text += f" ｜ 预计 {depart.strftime('%H:%M')} 发车（还有 {wait} 分钟）"
            return text, '#e67e22'
        
        elif status == 'arrived':
            st = position_info['current_station']
            arrive = position_info['arrive_time']
            text = f"🏁 已到达终点站「{st}」 ｜ 到达时间 {arrive.strftime('%H:%M')}"
            return text, '#8e44ad'
        
        else:
            return "? 无法确定列车当前位置", '#e74c3c'
    
    def _get_extra_info(self, position_info):
        """获取额外信息"""
        info_parts = []
        
        if position_info.get('offset', 0) != 0:
            offset = position_info['offset']
            info_parts.append(f"⏱ 正晚点偏移: {'+' if offset > 0 else ''}{offset} 分钟")
        
        if position_info.get('arrive_time') and position_info.get('depart_time'):
            arrive = position_info['arrive_time']
            depart = position_info['depart_time']
            if arrive and depart:
                stay = int((depart - arrive).total_seconds() // 60)
                if stay > 0:
                    info_parts.append(f"⏳ 停站时间: {stay} 分钟")
        
        return '  '.join(info_parts) if info_parts else None

    def _q_station_to_station(self, frame):
        """本地模式：两站间今日列车运行（含状态、正晚点）"""
        # ====== API开关判断 ======
        if self.app.use_api_query:
            self._q_station_to_station_api(frame)
            return
        # ====== 原有本地逻辑 ======
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_start = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_start.pack(side=tk.LEFT, padx=5)
        tk.Label(top_frame, text="终止站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_end = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_end.pack(side=tk.LEFT, padx=5)
        tk.Label(top_frame, text="日期(YYYYMMDD):", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_date = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_date.insert(0, datetime.datetime.now().strftime('%Y%m%d'))
        entry_date.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        delay_var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(top_frame, text="显示正晚点", variable=delay_var, bg='#f0f0f0')
        chk.pack(side=tk.LEFT, padx=20)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            start = entry_start.get().strip()
            end = entry_end.get().strip()
            date = entry_date.get().strip()
            if not start or not end:
                messagebox.showwarning("提示", "请输入起始站和终止站", parent=self)
                return
            if not date or len(date) != 8 or not date.isdigit():
                messagebox.showwarning("提示", "日期格式不正确，请输入 YYYYMMDD 格式", parent=self)
                return

            start_id = self.app.get_station_id_by_name(start)
            end_id = self.app.get_station_id_by_name(end)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if start_id is None or end_id is None:
                tk.Label(result_frame, text="未找到车站", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 获取候选车次 ----
            candidates = []
            for train in self.app.data.get('trains', []):
                stops = train.get('stops', [])
                start_idx = -1
                end_idx = -1
                for i, s in enumerate(stops):
                    if s['station_id'] == start_id:
                        start_idx = i
                    if s['station_id'] == end_id:
                        end_idx = i
                if start_idx >= 0 and end_idx > start_idx:
                    start_stop = stops[start_idx]
                    end_stop = stops[end_idx]
                    if start_stop.get('depart') and end_stop.get('arrive'):
                        candidates.append((train, start_stop, end_stop))

            if not candidates:
                tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 方向的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 合并去重 ----
            dedup_dict = {}
            for train, s_stop, e_stop in candidates:
                display_name = self._get_display_train_name(train['base_number'])
                if display_name not in dedup_dict:
                    dedup_dict[display_name] = (train, s_stop, e_stop)
            dedup_candidates = list(dedup_dict.values())

            # ---- 渲染表格 ----
            def render_table(delay_map):
                for widget in result_frame.winfo_children():
                    widget.destroy()

                now = datetime.datetime.now()
                today = now.date()
                results = []
                for train, s_stop, e_stop in dedup_candidates:
                    first_stop = train['stops'][0]
                    first_depart_raw = first_stop.get('depart') or first_stop.get('arrive')
                    first_depart = None
                    if first_depart_raw:
                        try:
                            first_depart = datetime.datetime.combine(today, datetime.datetime.strptime(first_depart_raw, '%H:%M').time()) + datetime.timedelta(days=first_stop.get('day_offset', 0))
                        except:
                            pass
                    today_departed = first_depart and first_depart <= now
                    base_date = today
                    date_label = "今天"
                    if not today_departed:
                        yesterday = today - datetime.timedelta(days=1)
                        y_first = None
                        if first_depart_raw:
                            try:
                                y_first = datetime.datetime.combine(yesterday, datetime.datetime.strptime(first_depart_raw, '%H:%M').time()) + datetime.timedelta(days=first_stop.get('day_offset', 0))
                            except:
                                pass
                        if y_first:
                            last_stop = train['stops'][-1]
                            last_time_raw = last_stop.get('arrive') or last_stop.get('depart')
                            y_last = None
                            if last_time_raw:
                                try:
                                    y_last = datetime.datetime.combine(yesterday, datetime.datetime.strptime(last_time_raw, '%H:%M').time()) + datetime.timedelta(days=last_stop.get('day_offset', 0))
                                except:
                                    pass
                            if y_last and y_last >= now:
                                base_date = yesterday
                                date_label = "昨天"

                    def get_abs_time(stop, base):
                        t = stop.get('depart') or stop.get('arrive')
                        if not t:
                            return None
                        try:
                            dt = datetime.datetime.combine(base, datetime.datetime.strptime(t, '%H:%M').time()) + datetime.timedelta(days=stop.get('day_offset', 0))
                            return dt
                        except:
                            return None
                    start_abs = get_abs_time(s_stop, base_date)
                    end_abs = get_abs_time(e_stop, base_date)
                    if not start_abs or not end_abs:
                        continue
                    if now < start_abs:
                        status = f"未到达 {start}"
                    elif start_abs <= now < end_abs:
                        status = f"正在 {start}->{end} 运行"
                    else:
                        status = f"已到达 {end}"
                    display_name = self._get_display_train_name(train['base_number'])
                    results.append({
                        'train': train['base_number'],
                        'display_name': display_name,
                        'start_time': start_abs,
                        'end_time': end_abs,
                        'status': status,
                        'date_label': date_label,
                        'train_obj': train,
                        'start_stop': s_stop,
                        'end_stop': e_stop
                    })
                results.sort(key=lambda x: x['start_time'])

                columns = ['序号', '车次', f'{start}发车', f'{end}到达', '状态']
                if delay_map:
                    columns.append('正晚点状态')

                just_passed = None
                coming_soon = None
                min_past_diff = None
                min_future_diff = None
                for r in results:
                    if r['status'].startswith("已到达"):
                        diff = (now - r['end_time']).total_seconds()
                        if diff >= 0:
                            if min_past_diff is None or diff < min_past_diff:
                                min_past_diff = diff
                                just_passed = r
                    elif r['status'].startswith("未到达"):
                        diff = (r['start_time'] - now).total_seconds()
                        if diff >= 0:
                            if min_future_diff is None or diff < min_future_diff:
                                min_future_diff = diff
                                coming_soon = r

                header = f"经过 '{start}' -> '{end}' 区间的车次 (共 {len(results)} 趟)\n"
                if just_passed:
                    t = just_passed['end_time'].strftime('%H:%M')
                    if just_passed['date_label'] == "昨天":
                        t += "(昨)"
                    header += f"刚过掉: {just_passed['display_name']}（{t} 到达 {end}）"
                else:
                    header += "刚过掉: 无"
                if coming_soon:
                    t = coming_soon['start_time'].strftime('%H:%M')
                    if coming_soon['date_label'] == "昨天":
                        t += "(昨)"
                    header += f"\n马上进入: {coming_soon['display_name']}（{t} 从 {start} 发车）"
                else:
                    header += "\n马上进入: 无"
                tk.Label(result_frame, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT).pack(fill=tk.X, padx=5, pady=2)

                style = ttk.Style()
                style.configure("Treeview", font=('微软雅黑', 11))
                style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
                tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, anchor='center', width=120)
                scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                idx = 1
                for r in results:
                    s_str = r['start_time'].strftime('%H:%M')
                    e_str = r['end_time'].strftime('%H:%M')
                    if r['date_label'] == "昨天":
                        s_str += "(昨)"
                        e_str += "(昨)"
                    row = (str(idx), r['display_name'], s_str, e_str, r['status'])
                    if delay_map:
                        train_num = r['train']
                        station_delay = delay_map.get(train_num, {})
                        status_delay = ''
                        if station_delay:
                            for st in [start, end]:
                                if st in station_delay:
                                    item = station_delay[st]
                                    code = item.get('delayStatusCode')
                                    time_val = item.get('delayTime', 0)
                                    if code in ('ON_TIME', 'ON_TIME_PREDICTION'):
                                        status_delay = '正点'
                                    elif code in ('DELAY', 'DELAY_PREDICTION'):
                                        status_delay = f'晚点{time_val}分钟'
                                    elif code in ('EARLY', 'EARLY_PREDICTION'):
                                        status_delay = f'提前{time_val}分钟'
                                    else:
                                        status_delay = '未维护'
                                    break
                        row = row + (status_delay,)
                    tree.insert('', 'end', values=row)
                    idx += 1

            if delay_var.get():
                loading_label = tk.Label(result_frame, text="正在获取所有车次正晚点数据，请稍候...", font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
                loading_label.pack(pady=20)
                btn.config(state='disabled')
                entry_start.config(state='disabled')
                entry_end.config(state='disabled')
                entry_date.config(state='disabled')

                def fetch_all():
                    delay_map = {}
                    dedup_dict = {}
                    for train, _, _ in candidates:
                        display_name = self._get_display_train_name(train['base_number'])
                        if display_name not in dedup_dict:
                            dedup_dict[display_name] = train
                    for train in dedup_dict.values():
                        train_num = train['base_number']
                        delay_data = self.app._get_train_delay(train_num)
                        if delay_data:
                            station_delay = {}
                            for item in delay_data:
                                st = item.get('stationName')
                                if st:
                                    station_delay[st] = item
                            delay_map[train_num] = station_delay
                    self.after(0, lambda: after_fetch(delay_map))

                def after_fetch(delay_map):
                    loading_label.destroy()
                    btn.config(state='normal')
                    entry_start.config(state='normal')
                    entry_end.config(state='normal')
                    entry_date.config(state='normal')
                    render_table(delay_map)

                threading.Thread(target=fetch_all, daemon=True).start()
            else:
                render_table({})

        btn.config(command=do_query)
        entry_start.bind('<Return>', lambda e: do_query())
        entry_end.bind('<Return>', lambda e: do_query())
        entry_date.bind('<Return>', lambda e: do_query())

    def _q_station_to_station_api(self, frame):
        """API 模式：两站间今日列车运行（V1站到站查询 → V2合并，双击打开详情）"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_start = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_start.pack(side=tk.LEFT, padx=5)
        tk.Label(top_frame, text="终止站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_end = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_end.pack(side=tk.LEFT, padx=5)
        tk.Label(top_frame, text="日期(YYYYMMDD):", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_date = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
        entry_date.insert(0, datetime.datetime.now().strftime('%Y%m%d'))
        entry_date.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        delay_var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(top_frame, text="显示正晚点", variable=delay_var, bg='#f0f0f0')
        chk.pack(side=tk.LEFT, padx=20)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            start = entry_start.get().strip()
            end = entry_end.get().strip()
            date = entry_date.get().strip()
            if not start or not end:
                messagebox.showwarning("提示", "请输入起始站和终止站", parent=self)
                return
            if not date or len(date) != 8 or not date.isdigit():
                messagebox.showwarning("提示", "日期格式不正确，请输入 YYYYMMDD 格式", parent=self)
                return

            from_telecode = self.app.get_telecode_by_station_name(start)
            to_telecode = self.app.get_telecode_by_station_name(end)
            if not from_telecode:
                tk.Label(result_frame, text=f"未找到车站 '{start}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            if not to_telecode:
                tk.Label(result_frame, text=f"未找到车站 '{end}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            trains_data = self.app._call_v1_sts_query(from_telecode, to_telecode, date)
            if trains_data is None:
                tk.Label(result_frame, text="获取数据失败，请检查网络连接", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            if not trains_data:
                tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            all_numbers = [t.get('number') for t in trains_data if t.get('number')]

            loading_label = tk.Label(result_frame, text=f"正在处理 {len(all_numbers)} 个车次，请稍候...",
                                     font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
            loading_label.pack(pady=20)
            btn.config(state='disabled')
            entry_start.config(state='disabled')
            entry_end.config(state='disabled')
            entry_date.config(state='disabled')

            def process():
                import concurrent.futures
                merged_results = {}

                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    future_to_num = {executor.submit(self.app.query_train_from_v2, num): num for num in all_numbers}
                    for future in concurrent.futures.as_completed(future_to_num):
                        num = future_to_num[future]
                        try:
                            v2_data, error_type, _ = future.result(timeout=120)
                            if error_type == 'success' and v2_data:
                                number_full = v2_data.get('numberFull', [num])
                                display_name = '/'.join(number_full) if len(number_full) > 1 else num
                                if display_name not in merged_results:
                                    merged_results[display_name] = {
                                        'numbers': number_full,
                                        'timetable': v2_data.get('timetable', []),
                                        'v2_data': v2_data
                                    }
                            else:
                                if num not in merged_results:
                                    merged_results[num] = {
                                        'numbers': [num],
                                        'timetable': [],
                                        'v2_data': {}
                                    }
                        except concurrent.futures.TimeoutError:
                            self.app.write_error_log(f"V2查询超时 {num}")
                            if num not in merged_results:
                                merged_results[num] = {
                                    'numbers': [num],
                                    'timetable': [],
                                    'v2_data': {}
                                }
                        except Exception as e:
                            self.app.write_error_log(f"并发获取V2失败 {num}: {e}")
                            if num not in merged_results:
                                merged_results[num] = {
                                    'numbers': [num],
                                    'timetable': [],
                                    'v2_data': {}
                                }

                # ---- 构建 v1_dict ----
                v1_dict = {}
                for train in trains_data:
                    number_full = train.get('numberFull', [])
                    if number_full:
                        for num in number_full:
                            v1_dict[num] = train
                    else:
                        number = train.get('number')
                        if number:
                            v1_dict[number] = train

                merged_list = []
                for display_name, info in merged_results.items():
                    from_depart = ''
                    to_arrive = ''
                    pass_time = ''
                    train_type = ''
                    
                    # 遍历所有 numbers 找到匹配的 V1 数据
                    for num in info.get('numbers', [display_name]):
                        v1_train = v1_dict.get(num)
                        if v1_train:
                            from_depart = v1_train.get('fromDepart', '')
                            to_arrive = v1_train.get('toArrive', '')
                            pass_time = v1_train.get('passTime', '')
                            train_type = v1_train.get('type', '')
                            
                            # 如果 from_depart 或 to_arrive 为空，从 timetable 中提取
                            if not from_depart or not to_arrive:
                                timetable = v1_train.get('timetable', [])
                                from_pos = v1_train.get('fromPos', 0)
                                to_pos = v1_train.get('toPos', 0)
                                if timetable and from_pos < len(timetable) and to_pos < len(timetable):
                                    if not from_depart:
                                        from_stop = timetable[from_pos]
                                        from_depart = from_stop.get('depart', '') or from_stop.get('arrive', '')
                                    if not to_arrive:
                                        to_stop = timetable[to_pos]
                                        to_arrive = to_stop.get('arrive', '') or to_stop.get('depart', '')
                            break

                    now = datetime.datetime.now()
                    today = now.date()
                    s_abs = None
                    e_abs = None
                    if from_depart:
                        try:
                            dt_s = datetime.datetime.strptime(from_depart, '%H:%M')
                            s_abs = datetime.datetime.combine(today, dt_s.time())
                        except:
                            pass
                    if to_arrive:
                        try:
                            dt_e = datetime.datetime.strptime(to_arrive, '%H:%M')
                            e_abs = datetime.datetime.combine(today, dt_e.time())
                        except:
                            pass
                    if s_abs is None or e_abs is None:
                        status = '时间缺失'
                    elif now < s_abs:
                        status = f'未到达 {start}'
                    elif s_abs <= now < e_abs:
                        status = f'正在 {start}->{end} 运行'
                    else:
                        status = f'已到达 {end}'

                    merged_list.append({
                        'display_name': display_name,
                        'numbers': info.get('numbers', [display_name]),
                        'from_depart': from_depart,
                        'to_arrive': to_arrive,
                        'pass_time': pass_time,
                        'type': train_type,
                        'status': status,
                        's_abs': s_abs,
                        'e_abs': e_abs
                    })

                delay_map = {}
                if delay_var.get() and merged_list:
                    for item in merged_list:
                        first_num = item['numbers'][0] if item.get('numbers') else item['display_name']
                        delay_data = self.app._get_train_delay(first_num, timeout=60)
                        if delay_data:
                            for d in delay_data:
                                if d.get('stationName') == start:
                                    delay_map[item['display_name']] = d
                                    break

                self.after(0, lambda: after_render(merged_list, delay_map))

            def after_render(merged_list, delay_map):
                loading_label.destroy()
                btn.config(state='normal')
                entry_start.config(state='normal')
                entry_end.config(state='normal')
                entry_date.config(state='normal')

                for widget in result_frame.winfo_children():
                    widget.destroy()

                if not merged_list:
                    tk.Label(result_frame, text="没有获取到任何车次数据", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                merged_list.sort(key=lambda x: x['s_abs'] or datetime.datetime.max)

                now = datetime.datetime.now()
                just_passed = None
                coming_soon = None
                min_past_diff = None
                min_future_diff = None
                for item in merged_list:
                    if item['status'].startswith("已到达"):
                        if item['e_abs']:
                            diff = (now - item['e_abs']).total_seconds()
                            if diff >= 0:
                                if min_past_diff is None or diff < min_past_diff:
                                    min_past_diff = diff
                                    just_passed = item
                    elif item['status'].startswith("未到达"):
                        if item['s_abs']:
                            diff = (item['s_abs'] - now).total_seconds()
                            if diff >= 0:
                                if min_future_diff is None or diff < min_future_diff:
                                    min_future_diff = diff
                                    coming_soon = item

                header = f"经过 '{start}' -> '{end}' 区间的车次 (共 {len(merged_list)} 趟)\n"
                if just_passed:
                    t = just_passed['to_arrive']
                    header += f"刚过掉: {just_passed['display_name']}（{t} 到达 {end}）"
                else:
                    header += "刚过掉: 无"
                if coming_soon:
                    t = coming_soon['from_depart']
                    header += f"\n马上进入: {coming_soon['display_name']}（{t} 从 {start} 发车）"
                else:
                    header += "\n马上进入: 无"

                tk.Label(result_frame, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT).pack(fill=tk.X, padx=5, pady=2)

                columns = ['序号', '车次', f'{start}发车', f'{end}到达', '历时', '状态']
                if delay_var.get():
                    columns.append('正晚点状态')

                style = ttk.Style()
                style.configure("Treeview", font=('微软雅黑', 11))
                style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
                tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, anchor='center', width=120)
                scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                idx = 1
                for item in merged_list:
                    row = (str(idx), item['display_name'], item['from_depart'], item['to_arrive'], item['pass_time'], item['status'])
                    if delay_var.get():
                        status = '未获取'
                        if item['display_name'] in delay_map:
                            d = delay_map[item['display_name']]
                            code = d.get('delayStatusCode')
                            time_val = d.get('delayTime', 0)
                            if code in ('ON_TIME', 'ON_TIME_PREDICTION'):
                                status = '正点'
                            elif code in ('DELAY', 'DELAY_PREDICTION'):
                                status = f'晚点{time_val}分钟'
                            elif code in ('EARLY', 'EARLY_PREDICTION'):
                                status = f'提前{time_val}分钟'
                            else:
                                status = '未维护'
                        row = row + (status,)
                    tree.insert('', 'end', values=row)
                    idx += 1

            threading.Thread(target=process, daemon=True).start()

        btn.config(command=do_query)
        entry_start.bind('<Return>', lambda e: do_query())
        entry_end.bind('<Return>', lambda e: do_query())
        entry_date.bind('<Return>', lambda e: do_query())

    def _q_bidirectional(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        # 主菜单界面（三个子功能按钮）
        menu_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        menu_frame.pack(pady=20)
        tk.Label(menu_frame, text="车站↔车次查询子功能:", font=('微软雅黑', 11), bg='#f0f0f0').pack(pady=5)

        # ----- 子功能1: 车次 → 始发/终点 -----
        def show_sub1():
            for widget in frame.display_frame.winfo_children():
                widget.destroy()
            top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
            top_frame.pack(fill=tk.X, pady=5)
            tk.Label(top_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
            entry.pack(side=tk.LEFT, padx=5)
            btn = tk.Button(top_frame, text="查询", width=12)
            btn.pack(side=tk.LEFT, padx=5)
            tk.Button(top_frame, text="返回", command=lambda: self._q_bidirectional(frame), width=12).pack(side=tk.LEFT, padx=5)

            result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
            result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

            def do_query():
                number = entry.get().strip()
                if not number:
                    messagebox.showwarning("提示", "请输入车次号", parent=self)
                    return
                train = self.app.get_train(number)
                for widget in result_frame.winfo_children():
                    widget.destroy()
                if not train:
                    tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                stops = train.get('stops', [])
                if not stops:
                    start = None
                    end = None
                else:
                    start = stops[0].get('station_name')
                    end = stops[-1].get('station_name')
                    if not start:
                        sid = stops[0].get('station_id')
                        if sid is not None:
                            start = self.app.get_station_name_by_id(sid)
                    if not end:
                        sid = stops[-1].get('station_id')
                        if sid is not None:
                            end = self.app.get_station_name_by_id(sid)
                tk.Label(result_frame, text=f"{number} 始发: {start} 终点: {end}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)

            btn.config(command=do_query)
            entry.bind('<Return>', lambda e: do_query())

        # ----- 子功能2: 起始站 → 所有始发车次（使用 V1 接口） -----
        def show_sub2():
            for widget in frame.display_frame.winfo_children():
                widget.destroy()
            top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
            top_frame.pack(fill=tk.X, pady=5)
            tk.Label(top_frame, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
            entry.pack(side=tk.LEFT, padx=5)
            btn = tk.Button(top_frame, text="查询", width=12)
            btn.pack(side=tk.LEFT, padx=5)
            tk.Button(top_frame, text="返回", command=lambda: self._q_bidirectional(frame), width=12).pack(side=tk.LEFT, padx=5)

            result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
            result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

            def do_query():
                station = entry.get().strip()
                if not station:
                    messagebox.showwarning("提示", "请输入车站名", parent=self)
                    return

                telecode = self.app.get_telecode_by_station_name(station)
                if not telecode:
                    tk.Label(result_frame, text=f"未找到车站 '{station}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                station_data = self.app._call_v1_station_query(telecode)
                if not station_data:
                    tk.Label(result_frame, text="获取车站数据失败，请检查网络连接", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                trains = station_data.get('trains', [])
                start_trains = []
                for train in trains:
                    if train.get('indexStopThere') == 0:
                        start_trains.append({
                            "number": train.get('number'),
                            "numberFull": train.get('numberFull', []),
                            "toStation": train.get('toStation', {}).get('station'),
                            "depart": train.get('depart')
                        })

                if not start_trains:
                    tk.Label(result_frame, text=f"没有从 '{station}' 始发的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                for widget in result_frame.winfo_children():
                    widget.destroy()
                columns = ['车次', '终点', '出发时间']
                style = ttk.Style()
                style.configure("Treeview", font=('微软雅黑', 11))
                style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
                tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, anchor='center', width=150)
                scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                for train in sorted(start_trains, key=lambda x: x.get('number', '')):
                    display_name = train.get('numberFull', [train.get('number', '')])[0] if train.get('numberFull') else train.get('number', '')
                    to_station = train.get('toStation') or '未知'
                    depart_time = train.get('depart') or '--:--'
                    tree.insert('', 'end', values=(display_name, to_station, depart_time))

            btn.config(command=do_query)
            entry.bind('<Return>', lambda e: do_query())

        # ----- 子功能3: 起点+终点 → 车次（使用 V1 站到站接口） -----
        def show_sub3():
            for widget in frame.display_frame.winfo_children():
                widget.destroy()
            top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
            top_frame.pack(fill=tk.X, pady=5)
            tk.Label(top_frame, text="起点:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry_start = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
            entry_start.pack(side=tk.LEFT, padx=5)
            tk.Label(top_frame, text="终点:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry_end = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
            entry_end.pack(side=tk.LEFT, padx=5)
            tk.Label(top_frame, text="日期(YYYYMMDD):", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry_date = tk.Entry(top_frame, font=('微软雅黑', 10), width=12)
            entry_date.insert(0, datetime.datetime.now().strftime('%Y%m%d'))
            entry_date.pack(side=tk.LEFT, padx=5)
            btn = tk.Button(top_frame, text="查询", width=12)
            btn.pack(side=tk.LEFT, padx=5)
            tk.Button(top_frame, text="返回", command=lambda: self._q_bidirectional(frame), width=12).pack(side=tk.LEFT, padx=5)

            delay_var = tk.BooleanVar(value=False)
            chk = tk.Checkbutton(top_frame, text="显示正晚点", variable=delay_var, bg='#f0f0f0')
            chk.pack(side=tk.LEFT, padx=20)

            result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
            result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

            def do_query():
                start = entry_start.get().strip()
                end = entry_end.get().strip()
                date = entry_date.get().strip()
                if not start or not end:
                    messagebox.showwarning("提示", "请输入起点和终点", parent=self)
                    return
                if not date or len(date) != 8 or not date.isdigit():
                    messagebox.showwarning("提示", "日期格式不正确，请输入 YYYYMMDD 格式", parent=self)
                    return

                from_telecode = self.app.get_telecode_by_station_name(start)
                to_telecode = self.app.get_telecode_by_station_name(end)
                if not from_telecode:
                    tk.Label(result_frame, text=f"未找到车站 '{start}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                if not to_telecode:
                    tk.Label(result_frame, text=f"未找到车站 '{end}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                trains = self.app._call_v1_sts_query(from_telecode, to_telecode, date)
                if trains is None:
                    tk.Label(result_frame, text="获取数据失败，请检查网络连接", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                if not trains:
                    tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                delay_map = {}
                if delay_var.get():
                    for train in trains:
                        number = train.get('number')
                        if number:
                            delay_data = self.app._get_train_delay(number, timeout=60)
                            if delay_data and len(delay_data) > 0:
                                item = delay_data[0]
                                code = item.get('delayStatusCode')
                                time_val = item.get('delayTime', 0)
                                if code in ('ON_TIME', 'ON_TIME_PREDICTION'):
                                    status = '正点'
                                elif code in ('DELAY', 'DELAY_PREDICTION'):
                                    status = f'晚点{time_val}分钟'
                                elif code in ('EARLY', 'EARLY_PREDICTION'):
                                    status = f'提前{time_val}分钟'
                                else:
                                    status = '未维护'
                                delay_map[number] = status

                for widget in result_frame.winfo_children():
                    widget.destroy()

                columns = ['车次', '起点出发', '终点到达', '历时', '类型']
                if delay_map:
                    columns.append('正晚点状态')
                style = ttk.Style()
                style.configure("Treeview", font=('微软雅黑', 11))
                style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
                tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, anchor='center', width=120)
                scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                for train in trains:
                    number = train.get('number', '')
                    from_depart = train.get('fromDepart', '')
                    to_arrive = train.get('toArrive', '')
                    pass_time = train.get('passTime', '')
                    train_type = train.get('type', '')
                    row = (number, from_depart, to_arrive, pass_time, train_type)
                    if delay_map:
                        status = delay_map.get(number, '未获取')
                        row = row + (status,)
                    tree.insert('', 'end', values=row)

            btn.config(command=do_query)
            entry_start.bind('<Return>', lambda e: do_query())
            entry_end.bind('<Return>', lambda e: do_query())
            entry_date.bind('<Return>', lambda e: do_query())

        # 主菜单按钮
        tk.Button(menu_frame, text="1. 车次 → 始发/终点", command=show_sub1, width=26).pack(pady=3)
        tk.Button(menu_frame, text="2. 起始站 → 所有始发车次", command=show_sub2, width=26).pack(pady=3)
        tk.Button(menu_frame, text="3. 起点+终点 → 车次", command=show_sub3, width=26).pack(pady=3)

    def _q_emu_car(self, frame):
        """查询动车组配属信息"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(top_frame, text="车组号 (如 CR200J1-C-6053):", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=25)
        entry.pack(side=tk.LEFT, padx=5)
        
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            car_id = entry.get().strip()
            if not car_id:
                messagebox.showwarning("提示", "请输入车组号", parent=self)
                return
            
            # 复用已有的打开车组详情标签页逻辑（内部自带查重和网络请求）
            self._open_car_detail_tab(car_id)
            
            # 给个界面反馈
            tk.Label(result_frame, text=f"正在请求查询：{car_id}\n请查看新弹出的标签页。", 
                     font=('微软雅黑', 12), bg='#f0f0f0', fg='#2980b9').pack(pady=20)

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_emu_running(self, frame):
        """查询动车组运行信息"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(top_frame, text="车次/车组号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=25)
        entry.pack(side=tk.LEFT, padx=5)
        
        btn = tk.Button(top_frame, text="查询动车组运行", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        def do_query():
            keyword = entry.get().strip()
            if not keyword:
                messagebox.showwarning("提示", "请输入车次号或车组号", parent=self)
                return
            
            # 直接在右侧内容区打开标签页（复用之前的逻辑）
            self._open_emu_running_tab(keyword)
            
            # 给个界面反馈
            tk.Label(result_frame, text=f"正在请求查询：{keyword}\n请查看新弹出的标签页。", 
                     font=('微软雅黑', 12), bg='#f0f0f0', fg='#2980b9').pack(pady=20)

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    # ====== 提权框架 ======
    def build_privilege_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)

        sub_frame = tk.Frame(frame, bg='#f0f0f0')
        sub_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        tk.Label(sub_frame, text="选择提权身份",
                 font=('微软雅黑', 11, 'bold'), bg='#f0f0f0').pack(anchor='w', pady=(0, 6))

        for text, cmd, ident in [
            ("Windows administrator", self.elevate_windows, None),
            ("TADS administrator", self.elevate_tads_admin, "TADS Administrator"),
            ("TADS Developer", self.elevate_developer, "TADS Developer"),
            ("TADS Root", self.elevate_root, "TADS Root"),
        ]:
            btn = tk.Button(
                sub_frame, text=text,
                command=lambda c=cmd, i=ident: self._dispatch_privilege(c, i, frame),
                font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                width=26, anchor='w', padx=5)
            btn.pack(anchor='w', pady=2)

        display_frame = tk.Frame(frame, bg='#f0f0f0')
        display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.display_frame = display_frame

        self._render_privilege_initial(frame)
        return frame

    def _dispatch_privilege(self, cmd, ident, frame):
        if ident is None:
            cmd()
            return
        self._render_privilege_login(frame, ident)

    def _render_privilege_initial(self, frame):
        df = frame.display_frame
        for w in df.winfo_children():
            w.destroy()
        lbl = tk.Label(df, text="请从左侧选择提权身份",
                       font=('微软雅黑', 12), bg='#f0f0f0', fg='#7f8c8d')
        lbl.place(relx=0.5, rely=0.5, anchor='center')

    def _render_privilege_login(self, frame, ident):
        df = frame.display_frame
        for w in df.winfo_children():
            w.destroy()

        is_developer = (ident == "TADS Developer")

        def draw():
            try:
                if not df.winfo_exists():
                    return
                w_area = df.winfo_width()
                h_area = df.winfo_height()
            except Exception:
                return
            if w_area < 100 or h_area < 100:
                self.after(80, draw)
                return

            # ====== 18:7 宽银幕比例计算 ======
            df_h = int(h_area * 0.50)
            df_w = int(df_h * 18 / 7)

            if df_w > w_area - 60:
                df_w = w_area - 60
                df_h = int(df_w * 7 / 18)
            
            if df_w < 760:
                df_w = 760
                df_h = int(760 * 7 / 18)

            radius = 12
            canvas = tk.Canvas(df, width=df_w, height=df_h, bg='#f0f0f0', highlightthickness=0)
            canvas.place(relx=0.5, rely=0.5, anchor='center')

            r = radius
            half = df_w // 2

            # ====== 1. 绘制底层白底圆角 ======
            canvas.create_oval(0, 0, 2 * r, 2 * r, fill='white', outline='')
            canvas.create_oval(df_w - 2 * r, 0, df_w, 2 * r, fill='white', outline='')
            canvas.create_oval(0, df_h - 2 * r, 2 * r, df_h, fill='white', outline='')
            canvas.create_oval(df_w - 2 * r, df_h - 2 * r, df_w, df_h, fill='white', outline='')
            canvas.create_rectangle(r, 0, df_w - r, df_h, fill='white', outline='')
            canvas.create_rectangle(0, r, df_w, df_h - r, fill='white', outline='')

            # ====== 2. 绘制左侧蓝底 ======
            canvas.create_oval(0, 0, 2 * r, 2 * r, fill='#1a2b47', outline='')
            canvas.create_oval(0, df_h - 2 * r, 2 * r, df_h, fill='#1a2b47', outline='')
            canvas.create_rectangle(0, r, half, df_h - r, fill='#1a2b47', outline='')
            canvas.create_rectangle(r, 0, half, r, fill='#1a2b47', outline='')
            canvas.create_rectangle(r, df_h - r, half, df_h, fill='#1a2b47', outline='')

            # ====== 3. 左侧文字 ======
            canvas.create_text(half // 2, df_h * 0.32, text="欢    迎    使    用", fill='white', font=('微软雅黑', 22, 'bold'))
            canvas.create_text(half // 2, df_h * 0.50, text="T A D S", fill='#3498db', font=('微软雅黑', 42, 'bold'))
            canvas.create_text(half // 2, df_h * 0.68, text="列车数据与查询服务系统", fill='white', font=('微软雅黑', 14))

            # ====== 4. 右侧区域坐标 ======
            right_x = half + int(half * 0.15)
            inner_w = int(half * 0.7)

            canvas.create_text(half + half // 2, df_h * 0.15, text="提权", fill='#2c3e50', font=('微软雅黑', 18, 'bold'))

            # ====== 5. 绘制自绘圆角输入框背景 ======
            def draw_rounded_rect(x1, y1, x2, y2, r, fill, outline):
                points = [
                    x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2, 
                    x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1
                ]
                return canvas.create_polygon(points, smooth=True, fill=fill, outline=outline, width=1)

            # 用户名框
            user_y = df_h * 0.30
            draw_rounded_rect(right_x, user_y, right_x + inner_w, user_y + 34, 6, '#dcdcdc', '#dcdcdc')
            draw_rounded_rect(right_x + 1, user_y + 1, right_x + inner_w - 1, user_y + 33, 5, 'white', 'white')
            canvas.create_text(right_x, user_y - 10, anchor='w', text="用户名", fill='#7f8c8d', font=('微软雅黑', 9))

            # 密码框
            pwd_y = df_h * 0.52
            draw_rounded_rect(right_x, pwd_y, right_x + inner_w, pwd_y + 34, 6, '#dcdcdc', '#dcdcdc')
            draw_rounded_rect(right_x + 1, pwd_y + 1, right_x + inner_w - 1, pwd_y + 33, 5, 'white', 'white')
            canvas.create_text(right_x, pwd_y - 10, anchor='w', text="密码", fill='#7f8c8d', font=('微软雅黑', 9))

            # ====== 6. 原生 Entry 悬浮在圆角框内 ======
            user_entry = tk.Entry(df, font=('微软雅黑', 10), relief=tk.FLAT, bd=0, highlightthickness=0, bg='white', fg='#2c3e50', disabledbackground='white', disabledforeground='#2c3e50')
            if is_developer:
                user_entry.insert(0, "")
                user_entry.unbind('<Key>')
            else:
                user_entry.insert(0, ident)
                user_entry.bind('<Key>', lambda e: 'break')
            
            canvas.create_window(right_x + 8, user_y + 8, anchor='nw', window=user_entry, width=inner_w - 16, height=18)

            pwd_entry = tk.Entry(df, font=('微软雅黑', 10), relief=tk.FLAT, bd=0, highlightthickness=0, show='*', bg='white', fg='#2c3e50')
            canvas.create_window(right_x + 8, pwd_y + 8, anchor='nw', window=pwd_entry, width=inner_w - 48, height=18)

            def toggle_pwd():
                pwd_entry.config(show='' if pwd_entry.cget('show') == '*' else '*')
            
            eye_btn = tk.Button(df, text="👁", command=toggle_pwd, bg='white', fg='#333', relief=tk.FLAT, font=('微软雅黑', 10), bd=0, highlightthickness=0)
            canvas.create_window(right_x + inner_w - 32, pwd_y + 2, anchor='nw', window=eye_btn, width=28, height=30)

            # ====== 7. 自绘圆角按钮 ======
            btn_y = df_h * 0.78
            btn_h = 36
            btn_r = 8
            
            def create_rounded_rect_btn(x1, y1, x2, y2, r, fill):
                points = [
                    x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2, 
                    x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1
                ]
                return canvas.create_polygon(points, smooth=True, fill=fill, outline=fill)
            
            btn_bg = create_rounded_rect_btn(right_x, btn_y, right_x + inner_w, btn_y + btn_h, btn_r, '#2980b9')
            btn_text = canvas.create_text(right_x + inner_w // 2, btn_y + btn_h // 2, text="提权", fill="black", font=('微软雅黑', 12, 'bold'))

            def on_btn_click(event):
                on_submit()
            def on_btn_enter(event):
                canvas.itemconfig(btn_bg, fill='#3498db')
            def on_btn_leave(event):
                canvas.itemconfig(btn_bg, fill='#2980b9')

            canvas.tag_bind(btn_text, "<Button-1>", on_btn_click)
            canvas.tag_bind(btn_bg, "<Button-1>", on_btn_click)
            canvas.tag_bind(btn_bg, "<Enter>", on_btn_enter)
            canvas.tag_bind(btn_bg, "<Leave>", on_btn_leave)

            # ====== 8. 提示信息和状态 ======
            tip_text = "请将物理密钥放在读卡器上" if not is_developer else "请输入开发者用户名及密码"
            tip_label = tk.Label(df, text=tip_text, font=('微软雅黑', 8), bg='white', fg='#e67e22' if not is_developer else '#2980b9', justify='left')
            canvas.create_window(right_x, df_h * 0.86, anchor='nw', window=tip_label, width=inner_w, height=20)

            status_label = tk.Label(df, text="", font=('微软雅黑', 8), bg='white', fg='#c0392b', justify='left')
            canvas.create_window(right_x, df_h * 0.91, anchor='nw', window=status_label, width=inner_w, height=20)

            def set_status(text, color='#c0392b'):
                try:
                    status_label.config(text=text, fg=color)
                except Exception:
                    pass
                try:
                    tip_label.config(text="") 
                except Exception:
                    pass

            def on_submit():
                pwd = pwd_entry.get()
                if not pwd:
                    set_status("验证失败  无权限  请重试")
                    return
                
                canvas.itemconfig(btn_bg, fill='#95a5a6')
                
                if is_developer:
                    username = user_entry.get().strip()
                    if not username:
                        canvas.itemconfig(btn_bg, fill='#2980b9')
                        set_status("验证失败  无权限  请重试")
                        return
                    set_status("正在验证...", '#2980b9')
                    def do_verify():
                        try:
                            res = self.app.verify_developer(pwd, username) if hasattr(self, 'app') else self.client.verify_developer(pwd, username)
                            if isinstance(res, tuple):
                                success, msg = res
                            else:
                                success = res
                            self.after(0, lambda: after_verify(success))
                        except Exception:
                            self.after(0, lambda: after_verify(False))
                    threading.Thread(target=do_verify, daemon=True).start()
                else:
                    if not self._ensure_pn532_connected():
                        canvas.itemconfig(btn_bg, fill='#2980b9')
                        set_status("验证失败  无权限  请重试")
                        return
                    
                    set_status("正在验证，请放好卡片...", '#2980b9')
                    def do_verify():
                        try:
                            if ident == "TADS Administrator":
                                res = self.app.verify_admin(pwd) if hasattr(self, 'app') else self.client.verify_admin(pwd)
                            else:
                                res = self.app.verify_root(pwd) if hasattr(self, 'app') else self.client.verify_root(pwd)
                            
                            if isinstance(res, tuple):
                                success = res[0]
                            else:
                                success = res
                                
                            self.after(0, lambda: after_verify(success))
                        except Exception:
                            self.after(0, lambda: after_verify(False))
                    threading.Thread(target=do_verify, daemon=True).start()

            def after_verify(success):
                if not df.winfo_exists(): return
                if success:
                    set_status("提权成功", '#27ae60')
                    canvas.itemconfig(btn_bg, fill='#27ae60')
                    try: self._play_ding()
                    except Exception: pass
                    self.refresh_status()
                    self.display_welcome()
                    if hasattr(self, 'update_edit_permission'):
                        self.update_edit_permission()
                    if hasattr(self, 'update_edit_status'):
                        self.update_edit_status()
                    self.after(1500, lambda: self._render_privilege_initial(frame))
                else:
                    canvas.itemconfig(btn_bg, fill='#2980b9')
                    set_status("验证失败  无权限  请重试")

            pwd_entry.bind('<Return>', lambda e: on_submit())
            if is_developer:
                user_entry.focus_set()
            else:
                pwd_entry.focus_set()

        self.after(50, draw)

    def elevate_windows(self):
        if is_admin():
            messagebox.showinfo("提示", "当前进程已是管理员身份", parent=self)
            return
        if run_as_admin():
            messagebox.showinfo("提示", "正在以管理员身份重新启动...", parent=self)
            self.destroy()
        else:
            messagebox.showerror("错误", "提权失败", parent=self)

    def elevate_tads_admin(self):
        # 已迁移到 _render_privilege_login
        if self.app.is_admin or self.app.is_root:
            messagebox.showinfo("提示", "已是管理员或ROOT", parent=self)
            return

        self.show_temp_message("正在检查读卡器...", 5000)
        self.update_idletasks()

        if not self._ensure_pn532_connected():
            return

        self.show_temp_message("✅ 读卡器已就绪", 3000)

        top = tk.Toplevel(self)
        top.title("管理员验证")
        top.geometry("420x260")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text="请输入管理员密码", font=('微软雅黑', 10)).pack(pady=8)

        pwd_frame = tk.Frame(top)
        pwd_frame.pack(pady=5)
        pwd_entry = tk.Entry(pwd_frame, show='*', width=25, font=('微软雅黑', 10))
        pwd_entry.pack(side=tk.LEFT, padx=5)

        pwd_visible = False
        def toggle_pwd():
            nonlocal pwd_visible
            pwd_visible = not pwd_visible
            pwd_entry.config(show='' if pwd_visible else '*')
        btn_show_pwd = tk.Button(pwd_frame, text="👁", command=toggle_pwd,
                                 width=3, font=('微软雅黑', 9))
        btn_show_pwd.pack(side=tk.LEFT)

        tip_label = tk.Label(top, text="请将物理密钥放在读卡器上",
                             font=('微软雅黑', 9), fg='orange')
        tip_label.pack(pady=5)

        status_label = tk.Label(top, text="", font=('微软雅黑', 9), fg='blue')
        status_label.pack(pady=5)

        def on_verify():
            verify_btn.config(state='disabled')
            cancel_btn.config(state='disabled')
            status_label.config(text="⏳ 正在验证，请确保物理密钥已放好...", fg='blue')

            pwd = pwd_entry.get()
            if not pwd:
                status_label.config(text="❌ 请输入密码", fg='red')
                verify_btn.config(state='normal')
                cancel_btn.config(state='normal')
                tip_label.config(text="请将物理密钥放在读卡器上", fg='orange')
                return

            def do_verify():
                success = self.app.verify_admin(pwd)
                self.after(0, lambda: self._on_admin_verify_result(
                    top, success, verify_btn, cancel_btn, status_label, tip_label))
            threading.Thread(target=do_verify, daemon=True).start()

        verify_btn = tk.Button(top, text="验证", width=10, command=on_verify)
        cancel_btn = tk.Button(top, text="取消", width=10, command=top.destroy)
        verify_btn.pack(side=tk.LEFT, padx=20, pady=10)
        cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10)
        pwd_entry.bind('<Return>', lambda e: on_verify())

    def _on_admin_verify_result(self, top, success, verify_btn, cancel_btn, status_label, tip_label):
        # 已迁移到 _render_privilege_login
        if not top.winfo_exists():
            return
        if success:
            top.destroy()
            self.refresh_status()
            self.display_welcome()
            self.update_edit_permission()
            self._play_ding()
            messagebox.showinfo("成功", "已提升为 TADS Administrator", parent=self)
        else:
            status_label.config(text="验证失败   无权限   请重试", fg='red')
            tip_label.config(text="⚠️ 请确保物理密钥已放好，且密码正确", fg='orange')
            verify_btn.config(state='normal')
            cancel_btn.config(state='normal')

    def elevate_developer(self):
        if self.app.is_developer:
            messagebox.showinfo("提示", "已是开发者", parent=self)
            return

        top = tk.Toplevel(self)
        top.title("开发者验证")
        top.geometry("420x240")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text="请输入开发者密码", font=('微软雅黑', 10)).pack(pady=12)
        
        pwd_frame = tk.Frame(top)
        pwd_frame.pack(pady=5)
        pwd_entry = tk.Entry(pwd_frame, show='*', width=25, font=('微软雅黑', 10))
        pwd_entry.pack(side=tk.LEFT, padx=5)
        
        pwd_visible = False
        def toggle_pwd():
            nonlocal pwd_visible
            pwd_visible = not pwd_visible
            pwd_entry.config(show='' if pwd_visible else '*')
        btn_show_pwd = tk.Button(pwd_frame, text="👁", command=toggle_pwd, width=3, font=('微软雅黑', 9))
        btn_show_pwd.pack(side=tk.LEFT)

        status_label = tk.Label(top, text="", font=('微软雅黑', 9), fg='blue')
        status_label.pack(pady=8)

        def on_verify():
            verify_btn.config(state='disabled')
            cancel_btn.config(state='disabled')
            status_label.config(text="验证中...", fg='blue')

            pwd = pwd_entry.get()
            if not pwd:
                status_label.config(text="请输入密码", fg='red')
                verify_btn.config(state='normal')
                cancel_btn.config(state='normal')
                return

            def do_verify():
                success = self.app.verify_developer(pwd)
                self.after(0, lambda: self._on_developer_verify_result(
                    top, success, verify_btn, cancel_btn, status_label
                ))

            threading.Thread(target=do_verify, daemon=True).start()

        verify_btn = tk.Button(top, text="验证", width=10, command=on_verify)
        cancel_btn = tk.Button(top, text="取消", width=10, command=top.destroy)
        verify_btn.pack(side=tk.LEFT, padx=20, pady=10)
        cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10)
        pwd_entry.bind('<Return>', lambda e: on_verify())

    def _on_developer_verify_result(self, top, success, verify_btn, cancel_btn, status_label):
        if success:
            top.destroy()
            self.refresh_status()
            self.display_welcome()
            self.update_edit_permission()
            self._play_ding()
            messagebox.showinfo("成功", "已提升为 Developer", parent=self)
        else:
            status_label.config(text="验证失败   无权限   请重试", fg='red')
            verify_btn.config(state='normal')
            cancel_btn.config(state='normal')

    def elevate_root(self):
        # 已迁移到 _render_privilege_login
        if self.app.is_root:
            messagebox.showinfo("提示", "已是Root", parent=self)
            return

        self.show_temp_message("正在检查读卡器...", 5000)
        self.update_idletasks()

        if not self._ensure_pn532_connected():
            return

        self.show_temp_message("✅ 读卡器已就绪", 3000)

        top = tk.Toplevel(self)
        top.title("ROOT验证")
        top.geometry("420x260")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text="请输入ROOT密码", font=('微软雅黑', 10)).pack(pady=8)

        pwd_frame = tk.Frame(top)
        pwd_frame.pack(pady=5)
        pwd_entry = tk.Entry(pwd_frame, show='*', width=25, font=('微软雅黑', 10))
        pwd_entry.pack(side=tk.LEFT, padx=5)

        pwd_visible = False
        def toggle_pwd():
            nonlocal pwd_visible
            pwd_visible = not pwd_visible
            pwd_entry.config(show='' if pwd_visible else '*')
        btn_show_pwd = tk.Button(pwd_frame, text="👁", command=toggle_pwd,
                                 width=3, font=('微软雅黑', 9))
        btn_show_pwd.pack(side=tk.LEFT)

        tip_label = tk.Label(top, text="请将物理密钥放在读卡器上",
                             font=('微软雅黑', 9), fg='orange')
        tip_label.pack(pady=5)

        status_label = tk.Label(top, text="", font=('微软雅黑', 9), fg='blue')
        status_label.pack(pady=5)

        def on_verify():
            verify_btn.config(state='disabled')
            cancel_btn.config(state='disabled')
            status_label.config(text="⏳ 正在验证，请确保物理密钥已放好...", fg='blue')

            pwd = pwd_entry.get()
            if not pwd:
                status_label.config(text="❌ 请输入密码", fg='red')
                verify_btn.config(state='normal')
                cancel_btn.config(state='normal')
                tip_label.config(text="请将物理密钥放在读卡器上", fg='orange')
                return

            def do_verify():
                success = self.app.verify_root(pwd)
                self.after(0, lambda: self._on_root_verify_result(
                    top, success, verify_btn, cancel_btn, status_label, tip_label))
            threading.Thread(target=do_verify, daemon=True).start()

        verify_btn = tk.Button(top, text="验证", width=10, command=on_verify)
        cancel_btn = tk.Button(top, text="取消", width=10, command=top.destroy)
        verify_btn.pack(side=tk.LEFT, padx=20, pady=10)
        cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10)
        pwd_entry.bind('<Return>', lambda e: on_verify())

    def _on_root_verify_result(self, top, success, verify_btn, cancel_btn, status_label, tip_label):
        # 已迁移到 _render_privilege_login
        if not top.winfo_exists():
            return
        if success:
            top.destroy()
            self.refresh_status()
            self.display_welcome()
            self.update_edit_permission()
            self._play_ding()
            messagebox.showinfo("成功", "已提升为 ROOT", parent=self)
        else:
            status_label.config(text="验证失败   无权限   请重试", fg='red')
            tip_label.config(text="⚠️ 请确保物理密钥已放好，且密码正确", fg='orange')
            verify_btn.config(state='normal')
            cancel_btn.config(state='normal')

    def _check_permission(self, perm_key):
        """检查当前用户是否拥有指定权限，若无则显示警告并返回 False"""
        if self.app.has_permission(perm_key):
            return True
        perm_def = self.app.config.get_permissions_definition()
        perm_display = perm_def.get(perm_key, {}).get('name', perm_key)
        messagebox.showwarning("权限不足", f"您没有执行此操作的权限", parent=self)
        return False

    def _config_paths(self):
        if not self.app.is_root:
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        
        top = tk.Toplevel(self)
        top.title("路径配置")
        top.geometry("500x300")
        top.transient(self)
        top.grab_set()

        paths = self.app.config.get('paths', {})
        entries = {}
        labels = ['数据根目录', '日志目录', '主数据目录', '还原点目录']
        keys = ['data_root', 'log_dir', 'main_data_dir', 'restore_dir']
        
        for i, (label, key) in enumerate(zip(labels, keys)):
            tk.Label(top, text=label+":", font=('微软雅黑', 10)).grid(row=i, column=0, padx=10, pady=8, sticky='e')
            entry = tk.Entry(top, width=40, font=('微软雅黑', 10))
            entry.insert(0, paths.get(key, ''))
            entry.grid(row=i, column=1, padx=10, pady=8, sticky='w')
            entries[key] = entry

        tk.Label(top, text="注意：配置目录固定为 %APPDATA%\\TADS\\Server\\config\\，不可修改", 
                 font=('微软雅黑', 9), fg='gray').grid(row=len(labels), column=0, columnspan=2, padx=10, pady=5)

        def do_save():
            new_paths = {}
            for key, entry in entries.items():
                val = entry.get().strip()
                if not val:
                    messagebox.showerror("错误", "路径不能为空", parent=top)
                    return
                new_paths[key] = val
            old_paths = self.app.config.get('paths', {})
            self.app.config.set('paths', new_paths)
            self.app._apply_paths_from_config()
            # 记录日志
            self.app.log_action("更改路径配置", f"数据根目录: {new_paths['data_root']}, 日志目录: {new_paths['log_dir']}, 主数据目录: {new_paths['main_data_dir']}, 还原点目录: {new_paths['restore_dir']}")
            messagebox.showinfo("成功", "路径已更新，请重启程序使所有更改生效", parent=top)
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.grid(row=len(labels)+1, column=0, columnspan=2, pady=15)
        tk.Button(btn_frame, text="保存", command=do_save, width=12, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=top.destroy, width=12, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)

    def _config_monitor(self):
        if not (self.app.is_root or self.app.is_admin):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        
        top = tk.Toplevel(self)
        top.title("站点监控配置")
        top.geometry("400x200")
        top.transient(self)
        top.grab_set()

        monitor = self.app.config.get('monitor', {})
        enabled = tk.BooleanVar(value=monitor.get('enabled', True))
        port = tk.StringVar(value=str(monitor.get('port', 10045)))
        name = tk.StringVar(value=monitor.get('display_name', '中枢站'))

        tk.Checkbutton(top, text="启用监控", variable=enabled, font=('微软雅黑', 10)).grid(row=0, column=0, columnspan=2, pady=8)
        tk.Label(top, text="端口:", font=('微软雅黑', 10)).grid(row=1, column=0, padx=10, pady=8, sticky='e')
        tk.Entry(top, textvariable=port, width=12, font=('微软雅黑', 10)).grid(row=1, column=1, padx=10, pady=8, sticky='w')
        tk.Label(top, text="显示名称:", font=('微软雅黑', 10)).grid(row=2, column=0, padx=10, pady=8, sticky='e')
        tk.Entry(top, textvariable=name, width=20, font=('微软雅黑', 10)).grid(row=2, column=1, padx=10, pady=8, sticky='w')

        def do_save():
            try:
                port_int = int(port.get())
                if port_int < 1 or port_int > 65535:
                    messagebox.showerror("错误", "端口号必须在1-65535之间", parent=top)
                    return
            except ValueError:
                messagebox.showerror("错误", "端口必须为数字", parent=top)
                return
            
            display_name = name.get().strip()
            if not display_name:
                display_name = "中枢站"
            
            old_monitor = self.app.config.get('monitor', {})
            new_monitor = {
                'enabled': enabled.get(),
                'port': port_int,
                'display_name': display_name
            }
            self.app.config.set('monitor', new_monitor)
            # 记录日志
            self.app.log_action("更改站点监控配置", f"启用: {enabled.get()}, 端口: {port_int}, 显示名称: {display_name}")
            top.destroy()
            self.refresh_status()
            messagebox.showinfo("成功", "站点监控配置已更新", parent=self)

        btn_frame = tk.Frame(top)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        tk.Button(btn_frame, text="保存", command=do_save, width=12, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=top.destroy, width=12, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)

    def _show_api_token(self):
        """展示当前 API Token（仅管理员/ROOT 可见）"""
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return

        token = self.app.api_token or ""
        expire_ts = self.app.api_token_expire or 0
        if not token:
            messagebox.showinfo("提示", "当前没有有效的 API Token", parent=self)
            return

        try:
            expire_str = datetime.datetime.fromtimestamp(expire_ts).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            expire_str = "未知"

        top = tk.Toplevel(self)
        top.title("API Token")
        top.geometry("620x220")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text=f"身份: {self.app.current_identity}   ｜   过期时间: {expire_str}",
                 font=('微软雅黑', 10), bg='#f0f0f0').pack(pady=8, padx=10, anchor='w')

        entry = tk.Entry(top, width=70, font=('Consolas', 10))
        entry.insert(0, token)
        entry.config(state='readonly')
        entry.pack(padx=10, pady=5, fill=tk.X)

        tk.Label(top, text="客户端可在请求头中加入：X-TADS-Token: <上面的值>",
                 font=('微软雅黑', 9), fg='gray').pack(pady=4, anchor='w', padx=10)

        def copy_to_clipboard():
            self.clipboard_clear()
            self.clipboard_append(token)
            messagebox.showinfo("成功", "已复制到剪贴板", parent=top)

        btn_bar = tk.Frame(top)
        btn_bar.pack(pady=10)
        tk.Button(btn_bar, text="复制", width=10, command=copy_to_clipboard).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_bar, text="关闭", width=10, command=top.destroy).pack(side=tk.LEFT, padx=10)

    def _show_server_info(self):
        """显示服务器实时信息（极其详尽版，每 1 秒刷新）"""
        import platform
        import shutil
        import socket
        import ctypes
        import time
        import sys
        import winreg
        import subprocess
        try:
            import psutil
            has_psutil = True
        except ImportError:
            has_psutil = False

        # 精准获取系统名称
        def get_os_name():
            try:
                win_ver = sys.getwindowsversion()
                build = win_ver.build
                if win_ver.major == 10 and build >= 22000:
                    return f"Windows 11 (Build {build})"
                elif win_ver.major == 10:
                    return f"Windows 10 (Build {build})"
                elif win_ver.major == 6 and win_ver.minor == 1:
                    return f"Windows 7 (Build {build})"
                elif win_ver.major == 6 and win_ver.minor == 2:
                    return f"Windows 8 (Build {build})"
                elif win_ver.major == 6 and win_ver.minor == 3:
                    return f"Windows 8.1 (Build {build})"
                else:
                    return f"Windows {win_ver.major}.{win_ver.minor} (Build {build})"
            except:
                return f"{platform.system()} {platform.release()}"

        # 精准获取 CPU 名称（读注册表）
        def get_cpu_name():
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
                cpu_name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                winreg.CloseKey(key)
                return cpu_name.strip()
            except:
                return platform.processor() or "未知 CPU"

        # 获取 GPU 名称（调用 wmic）
        def get_gpu_name():
            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                output = subprocess.check_output(
                    "wmic path win32_VideoController get name", 
                    shell=True, 
                    stderr=subprocess.DEVNULL, 
                    startupinfo=startupinfo
                )
                lines = output.decode('gbk', errors='ignore').splitlines()
                gpus = [line.strip() for line in lines if line.strip() and "Name" not in line]
                return ", ".join(gpus) if gpus else "未知显卡"
            except:
                return "获取失败"

        os_name = get_os_name()
        cpu_name = get_cpu_name()
        gpu_name = get_gpu_name()
        
        py_ver = platform.python_version()
        hostname = socket.gethostname()
        
        # CPU 核心数
        if has_psutil:
            cores_phys = psutil.cpu_count(logical=False)
            cores_logi = psutil.cpu_count(logical=True)
            cores_str = f"{cores_phys} 核 {cores_logi} 线程"
        else:
            cores_str = "需安装 psutil"

        top = tk.Toplevel(self)
        top.title("服务器系统仪表盘")
        top.geometry("850x780")  # 高度稍微加长
        top.transient(self)
        top.grab_set()

        # 顶部时间
        time_label = tk.Label(top, text="", font=('微软雅黑', 12, 'bold'), bg='#2c3e50', fg='white')
        time_label.pack(fill=tk.X, ipady=5)

        # 主体框架 (左右两列)
        body_frame = tk.Frame(top, bg='#f0f0f0')
        body_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        body_frame.grid_columnconfigure(0, weight=1)
        body_frame.grid_columnconfigure(1, weight=1)

        # ================= 左侧框架 =================
        left_frame = tk.LabelFrame(body_frame, text=" 系统与硬件 ", font=('微软雅黑', 10, 'bold'), bg='#f0f0f0', padx=10, pady=10)
        left_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 10))

        left_labels = {}
        def add_left(key, text):
            row = len(left_labels)
            tk.Label(left_frame, text=text, font=('微软雅黑', 9, 'bold'), bg='#f0f0f0', anchor='e').grid(row=row, column=0, sticky='e', pady=4)
            lbl = tk.Label(left_frame, text="获取中...", font=('微软雅黑', 9), bg='#f0f0f0', anchor='w', wraplength=300, justify='left')
            lbl.grid(row=row, column=1, sticky='w', padx=5, pady=4)
            left_labels[key] = lbl

        add_left("os", "操作系统:")
        add_left("py", "Python版本:")
        add_left("cpu_name", "CPU 型号:")
        add_left("gpu_name", "GPU 型号:")
        add_left("cores", "CPU 核心:")
        add_left("cpu_usage", "系统 CPU 占用:")
        add_left("mem", "系统内存:")
        add_left("proc_mem", "本程序内存:")
        add_left("proc_cpu", "本程序 CPU:")
        add_left("uptime", "系统运行时长:")

        left_labels["os"].config(text=os_name)
        left_labels["py"].config(text=py_ver)
        left_labels["cpu_name"].config(text=cpu_name)
        left_labels["gpu_name"].config(text=gpu_name)
        left_labels["cores"].config(text=cores_str)

        # ================= 右侧框架 =================
        right_frame = tk.LabelFrame(body_frame, text=" 网络与磁盘 ", font=('微软雅黑', 10, 'bold'), bg='#f0f0f0', padx=10, pady=10)
        right_frame.grid(row=0, column=1, sticky='nsew', padx=(10, 0))

        right_labels = {}
        def add_right(key, text):
            row = len(right_labels)
            tk.Label(right_frame, text=text, font=('微软雅黑', 9, 'bold'), bg='#f0f0f0', anchor='e').grid(row=row, column=0, sticky='ne', pady=4)
            lbl = tk.Label(right_frame, text="获取中...", font=('微软雅黑', 9), bg='#f0f0f0', anchor='w', wraplength=300, justify='left')
            lbl.grid(row=row, column=1, sticky='nw', padx=5, pady=4)
            right_labels[key] = lbl

        add_right("host", "主机名:")
        add_right("nets", "网络接口:")
        add_right("net_speed", "网络波动(↓/↑):")
        add_right("tcp", "TCP 连接数:")
        add_right("disks", "磁盘占用:")
        add_right("time", "当前时间:")

        right_labels["host"].config(text=hostname)

        # 获取系统运行时间
        try:
            uptime_ms = ctypes.windll.kernel32.GetTickCount64()
            uptime_sec = uptime_ms // 1000
            days = uptime_sec // 86400
            hours = (uptime_sec % 86400) // 3600
            minutes = (uptime_sec % 3600) // 60
            left_labels["uptime"].config(text=f"{days}天 {hours}小时 {minutes}分")
        except:
            left_labels["uptime"].config(text="未知")

        # 网速计算变量
        last_net_io = None
        last_net_time = time.time()

        if has_psutil:
            psutil.cpu_percent(interval=None)
            try:
                current_process = psutil.Process(os.getpid())
                current_process.cpu_percent(interval=None)
            except:
                current_process = None
        else:
            current_process = None

        def update_info():
            if not top.winfo_exists():
                return

            now = datetime.datetime.now()
            right_labels["time"].config(text=now.strftime("%Y-%m-%d %H:%M:%S"))
            time_label.config(text=f"服务器当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")

            # 1. CPU 和 内存 (系统级)
            if has_psutil:
                cpu_usage = psutil.cpu_percent(interval=None)
                left_labels["cpu_usage"].config(text=f"{cpu_usage}%")
                
                mem = psutil.virtual_memory()
                used_gb = mem.used / (1024**3)
                total_gb = mem.total / (1024**3)
                left_labels["mem"].config(text=f"{used_gb:.2f} GB / {total_gb:.2f} GB ({mem.percent}%)")
            else:
                left_labels["cpu_usage"].config(text="需安装 psutil")
                left_labels["mem"].config(text="需安装 psutil")

            # 2. 当前进程 内存 和 CPU
            if current_process:
                try:
                    proc_mem = current_process.memory_info().rss / (1024**2)
                    left_labels["proc_mem"].config(text=f"{proc_mem:.1f} MB")
                    proc_cpu = current_process.cpu_percent(interval=None)
                    left_labels["proc_cpu"].config(text=f"{proc_cpu}%")
                except:
                    left_labels["proc_mem"].config(text="获取失败")
                    left_labels["proc_cpu"].config(text="获取失败")

            # 3. 网络接口 (IP + MAC)
            if has_psutil:
                try:
                    net_info = psutil.net_if_addrs()
                    net_str = ""
                    for name, addrs in net_info.items():
                        if name.lower() in ['lo', 'loopback']: continue
                        ipv4 = mac = ""
                        for addr in addrs:
                            if addr.family == socket.AF_INET:
                                ipv4 = addr.address
                            elif addr.family == psutil.AF_LINK:
                                mac = addr.address
                        if ipv4 and not ipv4.startswith("169.254"):
                            net_str += f"{name}: {ipv4}\n"
                    right_labels["nets"].config(text=net_str.strip() if net_str else "未连接网络")
                except:
                    right_labels["nets"].config(text="获取失败")
            else:
                right_labels["nets"].config(text="需安装 psutil")

            # 4. 网络波动
            nonlocal last_net_io, last_net_time
            if has_psutil:
                try:
                    current_net_io = psutil.net_io_counters()
                    current_time = time.time()
                    if last_net_io is not None:
                        dt = current_time - last_net_time
                        if dt > 0:
                            sent = current_net_io.bytes_sent - last_net_io.bytes_sent
                            recv = current_net_io.bytes_recv - last_net_io.bytes_recv
                            sent_kb = (sent / dt) / 1024
                            recv_kb = (recv / dt) / 1024
                            if sent_kb > 1024 or recv_kb > 1024:
                                right_labels["net_speed"].config(text=f"{recv_kb/1024:.2f} MB/s  /  {sent_kb/1024:.2f} MB/s")
                            else:
                                right_labels["net_speed"].config(text=f"{recv_kb:.2f} KB/s  /  {sent_kb:.2f} KB/s")
                    last_net_io = current_net_io
                    last_net_time = current_time
                except:
                    right_labels["net_speed"].config(text="获取失败")

                # TCP 连接数
                try:
                    conns = psutil.net_connections(kind='tcp')
                    right_labels["tcp"].config(text=f"{len(conns)} 个")
                except:
                    right_labels["tcp"].config(text="需管理员权限")

                # 5. 所有磁盘分区
                try:
                    disk_str = ""
                    for part in psutil.disk_partitions():
                        if 'cdrom' in part.opts or part.fstype == '': continue
                        try:
                            usage = psutil.disk_usage(part.mountpoint)
                            used_gb = usage.used / (1024**3)
                            total_gb = usage.total / (1024**3)
                            percent = usage.percent
                            disk_str += f"{part.device} {used_gb:.1f}G / {total_gb:.1f}G ({percent}%)\n"
                        except:
                            pass
                    right_labels["disks"].config(text=disk_str.strip())
                except:
                    right_labels["disks"].config(text="获取失败")
            else:
                right_labels["net_speed"].config(text="需安装 psutil")
                right_labels["tcp"].config(text="需安装 psutil")
                try:
                    total, used, free = shutil.disk_usage("C:\\")
                    right_labels["disks"].config(text=f"C: {used/(1024**3):.1f}G / {total/(1024**3):.1f}G")
                except:
                    right_labels["disks"].config(text="获取失败")

            top.after(1000, update_info)

        # 启动刷新
        update_info()
        
        # 底部按钮区
        btn_frame = tk.Frame(top, bg='#f0f0f0')
        btn_frame.pack(side=tk.BOTTOM, pady=15)
        
        # 打开任务管理器按钮
        def open_taskmgr():
            try:
                VK_CONTROL = 0x11
                VK_SHIFT = 0x10
                VK_ESCAPE = 0x1B
                KEYEVENTF_KEYUP = 0x0002
                
                # 模拟按下 Ctrl + Shift + Esc
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                
                # 模拟松开按键
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
                ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
            except Exception as e:
                messagebox.showerror("错误", f"无法模拟快捷键: {e}", parent=top)

        tk.Button(btn_frame, text="打开任务管理器", command=open_taskmgr, width=15, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="关闭", command=top.destroy, width=15, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)

        # 居中显示
        top.update_idletasks()
        width = top.winfo_width()
        height = top.winfo_height()
        x = (top.winfo_screenwidth() // 2) - (width // 2)
        y = (top.winfo_screenheight() // 2) - (height // 2)
        top.geometry(f'{width}x{height}+{x}+{y}')

    # ====== 设置框架 ======
    def build_settings_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        tk.Button(btn_frame, text="导出日志", command=self._export_logs,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="更改API服务端口", command=self._change_api_port,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="API接口配置", command=self._config_api,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="路径配置", command=self._config_paths,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="站点监控", command=self._config_monitor,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="连接PN532", command=self._connect_pn532,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="显示当前API Token", command=self._show_api_token,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="活跃 Token 管理", command=self._manage_tokens,
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)

        current_state = self.app.get_auto_update_setting()
        btn_text = "关闭查询时自动更新该车次" if current_state else "开启查询时自动更新该车次"
        self.auto_update_btn = tk.Button(btn_frame, text=btn_text, command=self._toggle_auto_update,
                                         font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                                         width=26, anchor='w', padx=5)
        self.auto_update_btn.pack(anchor='w', pady=2)

        display_frame = tk.Frame(frame, bg='#f0f0f0')
        display_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        frame.display_frame = display_frame
        self._set_settings_content(frame, "请选择上方设置功能")
        return frame

    def _config_api(self):
        """API接口配置弹窗"""
        if not self.app.is_root:
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        
        top = tk.Toplevel(self)
        top.title("API接口配置")
        top.geometry("550x270")
        top.transient(self)
        top.grab_set()

        api_config = self.app.config.get('api', {})
        entries = {}
        
        tk.Label(top, text="V1接口地址:", font=('微软雅黑', 10)).grid(row=0, column=0, padx=10, pady=8, sticky='e')
        entry_v1 = tk.Entry(top, width=45, font=('微软雅黑', 10))
        entry_v1.insert(0, api_config.get('v1_base', 'https://data.railgo.zenglingkun.cn/api'))
        entry_v1.grid(row=0, column=1, padx=10, pady=8, sticky='w')
        entries['v1_base'] = entry_v1
        
        tk.Label(top, text="V2接口地址:", font=('微软雅黑', 10)).grid(row=1, column=0, padx=10, pady=8, sticky='e')
        entry_v2 = tk.Entry(top, width=45, font=('微软雅黑', 10))
        entry_v2.insert(0, api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2'))
        entry_v2.grid(row=1, column=1, padx=10, pady=8, sticky='w')
        entries['v2_base'] = entry_v2

        tk.Label(top, text="EMU接口地址:", font=('微软雅黑', 10)).grid(row=2, column=0, padx=10, pady=8, sticky='e')
        entry_emu = tk.Entry(top, width=45, font=('微软雅黑', 10))
        entry_emu.insert(0, api_config.get('emu_base', 'https://emu.railgo.zenglingkun.cn'))
        entry_emu.grid(row=2, column=1, padx=10, pady=8, sticky='w')
        entries['emu_base'] = entry_emu

        def do_save():
            new_config = {
                'v1_base': entries['v1_base'].get().strip(),
                'v2_base': entries['v2_base'].get().strip(),
                'emu_base': entries['emu_base'].get().strip()
            }
            if not new_config['v1_base'] or not new_config['v2_base'] or not new_config['emu_base']:
                messagebox.showerror("错误", "接口地址不能为空", parent=top)
                return
            self.app.config.set('api', new_config)
            self.app.log_action("更改API接口配置", 
                               f"V1: {new_config['v1_base']}, V2: {new_config['v2_base']}, EMU: {new_config['emu_base']}")
            messagebox.showinfo("成功", "API接口配置已更新，请重启程序生效", parent=top)
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=15)
        tk.Button(btn_frame, text="保存", command=do_save, width=12, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=top.destroy, width=12, font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=10)

    def _set_settings_content(self, frame, text):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        lbl = tk.Label(frame.display_frame, text=text, font=('微软雅黑', 12), bg='#f0f0f0')
        lbl.pack(pady=20)

    def _change_admin_pwd(self):
        if not self._check_permission("change_admin_pwd"):
            return
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        top = tk.Toplevel(self)
        top.title("更改管理员密码")
        top.geometry("320x210")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="新密码:", font=('微软雅黑', 10)).pack(pady=5)
        entry1 = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        entry1.pack(pady=5)
        tk.Label(top, text="确认密码:", font=('微软雅黑', 10)).pack(pady=5)
        entry2 = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        entry2.pack(pady=5)
        def do_change():
            p1 = entry1.get()
            p2 = entry2.get()
            if p1 != p2:
                messagebox.showerror("错误", "两次密码不一致", parent=top)
                return
            if len(p1) < 4:
                messagebox.showerror("错误", "密码长度至少4位", parent=top)
                return
            global ADMIN_PASSWORD_HASH
            ADMIN_PASSWORD_HASH = hash_password(p1)
            self.app.config.save()
            self.app.log_action("更改管理员密码", "密码已更新")
            messagebox.showinfo("成功", "管理员密码已更改", parent=self)
            top.destroy()
        tk.Button(top, text="确认", command=do_change, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _change_root_pwd(self):
        if not self._check_permission("change_root_pwd"):
            return
        top = tk.Toplevel(self)
        top.title("更改ROOT密码")
        top.geometry("320x210")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="新ROOT密码:", font=('微软雅黑', 10)).pack(pady=5)
        entry1 = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        entry1.pack(pady=5)
        tk.Label(top, text="确认密码:", font=('微软雅黑', 10)).pack(pady=5)
        entry2 = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        entry2.pack(pady=5)
        def do_change():
            p1 = entry1.get()
            p2 = entry2.get()
            if p1 != p2:
                messagebox.showerror("错误", "两次密码不一致", parent=top)
                return
            if len(p1) < 4:
                messagebox.showerror("错误", "密码长度至少4位", parent=top)
                return
            global ROOT_PASSWORD_HASH
            ROOT_PASSWORD_HASH = hash_password(p1)
            self.app.config.save()
            self.app.log_action("更改ROOT密码", "密码已更新")
            messagebox.showinfo("成功", "ROOT密码已更改", parent=self)
            top.destroy()
        tk.Button(top, text="确认", command=do_change, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _export_logs(self):
        if not self._check_permission("export_logs"):
            return
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "需要管理员或ROOT权限", parent=self)
            return
        
        # 选择导出格式
        format_choice = simpledialog.askstring(
            "选择导出格式",
            "请选择导出格式：\n\nCSV - 表格格式（推荐）\nJSON - 结构化数据\nTXT - 纯文本\n\n请输入 CSV / JSON / TXT：",
            parent=self
        )
        if format_choice is None:
            return
        format_choice = format_choice.upper()
        if format_choice not in ['CSV', 'JSON', 'TXT']:
            messagebox.showerror("错误", "不支持的格式，请选择 CSV、JSON 或 TXT", parent=self)
            return
        
        # 获取日志内容
        logs = self.app.get_recent_logs(999999)  # 获取全部日志
        
        if format_choice == 'CSV':
            # 导出为 CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["时间", "身份", "操作", "详情"])
            for line in logs.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'\[(.*?)\]\s*\[(.*?)\]\s*(.*?)(?:\s*–\s*(.*))?$', line)
                if match:
                    time_str, identity, action, detail = match.groups()
                    writer.writerow([time_str, identity, action, detail or ""])
                else:
                    writer.writerow(["", "", "", line])
            content = output.getvalue()
            ext = ".csv"
            file_types = [("CSV文件", "*.csv"), ("所有文件", "*.*")]
        elif format_choice == 'JSON':
            # 导出为 JSON
            json_data = []
            for line in logs.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = re.match(r'\[(.*?)\]\s*\[(.*?)\]\s*(.*?)(?:\s*–\s*(.*))?$', line)
                if match:
                    time_str, identity, action, detail = match.groups()
                    json_data.append({
                        "time": time_str,
                        "identity": identity,
                        "action": action,
                        "detail": detail or ""
                    })
                else:
                    json_data.append({"raw": line})
            content = json.dumps(json_data, ensure_ascii=False, indent=2)
            ext = ".json"
            file_types = [("JSON文件", "*.json"), ("所有文件", "*.*")]
        else:  # TXT
            content = logs
            ext = ".txt"
            file_types = [("文本文件", "*.txt"), ("所有文件", "*.*")]
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=file_types,
            title=f"保存日志为{format_choice}格式"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8-sig') as f:
                    f.write(content)
                messagebox.showinfo("成功", f"日志已导出至 {file_path}", parent=self)
            except Exception as e:
                messagebox.showerror("错误", f"保存文件失败: {e}", parent=self)

    def _change_api_port(self):
        if not self._check_permission("edit_config"):
            return
        if not (self.app.is_root or self.app.is_admin):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        top = tk.Toplevel(self)
        top.title("更改API服务端口")
        top.geometry("320x150")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="新API端口 (1024-65535):", font=('微软雅黑', 10)).pack(pady=10)
        entry = tk.Entry(top, width=10, font=('微软雅黑', 10))
        entry.pack(pady=5)
        current_port = self.app.config.get('api_port', 10076)
        entry.insert(0, str(current_port))
        def do_change():
            try:
                new_port = int(entry.get().strip())
                if new_port < 1024 or new_port > 65535:
                    messagebox.showerror("错误", "端口号必须在1024-65535之间", parent=top)
                    return
                old_port = self.app.config.get('api_port', 10076)
                self.app.config.set('api_port', new_port)
                # 记录日志
                self.app.log_action("更改API服务端口", f"{old_port} -> {new_port}")
                messagebox.showinfo("成功", f"API端口已更改为 {new_port}，需要重启程序生效", parent=top)
                top.destroy()
            except ValueError:
                messagebox.showerror("错误", "请输入有效的数字", parent=top)
        tk.Button(top, text="确认", command=do_change, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    # ====== 日志框架 ======
    def build_log_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        
        # 顶部控制栏
        control_frame = tk.Frame(frame, bg='#f0f0f0')
        control_frame.pack(fill=tk.X, pady=5)
        
        tk.Label(control_frame, text="日志类型:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        log_type_var = tk.StringVar(value='普通日志')
        log_type_combo = ttk.Combobox(control_frame, textvariable=log_type_var, 
                                      values=['普通日志', '报错日志'], width=12, state='readonly')
        log_type_combo.pack(side=tk.LEFT, padx=5)
        
        def refresh_log_wrapper():
            self._refresh_log_in_frame(frame, log_type_var.get())
            # 延迟0.06秒更新标签页标题，避免加载慢时污染标题/污染上一个标签页
            log_type_display = log_type_var.get()
            if self.current_tab_id is not None:
                self.after(60, lambda: self.update_tab_title(self.current_tab_id, f"日志-{log_type_display}"))
        
        tk.Button(control_frame, text="刷新", command=refresh_log_wrapper, width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="保存", command=lambda: self._save_log_in_frame(frame, log_type_var.get()), width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="清空日志", command=lambda: self._clear_log_in_frame(frame, log_type_var.get()), width=10).pack(side=tk.LEFT, padx=5)
        
        def on_log_type_change(event):
            log_type_display = log_type_var.get()
            self._refresh_log_in_frame(frame, log_type_display)
            # 延迟0.06秒更新标签页标题，防止污染上一个标签页
            if self.current_tab_id is not None:
                self.after(60, lambda: self.update_tab_title(self.current_tab_id, f"日志-{log_type_display}"))
        
        log_type_combo.bind('<<ComboboxSelected>>', on_log_type_change)

        log_text = scrolledtext.ScrolledText(frame, font=('Consolas', 10), wrap=tk.WORD, bg='white', height=20)
        log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        log_text.config(state='normal')
        frame.log_text = log_text
        frame.log_type_var = log_type_var
        
        # 初始加载，延迟0.06秒设置标题为"日志-普通日志"，防止污染上一个标签页
        self._refresh_log_in_frame(frame, '普通日志')
        if self.current_tab_id is not None:
            self.after(60, lambda: self.update_tab_title(self.current_tab_id, "日志-普通日志"))
        
        return frame

    def _refresh_log_in_frame(self, frame, log_type='普通日志'):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        
        if hasattr(frame, 'log_text'):
            text_widget = frame.log_text
            text_widget.config(state='normal')
            text_widget.delete(1.0, tk.END)
            
            if log_type == '普通日志':
                logs = self.app.get_recent_logs(3000)
            else:
                logs = self.app.get_recent_error_logs(3000)
            
            text_widget.insert(tk.END, logs)
            text_widget.config(state='normal')
            text_widget.see(tk.END)

    def _clear_log_in_frame(self, frame, log_type='普通日志'):
        if not self.app.is_root:
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        
        if log_type == '普通日志':
            log_file = LOG_FILE
            log_name = "普通日志"
        else:
            log_file = ERROR_LOG
            log_name = "报错日志"
        
        if not messagebox.askyesno("确认清空", f"确认清空 {log_name} 的所有内容？", parent=self):
            return
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("")
            messagebox.showinfo("成功", f"{log_name} 已清空", parent=self)
            self._refresh_log_in_frame(frame, log_type)
        except Exception as e:
            messagebox.showerror("错误", f"清空失败: {e}", parent=self)

    def _save_log_in_frame(self, frame, log_type='普通日志'):
        if not self.app.is_root:
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        
        if log_type == '普通日志':
            log_file = LOG_FILE
            log_name = "普通日志"
        else:
            log_file = ERROR_LOG
            log_name = "报错日志"
        
        if not messagebox.askyesno("确认保存", f"确认将当前内容保存到 {log_name}？", parent=self):
            return
        
        if hasattr(frame, 'log_text'):
            content = frame.log_text.get(1.0, tk.END).rstrip('\n')
            try:
                with open(log_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("成功", f"{log_name} 已保存", parent=self)
            except Exception as e:
                messagebox.showerror("错误", f"保存失败: {e}", parent=self)

    # ====== 还原点框架 ======
    def build_restore_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        def make_restore_callback(cmd):
            def callback():
                cmd()
            return callback

        tk.Button(btn_frame, text="添加还原点（上限3个）",
                  command=make_restore_callback(self._add_restore),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="从还原点恢复",
                  command=make_restore_callback(self._restore_from_point),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="编辑还原点（删除/重命名）",
                  command=make_restore_callback(self._edit_restore),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="格式化所有还原点",
                  command=make_restore_callback(self._format_restore),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)
        tk.Button(btn_frame, text="刷新列表",
                  command=make_restore_callback(self._refresh_restore_list),
                  font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                  width=26, anchor='w', padx=5).pack(anchor='w', pady=2)

        list_frame = tk.Frame(frame, bg='#f0f0f0')
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        listbox = Listbox(list_frame, font=('微软雅黑', 12), selectmode=EXTENDED)
        listbox.pack(fill=tk.BOTH, expand=True)
        frame.restore_listbox = listbox
        self._refresh_restore_list()
        return frame

    def _refresh_restore_list(self):
        if not (self.app.is_admin or self.app.is_root):
            return
        self.app.update_restore_points()
        for tid, data in self.tabs.items():
            if data['title'] == "还原点":
                frame = data['content_frame']
                if hasattr(frame, 'restore_listbox'):
                    listbox = frame.restore_listbox
                    listbox.delete(0, tk.END)
                    for name in self.app.restore_points:
                        listbox.insert(tk.END, name)
                    break

    def _add_restore(self):
        if not self._check_permission("add_restore"):
            return
        if len(self.app.restore_points) >= 3:
            messagebox.showinfo("提示", "还原点已达上限（3个）", parent=self)
            return
        top = tk.Toplevel(self)
        top.title("添加还原点")
        top.geometry("320x130")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="还原点名称:", font=('微软雅黑', 10)).pack(pady=10)
        entry = tk.Entry(top, width=20, font=('微软雅黑', 10))
        entry.pack(pady=5)
        def do_add():
            name = entry.get().strip()
            if not name:
                messagebox.showwarning("提示", "请输入名称", parent=top)
                return
            if re.search(r'[<>:"/\\|?*]', name):
                messagebox.showerror("错误", "名称包含非法字符", parent=top)
                return
            if name in self.app.restore_points:
                messagebox.showinfo("提示", "名称已存在", parent=top)
                return
            def async_backup():
                backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
                try:
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        json.dump(self.app.data, f, ensure_ascii=False, indent=2)
                    self.app.restore_points.append(name)
                    self.app.log_action("添加还原点", name)
                    self.after(0, lambda: messagebox.showinfo("成功", f"已添加还原点 {name}", parent=self))
                    self.after(0, self._refresh_restore_list)
                except Exception as e:
                    self.after(0, lambda: messagebox.showerror("错误", f"备份失败: {e}", parent=self))
            threading.Thread(target=async_backup, daemon=True).start()
            top.destroy()
        tk.Button(top, text="确认", command=do_add, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _restore_from_point(self):
        if not self._check_permission("restore_apply"):
            return
        current_tid = self.current_tab_id
        if current_tid is None or current_tid not in self.tabs:
            return
        frame = self.tabs[current_tid]['content_frame']
        if not hasattr(frame, 'restore_listbox'):
            messagebox.showinfo("提示", "请切换到还原点标签页", parent=self)
            return
        listbox = frame.restore_listbox
        selection = listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请选择还原点", parent=self)
            return
        name = listbox.get(selection[0])
        if not messagebox.askyesno("确认", f"从 {name} 恢复？", parent=self):
            return
        backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
        if not os.path.exists(backup_file):
            messagebox.showerror("错误", "文件丢失", parent=self)
            return
        def async_restore():
            try:
                with open(backup_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.app.data = data
                self.app.save_data()
                self.app.update_stats()
                self.app.log_action("从还原点恢复", name)
                self.after(0, lambda: messagebox.showinfo("成功", f"已从 {name} 恢复", parent=self))
                self.after(0, self.display_welcome)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("错误", f"恢复失败: {e}", parent=self))
        threading.Thread(target=async_restore, daemon=True).start()

    def _edit_restore(self):
        # 先不检查权限，允许进入选择对话框
        current_tid = self.current_tab_id
        if current_tid is None or current_tid not in self.tabs:
            return
        frame = self.tabs[current_tid]['content_frame']
        if not hasattr(frame, 'restore_listbox'):
            messagebox.showinfo("提示", "请切换到还原点标签页", parent=self)
            return
        listbox = frame.restore_listbox
        selection = listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请选择还原点", parent=self)
            return
        name = listbox.get(selection[0])

        # 弹出选择：是=删除，否=重命名
        choice = messagebox.askquestion("编辑", f"删除 {name}？\n点击“是”删除，“否”重命名", parent=self)
        if choice == 'yes':
            # 删除操作：需要 restore_delete 权限
            if not self._check_permission("restore_delete"):
                return
            if messagebox.askyesno("确认删除", f"删除 {name}？", parent=self):
                backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                self.app.restore_points.remove(name)
                self.app.log_action("删除还原点", name)
                messagebox.showinfo("成功", f"已删除 {name}", parent=self)
                self._refresh_restore_list()
        else:
            # 重命名操作：需要 add_restore 权限（管理员拥有）
            if not self._check_permission("add_restore"):
                return
            top = tk.Toplevel(self)
            top.title("重命名还原点")
            top.geometry("320x130")
            top.transient(self)
            top.grab_set()
            tk.Label(top, text="新名称:", font=('微软雅黑', 10)).pack(pady=10)
            entry = tk.Entry(top, width=20, font=('微软雅黑', 10))
            entry.pack(pady=5)
            def do_rename():
                new_name = entry.get().strip()
                if not new_name:
                    messagebox.showwarning("提示", "请输入新名称", parent=top)
                    return
                if re.search(r'[<>:"/\\|?*]', new_name):
                    messagebox.showerror("错误", "名称非法", parent=top)
                    return
                if new_name in self.app.restore_points:
                    messagebox.showerror("错误", "名称已存在", parent=top)
                    return
                old_file = os.path.join(RESTORE_DIR, f"{name}.json")
                new_file = os.path.join(RESTORE_DIR, f"{new_name}.json")
                def async_rename():
                    try:
                        os.rename(old_file, new_file)
                        self.app.restore_points = [new_name if x == name else x for x in self.app.restore_points]
                        self.app.log_action("重命名还原点", f"{name} -> {new_name}")
                        self.after(0, lambda: messagebox.showinfo("成功", f"已重命名为 {new_name}", parent=self))
                        self.after(0, self._refresh_restore_list)
                    except Exception as e:
                        self.after(0, lambda: messagebox.showerror("错误", f"重命名失败: {e}", parent=self))
                    top.destroy()
                threading.Thread(target=async_rename, daemon=True).start()
            tk.Button(top, text="确认", command=do_rename, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _format_restore(self):
        if not self._check_permission("restore_format"):
            return
        if not messagebox.askyesno("确认", "删除所有还原点？", parent=self):
            return
        def async_format():
            try:
                for f in os.listdir(RESTORE_DIR):
                    if f.endswith('.json'):
                        os.remove(os.path.join(RESTORE_DIR, f))
                self.app.restore_points = []
                self.app.log_action("格式化所有还原点")
                self.after(0, lambda: messagebox.showinfo("成功", "已删除所有还原点", parent=self))
                self.after(0, self._refresh_restore_list)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("错误", f"格式化失败: {e}", parent=self))
        threading.Thread(target=async_format, daemon=True).start()

    # ====== 车站大屏 ======
    def open_station_screen_tab(self):
        """打开车站大屏标签页"""
        frame = self.build_station_screen_frame()
        self.add_tab("车站大屏", frame, closable=True)

    def build_station_screen_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)

        # 顶部操作栏
        top_frame = tk.Frame(frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)

        tk.Label(top_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_station = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry_station.pack(side=tk.LEFT, padx=5)

        tk.Label(top_frame, text="方向:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        # 下拉框显示中文，默认“出发”
        kind_var = tk.StringVar(value="出发")
        kind_combo = ttk.Combobox(top_frame, textvariable=kind_var, values=["出发", "到达"], width=10, state="readonly")
        kind_combo.pack(side=tk.LEFT, padx=5)

        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        # 表格显示区
        result_frame = tk.Frame(frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 定义表格列
        columns = ('车次', '始发站', '终点站', '图定时间', '大屏状态', '检票口/出站口', '附加信息')
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        tree = ttk.Treeview(result_frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=120)
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # ---- 双击车次打开车次详情 ----
        def on_train_double_click(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            values = tree.item(item, 'values')
            if not values or len(values) < 1:
                return
            train_display = values[0]
            if not train_display:
                return
            # 如果是合并组显示（如 K973/K976），取第一个
            train_num = str(train_display).split('/')[0].strip()
            if train_num:
                self._open_train_detail_tab(train_num)

        tree.bind("<Double-1>", on_train_double_click)

        def do_query():
            # 清空表格
            for item in tree.get_children():
                tree.delete(item)
            station = entry_station.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return

            kind_display = kind_var.get()
            self.app.log_action("查询车站大屏", f"车站: {station}, 方向: {kind_display}")
            
            telecode = self.app.get_telecode(station)
            if not telecode:
                messagebox.showerror("错误", f"未找到车站 '{station}' 的电报码", parent=self)
                return
            kind_display = kind_var.get()
            kind_map = {"出发": "departure", "到达": "arrival"}
            kind = kind_map.get(kind_display, "departure")
            api_config = self.app.config.get('api', {})
            api_url = api_config.get('v2_base', 'https://rg-api.zenglingkun.cn/api/v2') + "/getStationBigScreen"
            try:
                params = {"stationTelecode": telecode, "kind": kind}
                resp = requests.get(api_url, params=params, timeout=5)
                if resp.status_code != 200:
                    messagebox.showerror("错误", f"请求失败，状态码 {resp.status_code}", parent=self)
                    return
                data = resp.json()
                if not data.get('success'):
                    messagebox.showerror("错误", f"接口返回失败: {data.get('msg', '')}", parent=self)
                    return
                items = data.get('data', [])
                if not items:
                    messagebox.showinfo("提示", "该站无客运列车停靠", parent=self)
                    return
                for item in items:
                    train_num = item.get('trainNum', '')
                    start_station = item.get('trainStartStation', '')
                    end_station = item.get('trainEndStation', '')
                    time_str = item.get('time', '')
                    status_code = item.get('bigScreenStatusCode', '')
                    status_text = item.get('bigScreenStatus', '')
                    ports = item.get('bigScreenPort', [])
                    port_str = '/'.join(ports) if ports else '--'
                    delay = item.get('timeDelay', 0)
                    extra = ''
                    if delay > 0:
                        if status_code == 'DELAY':
                            extra = f"晚点{delay}分钟"
                        elif status_code == 'EARLY':
                            extra = f"提前{delay}分钟"
                    tree.insert('', 'end', values=(train_num, start_station, end_station, time_str, status_text, port_str, extra))
            except Exception as e:
                messagebox.showerror("错误", f"请求异常: {e}", parent=self)

        btn.config(command=do_query)
        entry_station.bind('<Return>', lambda e: do_query())

        return frame

    # ====== 导航按钮方法 ======
    def open_home_tab(self):
        frame = self.build_home_frame()
        self.add_tab("主页", frame, closable=True)

    def open_edit_tab(self):
        # 仅ROOT可进入
        if not self.app.is_root:
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        frame = self.build_edit_frame()
        self.add_tab("编辑", frame, closable=True)

    def open_view_tab(self):
        frame = self.build_view_frame()
        self.add_tab("查看", frame, closable=True)

    def open_query_tab(self):
        frame = self.build_query_frame()
        self.add_tab("查询", frame, closable=True)

    def open_privilege_tab(self):
        frame = self.build_privilege_frame()
        self.add_tab("提权", frame, closable=True)

    def open_settings_tab(self):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        frame = self.build_settings_frame()
        self.add_tab("设置", frame, closable=True)

    def open_log_tab(self):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        frame = self.build_log_frame()
        self.add_tab("日志", frame, closable=True)

    def open_restore_tab(self):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return
        frame = self.build_restore_frame()
        self.add_tab("还原点", frame, closable=True)

    def update_edit_permission(self):
        for tid, data in self.tabs.items():
            if data['title'] == "编辑":
                frame = data['content_frame']
                if hasattr(frame, 'status_label'):
                    if self.app.is_admin or self.app.is_root:
                        frame.status_label.config(text="当前身份：管理员（可编辑）", fg='green')
                    else:
                        frame.status_label.config(text="当前身份：普通用户（需要管理员权限）", fg='red')

# ================== 启动入口 ==================
if __name__ == "__main__":
    root = MainWindow()
    root.mainloop()