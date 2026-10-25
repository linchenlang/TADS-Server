# -*- coding: utf-8 -*-
"""
TADS 列车数据与查询服务系统客户端
作者：Jason Michael

TADS（Train Arrival & Departure Schedule）列车到发时刻数据中心客户端
基于 Python + Tkinter 构建，通过 HTTP API 连接服务器，提供列车时刻数据的实时查询和展示

================================================================================
【核心功能】
================================================================================

一、双模式查询（一键切换）
    - 本地模式：通过内网 API 获取服务器本地完整数据
    - API 模式：通过内网服务器代理获取外部 V1/V2 实时数据
    - 切换后自动刷新当前查询结果

二、实时正晚点查询（V2 接口）
    - 调用 V2 接口获取列车实时正晚点数据
    - 显示晚点/提前分钟数，标注是否已过该站
    - 支持显示"预计正点"、"预计晚点"等预测状态
    - 正晚点数据与车次停站同步显示

三、列车详细查询
    - 车次停站数量：快速查看车次停靠站数
    - 车次全部经停详情：完整显示所有停站，包含：
      • 站名、到达、出发、跨天
      • 本站车次（列车在该站的实时车次号）
      • 站台（实时查询）
      • 检票口（实时查询）
      • 出站口（实时查询）
      • 正晚点状态（实时查询）

四、车站大屏（V2 接口）
    - 实时获取车站大屏数据（出发/到达）
    - 显示车次、始发站、终点站、图定时间、大屏状态
    - 显示检票口/出站口信息
    - 显示晚点/提前附加信息

五、站点时刻表（含上一班/下一班）
    - 显示当前时间
    - 自动计算上一班车和下一班车（含昨日/次日标记）
    - 按时间排序显示所有经过车次
    - 支持正晚点调整显示

六、两站间今日列车运行
    - 查询两站间所有车次及运行状态
    - 显示发车/到达时间、历时、状态
    - 支持正晚点显示
    - 自动计算"刚过掉"和"马上进入"的车次

七、车站↔车次双向查询
    - 车次 → 始发/终点
    - 起始站 → 所有始发车次（含终点、出发时间、类型）
    - 起点+终点 → 车次（含正晚点）

八、车次当前理论位置
    - 基于实际时刻表定位列车当前位置
    - 显示当前所在区间或停靠站
    - 支持正晚点偏移计算
    - 显示距离发车/到达剩余时间

九、列车组图片展示
    - 查看列车车厢分布图
    - 车厢图片双击放大查看
    - 显示列车参数（车型、车号等）
    - 支持多车厢图片横向/纵向滚动

十、列车信息展示
    - 显示列车完整信息：车次、类型、复车次、路局、车型、配属、担当、运行时长
    - 显示完整停站列表
    - 显示本站车次、站台、检票口、出站口、正晚点状态

十一、物理密钥认证系统（PN532 NFC 读卡器）
    - 管理员 M1 卡（4字节 UID）验证
    - ROOT NTAG215 卡（7字节 UID + Ed25519 签名）验证
    - 与服务器端安全机制完全对齐
    - 成熟的完全自研PN532驱动

十二、权限体系（与服务器端一致）
    - ROOT：全权（所有功能）
    - 管理员：固定权限（新增车次、录入停站、添加还原点、导出日志、查看配置、更改管理员密码、更新数据），不含任何删除、更改配置操作
    - 开发者：保留用于身份辨识
    - 普通用户：仅查询功能

十三、提权管理
    - Windows administrator（操作系统管理员）
    - TADS Administrator（密码 + M1 卡物理密钥）
    - TADS Developer（密码）
    - TADS Root（密码 + NTAG215 卡物理密钥）

十四、内网 API 代理
    - 所有外部 API 调用均通过服务器代理
    - 避免跨域问题
    - 统一管理 API 密钥和认证
    - 支持 V1 和 V2 接口

================================================================================
【技术架构】
================================================================================

- Python 3.8+
- Tkinter（GUI 界面）
- requests（HTTP 客户端）
- PySerial（串口通信）
- cryptography（Ed25519 签名验证）
- PN532（NFC 读写）

================================================================================
【数据来源】
================================================================================

- 本地模式：通过内网 API（/api/station/{name}/trains）获取服务器本地完整数据
- API 模式：通过内网服务器代理获取外部 V1/V2 实时数据
- 客户端本地不存储任何数据（除自身配置文件外）
- 所有数据均实时从服务器获取

================================================================================
【安全机制】
================================================================================

- 管理员认证：密码 + M1 卡物理密钥双重验证
- ROOT 认证：密码 + NTAG215 卡物理密钥双重认证
- 所有认证操作在本地完成
- 与服务器端安全机制完全对齐
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
try:
    _feat = _compat_probe()
    _mode = _compat_apply(_feat)
    # _compat_toast(f"已使用启动方式：{_mode}", duration=5)
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
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature
from typing import Dict, Optional, List, Any

# ================== 客户端本地配置（可被设置界面修改） ==================
APP_CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'TADS', 'Client')
if not os.path.exists(APP_CONFIG_DIR):
    os.makedirs(APP_CONFIG_DIR)
CLIENT_CONFIG_FILE = os.path.join(APP_CONFIG_DIR, "client_config.json")

DEFAULT_SERVER_IP = "192.168.100.101"
DEFAULT_SERVER_PORT = 10076
DEFAULT_COM_PORT = "COM3"
DEFAULT_BAUDRATE = 115200

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

def test_port_silent(host='localhost', port=10045, timeout=0.2):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

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

def get_hub_count():
    try:
        output = subprocess.check_output("netstat -an", shell=True, encoding='gbk')
        return len([line for line in output.splitlines() if ':10045' in line])
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

# ================== 客户端配置管理 ==================
class ClientConfig:
    """管理客户端本地配置（存储于 %APPDATA%\TADS\Client\client_config.json）"""
    def __init__(self):
        app_config_dir = os.path.join(os.getenv('APPDATA'), 'TADS', 'Client')
        if not os.path.exists(app_config_dir):
            os.makedirs(app_config_dir)
        self.config_file = os.path.join(app_config_dir, 'client_config.json')
        self.config = {}
        self.load()

    def load(self):
        if os.path.exists(CLIENT_CONFIG_FILE):
            try:
                with open(CLIENT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except:
                self.config = {}
        else:
            self.config = {}
        self._ensure_defaults()

    def _ensure_defaults(self):
        if 'server_ip' not in self.config:
            self.config['server_ip'] = DEFAULT_SERVER_IP
        if 'server_port' not in self.config:
            self.config['server_port'] = DEFAULT_SERVER_PORT
        if 'com_port' not in self.config:
            self.config['com_port'] = DEFAULT_COM_PORT
        if 'baudrate' not in self.config:
            self.config['baudrate'] = DEFAULT_BAUDRATE
        self.save()

    def save(self):
        try:
            with open(CLIENT_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存客户端配置失败: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()

    def get_api_base(self):
        return f"http://{self.config.get('server_ip', DEFAULT_SERVER_IP)}:{self.config.get('server_port', DEFAULT_SERVER_PORT)}"

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

        # ★★★ 客户端底层不再做盲扫，交由 UI 层的 _connect_pn532_with_selection 决定端口
        if auto or port is None or (isinstance(port, str) and port.lower() == "auto"):
            if isinstance(self.port, str) and self.port.lower() == "auto":
                self.port = "COM4"
                
        # 执行初始化
        if self.port:
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
        """重新连接PN532，不再自动扫描"""
        if port:
            self.port = port
        if baudrate:
            self.baudrate = baudrate
            
        if not self.port or (isinstance(self.port, str) and self.port.lower() == "auto"):
            return False
            
        self._init_reader()
        return self._connected

    def check_connection(self):
        """独立检测设备连接状态，通过发送空命令测试"""
        try:
            if not self.ser or not self.ser.is_open:
                return False
            import time
            self.ser.write(b'')
            self.ser.timeout = 0.1
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

    def list_ports(self):
        return [port.device for port in serial.tools.list_ports.comports()]

    # 以下两个方法是为了兼容原有接口（你的系统里可能没有调用，但保留以免报错）
    def read_ntag_uid_and_signature(self):
        return None, None

    def write_ntag_signature(self, signature_bytes):
        return False

# ================== 客户端应用类 ==================
class TADSClient:
    def __init__(self):
        # 加载本地配置
        self.client_config = ClientConfig()
        self.api_base = self.client_config.get_api_base()
        
        self.current_identity = "普通用户"
        self.is_admin = False
        self.is_developer = False
        self.is_root = False
        self.api_password = None
        # ===== 客户端 Token（持久化到 client_config.json） =====
        self.api_token = None
        self._load_token_from_config()
        self.data = None
        self.restore_points = []
        self.stats = None
        self.current_page = "主界面"
        self.api_available = False
        self._loading_data = False
        self._physical_key_present = False
        self._physical_key_update_stop = False

        self._telecode_cache = {}
        self._telecode_loaded = False
        self.use_api_query = True   # 改为 True，默认开启 API 实时查询

        # 获取服务器配置（COM口、公钥等）
        self.com_port = self.client_config.get('com_port', DEFAULT_COM_PORT)
        self.baudrate = self.client_config.get('baudrate', DEFAULT_BAUDRATE)
        self.root_public_key_b64 = None
        self.admin_uids = []
        self.root_uids = []
        self.admin_password_hash = ''
        self.root_password_hash = ''
        self.pn532 = None
        # self._fetch_server_config()
        # 初始化读卡器
        # self.pn532 = PN532Reader(
        #     port=self.com_port,
        #     baudrate=self.baudrate,
        #     auto=True
        # )
        # ★★★ 读卡器连接完全交由 MainWindow._initial_pn532_connect 处理，避免启动阻塞和盲目扫描

        # ====== 新增：自动更新配置 ======
        self.auto_update_on_query = self.client_config.get('auto_update_on_query', False)

        # ====== 新增：客户端日志初始化 ======
        self.log_file = os.path.join(APP_CONFIG_DIR, "operations.log")
        log_dir = os.path.dirname(self.log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # ====== 新增：配置版本监控相关属性 ======
        self.config_version_at_login = None
        self._version_monitor_thread = None
        self._version_monitor_stop = False
        self.main_window = None

        # 启动后台更新
        # threading.Thread(target=self._load_initial_data, daemon=True).start()
        # threading.Thread(target=self._physical_key_updater, daemon=True).start()

    def _get_network_key(self):
        """基于服务器拉取的 root_password_hash 动态派生网络加密密钥（带内存缓存，防狂转）"""
        # 如果已经算过了，直接返回，绝不再算第二次
        if hasattr(self, '_cached_network_key') and self._cached_network_key:
            return self._cached_network_key

        root_hash = getattr(self, 'root_password_hash', '')
        if not root_hash:
            try:
                # 拉取配置（明文接口）
                resp = requests.get(f"{self.api_base}/api/client_config", timeout=3)
                if resp.status_code == 200:
                    data = resp.json()
                    self.root_password_hash = data.get('root_password_hash', '')
                    root_hash = self.root_password_hash
            except Exception:
                pass
        
        if not root_hash:
            return None
            
        salt = b"TADS_NETWORK_SALT_v1"
        # 算一次，然后存入内存缓存
        self._cached_network_key = hashlib.pbkdf2_hmac('sha256', root_hash.encode('utf-8'), salt, 100000, 32)
        return self._cached_network_key

    def _request(self, method, url, **kwargs):
        """全局加密请求代理（自动处理加解密），兼容明文"""
        key = self._get_network_key()
        if not key:
            return requests.request(method, url, **kwargs)
            
        try:
            aesgcm = AESGCM(key)
            
            # 1. 加密请求体
            if 'json' in kwargs and kwargs['json'] is not None:
                plaintext = json.dumps(kwargs['json']).encode('utf-8')
                nonce = os.urandom(12)
                ciphertext = aesgcm.encrypt(nonce, plaintext, None)
                encrypted_b64 = base64.b64encode(nonce + ciphertext).decode('utf-8')
                kwargs['json'] = {"encrypted_payload": encrypted_b64}
                
            # 2. 发送请求
            resp = requests.request(method, url, **kwargs)
            
            # 3. 自动解密响应（排除 client_config 接口）
            if resp.headers.get('Content-Type', '').startswith('application/json') and '/api/client_config' not in url:
                try:
                    data = resp.json()
                    if isinstance(data, dict) and 'encrypted_payload' in data:
                        encrypted_data = base64.b64decode(data['encrypted_payload'])
                        nonce = encrypted_data[:12]
                        ciphertext = encrypted_data[12:]
                        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, None)
                        resp._content = decrypted_bytes
                except Exception:
                    pass
                    
            return resp
        except Exception:
            return requests.request(method, url, **kwargs)

    def _check_401_and_logout(self, resp):
        """检查请求是否 401 且未在注销中，若是则触发强制下线"""
        if getattr(resp, 'status_code', 0) == 401:
            if not getattr(self, '_is_logging_out', False):
                self._is_logging_out = True
                self.log_action("Token 失效", "收到服务器 401，自动强制下线")
                self._force_logout()
            return True
        return False

    def discover_server(self):
        """通过 UDP 广播自动发现局域网内的 TADS 服务器，并更新配置。"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(2.0)  # 等待 2 秒
            
            # 同时向全局广播和本机（方便本机测试）发送
            sock.sendto(b'TADS_DISCOVER', ('255.255.255.255', 10077))
            sock.sendto(b'TADS_DISCOVER', ('127.0.0.1', 10077))
            
            try:
                data, addr = sock.recvfrom(1024)
                decoded = data.decode('utf-8')
                if decoded.startswith('TADS_SERVER|'):
                    parts = decoded.split('|')
                    if len(parts) == 3:
                        server_ip = parts[1]
                        server_port = int(parts[2])
                        
                        old_ip = self.client_config.get('server_ip', DEFAULT_SERVER_IP)
                        old_port = self.client_config.get('server_port', DEFAULT_SERVER_PORT)
                        
                        if server_ip != old_ip or server_port != old_port:
                            self.client_config.set('server_ip', server_ip)
                            self.client_config.set('server_port', server_port)
                            self.api_base = self.client_config.get_api_base()
                            self.log_action("自动发现", f"自动更新服务器地址: {server_ip}:{server_port}")
                            return True, f"已自动切换至新服务器: {server_ip}:{server_port}"
                        
                        self.log_action("自动发现", f"服务器地址未变化: {server_ip}:{server_port}")
                        return True, f"服务器地址验证成功: {server_ip}"
            except socket.timeout:
                self.log_action("自动发现", "局域网内未响应 UDP 广播")
            finally:
                sock.close()
        except Exception as e:
            self.log_action("自动发现", f"UDP 广播异常: {e}")
            
        return False, "未发现局域网服务器（可能被防火墙拦截）"

    def set_main_window(self, window):
        """设置主窗口引用"""
        self.main_window = window

    def _api_headers(self):
        headers = {}
        if self.api_token:
            headers['X-TADS-Token'] = self.api_token
        return headers

    def _save_token_to_config(self):
        """把 api_token + identity + password 加密后写入 client_config.json"""
        try:
            payload = {
                'token': self.api_token or '',
                'identity': self.current_identity or '',
                'password': self.api_password or ''
            }
            if not payload['token']:
                self.client_config.set('api_token_enc', '')
                self.client_config.set('api_token', '')
                self.client_config.set('api_identity', '')
                return
            raw = json.dumps(payload).encode('utf-8')
            enc = dpapi_encrypt(raw)
            if enc:
                self.client_config.set('api_token_enc', base64.b64encode(enc).decode('ascii'))
                self.client_config.set('api_token', '')
                self.client_config.set('api_identity', '')
            else:
                self.client_config.set('api_token', payload['token'])
                self.client_config.set('api_identity', payload['identity'])
                self.client_config.set('api_token_enc', '')
        except Exception:
            pass

    def _load_token_from_config(self):
        """启动时加载 token 和密码；优先读加密字段"""
        self._is_logging_out = False
        try:
            enc_b64 = self.client_config.get('api_token_enc', '') or ''
            if enc_b64:
                try:
                    blob = base64.b64decode(enc_b64)
                    plain = dpapi_decrypt(blob)
                    if plain:
                        d = json.loads(plain.decode('utf-8'))
                        token = d.get('token', '') or ''
                        identity = d.get('identity', '') or ''
                        password = d.get('password', '') or ''
                        if token and identity:
                            self.api_token = token
                            self.current_identity = identity
                            self.api_password = password  # ★ 恢复密码
                            self.is_root = (identity == "TADS Root")
                            self.is_admin = (identity in ("TADS Administrator", "TADS Root"))
                            self.is_developer = (identity == "TADS Developer")
                            return
                except Exception:
                    pass
                self.api_token = None
                self._save_token_to_config()
                return

            # 迁移旧版明文（旧版没有存密码，所以迁移后密码为空）
            legacy_token = self.client_config.get('api_token', '') or ''
            legacy_identity = self.client_config.get('api_identity', '') or ''
            if legacy_token and legacy_identity:
                self.api_token = legacy_token
                self.current_identity = legacy_identity
                self.api_password = None
                self.is_root = (legacy_identity == "TADS Root")
                self.is_admin = (legacy_identity in ("TADS Administrator", "TADS Root"))
                self.is_developer = (legacy_identity == "TADS Developer")
                self._save_token_to_config()
        except Exception:
            self.api_token = None

    def _clear_token(self):
        self.api_token = None
        self._is_logging_out = False
        try:
            self.client_config.set('api_token', '')
            self.client_config.set('api_identity', '')
            self.client_config.set('api_token_enc', '')
        except Exception:
            pass

    def _get_config_version(self):
        """从服务器获取 config_version"""
        try:
            resp = self._request('GET', f"{self.api_base}/api/client_config", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('config_version', 0)
        except:
            pass
        return 0

    def _start_config_version_monitor(self):
        """启动 Token 活性监控（只负责探测 Token 是否被服务器端踢掉）"""
        self.log_action("启动 Token 活性监控", f"身份: {self.current_identity}")
        
        self._version_monitor_stop = True
        if self._version_monitor_thread is not None:
            try:
                self._version_monitor_thread.join(timeout=0.5)
            except:
                pass
            self._version_monitor_thread = None
        
        if not (self.is_admin or self.is_root or self.is_developer):
            self.log_action("监控未启动", "当前身份无需监控")
            return
            
        self._version_monitor_stop = False
        self._version_monitor_thread = threading.Thread(
            target=self._monitor_config_version,
            daemon=True
        )
        self._version_monitor_thread.start()

    def _monitor_config_version(self):
        """每 5 秒发一次带 Token 的请求，只要被撤销（401）就立刻强制下线"""
        while not self._version_monitor_stop:
            time.sleep(5)
            try:
                if not (self.is_admin or self.is_root or self.is_developer):
                    continue
                
                if not self.api_token:
                    continue
                    
                # 探测接口：只要服务器端撤销了 Token，这里必定返回 401
                resp = self._request('GET', f"{self.api_base}/api/logs",
                                    params={"lines": 1},
                                    headers=self._api_headers(),
                                    timeout=5)
                
                if resp.status_code == 401:
                    self.log_action("Token 失效", "收到 401，自动强制下线")
                    if self.main_window:
                        self.main_window.after(0, self.main_window._do_force_logout)
                    break
                    
            except Exception:
                pass # 网络波动忽略

    def _force_logout(self):
        """强制退出登录（由版本号变更或 Token 失效触发，一般由主线程外部调用）"""
        self.log_action("强制退出登录", "检测到配置版本变更或 Token 失效")
        
        # 停止监控线程 (如果在主线程中调用，可以 safely join)
        self._version_monitor_stop = True
        if self._version_monitor_thread:
            if threading.current_thread() != self._version_monitor_thread:
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
        self.api_password = None
        self.config_version_at_login = None
        self._clear_token()
        
        if self.main_window:
            self.main_window.after(0, self.main_window._do_force_logout)

    def get_auto_update_setting(self):
        return self.auto_update_on_query

    def set_auto_update_setting(self, enabled):
        self.auto_update_on_query = enabled
        self.client_config.set('auto_update_on_query', enabled)
        self.log_action("切换自动更新", f"状态: {'开启' if enabled else '关闭'}")

    def log_action(self, action, detail=""):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        identity = self.current_identity
        msg = f"[{timestamp}] [{identity}] {action}"
        if detail:
            msg += f" – {detail}"
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(msg + "\n")
        except:
            pass

    def batch_import_train(self, train_number, api_type="V2", password=None, auto_update=False):
        if not self.api_token:
            return False, "未登录，请先提权"
        data = {"train_number": train_number, "api_type": api_type, "auto_update": auto_update}
        try:
            resp = self._request('POST', f"{self.api_base}/api/admin/batch_import", json=data,
                                 headers=self._api_headers(), timeout=60)
            if resp.status_code == 200:
                result = resp.json()
                return result.get('success', False), result.get('message', '')
            else:
                return False, f"服务器错误 (HTTP {resp.status_code})"
        except Exception as e:
            return False, f"网络异常: {e}"

    def check_pn532_connection(self):
        """独立检测PN532连接状态"""
        if not self.pn532:
            return False
        try:
            return self.pn532.check_connection()
        except:
            return False

    def _fetch_server_config(self):
        """从服务器获取配置（公钥、推荐COM口、管理员/ROOT UID列表、密码哈希等）"""
        try:
            resp = requests.get(f"{self.api_base}/api/client_config", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                server_com = data.get('com_port')
                if server_com and self.client_config.get('com_port') == DEFAULT_COM_PORT:
                    self.com_port = server_com
                self.baudrate = data.get('baudrate', DEFAULT_BAUDRATE)
                self.root_public_key_b64 = data.get('root_public_key')
                self.admin_uids = data.get('admin_uids', [])
                self.root_uids = data.get('root_uids', [])
                self.admin_password_hash = data.get('admin_password_hash', '')
                self.root_password_hash = data.get('root_password_hash', '')
                # 保存 config_version 到客户端配置
                config_version = data.get('config_version', 0)
                self.client_config.set('config_version', config_version)
        except:
            pass

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
            if uid and uid in self.admin_uids:
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
            if uid and uid in self.root_uids:
                return True, uid
            time.sleep(0.2)
        return False, None

    def verify_developer(self, password, username):
        """开发者身份验证（用户名 + 密码，不读卡）"""
        self.log_action("开始开发者验证", f"用户名: {username}")
        username = (username or "").strip()
        if not username:
            self.log_action("开发者验证失败", "用户名为空")
            return False, "请输入用户名"
        try:
            resp = self._request('POST', 
                f"{self.api_base}/api/auth/login",
                json={"password": password, "username": username},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    identity = data.get('identity', '')
                    if identity != "TADS Developer":
                        self.log_action("开发者验证异常", f"服务器返回身份: {identity}")
                        return False, "身份异常"
                    self.api_token = data.get('token', '')
                    self.current_identity = identity
                    self.is_developer = True
                    self.is_admin = False
                    self.is_root = False
                    self.api_password = password
                    self._is_logging_out = False
                    self._save_token_to_config()

                    try:
                        self.config_version_at_login = self._get_config_version()
                        self._start_config_version_monitor()
                    except Exception:
                        pass

                    self.log_action("开发者验证通过", f"用户名: {username}")
                    return True, "验证通过"
                else:
                    self.log_action("开发者验证失败", data.get('error', '未知错误'))
                    return False, "用户名或密码错误"
            else:
                self.log_action("开发者验证失败", f"HTTP {resp.status_code}")
                return False, "用户名或密码错误"
        except Exception as e:
            self.log_action("开发者验证失败", f"网络异常: {e}")
            return False, f"网络异常: {e}"

    def verify_admin(self, password):
        self.log_action("开始管理员验证", "")
        if not self.pn532:
            return False, "读卡器未初始化"

        card_uid = self._wait_for_card_uid()
        if not card_uid:
            return False, "读卡超时，请确保已将物理密钥放在读卡器上"

        try:
            resp = self._request('POST', 
                f"{self.api_base}/api/auth/login",
                json={"password": password, "card_uid": card_uid},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    identity = data.get('identity', '')
                    self.api_token = data.get('token', '')
                    self.current_identity = identity
                    self.is_root = (identity == "TADS Root")
                    self.is_admin = (identity in ("TADS Administrator", "TADS Root"))
                    self.is_developer = (identity == "TADS Developer")
                    self.api_password = password
                    self._is_logging_out = False
                    self._save_token_to_config()
                    
                    try:
                        self.config_version_at_login = self._get_config_version()
                        self._start_config_version_monitor()
                    except Exception:
                        pass
                        
                    self.log_action("管理员验证通过", f"UID={card_uid} 身份={identity}")
                    return True, "验证通过"
                else:
                    return False, data.get('error', '服务器拒绝认证')
            else:
                return False, f"服务器错误 (HTTP {resp.status_code})"
        except Exception as e:
            return False, f"网络异常: {e}"

    def verify_root(self, password):
        self.log_action("开始 ROOT 验证", "")
        if not self.pn532:
            return False, "读卡器未初始化"

        card_uid = self._wait_for_card_uid()
        if not card_uid:
            return False, "读卡超时，请确保已将物理密钥放在读卡器上"

        try:
            resp = self._request('POST', 
                f"{self.api_base}/api/auth/login",
                json={"password": password, "card_uid": card_uid},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    identity = data.get('identity', '')
                    if identity != "TADS Root":
                        return False, f"该卡不是ROOT卡 (UID: {card_uid})"
                    self.api_token = data.get('token', '')
                    self.current_identity = identity
                    self.is_root = True
                    self.is_admin = True
                    self.is_developer = False
                    self.api_password = password
                    self._is_logging_out = False
                    self._save_token_to_config()
                    
                    try:
                        self.config_version_at_login = self._get_config_version()
                        self._start_config_version_monitor()
                    except Exception:
                        pass
                        
                    self.log_action("ROOT 验证通过", f"UID={card_uid}")
                    return True, "验证通过"
                else:
                    return False, data.get('error', '服务器拒绝认证')
            else:
                return False, f"服务器错误 (HTTP {resp.status_code})"
        except Exception as e:
            return False, f"网络异常: {e}"

    def _get_admin_password_hash(self):
        """从服务器获取最新的管理员密码哈希"""
        try:
            resp = self._request('GET', f"{self.api_base}/api/client_config", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('admin_password_hash', '')
        except Exception as e:
            self.write_error_log(f"获取管理员密码哈希失败: {e}")
        return ''

    def _get_root_password_hash(self):
        """从服务器获取最新的 ROOT 密码哈希"""
        try:
            resp = self._request('GET', f"{self.api_base}/api/client_config", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('root_password_hash', '')
        except Exception as e:
            self.write_error_log(f"获取 ROOT 密码哈希失败: {e}")
        return ''

    def _load_initial_data(self):
        """不再预加载数据"""
        pass

    def _physical_key_updater(self):
        while not self._physical_key_update_stop:
            # 只在提权时检测，此处不自动更新状态
            time.sleep(3)

    def load_data_from_api(self):
        """客户端切换到实时 API 模式，不缓存数据"""
        self.data = {"stations": [], "trains": []}
        self.stats = None
        print("✅ 客户端已切换为实时 API 模式")

    def update_stats_from_api(self):
        try:
            resp = self._request('GET', f"{self.api_base}/api/stats", timeout=5)
            if resp.status_code == 200:
                self.stats = resp.json()
            else:
                self.stats = None
        except:
            self.stats = None

    def update_restore_points_from_api(self):
        if not self.api_token:
            self.restore_points = []
            return
        try:
            resp = self._request('GET', f"{self.api_base}/api/admin/restore/list",
                                headers=self._api_headers(), timeout=10)
            if resp.status_code == 200:
                self.restore_points = resp.json()
            else:
                self.restore_points = []
        except Exception:
            self.restore_points = []

    def get_train(self, number):
        try:
            params = {}
            params["source"] = "api" if self.use_api_query else "local"
            resp = self._request('GET', f"{self.api_base}/api/train/{number}", params=params, timeout=10)
            
            # ★★★ 拦截 401
            if self._check_401_and_logout(resp):
                return {"success": False, "data": None, "error": "登录已过期，请重新提权", "error_type": "auth"}
                
            if resp.status_code == 200:
                result = resp.json()
                if "data" in result and result["data"] is not None:
                    v2_data = result["data"]
                    train_data = {
                        "display_name": result.get("display_name", number),
                        "numbers": result.get("numbers", [number]),
                        "timetable": v2_data.get("timetable", []),
                        "v2_data": v2_data,
                        "is_v2": True
                    }
                    return {"success": True, "data": train_data, "error": None, "error_type": None}
                else:
                    return {"success": True, "data": result, "error": None, "error_type": None}
            else:
                try:
                    err_data = resp.json()
                    error_msg = err_data.get("error", "未找到该车次")
                    error_type = err_data.get("error_type", "notfound")
                except:
                    error_msg = f"服务器错误 (HTTP {resp.status_code})"
                    error_type = "error"
                return {"success": False, "data": None, "error": error_msg, "error_type": error_type}
        except requests.exceptions.Timeout:
            return {"success": False, "data": None, "error": "请求超时，服务器无响应", "error_type": "timeout"}
        except Exception as e:
            return {"success": False, "data": None, "error": f"网络异常: {e}", "error_type": "error"}

    def get_station_id_by_name(self, name):
        """实时查询车站 ID（轻量缓存，仅本次运行）"""
        if not hasattr(self, '_station_cache'):
            try:
                resp = self._request('GET', f"{self.api_base}/api/stations", timeout=5)
                if resp.status_code == 200:
                    stations = resp.json()
                    self._station_cache = {s['name']: s['id'] for s in stations}
                else:
                    self._station_cache = {}
            except:
                self._station_cache = {}
        return self._station_cache.get(name)

    def get_station_name_by_id(self, sid):
        """实时查询车站名称（轻量缓存）"""
        if not hasattr(self, '_station_cache_id'):
            try:
                resp = self._request('GET', f"{self.api_base}/api/stations", timeout=5)
                if resp.status_code == 200:
                    stations = resp.json()
                    self._station_cache_id = {s['id']: s['name'] for s in stations}
                else:
                    self._station_cache_id = {}
            except:
                self._station_cache_id = {}
        return self._station_cache_id.get(sid)

    def search(self, keyword):
        try:
            resp = self._request('GET', f"{self.api_base}/api/search", params={"q": keyword}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                return []
        except:
            return []

    def _do_post(self, endpoint, data, password=None):
        if not self.api_token:
            return False, "未登录，请先提权"
        try:
            resp = self._request('POST', f"{self.api_base}{endpoint}", json=data,
                                 headers=self._api_headers(), timeout=30)
            # ★★★ 拦截 401
            if self._check_401_and_logout(resp):
                return False, "登录已过期，请重新提权"
                
            if resp.status_code == 200:
                return True, resp.json().get("message", "操作成功")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return False, f"服务器错误 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def add_train(self, number, password=None):
        success, msg = self._do_post("/api/admin/add_train", {"number": number}, password)
        if success:
            threading.Thread(target=self.load_data_from_api, daemon=True).start()
            self.update_stats_from_api()
        return success, msg

    def delete_train(self, number, password=None):
        success, msg = self._do_post("/api/admin/delete_train", {"number": number}, password)
        if success:
            threading.Thread(target=self.load_data_from_api, daemon=True).start()
            self.update_stats_from_api()
        return success, msg

    def add_stop(self, train_number, station_name, arrive, depart, day_offset, password=None):
        data = {
            "train_number": train_number,
            "station_name": station_name,
            "arrive": arrive,
            "depart": depart,
            "day_offset": day_offset
        }
        success, msg = self._do_post("/api/admin/add_stop", data, password)
        if success:
            threading.Thread(target=self.load_data_from_api, daemon=True).start()
            self.update_stats_from_api()
        return success, msg

    def delete_stop(self, train_number, index, password=None):
        data = {"train_number": train_number, "index": index}
        success, msg = self._do_post("/api/admin/delete_stop", data, password)
        if success:
            threading.Thread(target=self.load_data_from_api, daemon=True).start()
            self.update_stats_from_api()
        return success, msg

    def add_restore_point(self, name, password=None):
        success, msg = self._do_post("/api/admin/restore/add", {"name": name}, password)
        if success:
            self.update_restore_points_from_api()
        return success, msg

    def restore_from_point(self, name, password=None):
        success, msg = self._do_post("/api/admin/restore/apply", {"name": name}, password)
        if success:
            threading.Thread(target=self.load_data_from_api, daemon=True).start()
        return success, msg

    def delete_restore_point(self, name, password=None):
        success, msg = self._do_post("/api/admin/restore/delete", {"name": name}, password)
        if success:
            self.update_restore_points_from_api()
        return success, msg

    def format_restore_points(self, password=None):
        success, msg = self._do_post("/api/admin/restore/format", {}, password)
        if success:
            self.update_restore_points_from_api()
        return success, msg

    # 保留 update_train_data 方法，但UI已移除按钮，仅当其他地方调用时可用
    def update_train_data(self, password=None):
        if not self.api_token:
            return {"success": False, "error": "未登录，请先提权"}
        try:
            resp = self._request('POST', f"{self.api_base}/api/admin/update_data",
                                 json={}, headers=self._api_headers(), timeout=300)
            if resp.status_code == 200:
                threading.Thread(target=self.load_data_from_api, daemon=True).start()
                return resp.json()
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return {"success": False, "error": f"更新失败 (HTTP {resp.status_code}): {err}"}
        except Exception as e:
            return {"success": False, "error": f"网络异常: {e}"}

    def get_recent_logs(self, lines=30, password=None):
        if not self.api_token:
            return "未登录，请先提权"
        try:
            resp = self._request('GET', f"{self.api_base}/api/logs",
                                params={"lines": lines},
                                headers=self._api_headers(), timeout=10)
                                
            # ★★★ 拦截 401
            if self._check_401_and_logout(resp):
                return "登录已过期，请重新提权"
                
            if resp.status_code == 200:
                return resp.json().get("logs", "")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return f"获取日志失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return f"请求异常: {e}"

    def get_recent_error_logs(self, lines=300):
        if not self.api_token:
            return "未登录，请先提权"
        try:
            resp = self._request('GET', f"{self.api_base}/api/error_logs",
                                params={"lines": lines},
                                headers=self._api_headers(), timeout=10)
            if self._check_401_and_logout(resp):
                return "登录已过期，请重新提权"
            if resp.status_code == 200:
                return resp.json().get("logs", "")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return f"获取报错日志失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return f"请求异常: {e}"

    def export_logs(self, password=None):
        if not self.api_token:
            return None, "未登录，请先提权"
        try:
            resp = self._request('GET', f"{self.api_base}/api/export_logs",
                                headers=self._api_headers(), timeout=30)
            if resp.status_code == 200:
                return resp.content, None
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return None, f"导出失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return None, f"网络异常: {e}"

    def clear_logs(self, log_type='normal'):
        if not self.api_token:
            return False, "未登录，请先提权"
        try:
            # ★ 使用 params 放在 URL 里，彻底绕过 JSON 的加密和解密逻辑，绝不丢包
            resp = self._request('POST', f"{self.api_base}/api/admin/logs/clear",
                                 params={"log_type": log_type},
                                 headers=self._api_headers(), timeout=10)
            if self._check_401_and_logout(resp):
                return False, "登录已过期，请重新提权"
            if resp.status_code == 200:
                r = resp.json()
                return r.get("success", False), r.get("message", "") or r.get("error", "")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return False, f"清空失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def save_logs(self, log_type, content):
        if not self.api_token:
            return False, "未登录，请先提权"
        try:
            resp = self._request('POST', f"{self.api_base}/api/admin/logs/save",
                                 json={"log_type": log_type, "content": content},
                                 headers=self._api_headers(), timeout=15)
            if self._check_401_and_logout(resp):
                return False, "登录已过期，请重新提权"
            if resp.status_code == 200:
                r = resp.json()
                return r.get("success", False), r.get("message", "") or r.get("error", "")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return False, f"保存失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def change_admin_password(self, new_password, password=None):
        if not self.api_token:
            return False, "未登录，请先提权"
        try:
            resp = self._request('POST', f"{self.api_base}/api/admin/change_admin_pwd",
                                 json={"new_password": new_password},
                                 headers=self._api_headers(), timeout=10)
            if resp.status_code == 200:
                return True, resp.json().get("message", "密码已更改")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return False, f"更改失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def change_root_password(self, new_password, password=None):
        if not self.api_token:
            return False, "未登录，请先提权"
        try:
            resp = self._request('POST', f"{self.api_base}/api/admin/change_root_pwd",
                                 json={"new_password": new_password},
                                 headers=self._api_headers(), timeout=10)
            if resp.status_code == 200:
                return True, resp.json().get("message", "密码已更改")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return False, f"更改失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def get_physical_keys(self, password=None):
        if not self.api_token:
            return None, "未登录，请先提权"
        try:
            resp = self._request('GET', f"{self.api_base}/api/admin/physical_keys",
                                headers=self._api_headers(), timeout=10)
            if resp.status_code == 200:
                return resp.json(), None
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return None, f"获取失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return None, f"网络异常: {e}"

    def add_physical_key(self, key_data, password=None):
        if not self.api_token:
            return False, "未登录，请先提权"
        try:
            resp = self._request('POST', f"{self.api_base}/api/admin/physical_keys/add",
                                 json=key_data, headers=self._api_headers(), timeout=10)
            if resp.status_code == 200:
                return True, resp.json().get("message", "密钥已添加")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return False, f"添加失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def delete_physical_key(self, uid, password=None):
        if not self.api_token:
            return False, "未登录，请先提权"
        try:
            resp = self._request('POST', f"{self.api_base}/api/admin/physical_keys/delete",
                                 json={"uid": uid},
                                 headers=self._api_headers(), timeout=10)
            if resp.status_code == 200:
                return True, resp.json().get("message", "密钥已删除")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except Exception:
                    err = resp.text
                return False, f"删除失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def set_identity(self, identity, password=None):
        """设置身份，管理员/ROOT需要验证物理密钥"""
        if identity == "TADS Administrator":
            if password and verify_password(password, self.admin_password_hash):
                # 验证物理密钥（M1 UID）
                success, uid = self.verify_admin_card()
                if success:
                    self.is_admin = True
                    self.is_developer = False
                    self.is_root = False
                    self.current_identity = "TADS Administrator"
                    self.api_password = password
                    return True, "管理员身份已设置"
                else:
                    return False, "本地M1卡验证失败"
            else:
                return False, "密码错误或未设置管理员密码"
        elif identity == "TADS Developer":
            if password and verify_password(password, DEVELOPER_PASSWORD_HASH):
                self.is_developer = True
                self.is_admin = False
                self.is_root = False
                self.current_identity = "TADS Developer"
                self.api_password = password
                return True, "开发者身份已设置"
            else:
                return False, "开发者密码错误"
        elif identity == "TADS Root":
            if password and verify_password(password, self.root_password_hash):
                # 验证NTAG物理密钥
                uid, sig = self.pn532.read_ntag_uid_and_signature() if self.pn532 else (None, None)
                if uid and sig and self.root_public_key_b64:
                    try:
                        pub_key_bytes = base64.b64decode(self.root_public_key_b64)
                        pub_key = Ed25519PublicKey.from_public_bytes(pub_key_bytes)
                        pub_key.verify(sig, uid.encode('utf-8'))
                        self.is_root = True
                        self.is_admin = True
                        self.is_developer = False
                        self.current_identity = "TADS Root"
                        self.api_password = password
                        return True, "ROOT身份已设置"
                    except:
                        return False, "NTAG签名验证失败"
                else:
                    return False, "未检测到NTAG卡或公钥未获取"
            else:
                return False, "ROOT密码错误"
        else:
            self.is_admin = False
            self.is_developer = False
            self.is_root = False
            self.current_identity = "普通用户"
            self.api_password = None
            return True, "已切换为普通用户"

    def get_current_identity(self):
        return self.current_identity

    def log_action(self, action, detail=""):
        pass

    def _log_api_error(self, message):
        """仅在开启API实时查询时记录API相关错误到错误日志"""
        if self.use_api_query:
            self.write_error_log(message)

    def write_error_log(self, message):
        print(f"错误: {message}")
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window.after(0, lambda: self.main_window._show_cinematic_error("网络或请求异常", message))

    def get_api_base(self):
        return self.api_base

    def update_api_base(self, new_base):
        self.api_base = new_base

    def _get_uid_password_from_server(self, uid):
        """从服务器获取指定 UID 的专属密码（需已持有 token）"""
        uid = uid.upper()
        if not self.api_token:
            self.write_error_log("获取专属密码失败: 未登录")
            return ''
        try:
            resp = self._request('GET', f"{self.api_base}/api/admin/get_uid_password",
                                params={"uid": uid},
                                headers=self._api_headers(), timeout=10)
            if resp.status_code == 200:
                return resp.json().get('password', '')
            else:
                self.write_error_log(f"获取专属密码失败: HTTP {resp.status_code}")
                return ''
        except Exception as e:
            self.write_error_log(f"获取专属密码异常: {e}")
            return ''

    def _wait_for_card_uid(self, timeout=8.0):
        """等待卡片出现并返回 UID，超时返回 None（纯循环读卡，不加 reset 避免串口假死）"""
        if not self.pn532 or not self.pn532.ser:
            self.log_action("PN532 未连接", "无法读卡")
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
        self.log_action("读卡超时", f"{timeout}秒")
        return None

    def _get_admin_uids(self):
        """从服务器获取管理员 UID 列表"""
        try:
            resp = self._request('GET', f"{self.api_base}/api/client_config", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('admin_uids', [])
        except Exception as e:
            self.write_error_log(f"获取管理员 UID 列表失败: {e}")
        return []

    def _get_root_uids(self):
        """从服务器获取 ROOT UID 列表"""
        try:
            resp = self._request('GET', f"{self.api_base}/api/client_config", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('root_uids', [])
        except Exception as e:
            self.write_error_log(f"获取 ROOT UID 列表失败: {e}")
        return []

    # ---------- 正晚点获取函数（与服务器端一致） ----------
    def _get_train_delay(self, train_num, timeout=None):
        """调用服务器代理获取正晚点数据"""
        api_url = f"{self.api_base}/api/v2/getTrainDelayAll"
        try:
            params = {"trainNum": train_num}
            resp = self._request('GET', api_url, params=params, timeout=timeout or 10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data', [])
        except Exception as e:
            self._log_api_error(f"获取正晚点失败 {train_num}: {e}")
        return None

    def _adjust_time_str(self, time_str, minutes):
        """将时间字符串 'HH:MM' 调整 minutes 分钟，返回新字符串"""
        try:
            dt = datetime.datetime.strptime(time_str, '%H:%M')
            dt = dt + datetime.timedelta(minutes=minutes)
            return dt.strftime('%H:%M')
        except:
            return time_str

    # ---------- 新增：车站大屏获取 ----------
    def get_station_big_screen(self, station_telecode, kind):
        """通过服务器代理获取车站大屏数据"""
        api_url = f"{self.api_base}/api/v2/getStationBigScreen"
        try:
            params = {"stationTelecode": station_telecode, "kind": kind}
            resp = self._request('GET', api_url, params=params, timeout=5)
            if resp.status_code == 200:
                return resp.json()
            return None
        except Exception as e:
            self._log_api_error(f"获取大屏数据失败: {e}")
            return None

    # ---------- 新增：电报码映射（与服务器端一致） ----------
    def _load_telecode_map(self):
        """从服务器获取站名-电报码映射（服务器已从12306加载）"""
        try:
            # 先尝试从服务器获取
            resp = self._request('GET', f"{self.api_base}/api/v1/station/telecodes", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self._telecode_cache = data.get('telecodes', {})
                self._telecode_loaded = True
                print(f"✅ 已从服务器加载 {len(self._telecode_cache)} 个车站电报码")
                return
            else:
                print(f"⚠️ 从服务器获取电报码失败(HTTP {resp.status_code})，尝试从12306直接加载...")
        except Exception as e:
            print(f"⚠️ 加载电报码异常: {e}")
        
        # 备用方案：直接从12306加载
        self._load_telecode_from_12306()

    def _load_telecode_from_12306(self):
        """直接从12306官方接口加载站名-电报码映射（备用方案）"""
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
                    print(f"✅ 已从12306直接加载 {len(self._telecode_cache)} 个车站电报码")
                else:
                    print("⚠️ 未找到 station_names 数据")
                    self._telecode_loaded = False
            else:
                print(f"⚠️ 从12306获取电报码失败，状态码: {resp.status_code}")
                self._telecode_loaded = False
        except requests.exceptions.Timeout:
            self._telecode_loaded = False
            self.write_error_log("直接连接 12306 获取电报码超时")
            # ★ 通过主窗口弹窗提示
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.after(0, lambda: messagebox.showwarning(
                    "网络请求超时",
                    "无法连接至 12306 官方服务器获取车站电报码。\n部分涉及到“电报码”的功能（如车站大屏、站点时刻表等）可能无法正常使用。\n\n请检查当前电脑的外网连接状态。",
                    parent=self.main_window
                ))
        except Exception as e:
            self._telecode_loaded = False
            self.write_error_log(f"从12306加载电报码异常: {e}")
            print(f"⚠️ 从12306加载电报码异常: {e}")
            # ★ 其他网络错误（如无网络）也弹窗提示
            if hasattr(self, 'main_window') and self.main_window:
                self.main_window.after(0, lambda: messagebox.showerror(
                    "网络异常",
                    f"请求 12306 官方接口失败，可能无法使用车站大屏等功能。\n\n错误信息: {str(e)[:30]}",
                    parent=self.main_window
                ))

    def get_telecode(self, station_name):
        """获取站名对应的电报码，若未加载则同步加载"""
        if not self._telecode_loaded:
            self._load_telecode_map()
        return self._telecode_cache.get(station_name)

    # ---------- 新增：车次主数据 API ----------
    def _get_train_main(self, train_num, date=None):
        """调用服务器代理获取车次主数据"""
        api_url = f"{self.api_base}/api/v2/getTrainMain"
        try:
            params = {"trainNum": train_num}
            if date:
                params["date"] = date
            resp = self._request('GET', api_url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data')
        except Exception as e:
            self._log_api_error(f"获取车次主数据失败 {train_num}: {e}")
        return None

    def query_train_from_v2(self, train_number: str) -> tuple:
        """
        实时调用 V2 接口查询车次主数据（通过服务器代理）
        返回 (data, error_type, error_msg)
        """
        try:
            data = self._get_train_main(train_number)
            if data is not None:
                return data, 'success', ''
            else:
                return None, 'notfound', 'V2已重试，该车次未找到'
        except requests.exceptions.Timeout:
            return None, 'timeout', '未找到该车次，V2未重试'
        except Exception as e:
            self._log_api_error(f"V2 查询异常 {train_number}: {e}")
            return None, 'error', '未找到该车次，V2未重试'

    def get_merged_by_number(self, number):
        """获取车次的合并组信息（完全通过服务器 API 获取）"""
        result = self.get_train(number)
        if result.get("success"):
            train_data = result.get("data", {})
            display_name = train_data.get("display_name", number)
            numbers = train_data.get("numbers", [number])
            stops = train_data.get("stops", [])
            if not stops:
                stops = train_data.get("timetable", [])
            return {
                'display_name': display_name,
                'numbers': numbers,
                'representative': train_data,
                'stops': stops,
                'train_ids': []
            }
        return None

    # ====== V1 接口调用（新增） ======
    def _call_v1_station_query(self, telecode: str) -> Optional[Dict]:
        """通过服务器代理调用 V1 车站查询接口"""
        try:
            resp = self._request('GET', f"{self.api_base}/api/v1/station/query", params={"telecode": telecode}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self._log_api_error(f"V1 车站查询失败 {telecode}: {e}")
        return None

    def _call_v1_sts_query(self, from_telecode: str, to_telecode: str, date: str) -> Optional[List]:
        """通过服务器代理调用 V1 站到站车次查询接口"""
        try:
            resp = self._request('GET', f"{self.api_base}/api/v1/train/sts_query",
                                params={"from": from_telecode, "to": to_telecode, "date": date}, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self._log_api_error(f"V1 站到站查询失败: {e}")
        return None

    def get_trains_start_from(self, telecode: str) -> Optional[List]:
        """获取从某站始发的所有车次（通过 V1 车站查询接口）"""
        station_data = self._call_v1_station_query(telecode)
        if not station_data:
            return None
        trains = station_data.get('trains', [])
        # 筛选始发车次（indexStopThere == 0）
        start_trains = []
        for train in trains:
            if train.get('indexStopThere') == 0:
                start_trains.append(train)
        return start_trains

    def _get_train_exit(self, train_num: str, station_telecode: str, date: str = None) -> Optional[Dict]:
        """通过服务器代理获取检票口、站台、出站口信息"""
        api_url = f"{self.api_base}/api/v2/getExit"
        try:
            params = {"trainNum": train_num, "stationTelecode": station_telecode}
            if date:
                params["date"] = date
            resp = self._request('GET', api_url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data')
        except Exception as e:
            self._log_api_error(f"获取检票口失败 {train_num} {station_telecode}: {e}")
        return None

    def get_coach_pic(self, train_num: str) -> Optional[Dict]:
        """通过服务器代理获取列车车厢图"""
        api_url = f"{self.api_base}/api/v2/getCoachPic"
        try:
            resp = self._request('GET', api_url, params={"train": train_num}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data')
        except Exception as e:
            self._log_api_error(f"获取列车车厢图失败 {train_num}: {e}")
        return None

    def get_emu_running(self, keyword: str) -> tuple:
        """通过服务器代理查询动车组运行信息"""
        api_url = f"{self.api_base}/api/emu/query"
        try:
            resp = self._request('GET', api_url, params={"keyword": keyword}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data', []), None
                else:
                    return None, data.get('error', '未知错误')
            else:
                try:
                    err = resp.json().get('error', resp.text)
                except Exception:
                    err = resp.text
                return None, f"服务器错误 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            self._log_api_error(f"获取动车组运行信息失败 {keyword}: {e}")
            return None, f"请求超时或外部接口无响应，请稍后再试"

    def get_car_info(self, car_id: str) -> Optional[Dict]:
        """
        通过服务器代理查询配属详细信息
        返回: data对象，包含 bureau, model, depot, trainset_manufacturer 等
        """
        api_url = f"{self.api_base}/api/emu/car/info"
        try:
            resp = self._request('GET', api_url, params={"id": car_id}, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success'):
                    return data.get('data', {})
            return None
        except Exception as e:
            self._log_api_error(f"获取配属详细信息失败 {car_id}: {e}")
            return None

    def get_telecode_by_station_name(self, station_name: str) -> Optional[str]:
        """通过站名获取电报码"""
        if not self._telecode_loaded:
            self._load_telecode_map()
        # 直接匹配
        if station_name in self._telecode_cache:
            return self._telecode_cache[station_name]
        # 尝试模糊匹配（去除空格）
        for name, code in self._telecode_cache.items():
            if name.replace(' ', '') == station_name.replace(' ', ''):
                return code
        return None

# ================== 主窗口 ==================
class MainWindow(tk.Tk):
    def resource_path(self, relative_path):
        """获取打包后内部资源的绝对路径，使 exe 脱离外部原文件依赖"""
        import sys
        import os
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    def __init__(self):
        super().__init__()
        self.client = TADSClient()
        self.client.set_main_window(self)
        self._admin_temp_pwd = None
        self._root_temp_pwd = None
        self.title(" TADS 列车数据与查询服务系统（客户端） · QS Studio      v26.9.9")

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

        self.configure(bg='#f0f0f0')
        self.is_fullscreen = False

        from tkinter import ttk
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

        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="全屏", command=self.toggle_fullscreen)
        menubar.add_cascade(label="视图", menu=view_menu)
        menubar.add_command(label="连接PN532", command=self._connect_pn532)
        menubar.add_command(label="显示当前API Token", command=self._show_api_token)
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
        self._last_api_ok = False

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

        self.api_query_var = None
        self._api_status_label = None
        self._current_query_context = None
        self.client.use_api_query = True

        self.open_home_tab()
        self.after(5000, self.refresh_status)
        self.after(3000, self.check_physical_key_periodically)
        self.after(2000, self._verify_token_on_startup)
        self.after(500, self._initial_pn532_connect)

        self.client.log_action("系统启动", "客户端主界面已加载")
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

        self.after(100, self._async_init_server_connection)

    def _async_init_server_connection(self):
        """启动时后台静默连接服务器：先自动发现 IP，再拉取配置"""
        self.show_temp_message("正在搜索局域网服务器...", 3000)
        
        def do_connect():
            success, msg = self.client.discover_server()
            
            if success:
                self.after(0, lambda: self.show_temp_message(f"✅ {msg}", 3000))
            else:
                self.after(0, lambda: self.show_temp_message(f"⚠️ {msg}", 3000))
            
            try:
                self.client._fetch_server_config()
                
                if self.client.api_token:
                    try:
                        resp = self._request('GET', 
                            f"{self.client.api_base}/api/logs",
                            params={"lines": 1},
                            headers=self.client._api_headers(),
                            timeout=5
                        )
                        if resp.status_code == 401:
                            self.after(0, self._do_force_logout)
                            return
                    except Exception:
                        pass
                
                # 启动探针
                if self.client.is_admin or self.client.is_root or self.client.is_developer:
                    self.client._start_config_version_monitor()

                self.after(0, self._async_fetch_stats)
                self.after(0, lambda: self.show_temp_message("✅ API 通信正常", 3000))
                self.after(0, self.refresh_status)
                
            except Exception as e:
                self.after(0, lambda: self.show_temp_message("❌ 无法连接服务器，请检查网络", 5000))
                self.after(0, self.refresh_status)

        threading.Thread(target=do_connect, daemon=True).start()

    def _on_window_close(self):
        try:
            self.client.log_action("系统关闭", "客户端主界面已关闭")
        except Exception:
            pass
        self.destroy()

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
        """统一的 PN532 连接流程：0个报错/静默，1个直连，多个弹框"""
        try:
            ports = list(serial.tools.list_ports.comports())
        except Exception as e:
            if not silent_if_no_port:
                messagebox.showerror("错误", f"枚举串口失败: {e}", parent=self)
            return False

        if not ports:
            if not silent_if_no_port:
                messagebox.showerror("错误", "系统未检测到任何串口设备，请检查 PN532 是否已连接", parent=self)
            return False

        if len(ports) == 1:
            selected_port = ports[0].device
        else:
            selected_port = self._show_port_selection_dialog(ports)
            if selected_port is None:
                return False

        # 保存到客户端配置
        self.client.client_config.set('com_port', selected_port)
        self.client.com_port = selected_port

        # 执行连接
        try:
            if self.client.pn532 is None:
                self.client.pn532 = PN532Reader(port=selected_port, auto=False)
            else:
                self.client.pn532.port = selected_port
                self.client.pn532._init_reader()
        except Exception as e:
            if not silent_if_no_port:
                messagebox.showerror("错误", f"PN532 连接失败: {e}", parent=self)
            return False

        if self.client.pn532.is_connected():
            if not silent_on_success:
                messagebox.showinfo("成功", f"PN532 已连接（{selected_port}）", parent=self)
            return True
        else:
            if not silent_if_no_port:
                messagebox.showerror("错误", f"端口 {selected_port} 连接失败，请检查设备", parent=self)
            return False

    def _ensure_pn532_connected(self):
        """提权等操作前确保读卡器已连接，优先复用上次的配置端口，否则弹窗选择"""
        try:
            if (self.client.pn532 and self.client.pn532.is_connected()
                    and self.client.pn532.ser and self.client.pn532.ser.is_open):
                return True
        except Exception:
            pass

        saved_port = self.client.client_config.get('com_port', '')
        if saved_port and saved_port != "auto":
            try:
                current_ports = {p.device.upper() for p in serial.tools.list_ports.comports()}
                if saved_port.upper() in current_ports:
                    if self.client.pn532 is None:
                        self.client.pn532 = PN532Reader(port=saved_port, auto=False)
                    else:
                        self.client.pn532.port = saved_port
                        self.client.pn532._init_reader()
                    if self.client.pn532.is_connected():
                        return True
            except Exception:
                pass

        # 如果复连失败，调用统一选择逻辑
        return self._connect_pn532_with_selection(silent_on_success=True, silent_if_no_port=False)

    def _initial_pn532_connect(self):
        """启动时后台连接 PN532：多端口弹选择；单端口直连；无端口静默"""
        try:
            self._connect_pn532_with_selection(
                silent_on_success=True,
                silent_if_no_port=True
            )
        except Exception as e:
            self.client.write_error_log(f"启动时连接 PN532 失败: {e}")

    def _show_api_token(self):
        """展示当前 API Token（仅管理员/ROOT 可见）"""
        if not (self.client.is_admin or self.client.is_root):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return

        token = self.client.api_token or ""
        if not token:
            messagebox.showinfo("提示", "当前没有有效的 API Token", parent=self)
            return

        top = tk.Toplevel(self)
        top.title("API Token")
        top.geometry("620x220")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text=f"身份: {self.client.current_identity}   ｜   状态: 有效",
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

    def _verify_token_on_startup(self):
        """启动时验证客户端 token 是否仍被服务器端接受；若已失效则自动退出登录"""
        if not self.client.api_token:
            return

        def check():
            try:
                resp = self._request('GET', f"{self.client.api_base}/api/logs",
                                    params={"lines": 1},
                                    headers=self.client._api_headers(),
                                    timeout=5)
                if resp.status_code == 401:
                    self.after(0, self._do_force_logout)
            except Exception:
                pass

        threading.Thread(target=check, daemon=True).start()

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

    def _toggle_auto_update(self):
        """切换自动更新开关"""
        current = self.client.get_auto_update_setting()
        new_state = not current
        self.client.set_auto_update_setting(new_state)
        # 更新按钮文本
        self.auto_update_btn.config(
            text="关闭查询时自动更新该车次" if new_state else "开启查询时自动更新该车次"
        )
        # 显示临时消息
        self.show_temp_message(f"自动更新已{'开启' if new_state else '关闭'}")

    def _connect_pn532(self):
        """连接PN532读卡器"""
        ok = self._connect_pn532_with_selection(silent_on_success=False, silent_if_no_port=False)
        if ok:
            messagebox.showinfo("成功", "PN532 读卡器连接成功", parent=self)
        self.refresh_status()

    def _logout(self):
        """退出登录，重置为普通用户"""
        if not messagebox.askyesno("确认退出", "确定要退出当前登录吗？\n退出后将切换为普通用户权限。", parent=self):
            return

        self.client.is_admin = False
        self.client.is_developer = False
        self.client.is_root = False
        self.client.current_identity = "普通用户"
        self.client.api_password = None
        self.client._clear_token()
        self.client.log_action("退出登录", "已切换为普通用户")

        self.refresh_status()
        self.update_edit_status()
        self.show_temp_message("已退出登录，当前为普通用户", 2000)
        self.display_welcome()

    def _force_logout(self):
        """强制退出登录（由版本号变更触发）"""
        self.write_log("=== 强制退出登录 ===")

        self._version_monitor_stop = True
        if self._version_monitor_thread:
            try:
                self._version_monitor_thread.join(timeout=0.5)
            except:
                pass
            self._version_monitor_thread = None

        self.is_admin = False
        self.is_developer = False
        self.is_root = False
        self.current_identity = "普通用户"
        self.api_password = None
        self.config_version_at_login = None
        self._clear_token()
        self.log_action("强制退出登录", "检测到配置版本变更")

        if self.main_window:
            self.main_window.after(0, self.main_window._do_force_logout)

    def _do_force_logout(self):
        """强制退出登录（由服务器撤销 Token 触发）"""
        try:
            self.client.log_action("强制退出登录", "执行 UI 降级")
            self.client.is_admin = False
            self.client.is_developer = False
            self.client.is_root = False
            self.client.current_identity = "普通用户"
            self.client.api_password = None
            self.client._clear_token()
        except Exception:
            pass

        try:
            self.refresh_status()
            self.update_edit_status()
            self.show_temp_message("⚠️ 登录已过期，请重新登录", 5000)
            self.display_welcome()
        except Exception:
            pass

        try:
            close_keywords = ["编辑", "设置", "日志", "还原点"]
            tabs_to_close = []
            for tid, data in self.tabs.items():
                if any(kw in data['title'] for kw in close_keywords):
                    tabs_to_close.append(tid)
            for tid in tabs_to_close:
                self.close_tab(tid)
        except Exception:
            pass

        try:
            messagebox.showwarning(
                "登录过期",
                "您的登录凭证已失效或服务器配置已被修改。\n请重新提权以继续操作。",
                parent=self
            )
        except Exception:
            pass

    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes('-fullscreen', self.is_fullscreen)

    def update_status(self):
        now = datetime.datetime.now().strftime("%Y/%m/%d-%H:%M")
        identity = self.client.get_current_identity()
        base_text = f"当前页面：{self.client.current_page} | 身份：{identity} | 系统时间：{now}"

        pn532_ok = self.client.check_pn532_connection()
        pn532_status = "已连接" if pn532_ok else "未连接"

        pn532_port = ""
        try:
            if self.client.pn532:
                pv = (self.client.pn532.port or "").strip()
                if pv and pv.lower() != "auto":
                    pn532_port = pv
        except Exception:
            pn532_port = ""
        port_display = f"（{pn532_port}）" if pn532_port else "（未选择端口）"

        def async_status():
            api_ok = False
            try:
                resp = self._request('GET', f"{self.client.api_base}/api/health", timeout=3)
                api_ok = resp.status_code == 200
            except Exception:
                pass

            api_status = (f"已连接 ({self.client.api_base.replace('http://', '')})"
                          if api_ok else "未连接")

            if api_ok and not self._last_api_ok:
                self._last_api_ok = True
                self.after(0, self._async_fetch_stats)
            elif not api_ok:
                self._last_api_ok = False

            full_text = f"{base_text} | API：{api_status} | PN532：{pn532_status}{port_display}"

            if self.full_status_text != full_text:
                self.full_status_text = full_text
                self.after(0, self._start_scroll)

        threading.Thread(target=async_status, daemon=True).start()

    def _show_cinematic_error(self, title, message):
        """电影级超宽比例报错弹窗"""
        if hasattr(self, '_error_popup') and self._error_popup and self._error_popup.winfo_exists():
            try:
                self._error_text_var.set(message)
                self._error_popup.lift()
                return
            except Exception:
                pass

        self._error_popup = tk.Toplevel(self)
        self._error_popup.overrideredirect(True)
        self._error_popup.attributes('-topmost', True)
        
        w, h = 800, 150
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self._error_popup.geometry(f"{w}x{h}+{x}+{y}")
        self._error_popup.configure(bg='#111111')

        border = tk.Frame(self._error_popup, bg='#e74c3c', padx=2, pady=2)
        border.pack(fill=tk.BOTH, expand=True)
        
        inner = tk.Frame(border, bg='#111111')
        inner.pack(fill=tk.BOTH, expand=True)

        top_bar = tk.Frame(inner, bg='#e74c3c', height=30)
        top_bar.pack(fill=tk.X)
        top_bar.pack_propagate(False)
        tk.Label(top_bar, text=f" ⚠️ 系统警告 - {title}", font=('微软雅黑', 10, 'bold'), 
                 bg='#e74c3c', fg='white').pack(side=tk.LEFT, padx=10)
                 
        tk.Button(top_bar, text="×", command=self._error_popup.destroy, 
                  bg='#e74c3c', fg='white', relief=tk.FLAT, 
                  font=('微软雅黑', 12, 'bold'), bd=0).pack(side=tk.RIGHT, padx=10)

        content = tk.Frame(inner, bg='#111111')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self._error_text_var = tk.StringVar(value=message)
        err_lbl = tk.Label(content, textvariable=self._error_text_var, 
                           font=('Consolas', 11), bg='#111111', fg='#ff9999',
                           justify='left', anchor='w', wraplength=740)
        err_lbl.pack(fill=tk.BOTH, expand=True)

        tk.Button(inner, text="Dismiss / 确认", command=self._error_popup.destroy,
                  bg='#333333', fg='white', font=('微软雅黑', 9),
                  relief=tk.FLAT, width=15).pack(pady=(0, 10))

        top_bar.bind("<Button-1>", lambda e: self._error_popup.geometry(f"+{e.x_root - 400}+{e.y_root - 15}"))
        top_bar.bind("<B1-Motion>", lambda e: self._error_popup.geometry(f"+{e.x_root - 400}+{e.y_root - 15}"))

    def refresh_status(self):
        self.update_status()
        self.after(3000, self.refresh_status)

    def check_physical_key_periodically(self):
        # 检查物理密钥状态，若ROOT断开则降级
        # 但客户端ROOT降级由服务器控制，客户端仅刷新状态
        # 由于客户端不存储物理密钥状态，此方法留空或刷新API状态
        self.after(3000, self.check_physical_key_periodically)

    # ====== 标签管理 ======
    def show_placeholder(self):
        if hasattr(self, 'tab_bar_frame'):
            self.tab_bar_frame.pack_forget()
        for widget in self.content_area.winfo_children():
            widget.destroy()
        container = tk.Frame(self.content_area, bg='#f0f0f0')
        container.pack(fill=tk.BOTH, expand=True)
        big_font = ('微软雅黑', 28, 'bold')
        title_label = tk.Label(container, text="\n\n欢 迎 使 用\nT A D S 列 车 数 据 与 查 询 服 务 客 户 端", font=big_font, bg='#f0f0f0', justify='center')
        title_label.pack(expand=True, pady=(50, 0))
        small_font = ('微软雅黑', 10)
        small_text = (
            "© 2026 QS Studio\n"
            "开发者/负责人：Jason Michael (linchenlang)\n"
            "linchenlang@outlook.com\n\n"
            "版本  v26.9.9\n\n\n"
            "RailGo 提供数据支持"
        )
        small_label = tk.Label(container, text=small_text, font=small_font, bg='#f0f0f0', justify='center')
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
        self.client.current_page = title
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
                self.client.current_page = new_title
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
        self.client.current_page = current['title']
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
            self.client.current_page = "无标签"
            self.update_status()
            
        self.update_status()

    # ====== 构建各标签页 ======
    def build_home_frame(self):
        outer_frame = tk.Frame(self.content_area, bg='#f0f0f0')
        outer_frame.pack(fill=tk.BOTH, expand=True)

        content_container = tk.Frame(outer_frame, bg='#f0f0f0')
        content_container.place(relx=0.5, rely=0.5, anchor='center')

        tk.Label(
            content_container,
            text="欢迎使用 TADS 列车数据与查询服务客户端\n",
            font=('微软雅黑', 25, 'bold'),
            bg='#f0f0f0'
        ).pack(pady=10)

        home_text = scrolledtext.ScrolledText(
            content_container,
            font=('Consolas', 12),
            wrap=tk.NONE,
            bg='white',
            height=20,
            width=80
        )
        home_text.pack(padx=10, pady=10)
        home_text.config(state='disabled')
        outer_frame.home_text = home_text
        self._display_welcome_to_text(home_text)
        return outer_frame

    def _display_welcome_to_text(self, text_widget):
        text_widget.config(state='normal')
        text_widget.delete(1.0, tk.END)
        
        # ★★★ 移除同步请求：self.client.update_stats_from_api()
        
        last_write = ""
        if self.client.data and 'last_updated' in self.client.data:
            last_write = self.client.data['last_updated']
        else:
            last_write = "无数据"
        info = f"""\n\n\n\n
                 T A D S  列  车  数  据  与  查  询  服  务  系  统
                      TADS Train Data & Query Service System
                                       T A D S

                      · 数据库最后修改日期：{last_write}
"""
        if self.client.stats:
            s = self.client.stats
            info += f"                      · 数据库记录车站数：{s.get('station_count', 0)} 个\n"
            info += f"                      · 数据库记录车次数：{s.get('train_count', 0)} 个\n"
            if s.get('train_count', 0) > 0:
                info += f"                        平均每趟车停靠 {s.get('avg_stops', 0)} 个站\n"
            if s.get('busy_station_name'):
                info += f"                        经过列车最多的车站：{s['busy_station_name']} ({s.get('busy_station_count', 0)}趟)\n"
        else:
            info += "                      · 数据库尚未加载或数据为空。\n"
        info += "\n                      （客户端版，数据通过内网 API 访问）"
        text_widget.insert(tk.END, info)
        text_widget.config(state='disabled')

    def display_welcome(self):
        for tid, data in self.tabs.items():
            if data['title'] == "主页":
                frame = data['content_frame']
                if hasattr(frame, 'home_text'):
                    self._display_welcome_to_text(frame.home_text)

    def _async_fetch_stats(self):
        """后台异步拉取服务器统计数据，完成后刷新主页"""
        def do_fetch():
            self.client.update_stats_from_api()
            self.after(0, self.display_welcome)
        threading.Thread(target=do_fetch, daemon=True).start()

    def _open_train_detail_tab(self, train_number: str):
        """打开一个车次详情标签页（含列车信息 + 停站 + 本站车次/站台/检票口/出站口 + 正晚点）"""
        for tid, data in self.tabs.items():
            if data['title'] == f"车次-{train_number}":
                self.switch_tab(tid)
                return

        frame = ttk.Frame(self.content_area, padding=10)
        tk.Label(frame, text=f"车次 {train_number} 详情", font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=5)

        info_frame = tk.Frame(frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
        info_frame.pack(fill=tk.X, pady=5, padx=5)
        info_label = tk.Label(info_frame, text="正在加载列车信息...", font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
        info_label.pack(fill=tk.X, padx=10, pady=5)

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

        status_label = tk.Label(frame, text="正在加载数据...", font=('微软雅黑', 9), bg='#f0f0f0', fg='blue')
        status_label.pack(pady=5)

        self.add_tab(f"车次-{train_number}", frame, closable=True)

        def load_data():
            import concurrent.futures
            try:
                use_api = self.client.use_api_query

                if use_api:
                    # ---- API 模式 ----
                    v2_data, error_type, _ = self.client.query_train_from_v2(train_number)
                    if error_type != 'success' or not v2_data:
                        self.after(0, lambda: status_label.config(text="❌ 未找到该车次", fg='red'))
                        return

                    group = self.client.get_merged_by_number(train_number)
                    display_name = group['display_name'] if group else train_number

                    timetable = v2_data.get('timetable', [])
                    if not timetable:
                        self.after(0, lambda: status_label.config(text="⚠️ 该车次没有停站数据", fg='orange'))
                        return

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
                    # ---- 本地模式 ----
                    result = self.client.get_train(train_number)
                    if not result.get("success"):
                        self.after(0, lambda: status_label.config(
                            text="❌ 本地数据中未找到该车次\n可开启“使用API实时查询”后再试", fg='red'))
                        return
                    train_obj = result["data"]
                    display_name = train_obj.get('display_name') or train_number
                    stops = train_obj.get('stops', [])
                    if not stops:
                        stops = train_obj.get('timetable', [])
                    if not stops:
                        self.after(0, lambda: status_label.config(text="⚠️ 该车次没有停站数据", fg='orange'))
                        return

                    info_parts = [f"车次: {display_name}"]
                    if train_obj.get('type') and train_obj.get('type') != '未知':
                        info_parts.append(f"类型: {train_obj['type']}")
                    info_parts.append("数据来源: 本地数据库")
                    info_text = " | ".join(info_parts)

                    unified_timetable = []
                    for stop in stops:
                        name = stop.get('station_name') or self.client.get_station_name_by_id(stop.get('station_id')) or ''
                        unified_timetable.append({
                            'station': name,
                            'arrive': stop.get('arrive') or '',
                            'depart': stop.get('depart') or '',
                            'day': stop.get('day_offset', 0),
                            'trainCode': train_number,
                            'stationTelecode': '',
                        })

                self.after(0, lambda: info_label.config(text=info_text))

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
                    self.after(0, lambda: status_label.config(text="✅ 数据加载完成（离线模式）", fg='green'))
                    return

                self.after(0, lambda: status_label.config(text="正在获取正晚点和检票口信息...", fg='blue'))

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
                                self.client._get_train_exit,
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
                                self.client._log_api_error(f"获取检票口失败 {station_name}: {e}")

                delay_data = self.client._get_train_delay(train_number, timeout=30)

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

                if self.client.get_auto_update_setting():
                    pwd = self.client.api_password
                    if pwd:
                        def do_auto_update():
                            try:
                                success, msg = self.client.batch_import_train(train_number, "V2", pwd, auto_update=True)
                                if success:
                                    self.show_temp_message(f"{train_number} 已更新至本地数据库")
                                    self.client.log_action("自动更新车次", f"{train_number} 成功")
                                else:
                                    self.client.log_action("自动更新车次失败", f"{train_number}: {msg}")
                            except Exception as e:
                                self.client.log_action("自动更新车次异常", f"{train_number}: {str(e)}")
                        threading.Thread(target=do_auto_update, daemon=True).start()

            except Exception as e:
                self.client.write_error_log(f"加载车次详情失败 {train_number}: {e}")
                self.after(0, lambda: status_label.config(text=f"❌ 加载失败: {str(e)[:50]}", fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _open_station_detail_tab(self, station_name: str):
        """打开车站详情标签页（含基本信息 + 时刻表）"""
        for tid, data in self.tabs.items():
            if data['title'] == f"车站-{station_name}":
                self.switch_tab(tid)
                return

        frame = ttk.Frame(self.content_area, padding=10)
        tk.Label(frame, text=f"车站 {station_name} 详情", font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=5)

        info_frame = tk.Frame(frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
        info_frame.pack(fill=tk.X, pady=5, padx=5)
        info_label = tk.Label(info_frame, text="正在加载车站信息...", font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
        info_label.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(frame, text="经过该站的车次", font=('微软雅黑', 12, 'bold'), bg='#f0f0f0').pack(pady=5)

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

        tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))

        status_label = tk.Label(frame, text="正在加载数据...", font=('微软雅黑', 9), bg='#f0f0f0', fg='blue')
        status_label.pack(pady=5)

        self.add_tab(f"车站-{station_name}", frame, closable=True)

        def load_data():
            try:
                # 1. 车站信息（仅在 API 模式下调用 V1 接口）
                station_info = None
                if self.client.use_api_query:
                    telecode = self.client.get_telecode(station_name)
                    if telecode:
                        station_data = self.client._call_v1_station_query(telecode)
                        if station_data and 'data' in station_data:
                            station_info = station_data['data']

                # 2. 经过该站的车次（从服务器本地数据）
                source = "api" if self.client.use_api_query else "local"
                try:
                    resp = self._request('GET', f"{self.client.api_base}/api/station/{station_name}/trains",
                                        params={"source": source}, timeout=10)
                    if resp.status_code == 200:
                        station_trains = resp.json()
                    else:
                        station_trains = []
                except:
                    station_trains = []

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

                if station_trains:
                    import concurrent.futures
                    train_info = {}
                    def fetch_train_info(train_num):
                        try:
                            src = "api" if self.client.use_api_query else "local"
                            resp = self._request('GET', f"{self.client.api_base}/api/train/{train_num}",
                                                params={"source": src}, timeout=10)
                            if resp.status_code == 200:
                                data = resp.json()
                                stops = data.get('stops', [])
                                start_station = ''
                                end_station = ''
                                if stops:
                                    start_station = stops[0].get('station_name', '')
                                    end_station = stops[-1].get('station_name', '')
                                return train_num, data.get('display_name', train_num), data.get('numbers', [train_num]), start_station, end_station
                            else:
                                return train_num, train_num, [train_num], '', ''
                        except:
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
                else:
                    self.after(0, lambda: status_label.config(text="该站暂无车次数据", fg='orange'))

            except Exception as e:
                self.client.write_error_log(f"加载车站详情失败 {station_name}: {e}")
                self.after(0, lambda: status_label.config(text=f"加载失败: {str(e)[:50]}", fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _show_coach_pic(self, train_num: str):
        """显示列车车厢图，支持车次组内自动切换"""
        import concurrent.futures
        from PIL import Image, ImageTk
        import requests
        from io import BytesIO

        # ===== 离线模式检查 =====
        if not self.client.use_api_query:
            messagebox.showinfo(
                "离线模式",
                "当前为离线模式，请开启“使用API实时查询”后再尝试查询本项。",
                parent=self
            )
            return

        # 获取合并组
        group = self.client.get_merged_by_number(train_num)
        candidates = group['numbers'] if group else [train_num]
        display_name = group['display_name'] if group else train_num

        data = None
        for num in candidates:
            data = self.client.get_coach_pic(num)
            if data:
                break

        if not data:
            messagebox.showinfo("提示", f"未获取到车次组 {display_name} 的车厢图数据", parent=self)
            return

        top = tk.Toplevel(self)
        top.title(f"列车组图片 - {display_name}")
        top.geometry("1400x850")
        top.minsize(1200, 750)
        top.configure(bg='#f0f0f0')

        car_type = data.get('carType', '未知车型')
        train_style = data.get('trainStyle', '')
        car_code = data.get('carCode', '')
        info_text = f"车型: {car_type}"
        if train_style:
            info_text += f"  ({train_style})"
        if car_code:
            info_text += f"  |  车号: {car_code}"
        tk.Label(top, text=info_text,
                 font=('微软雅黑', 14, 'bold'), bg='#f0f0f0').pack(pady=10)

        main_frame = tk.Frame(top, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left_frame = tk.Frame(main_frame, bg='#f0f0f0')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        tk.Label(left_frame, text="车厢分布图",
                 font=('微软雅黑', 12, 'bold'), bg='#f0f0f0').pack(pady=5)

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

        btn_frame_bottom = tk.Frame(top, bg='#f0f0f0')
        btn_frame_bottom.pack(fill=tk.X, pady=10)
        tk.Button(btn_frame_bottom, text="关闭", command=top.destroy,
                  width=15, font=('微软雅黑', 10)).pack()

        if load_tasks:
            for url, img_label in load_tasks:
                img_label.config(text="加载中...")

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
            top._executor = executor

            for url, img_label in load_tasks:
                executor.submit(self._load_thumbnail_with_executor, url, img_label)

    def _open_emu_running_from_entry(self, entry):
        """从输入框获取车次号并查询动车组运行"""
        keyword = entry.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请先输入车次或车组号", parent=self)
            return
        self._open_emu_running_tab(keyword)

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

        if not self.client.use_api_query:
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
                data, err_msg = self.client.get_emu_running(keyword)
                
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
                self.client.write_error_log(f"客户端动车组运行查询UI异常 {keyword}: {e}")
                err_text = f"❌ 查询异常: {str(e)[:50]}"
                self.after(0, lambda m=err_text: status_label.config(text=m, fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _open_car_detail_tab(self, car_id: str):
        """打开车组详细信息标签页（客户端美化版）"""
        if not car_id:
            return

        tab_title = f"车组-{car_id}"
        for tid, data in self.tabs.items():
            if data['title'] == tab_title:
                self.switch_tab(tid)
                return

        frame = ttk.Frame(self.content_area, padding=10)

        title_frame = tk.Frame(frame, bg='#2c3e50', height=80)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text=f"车组详细信息",
                 font=('微软雅黑', 18, 'bold'), bg='#2c3e50', fg='white').pack(side=tk.LEFT, padx=20, pady=20)
        tk.Label(title_frame, text=car_id,
                 font=('微软雅黑', 14), bg='#2c3e50', fg='#3498db').pack(side=tk.LEFT, padx=10, pady=20)

        # ===== 离线模式检查 =====
        if not self.client.use_api_query:
            self.add_tab(tab_title, frame, closable=True)
            self._show_offline_message(frame)
            return

        status_label = tk.Label(frame, text="⏳ 正在加载详细信息...",
                                font=('微软雅黑', 10), bg='#f0f0f0', fg='blue')
        status_label.pack(pady=5)

        canvas_frame = tk.Frame(frame, bg='#f0f0f0')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        canvas = tk.Canvas(canvas_frame, bg='#f0f0f0', highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#f0f0f0')

        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def on_scrollable_configure(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)

        scrollable_frame.bind("<Configure>", on_scrollable_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.add_tab(tab_title, frame, closable=True)

        def load_data():
            try:
                data = self.client.get_car_info(car_id)
                if not data:
                    self.after(0, lambda: status_label.config(
                        text=f"❌ 未找到车组 {car_id} 的详细信息", fg='red'))
                    return

                self.after(0, lambda: status_label.config(
                    text=f"✅ 车组 {car_id} 详细信息加载完成", fg='green'))

                self.after(0, lambda: self._build_car_detail_cards(scrollable_frame, data))

            except Exception as e:
                self.after(0, lambda: status_label.config(
                    text=f"❌ 加载失败: {str(e)[:50]}", fg='red'))

        threading.Thread(target=load_data, daemon=True).start()

    def _build_car_detail_cards(self, parent, data):
        """构建车组详细信息的卡片式布局"""
        colors = {
            'card_bg': '#ffffff',
            'header_bg': '#34495e',
            'header_text': '#ffffff',
            'label_color': '#7f8c8d',
            'value_color': '#2c3e50',
            'border': '#ecf0f1',
            'section_bg': '#f8f9fa'
        }

        # 关键：parent 由 canvas 管理，不能再 pack
        parent.grid_columnconfigure(0, weight=1)

        # ---- 基本信息卡片 ----
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
        self._render_car_info_items(body1, info_items1, colors)

        # ---- 配属信息卡片 ----
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
        self._render_car_info_items(body2, info_items2, colors)

        # ---- 设施信息卡片 ----
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
        self._render_car_info_items(body3, info_items3, colors)

        # ---- 备注信息卡片 ----
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
                    tk.Label(row_frame, text="车型备注：", font=('微软雅黑', 12),
                             bg=colors['card_bg'], fg=colors['label_color']).pack(side=tk.LEFT)
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
                        tk.Label(row_frame, text="车辆备注：", font=('微软雅黑', 12),
                                 bg=colors['card_bg'], fg=colors['label_color']).pack(side=tk.LEFT)
                        text_widget = tk.Text(row_frame, height=2, font=('微软雅黑', 12),
                                              bg='#e8f5e9', fg='#2e7d32', relief=tk.FLAT, wrap=tk.WORD)
                        text_widget.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
                        text_widget.insert(tk.END, note)
                        text_widget.config(state='disabled')

                    tags = car_remark.get('tags', '')
                    if tags:
                        row_frame = tk.Frame(body4, bg=colors['card_bg'])
                        row_frame.pack(fill=tk.X, pady=6)
                        tk.Label(row_frame, text="标签：", font=('微软雅黑', 12),
                                 bg=colors['card_bg'], fg=colors['label_color']).pack(side=tk.LEFT)
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
                            tk.Label(row_frame, text=tags, font=('微软雅黑', 12),
                                     bg=colors['card_bg'], fg=colors['value_color']).pack(side=tk.LEFT, padx=5)

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

        _update_scrollregion()
        parent.after(50, _update_scrollregion)
        parent.after(200, _update_scrollregion)

    def _render_car_info_items(self, parent, items, colors):
        """渲染车组信息项，自动适配长文本"""
        short_items = []
        long_items = []
        
        for label, value in items:
            value_str = str(value)
            if len(value_str) > 20 or '；' in value_str or '，' in value_str:
                long_items.append((label, value_str))
            else:
                short_items.append((label, value_str))
        
        row_idx = 0
        
        for label, value in long_items:
            container = tk.Frame(parent, bg=colors['card_bg'])
            container.grid(row=row_idx, column=0, columnspan=3, sticky='ew', padx=10, pady=6)
            container.grid_columnconfigure(0, weight=0)
            container.grid_columnconfigure(1, weight=1)
            
            tk.Label(container, text=label + "：", font=('微软雅黑', 12),
                     bg=colors['card_bg'], fg=colors['label_color']).grid(row=0, column=0, sticky='w')
            tk.Label(container, text=value, font=('微软雅黑', 12, 'bold'),
                     bg=colors['card_bg'], fg=colors['value_color'],
                     wraplength=1000, justify='left').grid(row=0, column=1, sticky='w', padx=(5, 0))
            row_idx += 1
        
        col = 0
        for label, value in short_items:
            container = tk.Frame(parent, bg=colors['card_bg'])
            container.grid(row=row_idx, column=col, sticky='w', padx=10, pady=6)
            tk.Label(container, text=label + "：", font=('微软雅黑', 12),
                     bg=colors['card_bg'], fg=colors['label_color']).grid(row=0, column=0, sticky='w')
            tk.Label(container, text=value, font=('微软雅黑', 12, 'bold'),
                     bg=colors['card_bg'], fg=colors['value_color']).grid(row=0, column=1, sticky='w', padx=(5, 0))
            col += 1
            if col >= 3:
                col = 0
                row_idx += 1
        
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
            
            resp = self._request('GET', url, timeout=10)
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
            self.client.write_error_log(f"加载车厢图失败 {url}: {e}")

    def _load_thumbnail_async(self, url, img_label, parent_frame):
        """异步加载缩略图"""
        try:
            from PIL import Image, ImageTk
            import requests
            from io import BytesIO
            
            resp = self._request('GET', url, timeout=10)
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
            self.client.write_error_log(f"加载车厢图失败 {url}: {e}")

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
            
            resp = self._request('GET', url, timeout=30)
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
            self.client.write_error_log(f"加载大图失败 {url}: {e}")
    
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
        train_num = train_display.split('/')[0]
        self._open_train_detail_tab(train_num)

    # ====== 编辑框架（已移除“从 RailRhythm 更新数据”按钮） ======
    def build_edit_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        current_identity = self.client.get_current_identity()
        if current_identity in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            status_text = f"当前身份：{current_identity}（可编辑）"
            status_color = 'green'
        else:
            status_text = "当前身份：普通用户（需要管理员权限）"
            status_color = 'red'
        status_label = tk.Label(frame, text=status_text, font=('微软雅黑', 10), bg='#f0f0f0', fg=status_color)
        status_label.pack(pady=5)

        op_frame = tk.Frame(frame, bg='#f0f0f0')
        op_frame.pack(fill=tk.X, pady=10)

        tk.Label(op_frame, text="新增车次:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=0, column=0, padx=5, pady=3, sticky='e')
        entry_new_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_new_train.grid(row=0, column=1, padx=5, pady=3)
        def add_train_wrapper():
            self._add_train(entry_new_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-新增车次")
        tk.Button(op_frame, text="确认新增", command=add_train_wrapper, width=12).grid(row=0, column=2, padx=5, pady=3)

        tk.Label(op_frame, text="删除车次:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=1, column=0, padx=5, pady=3, sticky='e')
        entry_del_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_del_train.grid(row=1, column=1, padx=5, pady=3)
        def del_train_wrapper():
            self._del_train(entry_del_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-删除车次")
        tk.Button(op_frame, text="确认删除", command=del_train_wrapper, width=12).grid(row=1, column=2, padx=5, pady=3)

        tk.Label(op_frame, text="录入停站(车次):", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=2, column=0, padx=5, pady=3, sticky='e')
        entry_add_stop_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_add_stop_train.grid(row=2, column=1, padx=5, pady=3)
        def show_add_stop_wrapper():
            self._show_add_stop_form(frame, entry_add_stop_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-录入停站")
        tk.Button(op_frame, text="显示录入表单", command=show_add_stop_wrapper, width=14).grid(row=2, column=2, padx=5, pady=3)

        tk.Label(op_frame, text="删除停站(车次):", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=3, column=0, padx=5, pady=3, sticky='e')
        entry_del_stop_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_del_stop_train.grid(row=3, column=1, padx=5, pady=3)
        def show_del_stop_wrapper():
            self._show_del_stop_form(frame, entry_del_stop_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-删除停站")
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

        # ★★★ 保存按钮引用到实例变量 ★★★
        self.batch_import_btn = tk.Button(batch_frame, text="抓取并导入全部经停站",
                                          command=lambda: self._batch_import_train(entry_batch_train, batch_api_var),
                                          width=20)
        self.batch_import_btn.grid(row=0, column=4, padx=5, pady=5)

        # ★★★ 保存状态标签到实例变量 ★★★
        self.batch_status_label = tk.Label(batch_frame, text="", bg='#f0f0f0', font=('微软雅黑', 9), fg='blue')
        self.batch_status_label.grid(row=1, column=0, columnspan=5, padx=5, pady=2)
        frame.batch_status = self.batch_status_label
        frame.entry_batch_train = entry_batch_train
        frame.batch_api_var = batch_api_var

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

        # ★★★ 修改点：crawl_status 定义移到按钮之前 ★★★
        crawl_status = tk.Label(station_crawl_frame, text="", bg='#f0f0f0', font=('微软雅黑', 9), fg='blue')
        crawl_status.grid(row=1, column=0, columnspan=5, padx=5, pady=2)
        frame.crawl_status = crawl_status

        # ★★★ 修改点：第三个参数从 batch_status 改为 crawl_status ★★★
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
        return frame

    # ====== 编辑功能实现 ======
    def _get_admin_password(self, purpose="操作"):
        """
        确保已登录为管理员/ROOT。
        - 已有 token：直接返回
        - 未登录：弹窗 + 走完整认证流程（读卡 + /api/auth/login）
        """
        if self.client.api_token:
            return self.client.api_password

        # 先尝试确保读卡器已连接
        if not self._ensure_pn532_connected():
            return None

        top = tk.Toplevel(self)
        top.title("管理员验证")
        top.geometry("380x280")
        top.transient(self)
        top.grab_set()

        tk.Label(top, text=f"请输入管理员密码（{purpose}）:", font=('微软雅黑', 10)).pack(pady=10)

        pwd_frame = tk.Frame(top)
        pwd_frame.pack(pady=5)
        pwd_entry = tk.Entry(pwd_frame, show='*', width=25, font=('微软雅黑', 10))
        pwd_entry.pack(side=tk.LEFT, padx=5)

        pwd_visible = False
        def toggle_pwd():
            nonlocal pwd_visible
            pwd_visible = not pwd_visible
            pwd_entry.config(show='' if pwd_visible else '*')
        tk.Button(pwd_frame, text="👁", command=toggle_pwd, width=3, font=('微软雅黑', 9)).pack(side=tk.LEFT)

        tip_label = tk.Label(top, text="请将物理密钥放在读卡器上", font=('微软雅黑', 9), fg='orange')
        tip_label.pack(pady=5)

        status_label = tk.Label(top, text="", font=('微软雅黑', 9), fg='blue')
        status_label.pack(pady=5)

        result = {'pwd': None}

        def do_verify():
            verify_btn.config(state='disabled')
            pwd = pwd_entry.get()
            if not pwd:
                status_label.config(text="请输入密码", fg='red')
                verify_btn.config(state='normal')
                return

            status_label.config(text="⏳ 正在读卡验证...", fg='blue')
            top.update_idletasks()

            try:
                if self.client.pn532 and self.client.pn532.ser:
                    self.client.pn532.reset()
            except Exception:
                pass

            r = self.client.verify_admin(pwd)
            if isinstance(r, tuple):
                success = r[0]
            else:
                success = bool(r)

            if success:
                result['pwd'] = pwd
                status_label.config(text="✅ 验证通过", fg='green')
                self.refresh_status()
                self.update_edit_status()
                self.after(300, top.destroy)
            else:
                status_label.config(text="❌ 验证失败，请重试", fg='red')
                tip_label.config(text="⚠️ 请确保物理密钥已放好，且密码正确", fg='orange')
                verify_btn.config(state='normal')

        def on_cancel():
            result['pwd'] = None
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=10)
        verify_btn = tk.Button(btn_frame, text="验证", command=do_verify, width=10)
        verify_btn.pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

        pwd_entry.bind('<Return>', lambda e: do_verify())
        self.wait_window(top)
        return result['pwd']

    def _add_train(self, entry):
        current_identity = self.client.get_current_identity()
        if current_identity not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "请先提权为管理员或更高权限", parent=self)
            return
        number = entry.get().strip()
        if not number:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        if re.search(r'[<>:"/\\|?*]', number):
            messagebox.showerror("错误", "车次号包含非法字符", parent=self)
            return
        # 先检查是否已存在（使用 get_train）
        result = self.client.get_train(number)
        if result["success"]:
            messagebox.showinfo("提示", "该车次已存在", parent=self)
            return
        # 注意：get_train 失败不代表不能新增，只有超时/错误才阻止
        if result["error_type"] in ("timeout", "error"):
            messagebox.showerror("错误", f"无法验证车次是否存在: {result['error']}", parent=self)
            return

        if self.client.api_password:
            pwd = self.client.api_password
        else:
            pwd = self._get_admin_password("新增车次")
        if pwd is None:
            return
        success, msg = self.client.add_train(number, pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self.display_welcome()
            entry.delete(0, tk.END)
            self.client.update_stats_from_api()
            self.after(1000, self.refresh_status)
        else:
            messagebox.showerror("错误", f"添加失败: {msg}", parent=self)

    def _del_train(self, entry):
        current_identity = self.client.get_current_identity()
        if current_identity not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "请先提权为管理员或更高权限", parent=self)
            return
        number = entry.get().strip()
        if not number:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        result = self.client.get_train(number)
        if not result["success"]:
            if result["error_type"] == "timeout":
                messagebox.showinfo("提示", "未找到该车次，V2未重试", parent=self)
            else:
                messagebox.showinfo("提示", result["error"], parent=self)
            return
        train = result["data"]
        if self.client.api_password:
            pwd = self.client.api_password
        else:
            pwd = self._get_admin_password("删除车次")
        if pwd is None:
            return
        if not messagebox.askyesno("确认", f"确认删除 {number} 及其所有停站？", parent=self):
            return
        success, msg = self.client.delete_train(number, pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self.display_welcome()
            entry.delete(0, tk.END)
            self.client.update_stats_from_api()
            self.after(1000, self.refresh_status)
        else:
            messagebox.showerror("错误", f"删除失败: {msg}", parent=self)

    def _show_add_stop_form(self, parent_frame, entry_train):
        current_identity = self.client.get_current_identity()
        if current_identity not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "请先提权为管理员或更高权限", parent=self)
            return
        train_num = entry_train.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        result = self.client.get_train(train_num)
        if not result["success"]:
            if result["error_type"] == "timeout":
                messagebox.showinfo("提示", "未找到该车次，V2未重试", parent=self)
            else:
                messagebox.showinfo("提示", result["error"], parent=self)
            return
        train = result["data"]
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
            station = entry_station.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入站名", parent=self)
                return
            arrive = entry_arrive.get().strip() or None
            depart = entry_depart.get().strip() or None
            day_str = entry_day.get().strip()
            day_offset = int(day_str) if day_str.isdigit() else 0
            if self.client.api_password:
                pwd = self.client.api_password
            else:
                pwd = self._get_admin_password("录入停站")
            if pwd is None:
                return
            success, msg = self.client.add_stop(train_num, station, arrive, depart, day_offset, pwd)
            if success:
                messagebox.showinfo("成功", msg, parent=self)
                self.display_welcome()
                for widget in parent_frame.stop_form_frame.winfo_children():
                    widget.destroy()
                self.client.update_stats_from_api()
                self.after(1000, self.refresh_status)
            else:
                messagebox.showerror("错误", f"录入失败: {msg}", parent=self)

        tk.Button(parent_frame.stop_form_frame, text="确认录入", command=confirm_add, width=15).pack(pady=5)

    def _show_del_stop_form(self, parent_frame, entry_train):
        current_identity = self.client.get_current_identity()
        if current_identity not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "请先提权为管理员或更高权限", parent=self)
            return
        train_num = entry_train.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        result = self.client.get_train(train_num)
        if not result["success"]:
            if result["error_type"] == "timeout":
                messagebox.showinfo("提示", "未找到该车次，V2未重试", parent=self)
            else:
                messagebox.showinfo("提示", result["error"], parent=self)
            return
        train = result["data"]
        if not train.get('stops'):
            messagebox.showinfo("提示", "该车次没有停站", parent=self)
            return
        display = parent_frame.edit_display
        display.config(state='normal')
        display.delete(1.0, tk.END)
        display.insert(tk.END, "选择要删除的停站（输入序号）:\n")
        for i, stop in enumerate(train['stops']):
            name = stop.get('station_name') or self.client.get_station_name_by_id(stop.get('station_id'))
            display.insert(tk.END, f"{i+1}. {name}  {stop.get('arrive','')}->{stop.get('depart','')} (跨{stop.get('day_offset',0)})\n")
        display.config(state='disabled')

        def remove_by_index():
            try:
                idx = int(tk.simpledialog.askstring("删除", "请输入要删除的序号:", parent=self))
                if idx is None:
                    return
                if idx < 1 or idx > len(train['stops']):
                    messagebox.showerror("错误", "序号无效", parent=self)
                    return
                if self.client.api_password:
                    pwd = self.client.api_password
                else:
                    pwd = self._get_admin_password("删除停站")
                if pwd is None:
                    return
                if messagebox.askyesno("确认删除", f"确认删除序号 {idx} 的停站？", parent=self):
                    success, msg = self.client.delete_stop(train_num, idx, pwd)
                    if success:
                        messagebox.showinfo("成功", msg, parent=self)
                        self.display_welcome()
                        self._show_del_stop_form(parent_frame, entry_train)
                        self.client.update_stats_from_api()
                        self.after(1000, self.refresh_status)
                    else:
                        messagebox.showerror("错误", f"删除失败: {msg}", parent=self)
            except:
                pass

        tk.Button(parent_frame.stop_form_frame, text="输入序号删除", command=remove_by_index, width=15).pack(pady=5)

    def _batch_import_train(self, entry_train, api_var):
        """批量导入/更新车次：从 API 抓取全部经停站"""
        if not (self.client.is_admin or self.client.is_root):
            messagebox.showwarning("权限不足", "请先提权为管理员或ROOT", parent=self)
            return

        train_num = entry_train.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return

        if hasattr(self, 'batch_status_label') and self.batch_status_label:
            self.batch_status_label.config(text="正在抓取数据，请稍候...", fg='blue')
            self.batch_status_label.update()

        if hasattr(self, 'batch_import_btn') and self.batch_import_btn:
            self.batch_import_btn.config(state='disabled')

        def do_import():
            try:
                api_type = api_var.get()
                pwd = self.client.api_password
                if not pwd:
                    pwd = self._get_admin_password("批量导入车次")
                if pwd is None:
                    self.after(0, lambda: self._batch_import_result(False, "已取消密码验证", 0, train_num, silent=True))
                    return
                
                # ★ 唯一改变的地方：强制走 _do_post，自动带 Token 并处理 401
                data = {"train_number": train_num, "api_type": api_type, "password": pwd}
                success, msg = self.client._do_post("/api/admin/batch_import", data, pwd)
                
                # 成功或失败都直接返回，由于没有返回 stop_count，这里传 0
                self.after(0, lambda: self._batch_import_result(success, msg, 0, train_num))
                
                if success:
                    self.display_welcome()
                    self.client.update_stats_from_api()
                    self.after(1000, self.refresh_status)
            except Exception as e:
                self.after(0, lambda: self._batch_import_result(False, f"异常: {str(e)}", 0, train_num))

        threading.Thread(target=do_import, daemon=True).start()

    def _batch_import_result(self, success, msg, count, train_num, silent=False):
        """批量导入结果回调"""
        if hasattr(self, 'batch_status_label') and self.batch_status_label:
            if success:
                self.batch_status_label.config(text=f"✅ {msg}", fg='green')
                if not silent:
                    messagebox.showinfo("导入成功", f"{msg}", parent=self)
            else:
                self.batch_status_label.config(text=f"❌ {msg}", fg='red')
                if not silent:
                    messagebox.showerror("导入失败", msg, parent=self)

        if hasattr(self, 'batch_import_btn') and self.batch_import_btn and self.batch_import_btn.winfo_exists():
            self.batch_import_btn.config(state='normal')

    def _crawl_station_trains(self, entry_station, api_var, status_label):
        """抓取该站所有车次（客户端版本）"""
        if not (self.client.is_admin or self.client.is_root):
            messagebox.showwarning("权限不足", "请先提权为管理员或ROOT", parent=self)
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
                telecode = self.client.get_telecode(station)
                if not telecode:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, f"未找到车站 '{station}' 的电报码"))
                    return

                # 2. 调用 V1 车站查询接口
                station_data = self.client._call_v1_station_query(telecode)
                if not station_data or 'trains' not in station_data:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, "获取车站数据失败，请检查网络连接"))
                    return

                trains = station_data.get('trains', [])
                if not trains:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, f"没有车次经过 '{station}'"))
                    return

                # 3. 提取车次号
                train_numbers = []
                for train in trains:
                    number_full = train.get('numberFull', [])
                    if number_full:
                        train_numbers.append(number_full[0])
                    else:
                        num = train.get('number')
                        if num:
                            train_numbers.append(num)

                train_numbers = list(dict.fromkeys(train_numbers))

                if not train_numbers:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, "未解析到有效车次号"))
                    return

                total = len(train_numbers)
                self.after(0, lambda: status_label.config(
                    text=f"找到 {total} 个车次，开始抓取（每秒4个）...", fg='blue'))

                # 4. 逐个抓取
                success_list = []
                failed_list = []
                api_type = api_var.get()
                pwd = self.client.api_password
                if not pwd:
                    pwd = self._get_admin_password("车站抓取")
                if pwd is None:
                    self.after(0, lambda: self._crawl_station_result(
                        status_label, btn_widget, False, "取消操作"))
                    return

                for idx, train_num in enumerate(train_numbers):
                    try:
                        progress = f"({idx+1}/{total})"
                        self.after(0, lambda p=progress, t=train_num: status_label.config(
                            text=f"正在抓取 {t} {p}...", fg='blue'))

                        # 调用批量导入接口
                        data = {"train_number": train_num, "api_type": api_type, "password": pwd}
                        resp = self._request('POST', f"{self.client.api_base}/api/admin/batch_import", json=data, timeout=60)
                        if resp.status_code == 200:
                            result = resp.json()
                            if result.get('success', False):
                                success_list.append(train_num)
                            else:
                                failed_list.append((train_num, result.get('message', '未知错误')))
                        else:
                            failed_list.append((train_num, f"HTTP {resp.status_code}"))

                        if (idx + 1) < total:
                            time.sleep(0.25)

                    except Exception as e:
                        failed_list.append((train_num, str(e)))

                # 5. 显示结果
                result_msg = f"抓取完成！成功: {len(success_list)} 个，失败: {len(failed_list)} 个"
                self.after(0, lambda: self._crawl_station_result(
                    status_label, btn_widget, True, result_msg))

                if failed_list:
                    failed_detail = "\n".join([f"{num}: {msg}" for num, msg in failed_list[:20]])
                    if len(failed_list) > 20:
                        failed_detail += f"\n... 共 {len(failed_list)} 个失败"
                    self.after(0, lambda: messagebox.showwarning(
                        "部分失败", f"以下车次抓取失败：\n{failed_detail}", parent=self))

                self.after(0, self.display_welcome)
                self.after(0, self.client.update_stats_from_api)

            except Exception as e:
                self.after(0, lambda: self._crawl_station_result(
                    status_label, btn_widget, False, f"异常: {str(e)}"))

        threading.Thread(target=do_crawl, daemon=True).start()

    def _crawl_station_result(self, status_label, btn_widget, success, msg):
        """车站抓取结果回调（客户端版本）"""
        if status_label:
            if success:
                status_label.config(text=f"✅ {msg}", fg='green')
            else:
                status_label.config(text=f"❌ {msg}", fg='red')
        if btn_widget and btn_widget.winfo_exists():
            btn_widget.config(state='normal')

    # ====== 查看框架 ======
    def build_view_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=10)

        def make_view_callback(cmd, frame, suffix):
            def callback():
                cmd(frame)
                if self.current_tab_id is not None:
                    self.update_tab_title(self.current_tab_id, f"查看-{suffix}")
            return callback

        tk.Button(btn_frame, text="车次排行榜（停站数）",
                  command=make_view_callback(self._view_rank, frame, "车次排行榜"), width=26).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="查看车次所有经停站",
                  command=make_view_callback(self._view_train_stops, frame, "查看车次所有经停站"), width=26).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="查看所有车次时刻表（需管理员）",
                  command=make_view_callback(self._view_all_trains, frame, "查看所有车次时刻表"), width=26).pack(side=tk.LEFT, padx=5)

        tree_frame = tk.Frame(frame, bg='#f0f0f0')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
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
        """车次排行榜（停站数）"""
        try:
            resp = self._request('GET', f"{self.client.api_base}/api/trains", timeout=10)
            if resp.status_code != 200:
                self._set_view_table(frame, ['名次', '车次', '停站数'], [])
                return
            trains = resp.json()
            # trains 格式: [{"number": "K973/K976", "stops": 30}, ...]
            ranked = sorted(trains, key=lambda x: x.get('stops', 0), reverse=True)[:20]
            rows = [(str(i+1), item['number'], str(item.get('stops', 0))) for i, item in enumerate(ranked)]
            self._set_view_table(frame, ['名次', '车次', '停站数'], rows)
        except Exception as e:
            self.client.write_error_log(f"获取车次排行榜失败: {e}")
            self._set_view_table(frame, ['名次', '车次', '停站数'], [])

    def _view_train_stops(self, frame):
        """查看车次所有经停站"""
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
            
            # 从 display_name 中提取第一个车次号
            first_num = number.split('/')[0] if '/' in number else number
            
            result = self.client.get_train(first_num)
            if not result["success"]:
                if result["error_type"] == "timeout":
                    messagebox.showinfo("提示", "未找到该车次，V2未重试", parent=self)
                else:
                    messagebox.showinfo("提示", result["error"], parent=self)
                self._set_view_table(frame, ['序号', '站名', '到达', '出发', '跨天'], [])
                return
            
            train = result["data"]
            display_name = train.get('display_name', number)
            
            # 获取停站
            stops = train.get('stops', [])
            if not stops:
                stops = train.get('timetable', [])
            
            if not stops:
                self._set_view_table(frame, ['序号', '站名', '到达', '出发', '跨天'], [])
                return
            
            columns = ['序号', '站名', '到达', '出发', '跨天']
            rows = []
            for i, stop in enumerate(stops):
                name = stop.get('station_name') or stop.get('station', '')
                if not name:
                    sid = stop.get('station_id')
                    if sid is not None:
                        name = self.client.get_station_name_by_id(sid)
                    else:
                        name = ''
                arrive = stop.get('arrive') or ''
                depart = stop.get('depart') or ''
                day_offset = stop.get('day_offset', 0)
                day_info = "次日" if day_offset == 1 else "当日"
                rows.append((str(i+1), name, arrive, depart, day_info))
            
            # 更新标签页标题显示车次名
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, f"查看-{display_name}经停站")
            
            self._set_view_table(frame, columns, rows)
        
        entry.bind('<Return>', lambda e: do_view())
        tk.Button(f, text="查看", command=do_view, width=12).pack(side=tk.LEFT, padx=5)

    def _view_all_trains(self, frame):
        """查看所有车次时刻表（需管理员权限）"""
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showinfo("提示", "需要管理员权限", parent=self)
            return
        
        # 获取所有车次列表
        try:
            resp = self._request('GET', f"{self.client.api_base}/api/trains", timeout=10)
            if resp.status_code != 200:
                self._set_view_table(frame, ['车次', '类型', '停站数'], [])
                return
            trains = resp.json()
        except Exception as e:
            self.client.write_error_log(f"获取所有车次失败: {e}")
            self._set_view_table(frame, ['车次', '类型', '停站数'], [])
            return
        
        if not trains:
            self._set_view_table(frame, ['车次', '类型', '停站数'], [])
            return
        
        # 并发获取每个车次的详细信息（类型）
        import concurrent.futures
        train_details = {}
        
        def fetch_train_detail(train_num):
            try:
                # 从 display_name 中提取第一个车次号
                first_num = train_num.split('/')[0] if '/' in train_num else train_num
                resp = self._request('GET', f"{self.client.api_base}/api/train/{first_num}", timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    # 获取类型
                    train_type = data.get('type', '未知')
                    # 如果是 V2 数据，从 v2_data 中获取
                    if 'v2_data' in data:
                        train_type = data['v2_data'].get('numberKind', '') or data['v2_data'].get('type', '未知')
                    return train_num, train_type
                else:
                    return train_num, '未知'
            except:
                return train_num, '未知'
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(fetch_train_detail, item['number']) for item in trains]
            for future in concurrent.futures.as_completed(futures):
                num, train_type = future.result()
                train_details[num] = train_type
        
        # 构建表格数据
        rows = []
        for item in trains:
            number = item.get('number', '')
            stops = item.get('stops', 0)
            train_type = train_details.get(number, '未知')
            rows.append((number, train_type, str(stops)))
        
        self._set_view_table(frame, ['车次', '类型', '停站数'], rows)

    # ====== 查询框架 ======
    def build_query_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)

        # ---- API 查询开关 ----
        top_control_frame = tk.Frame(frame, bg='#f0f0f0')
        top_control_frame.pack(fill=tk.X, pady=(0, 5))

        # 每个 frame 独立保存自己的 API 状态
        frame._api_query_state = tk.BooleanVar(value=self.client.use_api_query)

        def on_api_toggle(*args):
            new_state = frame._api_query_state.get()
            self.client.use_api_query = new_state
            self.client.log_action("切换API查询", f"状态: {new_state}")

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
            text="当前: API实时查询" if self.client.use_api_query else "当前: 本地数据",
            bg='#f0f0f0',
            font=('微软雅黑', 9),
            fg='green' if self.client.use_api_query else 'blue'
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

    # ====== 查询子功能（全部增加正晚点支持） ======
    def _q_stop_count(self, frame):
        if self.client.use_api_query:
            self._q_stop_count_api(frame)
            return

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

            for widget in result_frame.winfo_children():
                widget.destroy()

            # ---- 获取车次数据 ----
            train_data = self.client.get_train(number)
            if not train_data.get("success"):
                tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            train = train_data["data"]
            stops = train.get('stops', [])
            display_name = train.get('display_name') or number

            # ---- 构建列车信息 ----
            info_parts = []
            info_parts.append(f"车次: {display_name}")

            train_type = train.get('type', '')
            if train_type:
                info_parts.append(f"类型: {train_type}")

            number_full = train.get('numbers', [])
            if number_full and len(number_full) > 1:
                info_parts.append(f"复车次: {', '.join(number_full)}")

            v2_data = train.get('v2_data', {})
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
            info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
            info_frame.pack(fill=tk.X, pady=5, padx=5)
            info_label = tk.Label(info_frame, text=info_text, font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
            info_label.pack(fill=tk.X, padx=10, pady=5)

            # ---- 显示停站数量 ----
            tk.Label(result_frame, text=f"该车次停靠 {len(stops)} 个站", 
                     font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_stop_count_api(self, frame):
        """API 模式：车次停站数量"""
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

            for widget in result_frame.winfo_children():
                widget.destroy()

            try:
                resp = self._request('GET', f"{self.client.api_base}/api/train/{number}", timeout=10)
                if resp.status_code != 200:
                    tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                result = resp.json()
                # 服务器端返回的格式可能是 {display_name, numbers, stops} 或 {display_name, numbers, data}
                stops = result.get('stops', [])
                if not stops and 'data' in result:
                    # V2 数据格式
                    v2_data = result.get('data', {})
                    timetable = v2_data.get('timetable', [])
                    stops = timetable
                display_name = result.get('display_name') or number
                numbers = result.get('numbers', [number])

                # 构建列车信息
                info_parts = []
                info_parts.append(f"车次: {display_name}")
                if len(numbers) > 1:
                    info_parts.append(f"复车次: {', '.join(numbers)}")

                info_text = " | ".join(info_parts)

                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                info_label = tk.Label(info_frame, text=info_text, font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left')
                info_label.pack(fill=tk.X, padx=10, pady=5)

                tk.Label(result_frame, text=f"该车次停靠 {len(stops)} 个站",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
            except Exception as e:
                tk.Label(result_frame, text=f"请求异常: {e}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

    def _q_train_detail(self, frame):
        if self.client.use_api_query:
            self._q_train_detail_api(frame)
            return

        """本地模式：车次全部经停详情（纯本地数据，不联网）"""
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        top_frame = tk.Frame(frame.display_frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        train_info_var = tk.BooleanVar(value=True)
        chk_info = tk.Checkbutton(top_frame, text="显示列车信息", variable=train_info_var, bg='#f0f0f0')
        chk_info.pack(side=tk.LEFT, padx=20)

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

            result = self.client.get_train(number)
            if not result["success"]:
                tk.Label(result_frame, text=f"本地数据库未找到车次 {number}",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            train = result["data"]
            display_name = train.get("display_name") or number
            stops = train.get('stops', [])
            if not stops:
                stops = train.get('timetable', [])
            if not stops:
                tk.Label(result_frame, text="该车次没有停站数据",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            info_parts = [f"车次: {display_name}"]
            if train.get('type') and train.get('type') != '未知':
                info_parts.append(f"类型: {train['type']}")
            info_parts.append("数据来源: 本地数据库")
            info_text = " | ".join(info_parts)

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

            for i, stop in enumerate(stops):
                station_name = stop.get('station_name') or self.client.get_station_name_by_id(stop.get('station_id')) or ''
                arrive = stop.get('arrive') or ''
                depart = stop.get('depart') or ''
                tree.insert('', 'end', values=(str(i + 1), station_name, arrive, depart))

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

            # 记录客户端查询操作
            self.client.log_action("客户端查询车次详情", number)

            for widget in result_frame.winfo_children():
                widget.destroy()

            # ---- 获取 V2 车次主数据（包含 timetable 和 trainCode） ----
            v2_data, error_type, _ = self.client.query_train_from_v2(number)
            if error_type != 'success' or not v2_data:
                tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # 获取合并组信息
            group = self.client.get_merged_by_number(number)
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
                if self.client.get_auto_update_setting():
                    pwd = self.client.api_password
                    if pwd:
                        def do_auto_update():
                            try:
                                success, msg = self.client.batch_import_train(number, "V2", pwd, auto_update=True)
                                if success:
                                    self.show_temp_message(f"{number} 已更新至本地数据库")
                                    self.client.log_action("自动更新车次", f"{number} 成功")
                                else:
                                    self.client.log_action("自动更新车次失败", f"{number}: {msg}")
                            except Exception as e:
                                self.client.log_action("自动更新车次异常", f"{number}: {str(e)}")
                        threading.Thread(target=do_auto_update, daemon=True).start()
                    else:
                        self.client.log_action("自动更新车次失败", f"{number}: 未设置管理员密码")

            # ---- 获取正晚点和检票口信息 ----
            loading_label = tk.Label(result_frame, text="正在获取数据，请稍候...", font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
            loading_label.pack(pady=20)
            btn.config(state='disabled')
            entry.config(state='disabled')

            def fetch_all():
                import concurrent.futures
                
                delay_data = None
                if delay_var.get():
                    delay_data = self.client._get_train_delay(number, timeout=5)
                
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
                                self.client._get_train_exit, 
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
                                self.client.write_error_log(f"获取检票口失败 {station_name}: {e}")
                
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
        """本地模式：某站经过的所有车次（按时间排序）"""
        if self.client.use_api_query:
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

            try:
                resp = self._request('GET',f"{self.client.api_base}/api/station/{station}/trains",
                                    params={"source": "local"}, timeout=10)
                if resp.status_code != 200:
                    tk.Label(result_frame, text=f"获取车站数据失败 (HTTP {resp.status_code})",
                             font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                station_trains = resp.json()
            except Exception as e:
                tk.Label(result_frame, text=f"请求异常: {e}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            if not station_trains:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            station_info = None
            try:
                resp = self._request('GET',f"{self.client.api_base}/api/station_info/{station}",
                                    params={"source": "local"}, timeout=5)
                if resp.status_code == 200:
                    station_info = resp.json()
            except:
                pass

            import concurrent.futures
            train_info = {}
            def fetch_train_info(train_num):
                try:
                    resp = self._request('GET',f"{self.client.api_base}/api/train/{train_num}",
                                        params={"source": "local"}, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        stops = data.get('stops', [])
                        start_station = stops[0].get('station_name', '') if stops else ''
                        end_station = stops[-1].get('station_name', '') if stops else ''
                        return train_num, data.get('display_name', train_num), data.get('numbers', [train_num]), start_station, end_station
                    else:
                        return train_num, train_num, [train_num], '', ''
                except:
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
                display_name = info['display']
                numbers = info['numbers']
                start_st = info['start']
                end_st = info['end']

                if display_name not in merged_results:
                    merged_results[display_name] = {
                        'numbers': numbers,
                        'start': start_st,
                        'end': end_st,
                        'arrive': item.get('arrive') or '',
                        'depart': item.get('depart') or '',
                        'day_offset': item.get('day_offset', 0)
                    }

            for widget in result_frame.winfo_children():
                widget.destroy()

            if station_info:
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                d = station_info
                info_parts = [f"车站: {d.get('name', station)}"]
                if d.get('telecode'): info_parts.append(f"电报码: {d['telecode']}")
                if d.get('bureau'): info_parts.append(f"路局: {d['bureau']}")
                tk.Label(info_frame, text=" | ".join(info_parts), font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left').pack(fill=tk.X, padx=10, pady=5)

            columns = ['序号', '车次', '始发站', '终点站', '到达', '出发', '跨天']
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
                display = '/'.join(numbers) if len(numbers) > 1 else display_name
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

            telecode = self.client.get_telecode(station)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not telecode:
                tk.Label(result_frame, text=f"未找到车站 '{station}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            station_data = self.client._call_v1_station_query(telecode)
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
        """本地模式：站点时刻表（通过服务器获取本地完整数据）"""
        if self.client.use_api_query:
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

            try:
                resp = self._request('GET',f"{self.client.api_base}/api/station/{station}/trains",
                                    params={"source": "local"}, timeout=10)
                if resp.status_code != 200:
                    tk.Label(result_frame, text=f"获取车站数据失败 (HTTP {resp.status_code})",
                             font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                station_trains = resp.json()
            except Exception as e:
                tk.Label(result_frame, text=f"请求异常: {e}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            if not station_trains:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            station_info = None
            try:
                resp = self._request('GET',f"{self.client.api_base}/api/station_info/{station}",
                                    params={"source": "local"}, timeout=5)
                if resp.status_code == 200:
                    station_info = resp.json()
            except:
                pass

            import concurrent.futures
            train_info = {}
            def fetch_train_info(train_num):
                try:
                    resp = self._request('GET',f"{self.client.api_base}/api/train/{train_num}",
                                        params={"source": "local"}, timeout=10)
                    if resp.status_code == 200:
                        data = resp.json()
                        stops = data.get('stops', [])
                        start_station = stops[0].get('station_name', '') if stops else ''
                        end_station = stops[-1].get('station_name', '') if stops else ''
                        return train_num, data.get('display_name', train_num), data.get('numbers', [train_num]), start_station, end_station
                    else:
                        return train_num, train_num, [train_num], '', ''
                except:
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
                display_name = info['display']
                start_st = info['start']
                end_st = info['end']

                if display_name not in merged_results:
                    merged_results[display_name] = {
                        'numbers': info['numbers'],
                        'start': start_st,
                        'end': end_st,
                        'arrive': item.get('arrive') or '',
                        'depart': item.get('depart') or '',
                        'day_offset': item.get('day_offset', 0),
                        'train_code': train_num
                    }

            merged_list = []
            for display_name, info in merged_results.items():
                time_str = info['depart'] or info['arrive']
                if not time_str: continue
                merged_list.append({
                    'display_name': display_name,
                    'numbers': info['numbers'],
                    'start': info['start'],
                    'end': info['end'],
                    'time': time_str,
                    'day_offset': info['day_offset'],
                    'arrive': info['arrive'],
                    'depart': info['depart'],
                    'train_code': info['train_code']
                })

            if not merged_list:
                tk.Label(result_frame, text=f"没有车次经过 '{station}'", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            for widget in result_frame.winfo_children():
                widget.destroy()

            if station_info:
                info_frame = tk.Frame(result_frame, bg='#f0f0f0', relief=tk.RIDGE, bd=1)
                info_frame.pack(fill=tk.X, pady=5, padx=5)
                d = station_info
                info_parts = [f"车站: {d.get('name', station)}"]
                if d.get('telecode'): info_parts.append(f"电报码: {d['telecode']}")
                if d.get('bureau'): info_parts.append(f"路局: {d['bureau']}")
                tk.Label(info_frame, text=" | ".join(info_parts), font=('微软雅黑', 10), bg='#f0f0f0', anchor='w', justify='left').pack(fill=tk.X, padx=10, pady=5)

            now = datetime.datetime.now()
            today = now.date()

            stops_with_time = []
            for item in merged_list:
                t = item.get('time')
                if not t: continue
                try:
                    time_obj = datetime.datetime.strptime(t, '%H:%M').time()
                    abs_date = today + datetime.timedelta(days=item.get('day_offset', 0))
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
                date_mark = "（昨日）" if abs_dt.date() < now.date() else ("（次日）" if abs_dt.date() > now.date() else "")
                header += f"上一班车: {item.get('display_name')}  {item.get('time')}{date_mark}\n"
            else:
                header += "上一班车: 无\n"

            if next_item:
                item, abs_dt = next_item
                date_mark = "（昨日）" if abs_dt.date() < now.date() else ("（次日）" if abs_dt.date() > now.date() else "")
                header += f"下一班车: {item.get('display_name')}  {item.get('time')}{date_mark}\n"
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
                day_info = "次日" if item.get('day_offset', 0) == 1 else "当日"
                tree.insert('', 'end', values=(str(idx), item.get('display_name'), item.get('start', ''), item.get('end', ''), item.get('arrive', ''), item.get('depart', ''), day_info))
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

            telecode = self.client.get_telecode(station)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not telecode:
                tk.Label(result_frame, text=f"未找到车站 '{station}' 的电报码",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            station_data = self.client._call_v1_station_query(telecode)
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
            result = self.client.get_train(number)
            for widget in result_frame.winfo_children():
                widget.destroy()
            if not result["success"]:
                if result["error_type"] == "timeout":
                    tk.Label(result_frame, text="未找到该车次，V2未重试", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                else:
                    tk.Label(result_frame, text=result["error"], font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            train = result["data"]
            # 直接通过站名匹配
            match = any(stop.get('station_name') == station for stop in train.get('stops', []))
            display = train.get('display_name') or train.get('base_number') or number
            result_text = f"{display} {'经停' if match else '不经停'} {station}"
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
            results = self.client.search(keyword)
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

            # 通过 get_train 统一数据源（内部会自动带 source=local 或 source=api）
            result = self.client.get_train(number)
            if not result["success"]:
                tk.Label(result_frame, text=f"未找到车次 {number}",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            train = result["data"]

            # ---- 统一停站字段到 train['stops'] ----
            stops = train.get('stops', [])
            if not stops:
                stops = train.get('timetable', [])
            if not stops:
                tk.Label(result_frame, text="该车次没有停站数据",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            # 写回 stops 字段，_render_current_position 依赖 train['stops']
            train['stops'] = stops

            display_name = train.get('display_name') or number
            if len(stops) < 2:
                tk.Label(result_frame, text="该车次停站不足，无法判断区间",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 离线模式不查正晚点 ----
            if not self.client.use_api_query:
                self._render_current_position(result_frame, train, display_name, {})
                return

            loading_label = tk.Label(result_frame, text="正在获取正晚点数据，请稍候...",
                                     font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
            loading_label.pack(pady=20)
            btn.config(state='disabled')
            entry.config(state='disabled')

            def fetch_and_calc():
                delay_data = self.client._get_train_delay(number)
                self.after(0, lambda: after_fetch(delay_data))

            def after_fetch(delay_data):
                loading_label.destroy()
                btn.config(state='normal')
                entry.config(state='normal')
                delay_map = {}
                if delay_data:
                    for item in delay_data:
                        station = item.get('stationName')
                        if station:
                            delay_map[station] = item
                self._render_current_position(result_frame, train, display_name, delay_map)

            threading.Thread(target=fetch_and_calc, daemon=True).start()

        btn.config(command=do_query)
        entry.bind('<Return>', lambda e: do_query())

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
                        station_name = self.client.get_station_name_by_id(sid)
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

    def _render_current_position_from_api(self, result_frame, stops, display_name, delay_map):
        """根据 API 返回的 stops 和显示名渲染当前位置"""
        for widget in result_frame.winfo_children():
            widget.destroy()

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
                station_name = stop.get('station_name') or self.client.get_station_name_by_id(stop.get('station_id'))
                arrive_raw = stop.get('arrive')
                depart_raw = stop.get('depart')
                day_off = stop.get('day_offset', 0)

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

        text = f"{date_label} 的 '{display_name}' 实际时刻表（已考虑正晚点）:\n"
        text += "站名         到达    出发\n"
        text += "---------------------------\n"
        for st in times:
            arrive = st['arrive'].strftime('%H:%M') if st['arrive'] else ''
            depart = st['depart'].strftime('%H:%M') if st['depart'] else ''
            text += f"{st['station_name']:<12} {arrive:<6} {depart:<6}\n"

        pos_msg = ""
        for i, st in enumerate(times):
            if st['arrive'] and st['depart'] and st['arrive'] <= now <= st['depart']:
                pos_msg = f"\n当前位置: 正在停靠 '{st['station_name']}' 站\n"
                pos_msg += f"到达：{st['arrive'].strftime('%H:%M')}  出发：{st['depart'].strftime('%H:%M')}"
                if st['offset'] != 0:
                    pos_msg += f"（正晚点偏移 {st['offset']:+d} 分钟）"
                if st['depart'] > now:
                    wait = int((st['depart'] - now).total_seconds() // 60)
                    pos_msg += f"\n距离发车还有：{wait} 分钟"
                break
        if not pos_msg:
            for i in range(len(times)-1):
                cur = times[i]
                nxt = times[i+1]
                depart_cur = cur['depart'] or cur['arrive']
                arrive_next = nxt['arrive'] or nxt['depart']
                if depart_cur and arrive_next and depart_cur <= now < arrive_next:
                    pos_msg = f"\n当前位置: 正在从 '{cur['station_name']}' 前往 '{nxt['station_name']}' 的途中\n"
                    pos_msg += f"预计到达 '{nxt['station_name']}' 时间：{arrive_next.strftime('%H:%M')}"
                    if nxt['offset'] != 0:
                        pos_msg += f"（正晚点偏移 {nxt['offset']:+d} 分钟）"
                    delta = (arrive_next - now).total_seconds() // 60
                    if delta > 0:
                        pos_msg += f"\n距离到达还有：{int(delta)} 分钟"
                    break
        if not pos_msg:
            first = times[0]
            last = times[-1]
            if first['depart'] and now < first['depart']:
                pos_msg = f"\n尚未从始发站 '{first['station_name']}' 发车"
            elif last['arrive'] and now >= last['arrive']:
                pos_msg = f"\n已到达终点站 '{last['station_name']}'"
            else:
                pos_msg = "\n无法确定列车当前位置（可能数据异常）"

        text += pos_msg
        st_widget = scrolledtext.ScrolledText(result_frame, font=('Consolas', 11), wrap=tk.WORD, bg='white')
        st_widget.pack(fill=tk.BOTH, expand=True)
        st_widget.insert(tk.END, text)
        st_widget.config(state='disabled')

    def _q_station_to_station(self, frame):
        """本地模式：两站间今日列车运行（使用服务器本地数据）"""
        if self.client.use_api_query:
            self._q_station_to_station_api(frame)
            return

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

            # ---- 客户端独立数据源：强制 local ----
            try:
                resp1 = self._request('GET', f"{self.client.api_base}/api/station/{start}/trains",
                                     params={"source": "local"}, timeout=10)
                if resp1.status_code != 200:
                    tk.Label(result_frame, text="获取起始站数据失败", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                start_trains = {item['train']: item for item in resp1.json()}
            except Exception as e:
                tk.Label(result_frame, text=f"请求异常: {e}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            try:
                resp2 = self._request('GET', f"{self.client.api_base}/api/station/{end}/trains",
                                     params={"source": "local"}, timeout=10)
                if resp2.status_code != 200:
                    tk.Label(result_frame, text="获取终止站数据失败", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                end_trains = {item['train']: item for item in resp2.json()}
            except Exception as e:
                tk.Label(result_frame, text=f"请求异常: {e}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            common_trains = set(start_trains.keys()) & set(end_trains.keys())
            if not common_trains:
                tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 方向的车次",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            import concurrent.futures
            train_details = {}

            def fetch_detail(tn):
                try:
                    detail_resp = self._request('GET', f"{self.client.api_base}/api/train/{tn}",
                                               params={"source": "local"}, timeout=10)
                    if detail_resp.status_code == 200:
                        detail = detail_resp.json()
                        stops = detail.get('stops', [])
                        station_names = []
                        for s in stops:
                            name = s.get('station_name') or self.client.get_station_name_by_id(s.get('station_id'))
                            station_names.append(name)
                        if start in station_names and end in station_names and station_names.index(start) < station_names.index(end):
                            start_idx = station_names.index(start)
                            end_idx = station_names.index(end)
                            start_stop = stops[start_idx]
                            end_stop = stops[end_idx]
                            display_name = detail.get('display_name') or tn
                            numbers = detail.get('numbers') or [tn]
                            return {
                                'train_num': tn,
                                'display_name': display_name,
                                'numbers': numbers,
                                'start_stop': start_stop,
                                'end_stop': end_stop,
                            }
                except:
                    pass
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                futures = [executor.submit(fetch_detail, tn) for tn in common_trains]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        train_details[result['train_num']] = result

            if not train_details:
                tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 方向的车次",
                         font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            groups = {}
            for tn, info in train_details.items():
                disp = info['display_name']
                groups.setdefault(disp, []).append(info)

            merged = []
            for disp, infos in groups.items():
                first = infos[0]
                numbers = sorted([info['train_num'] for info in infos])
                merged.append({
                    'display_name': disp,
                    'numbers': numbers,
                    'start_stop': first['start_stop'],
                    'end_stop': first['end_stop'],
                })

            def render_table(delay_map):
                for widget in result_frame.winfo_children():
                    widget.destroy()

                now = datetime.datetime.now()
                today = now.date()

                for item in merged:
                    start_stop = item['start_stop']
                    end_stop = item['end_stop']
                    s_time = start_stop.get('depart') or start_stop.get('arrive')
                    e_time = end_stop.get('arrive') or end_stop.get('depart')
                    s_abs = None
                    e_abs = None
                    if s_time:
                        try:
                            dt_s = datetime.datetime.strptime(s_time, '%H:%M')
                            day_off_s = start_stop.get('day_offset', 0)
                            s_abs = datetime.datetime.combine(today, dt_s.time()) + datetime.timedelta(days=day_off_s)
                        except:
                            pass
                    if e_time:
                        try:
                            dt_e = datetime.datetime.strptime(e_time, '%H:%M')
                            day_off_e = end_stop.get('day_offset', 0)
                            e_abs = datetime.datetime.combine(today, dt_e.time()) + datetime.timedelta(days=day_off_e)
                        except:
                            pass
                    if s_abs is None or e_abs is None:
                        status = '时间缺失'
                        duration = ''
                    elif now < s_abs:
                        status = f'未到达 {start}'
                        diff_minutes = int((e_abs - s_abs).total_seconds() // 60)
                        if diff_minutes > 0:
                            hours = diff_minutes // 60
                            minutes = diff_minutes % 60
                            duration = f"{hours}时{minutes}分" if hours > 0 else f"{minutes}分"
                        else:
                            duration = ''
                    elif s_abs <= now < e_abs:
                        status = f'正在 {start}->{end} 运行'
                        diff_minutes = int((e_abs - s_abs).total_seconds() // 60)
                        if diff_minutes > 0:
                            hours = diff_minutes // 60
                            minutes = diff_minutes % 60
                            duration = f"{hours}时{minutes}分" if hours > 0 else f"{minutes}分"
                        else:
                            duration = ''
                    else:
                        status = f'已到达 {end}'
                        diff_minutes = int((e_abs - s_abs).total_seconds() // 60)
                        if diff_minutes > 0:
                            hours = diff_minutes // 60
                            minutes = diff_minutes % 60
                            duration = f"{hours}时{minutes}分" if hours > 0 else f"{minutes}分"
                        else:
                            duration = ''
                    item['status'] = status
                    item['s_abs'] = s_abs
                    item['e_abs'] = e_abs
                    item['s_time'] = s_time
                    item['e_time'] = e_time
                    item['duration'] = duration

                merged_sorted = sorted(merged, key=lambda x: x['s_abs'] or datetime.datetime.max)

                just_passed = None
                coming_soon = None
                min_past_diff = None
                min_future_diff = None

                for item in merged_sorted:
                    if item['status'].startswith("已到达"):
                        diff = (now - item['e_abs']).total_seconds()
                        if diff >= 0:
                            if min_past_diff is None or diff < min_past_diff:
                                min_past_diff = diff
                                just_passed = item
                    elif item['status'].startswith("未到达"):
                        diff = (item['s_abs'] - now).total_seconds()
                        if diff >= 0:
                            if min_future_diff is None or diff < min_future_diff:
                                min_future_diff = diff
                                coming_soon = item

                header = f"经过 '{start}' -> '{end}' 区间的车次 (共 {len(merged_sorted)} 趟)\n"
                if just_passed:
                    t = just_passed['e_time']
                    if just_passed['e_abs'] and just_passed['e_abs'].date() < today:
                        t += "(昨)"
                    header += f"刚过掉: {just_passed['display_name']}（{t} 到达 {end}）"
                else:
                    header += "刚过掉: 无"
                if coming_soon:
                    t = coming_soon['s_time']
                    if coming_soon['s_abs'] and coming_soon['s_abs'].date() < today:
                        t += "(昨)"
                    header += f"\n马上进入: {coming_soon['display_name']}（{t} 从 {start} 发车）"
                else:
                    header += "\n马上进入: 无"

                tk.Label(result_frame, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT).pack(fill=tk.X, padx=5, pady=2)

                columns = ['序号', '车次', f'{start}发车', f'{end}到达', '历时', '状态']
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
                tree.bind("<Double-1>", lambda event: self._on_train_row_double_click(event, tree))
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

                idx = 1
                for item in merged_sorted:
                    disp = item['display_name']
                    s_time = item['s_time'] or ''
                    e_time = item['e_time'] or ''
                    status = item['status']
                    duration = item.get('duration', '')
                    row = (str(idx), disp, s_time, e_time, duration, status)
                    if delay_map:
                        first_tn = item['numbers'][0]
                        station_delay = delay_map.get(first_tn, {})
                        delay_status = '未获取'
                        if station_delay and start in station_delay:
                            info = station_delay[start]
                            code = info.get('delayStatusCode')
                            time_val = info.get('delayTime', 0)
                            if code in ('ON_TIME', 'ON_TIME_PREDICTION'):
                                delay_status = '正点'
                            elif code in ('DELAY', 'DELAY_PREDICTION'):
                                delay_status = f'晚点{time_val}分钟'
                            elif code in ('EARLY', 'EARLY_PREDICTION'):
                                delay_status = f'提前{time_val}分钟'
                            else:
                                delay_status = '未维护'
                        row = row + (delay_status,)
                    tree.insert('', 'end', values=row)
                    idx += 1

            if delay_var.get():
                loading_label = tk.Label(result_frame, text="正在获取所有车次正晚点数据，请稍候...",
                                         font=('微软雅黑', 12), fg='blue', bg='#f0f0f0')
                loading_label.pack(pady=20)
                btn.config(state='disabled')
                entry_start.config(state='disabled')
                entry_end.config(state='disabled')
                entry_date.config(state='disabled')

                def fetch_all():
                    delay_map = {}
                    for item in merged:
                        first_tn = item['numbers'][0]
                        delay_data = self.client._get_train_delay(first_tn, timeout=60)
                        if delay_data:
                            station_delay = {}
                            for info in delay_data:
                                st = info.get('stationName')
                                if st:
                                    station_delay[st] = info
                            delay_map[first_tn] = station_delay
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
        """API 模式：两站间今日列车运行（使用外网V1接口）"""
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

            from_telecode = self.client.get_telecode_by_station_name(start)
            to_telecode = self.client.get_telecode_by_station_name(end)
            if not from_telecode:
                tk.Label(result_frame, text=f"未找到车站 '{start}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return
            if not to_telecode:
                tk.Label(result_frame, text=f"未找到车站 '{end}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            trains = self.client._call_v1_sts_query(from_telecode, to_telecode, date)
            if trains is None:
                tk.Label(result_frame, text="获取数据失败，请检查网络连接", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            if not trains:
                tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            # ---- 构建 v1_dict ----
            v1_dict = {}
            for train in trains:
                number_full = train.get('numberFull', [])
                if number_full:
                    for num in number_full:
                        v1_dict[num] = train
                else:
                    number = train.get('number')
                    if number:
                        v1_dict[number] = train

            # ---- 处理每个车次，合并复车次 ----
            merged_results = {}
            for train in trains:
                number_full = train.get('numberFull', [train.get('number', '')])
                if not number_full:
                    number_full = [train.get('number', '')]
                display_name = '/'.join(number_full) if len(number_full) > 1 else number_full[0]
                
                if display_name not in merged_results:
                    from_depart = train.get('fromDepart', '')
                    to_arrive = train.get('toArrive', '')
                    
                    # 如果 from_depart 或 to_arrive 为空，从 timetable 中提取
                    if not from_depart or not to_arrive:
                        timetable = train.get('timetable', [])
                        from_pos = train.get('fromPos', 0)
                        to_pos = train.get('toPos', 0)
                        if timetable and from_pos < len(timetable) and to_pos < len(timetable):
                            if not from_depart:
                                from_stop = timetable[from_pos]
                                from_depart = from_stop.get('depart', '') or from_stop.get('arrive', '')
                            if not to_arrive:
                                to_stop = timetable[to_pos]
                                to_arrive = to_stop.get('arrive', '') or to_stop.get('depart', '')
                    
                    merged_results[display_name] = {
                        'numbers': number_full,
                        'from_depart': from_depart,
                        'to_arrive': to_arrive,
                        'pass_time': train.get('passTime', ''),
                        'type': train.get('type', ''),
                        'v1_train': train
                    }

            merged_list = []
            for display_name, info in merged_results.items():
                from_depart = info.get('from_depart', '')
                to_arrive = info.get('to_arrive', '')
                pass_time = info.get('pass_time', '')
                train_type = info.get('type', '')

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
            if delay_var.get():
                for item in merged_list:
                    first_num = item['numbers'][0] if item.get('numbers') else item['display_name']
                    delay_data = self.client._get_train_delay(first_num, timeout=60)
                    if delay_data:
                        for d in delay_data:
                            if d.get('stationName') == start:
                                delay_map[item['display_name']] = d
                                break

            for widget in result_frame.winfo_children():
                widget.destroy()

            if not merged_list:
                tk.Label(result_frame, text="没有获取到任何车次数据", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                return

            merged_list.sort(key=lambda x: x['s_abs'] or datetime.datetime.max)

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
                # ★★★ 修复：self.app → self.client ★★★
                result = self.client.get_train(number)
                for widget in result_frame.winfo_children():
                    widget.destroy()
                if not result["success"]:
                    tk.Label(result_frame, text=f"未找到车次 {number}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                train = result["data"]
                stops = train.get('stops', [])
                if not stops:
                    stops = train.get('timetable', [])
                if not stops:
                    start = "未知"
                    end = "未知"
                else:
                    start = stops[0].get('station_name') or stops[0].get('station', '')
                    end = stops[-1].get('station_name') or stops[-1].get('station', '')
                display_name = train.get('display_name') or number
                tk.Label(result_frame, text=f"{display_name} 始发: {start} 终点: {end}", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)

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

                # 获取电报码
                telecode = self.client.get_telecode_by_station_name(station)
                if not telecode:
                    tk.Label(result_frame, text=f"未找到车站 '{station}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                # ★★★ 调用 get_trains_start_from 方法 ★★★
                start_trains = self.client.get_trains_start_from(telecode)
                if start_trains is None:
                    tk.Label(result_frame, text="获取数据失败，请检查网络连接", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                if not start_trains:
                    tk.Label(result_frame, text=f"没有从 '{station}' 始发的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                # 渲染表格
                for widget in result_frame.winfo_children():
                    widget.destroy()
                columns = ['车次', '终点', '出发时间', '类型']
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
                    train_type = train.get('type') or train.get('numberKind') or '未知'
                    tree.insert('', 'end', values=(display_name, to_station, depart_time, train_type))

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

                # 获取起点和终点的电报码
                from_telecode = self.client.get_telecode_by_station_name(start)
                to_telecode = self.client.get_telecode_by_station_name(end)
                if not from_telecode:
                    tk.Label(result_frame, text=f"未找到车站 '{start}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return
                if not to_telecode:
                    tk.Label(result_frame, text=f"未找到车站 '{end}' 的电报码", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                # 调用 V1 站到站查询接口
                trains = self.client._call_v1_sts_query(from_telecode, to_telecode, date)
                if trains is None:
                    tk.Label(result_frame, text="获取数据失败，请检查网络连接", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                if not trains:
                    tk.Label(result_frame, text=f"没有从 '{start}' 到 '{end}' 的车次", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=20)
                    return

                # 获取正晚点（若勾选）
                delay_map = {}
                if delay_var.get():
                    for train in trains:
                        number = train.get('number')
                        if number:
                            delay_data = self.client._get_train_delay(number, timeout=60)
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

                # 渲染表格
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
        if self.client.is_admin or self.client.is_root:
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
        btn_show_pwd = tk.Button(pwd_frame, text="👁", command=toggle_pwd, width=3, font=('微软雅黑', 9))
        btn_show_pwd.pack(side=tk.LEFT)

        tip_label = tk.Label(top, text="请将物理密钥放在读卡器上", font=('微软雅黑', 9), fg='orange')
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
                success, msg = self.client.verify_admin(pwd)
                self.after(0, lambda: self._on_admin_verify_result(
                    top, success, msg, verify_btn, cancel_btn, status_label, tip_label
                ))

            threading.Thread(target=do_verify, daemon=True).start()

        verify_btn = tk.Button(top, text="验证", width=10, command=on_verify)
        cancel_btn = tk.Button(top, text="取消", width=10, command=top.destroy)
        verify_btn.pack(side=tk.LEFT, padx=20, pady=10)
        cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10)
        pwd_entry.bind('<Return>', lambda e: on_verify())

    def _on_admin_verify_result(self, top, success, msg, verify_btn, cancel_btn, status_label, tip_label):
        if not top.winfo_exists():
            return
        if success:
            top.destroy()
            self.refresh_status()
            self.display_welcome()
            self.update_edit_status()
            self._play_ding()
            messagebox.showinfo("成功", "已提升为 TADS Administrator", parent=self)
        else:
            status_label.config(text="验证失败   无权限   请重试", fg='red')
            tip_label.config(text="⚠️ 请确保物理密钥已放好，且密码正确", fg='orange')
            verify_btn.config(state='normal')
            cancel_btn.config(state='normal')

    def elevate_developer(self):
        if self.client.is_developer:
            messagebox.showinfo("提示", "已是开发者", parent=self)
            return

        # 开发者不需要读卡，直接弹出密码输入框
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
                success = self.client.verify_developer(pwd)
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
            self.update_edit_status()
            self._play_ding()
            messagebox.showinfo("成功", "已提升为 Developer", parent=self)
        else:
            status_label.config(text="验证失败   无权限   请重试", fg='red')
            verify_btn.config(state='normal')
            cancel_btn.config(state='normal')

    def elevate_root(self):
        if self.client.is_root:
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
        btn_show_pwd = tk.Button(pwd_frame, text="👁", command=toggle_pwd, width=3, font=('微软雅黑', 9))
        btn_show_pwd.pack(side=tk.LEFT)

        tip_label = tk.Label(top, text="请将物理密钥放在读卡器上", font=('微软雅黑', 9), fg='orange')
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
                success, msg = self.client.verify_root(pwd)
                self.after(0, lambda: self._on_root_verify_result(
                    top, success, msg, verify_btn, cancel_btn, status_label, tip_label
                ))

            threading.Thread(target=do_verify, daemon=True).start()

        verify_btn = tk.Button(top, text="验证", width=10, command=on_verify)
        cancel_btn = tk.Button(top, text="取消", width=10, command=top.destroy)
        verify_btn.pack(side=tk.LEFT, padx=20, pady=10)
        cancel_btn.pack(side=tk.RIGHT, padx=20, pady=10)
        pwd_entry.bind('<Return>', lambda e: on_verify())

    def _on_root_verify_result(self, top, success, msg, verify_btn, cancel_btn, status_label, tip_label):
        if not top.winfo_exists():
            return
        if success:
            top.destroy()
            self.refresh_status()
            self.display_welcome()
            self.update_edit_status()
            self._play_ding()
            messagebox.showinfo("成功", "已提升为 ROOT", parent=self)
        else:
            status_label.config(text="验证失败   无权限   请重试", fg='red')
            tip_label.config(text="⚠️ 请确保物理密钥已放好，且密码正确", fg='orange')
            verify_btn.config(state='normal')
            cancel_btn.config(state='normal')

    # ====== 设置框架 ======
    def build_settings_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        tk.Label(frame, text="客户端设置", font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=10)

        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=10)

        tk.Button(btn_frame, text="更改服务器地址", command=self._change_server_address, width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="导出日志", command=self._export_logs, width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="更改COM口", command=self._change_com_port, width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="连接PN532", command=self._connect_pn532, width=20).pack(side=tk.LEFT, padx=5)
        # 删除了 更改管理员密码 和 更改ROOT密码

        # ====== 自动更新开关按钮 ======
        current_state = self.client.get_auto_update_setting()
        btn_text = "关闭查询时自动更新该车次" if current_state else "开启查询时自动更新该车次"
        self.auto_update_btn = tk.Button(btn_frame, text=btn_text, command=self._toggle_auto_update,
                                         font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                                         width=20)
        self.auto_update_btn.pack(side=tk.LEFT, padx=5)

        display_frame = tk.Frame(frame, bg='#f0f0f0')
        display_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        frame.display_frame = display_frame
        self._set_settings_content(frame, "请选择上方设置功能")
        return frame

    def _set_settings_content(self, frame, text):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        lbl = tk.Label(frame.display_frame, text=text, font=('微软雅黑', 12), bg='#f0f0f0')
        lbl.pack(pady=20)

    def _change_server_address(self):
        top = tk.Toplevel(self)
        top.title("更改服务器地址")
        top.geometry("400x160")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="服务器IP:", font=('微软雅黑', 10)).grid(row=0, column=0, padx=5, pady=5, sticky='e')
        entry_ip = tk.Entry(top, width=20)
        entry_ip.insert(0, self.client.client_config.get('server_ip', DEFAULT_SERVER_IP))
        entry_ip.grid(row=0, column=1, padx=5, pady=5)
        tk.Label(top, text="端口:", font=('微软雅黑', 10)).grid(row=1, column=0, padx=5, pady=5, sticky='e')
        entry_port = tk.Entry(top, width=10)
        entry_port.insert(0, str(self.client.client_config.get('server_port', DEFAULT_SERVER_PORT)))
        entry_port.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        def do_change():
            ip = entry_ip.get().strip()
            try:
                port = int(entry_port.get().strip())
            except Exception:
                messagebox.showerror("错误", "端口必须是数字", parent=top)
                return
            if not ip:
                messagebox.showerror("错误", "IP不能为空", parent=top)
                return
            self.client.client_config.set('server_ip', ip)
            self.client.client_config.set('server_port', port)
            self.client.api_base = self.client.client_config.get_api_base()

            # 服务器变了，旧 token 立刻失效
            self.client._clear_token()
            self.client.is_admin = False
            self.client.is_developer = False
            self.client.is_root = False
            self.client.current_identity = "普通用户"
            self.client.api_password = None

            self.client._fetch_server_config()
            
            # 服务器变了，读卡器也重置，等待下次提权时重新枚举端口
            self.client.pn532 = None

            messagebox.showinfo("成功", f"服务器地址已更改为 {ip}:{port}，请重新提权", parent=top)
            top.destroy()
            self.refresh_status()
            self.update_edit_status()

        btn_frame = tk.Frame(top)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="确认", command=do_change, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=top.destroy, width=10).pack(side=tk.LEFT, padx=10)

    def _change_admin_pwd(self):
        current_identity = self.client.get_current_identity()
        if current_identity not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
            return
        pwd = self.client.api_password
        if not pwd:
            pwd = self._get_admin_password("更改管理员密码")
        if pwd is None:
            return
        top = tk.Toplevel(self)
        top.title("更改管理员密码")
        top.geometry("320x200")
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
            success, msg = self.client.change_admin_password(p1, pwd)
            if success:
                messagebox.showinfo("成功", msg, parent=self)
                top.destroy()
            else:
                messagebox.showerror("错误", msg, parent=top)
        tk.Button(top, text="确认", command=do_change, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _change_root_pwd(self):
        if self.client.get_current_identity() != "TADS Root":
            messagebox.showwarning("权限不足", "仅ROOT可更改ROOT密码", parent=self)
            return
        pwd = self.client.api_password
        if not pwd:
            messagebox.showerror("错误", "未设置ROOT密码", parent=self)
            return
        top = tk.Toplevel(self)
        top.title("更改ROOT密码")
        top.geometry("320x200")
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
            success, msg = self.client.change_root_password(p1, pwd)
            if success:
                messagebox.showinfo("成功", msg, parent=self)
                top.destroy()
            else:
                messagebox.showerror("错误", msg, parent=top)
        tk.Button(top, text="确认", command=do_change, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _export_logs(self):
        current_identity = self.client.get_current_identity()
        if current_identity not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
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
        
        pwd = self.client.api_password
        if not pwd:
            pwd = self._get_admin_password("导出日志")
        if pwd is None:
            return
            
        # 获取日志内容
        logs = self.client.get_recent_logs(999999, pwd)
        if not logs or "失败" in logs:
            messagebox.showerror("错误", logs or "获取日志失败", parent=self)
            return
        
        if format_choice == 'CSV':
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

    def _change_com_port(self):
        current_identity = self.client.get_current_identity()
        if current_identity not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
            return
        # 直接弹出串口选择并连接
        self._connect_pn532_with_selection(silent_on_success=False, silent_if_no_port=False)
        self.refresh_status()

    def update_edit_status(self):
        """更新编辑标签页的状态显示"""
        current_identity = self.client.get_current_identity()
        for tid, data in self.tabs.items():
            if data['title'] == "编辑":
                frame = data['content_frame']
                if hasattr(frame, 'status_label'):
                    if current_identity in ["TADS Administrator", "TADS Developer", "TADS Root"]:
                        frame.status_label.config(
                            text=f"当前身份：{current_identity}（可编辑）",
                            fg='green'
                        )
                    else:
                        frame.status_label.config(
                            text="当前身份：普通用户（需要管理员权限）",
                            fg='red'
                        )

    # ====== 日志框架 ======
    def build_log_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)

        control_frame = tk.Frame(frame, bg='#f0f0f0')
        control_frame.pack(fill=tk.X, pady=5)

        tk.Label(control_frame, text="日志类型:", bg='#f0f0f0',
                 font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        log_type_var = tk.StringVar(value='普通日志')
        log_type_combo = ttk.Combobox(control_frame, textvariable=log_type_var,
                                      values=['普通日志', '报错日志'],
                                      width=12, state='readonly')
        log_type_combo.pack(side=tk.LEFT, padx=5)

        def refresh_log_wrapper():
            self._refresh_log_in_frame(frame, log_type_var.get())
            log_type_display = log_type_var.get()
            if self.current_tab_id is not None:
                self.after(60, lambda: self.update_tab_title(
                    self.current_tab_id, f"日志-{log_type_display}"))

        tk.Button(control_frame, text="刷新", command=refresh_log_wrapper,
                  width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="保存",
                  command=lambda: self._save_log_in_frame(frame, log_type_var.get()),
                  width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="清空日志",
                  command=lambda: self._clear_log_in_frame(frame, log_type_var.get()),
                  width=10).pack(side=tk.LEFT, padx=5)

        def on_log_type_change(event):
            log_type_display = log_type_var.get()
            self._refresh_log_in_frame(frame, log_type_display)
            if self.current_tab_id is not None:
                self.after(60, lambda: self.update_tab_title(
                    self.current_tab_id, f"日志-{log_type_display}"))

        log_type_combo.bind('<<ComboboxSelected>>', on_log_type_change)

        log_text = scrolledtext.ScrolledText(
            frame, font=('Consolas', 10), wrap=tk.WORD,
            bg='white', height=20)
        log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        log_text.config(state='normal')
        frame.log_text = log_text
        frame.log_type_var = log_type_var

        self._refresh_log_in_frame(frame, '普通日志')
        if self.current_tab_id is not None:
            self.after(60, lambda: self.update_tab_title(
                self.current_tab_id, "日志-普通日志"))

        return frame

    def _refresh_log_in_frame(self, frame, log_type='普通日志'):
        if self.client.get_current_identity() not in (
                "TADS Administrator", "TADS Developer", "TADS Root"):
            messagebox.showwarning("权限不足", "您没有执行此操作的权限", parent=self)
            return

        if log_type == '普通日志':
            logs = self.client.get_recent_logs(3000)
        else:
            logs = self.client.get_recent_error_logs(3000)

        if hasattr(frame, 'log_text'):
            text_widget = frame.log_text
            text_widget.config(state='normal')
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, logs)
            text_widget.config(state='normal')
            text_widget.see(tk.END)

    def _clear_log_in_frame(self, frame, log_type='普通日志'):
        if self.client.get_current_identity() != "TADS Root":
            messagebox.showwarning("权限不足", "仅 ROOT 可清空日志", parent=self)
            return
        log_name = "普通日志" if log_type.strip() == '普通日志' else "报错日志"
        if not messagebox.askyesno("确认清空",
                                   f"确认清空 {log_name} 的所有内容？", parent=self):
            return
        
        # ★ 修复这里：严格判断，去除空格
        key = 'normal' if log_type.strip() == '普通日志' else 'error'
        ok, msg = self.client.clear_logs(key)
        if ok:
            messagebox.showinfo("成功", f"{log_name} 已清空", parent=self)
            self._refresh_log_in_frame(frame, log_type)
        else:
            messagebox.showerror("错误", f"清空失败: {msg}", parent=self)

    def _save_log_in_frame(self, frame, log_type='普通日志'):
        if self.client.get_current_identity() != "TADS Root":
            messagebox.showwarning("权限不足", "仅 ROOT 可保存日志", parent=self)
            return
        log_name = "普通日志" if log_type.strip() == '普通日志' else "报错日志"
        if not messagebox.askyesno("确认保存",
                                   f"确认将当前内容保存到 {log_name}？", parent=self):
            return
        if hasattr(frame, 'log_text'):
            content = frame.log_text.get(1.0, tk.END).rstrip('\n')
            # ★ 修复这里：严格判断，去除空格
            key = 'normal' if log_type.strip() == '普通日志' else 'error'
            ok, msg = self.client.save_logs(key, content)
            if ok:
                messagebox.showinfo("成功", f"{log_name} 已保存", parent=self)
            else:
                messagebox.showerror("错误", f"保存失败: {msg}", parent=self)

    # ====== 还原点框架 ======
    def build_restore_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=5)

        def make_restore_callback(cmd, suffix):
            def callback():
                cmd()
                if self.current_tab_id is not None:
                    self.update_tab_title(self.current_tab_id, f"还原点-{suffix}")
            return callback

        tk.Button(btn_frame, text="添加还原点（上限3个）",
                  command=make_restore_callback(self._add_restore, "添加还原点"), width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="从还原点恢复",
                  command=make_restore_callback(self._restore_from_point, "从还原点恢复"), width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="编辑还原点（删除/重命名）",
                  command=make_restore_callback(self._edit_restore, "编辑还原点"), width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="格式化所有还原点",
                  command=make_restore_callback(self._format_restore, "格式化所有还原点"), width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="刷新列表",
                  command=make_restore_callback(self._refresh_restore_list, "刷新列表"), width=20).pack(side=tk.LEFT, padx=5)

        list_frame = tk.Frame(frame, bg='#f0f0f0')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        listbox = Listbox(list_frame, font=('微软雅黑', 12), selectmode=EXTENDED)
        listbox.pack(fill=tk.BOTH, expand=True)
        frame.restore_listbox = listbox
        self._refresh_restore_list()
        return frame

    def _refresh_restore_list(self):
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            return
        pwd = self.client.api_password
        if not pwd:
            pwd = self._get_admin_password("刷新还原点")
        if pwd is None:
            return
        self.client.api_password = pwd
        self.client.update_restore_points_from_api()
        for tid, data in self.tabs.items():
            if data['title'] == "还原点":
                frame = data['content_frame']
                if hasattr(frame, 'restore_listbox'):
                    listbox = frame.restore_listbox
                    listbox.delete(0, tk.END)
                    for name in self.client.restore_points:
                        listbox.insert(tk.END, name)
                    break

    def _add_restore(self):
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
            return
        pwd = self.client.api_password
        if not pwd:
            pwd = self._get_admin_password("添加还原点")
        if pwd is None:
            return
        if len(self.client.restore_points) >= 3:
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
            if name in self.client.restore_points:
                messagebox.showinfo("提示", "名称已存在", parent=top)
                return
            success, msg = self.client.add_restore_point(name, pwd)
            if success:
                messagebox.showinfo("成功", msg, parent=self)
                top.destroy()
                self._refresh_restore_list()
            else:
                messagebox.showerror("错误", f"添加失败: {msg}", parent=top)
        tk.Button(top, text="确认", command=do_add, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _restore_from_point(self):
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
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
        pwd = self.client.api_password
        if not pwd:
            pwd = self._get_admin_password("恢复还原点")
        if pwd is None:
            return
        if not messagebox.askyesno("确认", f"从 {name} 恢复？", parent=self):
            return
        success, msg = self.client.restore_from_point(name, pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self.display_welcome()
            self._refresh_restore_list()
        else:
            messagebox.showerror("错误", f"恢复失败: {msg}", parent=self)

    def _edit_restore(self):
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
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
        pwd = self.client.api_password
        if not pwd:
            pwd = self._get_admin_password("编辑还原点")
        if pwd is None:
            return
        choice = messagebox.askquestion("编辑", f"删除 {name}？\n点击“是”删除，“否”重命名", parent=self)
        if choice == 'yes':
            if messagebox.askyesno("确认删除", f"删除 {name}？", parent=self):
                success, msg = self.client.delete_restore_point(name, pwd)
                if success:
                    messagebox.showinfo("成功", msg, parent=self)
                    self._refresh_restore_list()
                else:
                    messagebox.showerror("错误", f"删除失败: {msg}", parent=self)
        else:
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
                if new_name in self.client.restore_points:
                    messagebox.showerror("错误", "名称已存在", parent=top)
                    return
                # 先添加新名称再删除旧名称（原子性要求较高，简化处理）
                success_add, msg_add = self.client.add_restore_point(new_name, pwd)
                if success_add:
                    success_del, msg_del = self.client.delete_restore_point(name, pwd)
                    if success_del:
                        messagebox.showinfo("成功", f"已重命名为 {new_name}", parent=self)
                        top.destroy()
                        self._refresh_restore_list()
                    else:
                        # 回滚
                        self.client.delete_restore_point(new_name, pwd)
                        messagebox.showerror("错误", f"重命名失败: {msg_del}", parent=top)
                else:
                    messagebox.showerror("错误", f"添加新名称失败: {msg_add}", parent=top)
            tk.Button(top, text="确认", command=do_rename, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _format_restore(self):
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
            return
        pwd = self.client.api_password
        if not pwd:
            pwd = self._get_admin_password("格式化还原点")
        if pwd is None:
            return
        if not messagebox.askyesno("确认", "删除所有还原点？", parent=self):
            return
        success, msg = self.client.format_restore_points(pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self._refresh_restore_list()
        else:
            messagebox.showerror("错误", f"格式化失败: {msg}", parent=self)

    # ====== 车站大屏（新增，与服务器端完全一致） ======
    def open_station_screen_tab(self):
        """打开车站大屏标签页"""
        frame = self.build_station_screen_frame()
        self.add_tab("车站大屏", frame, closable=True)

    def build_station_screen_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)

        top_frame = tk.Frame(frame, bg='#f0f0f0')
        top_frame.pack(fill=tk.X, pady=5)

        tk.Label(top_frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_station = tk.Entry(top_frame, font=('微软雅黑', 10), width=15)
        entry_station.pack(side=tk.LEFT, padx=5)

        tk.Label(top_frame, text="方向:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        kind_var = tk.StringVar(value="出发")
        kind_combo = ttk.Combobox(top_frame, textvariable=kind_var, values=["出发", "到达"], width=10, state="readonly")
        kind_combo.pack(side=tk.LEFT, padx=5)

        btn = tk.Button(top_frame, text="查询", width=12)
        btn.pack(side=tk.LEFT, padx=5)

        result_frame = tk.Frame(frame, bg='#f0f0f0')
        result_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

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
            # 合并组显示（如 K973/K976）取第一个
            train_num = str(train_display).split('/')[0].strip()
            if train_num:
                self._open_train_detail_tab(train_num)

        tree.bind("<Double-1>", on_train_double_click)

        def do_query():
            for item in tree.get_children():
                tree.delete(item)
            station = entry_station.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return

            self.client.log_action("查询车站大屏", f"车站: {station}, 方向: {kind_var.get()}")

            telecode = self.client.get_telecode(station)
            if not telecode:
                messagebox.showerror("错误", f"未找到车站 '{station}' 的电报码", parent=self)
                return
            kind_display = kind_var.get()
            kind_map = {"出发": "departure", "到达": "arrival"}
            kind = kind_map.get(kind_display, "departure")

            # 使用客户端代理方法（车站大屏本身是 API 功能）
            data = self.client.get_station_big_screen(telecode, kind)
            if not data or not data.get('success'):
                error_msg = data.get('error', '请求失败') if data else '请求失败'
                messagebox.showerror("错误", f"获取大屏数据失败: {error_msg}", parent=self)
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

        btn.config(command=do_query)
        entry_station.bind('<Return>', lambda e: do_query())

        return frame

    # ====== 导航按钮 ======
    def open_home_tab(self):
        frame = self.build_home_frame()
        self.add_tab("主页", frame, closable=True)

    def open_edit_tab(self):
        # 仅ROOT可进入
        if self.client.get_current_identity() != "TADS Root":
            messagebox.showwarning("权限不足", "仅ROOT可进入编辑界面", parent=self)
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
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "需要管理员或更高权限", parent=self)
            return
        frame = self.build_settings_frame()
        self.add_tab("设置", frame, closable=True)

    def open_log_tab(self):
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "请先提权为管理员或更高权限", parent=self)
            return
        frame = self.build_log_frame()
        self.add_tab("日志", frame, closable=True)

    def open_restore_tab(self):
        if self.client.get_current_identity() not in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            messagebox.showwarning("权限不足", "请先提权为管理员或更高权限", parent=self)
            return
        frame = self.build_restore_frame()
        self.add_tab("还原点", frame, closable=True)

# ================== 启动入口 ==================
if __name__ == "__main__":
    root = MainWindow()
    root.mainloop()