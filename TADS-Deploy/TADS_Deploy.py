# -*- coding: utf-8 -*-
"""
TADS 辅助部署程序
- 内置 PN532 读卡驱动（支持直接读卡填入 UID）
- 内置 CH341 串口驱动启动入口（4225890350/CH341SER/SETUP.EXE）
"""

# ============================================================================
# TADS 兼容层 —— 仅做 CPU 二次检测
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

import time
import binascii
import json
import base64
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding


APP_CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'TADS', 'Server', 'config')
CONFIG_FILE = os.path.join(APP_CONFIG_DIR, 'config.json')
ENV_FILE = os.path.join(APP_CONFIG_DIR, '.env')
KEY_STATUS_FILE = os.path.join(APP_CONFIG_DIR, 'key_status.env')
NAME_FILE = os.path.join(APP_CONFIG_DIR, 'name.env')


# ================== 内置 PN532 读卡器驱动（仅读 UID） ==================
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
    """内置 PN532 读卡器驱动（仅读 UID）"""

    def __init__(self, port="auto", baudrate=115200, auto=True):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self._connected = False
        self._lock = threading.Lock()

        if auto or not port or (isinstance(port, str) and port.lower() == "auto"):
            auto_port = find_pn532_port(baudrate)
            if auto_port:
                self.port = auto_port
            else:
                ports = serial.tools.list_ports.comports()
                if ports:
                    self.port = ports[0].device
                else:
                    self.port = None
        if self.port:
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
            print(f"PN532 初始化失败: {e}")
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

    def _send_command(self, cmd, params=b'', timeout=0.1):
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
                self.ser.read(6)
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

    def read_card_uid(self):
        resp = self._send_command(0x4A, b'\x01\x00', timeout=0.1)
        if not resp:
            return None, None
        if resp[0] == 0xD5:
            resp = resp[1:]
        if len(resp) < 7 or resp[0] != 0x4B:
            return None, None
        if resp[1] == 0:
            return None, None
        uid_len = resp[6]
        if uid_len == 0 or len(resp) < 7 + uid_len:
            return None, None
        uid = resp[7:7 + uid_len]
        return uid.hex().upper(), uid_len

    def is_connected(self):
        return (self._connected and self.ser is not None and self.ser.is_open)

    def close(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass
        self._connected = False


# ================== 密码工具 ==================
def hash_password(password):
    salt = os.urandom(16)
    pwd_bytes = password.encode('utf-8')
    computed = hashlib.sha256(pwd_bytes + salt).digest()
    return base64.b64encode(salt + computed).decode('utf-8')


# ================== 辅助部署主程序 ==================
class DeployApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(" TADS 辅助部署程序 · QS Studio      v26.9.9")
        self.geometry("760x930")
        self.configure(bg='#f0f0f0')
        self.resizable(False, False)
        if not os.path.exists(APP_CONFIG_DIR):
            os.makedirs(APP_CONFIG_DIR)

        self.pn532 = None  # 读卡器实例（懒加载）

        try:
            self.iconbitmap(self.resource_path('ic_directions_train_128_28252.ico'))
        except Exception:
            pass

        # Toplevel 图标继承
        orig_top_init = tk.Toplevel.__init__

        def new_top_init(self_t, master=None, cnf={}, **kw):
            orig_top_init(self_t, master, cnf, **kw)
            try:
                icon = self.resource_path('ic_directions_train_128_28252.ico')
                if os.path.exists(icon):
                    self_t.iconbitmap(icon)
            except Exception:
                pass
        tk.Toplevel.__init__ = new_top_init

        self._create_widgets()

    def resource_path(self, relative_path):
        """定位内置资源：
        - 打包后：sys._MEIPASS
        - 源码运行：脚本所在目录
        """
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

    def _create_widgets(self):
        header = tk.Frame(self, bg='#2c3e50', height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="TADS 辅助部署程序",
                 font=('微软雅黑', 16, 'bold'),
                 bg='#2c3e50', fg='white').pack(pady=15)

        main_frame = tk.Frame(self, bg='#f0f0f0', padx=20, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ====== 1. 密码配置 ======
        pwd_frame = tk.LabelFrame(main_frame, text=" 角色密码配置 ",
                                   bg='#f0f0f0', font=('微软雅黑', 10, 'bold'))
        pwd_frame.pack(fill=tk.X, pady=5)

        tk.Label(pwd_frame, text="管理员 (Admin) 密码:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=0, column=0, padx=10, pady=5, sticky='e')
        self.entry_admin_pwd = tk.Entry(pwd_frame, show='*', width=25,
                                         font=('微软雅黑', 10))
        self.entry_admin_pwd.grid(row=0, column=1, padx=10, pady=5, sticky='w')

        tk.Label(pwd_frame, text="ROOT 密码:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=1, column=0, padx=10, pady=5, sticky='e')
        self.entry_root_pwd = tk.Entry(pwd_frame, show='*', width=25,
                                        font=('微软雅黑', 10))
        self.entry_root_pwd.grid(row=1, column=1, padx=10, pady=5, sticky='w')

        tk.Label(pwd_frame, text="开发者 (Developer) 用户名:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=2, column=0, padx=10, pady=5, sticky='e')
        self.entry_dev_username = tk.Entry(pwd_frame, width=25,
                                            font=('微软雅黑', 10))
        self.entry_dev_username.grid(row=2, column=1, padx=10, pady=5, sticky='w')

        tk.Label(pwd_frame, text="开发者 (Developer) 密码:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=3, column=0, padx=10, pady=5, sticky='e')
        self.entry_dev_pwd = tk.Entry(pwd_frame, show='*', width=25,
                                       font=('微软雅黑', 10))
        self.entry_dev_pwd.grid(row=3, column=1, padx=10, pady=5, sticky='w')

        # ====== 2. 物理密钥配置（带读卡 + 连接PN532） ======
        key_frame = tk.LabelFrame(
            main_frame,
            text=" 物理密钥配置 (必须至少 1 个 Admin/Both 和 1 个 ROOT/Both) ",
            bg='#f0f0f0', font=('微软雅黑', 10, 'bold'))
        key_frame.pack(fill=tk.X, pady=10)

        pn532_row = tk.Frame(key_frame, bg='#f0f0f0')
        pn532_row.grid(row=0, column=0, columnspan=6, sticky='w', padx=10, pady=(5, 3))
        tk.Button(pn532_row, text="连接PN532",
                  command=self._connect_pn532_menu,
                  bg='#2c3e50', fg='white',
                  font=('微软雅黑', 9), width=12).pack(side=tk.LEFT)
        self.label_pn532_status = tk.Label(
            pn532_row, text="读卡器状态：未连接",
            bg='#f0f0f0', font=('微软雅黑', 9), fg='red')
        self.label_pn532_status.pack(side=tk.LEFT, padx=10)

        # 密钥 1
        tk.Label(key_frame, text="密钥 1 UID:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=1, column=0, padx=10, pady=5, sticky='e')
        self.entry_uid1 = tk.Entry(key_frame, width=20,
                                    font=('微软雅黑', 10))
        self.entry_uid1.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        tk.Button(key_frame, text="读卡",
                  command=lambda: self._read_card_to_entry(self.entry_uid1),
                  width=6, font=('微软雅黑', 9),
                  bg='#2c3e50', fg='white').grid(
            row=1, column=2, padx=5, pady=5)
        self.combo_perm1 = ttk.Combobox(
            key_frame, values=['Administrator', 'ROOT', 'Both'],
            state='readonly', width=15)
        self.combo_perm1.set('Administrator')
        self.combo_perm1.grid(row=1, column=3, padx=5, pady=5, sticky='w')
        tk.Label(key_frame, text="名称:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=1, column=4, padx=5, pady=5, sticky='e')
        self.entry_name1 = tk.Entry(key_frame, width=10,
                                     font=('微软雅黑', 10))
        self.entry_name1.grid(row=1, column=5, padx=5, pady=5, sticky='w')

        # 密钥 2
        tk.Label(key_frame, text="密钥 2 UID:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=2, column=0, padx=10, pady=5, sticky='e')
        self.entry_uid2 = tk.Entry(key_frame, width=20,
                                    font=('微软雅黑', 10))
        self.entry_uid2.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        tk.Button(key_frame, text="读卡",
                  command=lambda: self._read_card_to_entry(self.entry_uid2),
                  width=6, font=('微软雅黑', 9),
                  bg='#2c3e50', fg='white').grid(
            row=2, column=2, padx=5, pady=5)
        self.combo_perm2 = ttk.Combobox(
            key_frame, values=['Administrator', 'ROOT', 'Both'],
            state='readonly', width=15)
        self.combo_perm2.set('ROOT')
        self.combo_perm2.grid(row=2, column=3, padx=5, pady=5, sticky='w')
        tk.Label(key_frame, text="名称:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=2, column=4, padx=5, pady=5, sticky='e')
        self.entry_name2 = tk.Entry(key_frame, width=10,
                                     font=('微软雅黑', 10))
        self.entry_name2.grid(row=2, column=5, padx=5, pady=5, sticky='w')

        # ====== 3. 服务器配置 ======
        net_frame = tk.LabelFrame(main_frame, text=" 服务器配置 ",
                                   bg='#f0f0f0', font=('微软雅黑', 10, 'bold'))
        net_frame.pack(fill=tk.X, pady=5)

        tk.Label(net_frame, text="服务器端 IP (内网 API):",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=0, column=0, padx=10, pady=5, sticky='e')
        self.entry_ip = tk.Entry(net_frame, width=20,
                                  font=('微软雅黑', 10))
        self.entry_ip.insert(0, "127.0.0.1")
        self.entry_ip.grid(row=0, column=1, padx=10, pady=5, sticky='w')

        tk.Label(net_frame, text="API 监听端口:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=1, column=0, padx=10, pady=5, sticky='e')
        self.entry_port = tk.Entry(net_frame, width=15,
                                    font=('微软雅黑', 10))
        self.entry_port.insert(0, "10076")
        self.entry_port.grid(row=1, column=1, padx=10, pady=5, sticky='w')

        # ====== 4. 数据库路径配置 ======
        path_frame = tk.LabelFrame(main_frame, text=" 数据库路径配置 ",
                                    bg='#f0f0f0', font=('微软雅黑', 10, 'bold'))
        path_frame.pack(fill=tk.X, pady=5)

        default_root = r"E:\数据库\TADS_Data"
        
        tk.Label(path_frame, text="数据根目录:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=0, column=0, padx=10, pady=5, sticky='e')
        self.entry_data_root = tk.Entry(path_frame, width=35,
                                         font=('微软雅黑', 10))
        self.entry_data_root.insert(0, default_root)
        self.entry_data_root.grid(row=0, column=1, padx=10, pady=5, sticky='w')

        tk.Label(path_frame, text="日志目录:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=1, column=0, padx=10, pady=5, sticky='e')
        self.entry_log_dir = tk.Entry(path_frame, width=35,
                                       font=('微软雅黑', 10))
        self.entry_log_dir.insert(0, os.path.join(default_root, "log"))
        self.entry_log_dir.grid(row=1, column=1, padx=10, pady=5, sticky='w')

        tk.Label(path_frame, text="主数据目录:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=2, column=0, padx=10, pady=5, sticky='e')
        self.entry_main_data_dir = tk.Entry(path_frame, width=35,
                                             font=('微软雅黑', 10))
        self.entry_main_data_dir.insert(0, os.path.join(default_root, "主数据"))
        self.entry_main_data_dir.grid(row=2, column=1, padx=10, pady=5, sticky='w')

        tk.Label(path_frame, text="还原点目录:",
                 bg='#f0f0f0', font=('微软雅黑', 10)).grid(
            row=3, column=0, padx=10, pady=5, sticky='e')
        self.entry_restore_dir = tk.Entry(path_frame, width=35,
                                           font=('微软雅黑', 10))
        self.entry_restore_dir.insert(0, os.path.join(default_root, "还原点"))
        self.entry_restore_dir.grid(row=3, column=1, padx=10, pady=5, sticky='w')

        # ====== 5. 串口驱动工具 ======
        driver_frame = tk.LabelFrame(main_frame, text=" 串口驱动工具 ",
                                      bg='#f0f0f0',
                                      font=('微软雅黑', 10, 'bold'))
        driver_frame.pack(fill=tk.X, pady=5)

        tk.Label(
            driver_frame,
            text=("如系统无法识别 PN532 串口设备，\n"
                  "请先点击下方按钮安装 CH341 串口驱动。\n"
                  "（驱动安装程序路径：4225890350\\CH341SER\\SETUP.EXE）"),
            bg='#f0f0f0', font=('微软雅黑', 9), fg='#7f8c8d',
            justify='left').pack(anchor='w', padx=10, pady=(5, 2))

        tk.Button(driver_frame, text="启动内置 CH341 串口驱动安装程序",
                  command=self._launch_driver_installer,
                  font=('微软雅黑', 10), bg='#2980b9', fg='white',
                  width=30).pack(anchor='w', padx=10, pady=10)

        # ====== 6. 部署按钮 ======
        btn_frame = tk.Frame(main_frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=15)
        tk.Button(btn_frame, text="一键部署并写入配置",
                  command=self._do_deploy,
                  bg='#27ae60', fg='white',
                  font=('微软雅黑', 12, 'bold'),
                  width=25).pack()

    def _connect_pn532_menu(self):
        """连接 PN532 按钮：复用主系统服务端的选择逻辑"""
        ok = self._connect_pn532_with_selection(
            silent_on_success=False, silent_if_no_port=False)
        try:
            if ok and getattr(self, 'pn532', None) is not None and self.pn532.is_connected():
                port = (self.pn532.port or '').strip()
                self.label_pn532_status.config(
                    text=f"读卡器状态：已连接（{port}）", fg='green')
            else:
                self.label_pn532_status.config(
                    text="读卡器状态：未连接", fg='red')
        except Exception:
            try:
                self.label_pn532_status.config(
                    text="读卡器状态：未连接", fg='red')
            except Exception:
                pass

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
        """把选择结果合并写入 config.json"""
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
        except Exception as e:
            print(f"保存 com_port 失败: {e}")

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
            print(f"枚举串口失败: {e}")
            if not silent_if_no_port:
                messagebox.showerror("错误", f"枚举串口失败: {e}", parent=self)
            return False

        if not ports:
            print("PN532 连接：系统未检测到任何串口设备")
            if not silent_if_no_port:
                messagebox.showerror(
                    "错误", "系统未检测到任何串口设备，请检查 PN532 是否已连接", parent=self)
            return False

        if len(ports) == 1:
            selected_port = ports[0].device
        else:
            selected_port = self._show_port_selection_dialog(ports)
            if selected_port is None:
                return False

        self._save_com_port(selected_port)

        try:
            if getattr(self, 'pn532', None) is None:
                self.pn532 = PN532Reader(port=selected_port, auto=False)
            else:
                self.pn532.port = selected_port
                self.pn532._init_reader()
        except Exception as e:
            print(f"PN532 连接失败 {selected_port}: {e}")
            if not silent_if_no_port:
                messagebox.showerror("错误", f"PN532 连接失败: {e}", parent=self)
            return False

        if self.pn532.is_connected():
            if not silent_on_success:
                messagebox.showinfo("成功", f"PN532 已连接（{selected_port}）", parent=self)
            return True
        else:
            if not silent_if_no_port:
                messagebox.showerror(
                    "错误", f"端口 {selected_port} 连接失败，请检查设备", parent=self)
            return False

    def _ensure_pn532_connected(self):
        """
        确保 PN532 已连接：
        - 已连接：直接返回 True
        - 未连接：用上次保存的 com_port 直接连接
        - 保存端口不可用/不存在：让用户重新选择
        """
        try:
            if (getattr(self, 'pn532', None) is not None
                    and self.pn532.is_connected()):
                return True
        except Exception:
            pass

        saved_port = self._get_saved_com_port()
        if saved_port:
            try:
                current_ports = {p.device.upper() for p in serial.tools.list_ports.comports()}
                if saved_port.upper() in current_ports:
                    if getattr(self, 'pn532', None) is None:
                        self.pn532 = PN532Reader(port=saved_port, auto=False)
                    else:
                        self.pn532.port = saved_port
                        self.pn532._init_reader()
                    if self.pn532.is_connected():
                        return True
            except Exception as e:
                print(f"复用端口 {saved_port} 失败: {e}")

        return self._connect_pn532_with_selection(
            silent_on_success=True, silent_if_no_port=False)

    # ==================== 内置读卡：填入 UID 输入框 ====================
    def _ensure_pn532(self):
        """兼容旧调用：委托给 _ensure_pn532_connected"""
        return self._ensure_pn532_connected()

    def _read_card_to_entry(self, entry_widget):
        """弹出读卡对话框，读到的 UID 填入 entry_widget"""
        if not self._ensure_pn532_connected():
            # 连接/选择过程已经弹过提示框
            return

        top = tk.Toplevel(self)
        top.title("请刷卡")
        top.geometry("380x160")
        top.resizable(False, False)
        top.configure(bg='#f0f0f0')
        try:
            top.grab_set()
        except Exception:
            pass

        tk.Label(top, text="请将卡片放到 PN532 读卡器上...",
                 font=('微软雅黑', 11), bg='#f0f0f0').pack(pady=20)
        status_label = tk.Label(top, text="正在读取...",
                                font=('微软雅黑', 9), fg='blue', bg='#f0f0f0')
        status_label.pack(pady=5)

        result = {'uid': None}

        def safe_ui(fn):
            try:
                if top.winfo_exists():
                    fn()
            except Exception:
                pass

        def do_read():
            deadline = time.time() + 15
            uid = None
            while time.time() < deadline:
                try:
                    u, _ = self.pn532.read_card_uid()
                    if u:
                        uid = u.upper()
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            result['uid'] = uid
            if uid:
                safe_ui(lambda: status_label.config(
                    text=f"✅ 读到 UID: {uid}", fg='green'))
                self.after(600, lambda: safe_ui(top.destroy))
            else:
                safe_ui(lambda: status_label.config(
                    text="❌ 读卡超时，未检测到卡片", fg='red'))
                self.after(1200, lambda: safe_ui(top.destroy))

        threading.Thread(target=do_read, daemon=True).start()
        self.wait_window(top)

        if result['uid']:
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, result['uid'])
        else:
            messagebox.showwarning("提示", "未读到卡片，请重试", parent=self)

    # ==================== 启动驱动安装程序 ====================
    def _launch_driver_installer(self):
        """启动 4225890350/CH341SER/SETUP.EXE（自动提权）"""
        rel = os.path.join('4225890350', 'CH341SER', 'SETUP.EXE')
        exe_path = self.resource_path(rel)

        if not os.path.exists(exe_path):
            messagebox.showerror(
                "未找到驱动安装程序",
                f"未找到：\n{exe_path}\n\n"
                f"请确认程序目录中包含 4225890350 文件夹，\n"
                f"且内部包含 CH341SER\\SETUP.EXE。\n\n"
                f"打包提示：PyInstaller 需加 --add-data \"4225890350;4225890350\"",
                parent=self)
            return

        try:
            work_dir = os.path.dirname(exe_path)
            # 通过 ShellExecuteW 以管理员权限启动
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe_path, None, work_dir, 1)
            if ret <= 32:
                messagebox.showwarning(
                    "启动失败",
                    f"ShellExecuteW 返回码: {ret}\n"
                    f"可能被用户取消，或缺少权限。",
                    parent=self)
        except Exception as e:
            messagebox.showerror("错误", f"启动失败: {e}", parent=self)

    # ==================== 部署 ====================
    def _do_deploy(self):
        admin_pwd = self.entry_admin_pwd.get().strip()
        root_pwd = self.entry_root_pwd.get().strip()
        dev_username = self.entry_dev_username.get().strip()
        dev_pwd = self.entry_dev_pwd.get().strip()
        uid1 = self.entry_uid1.get().strip().upper()
        perm1 = self.combo_perm1.get()
        name1 = self.entry_name1.get().strip()
        uid2 = self.entry_uid2.get().strip().upper()
        perm2 = self.combo_perm2.get()
        name2 = self.entry_name2.get().strip()
        ip = self.entry_ip.get().strip()

        # 获取路径输入框的值
        path_data_root = self.entry_data_root.get().strip()
        path_log_dir = self.entry_log_dir.get().strip()
        path_main_dir = self.entry_main_data_dir.get().strip()
        path_restore_dir = self.entry_restore_dir.get().strip()

        try:
            port = int(self.entry_port.get().strip())
        except Exception:
            messagebox.showerror("错误", "端口必须是数字", parent=self)
            return

        if not admin_pwd or not root_pwd:
            messagebox.showerror("错误", "管理员和ROOT密码必须填写", parent=self)
            return
        if len(admin_pwd) < 4 or len(root_pwd) < 4:
            messagebox.showerror("错误", "管理员和ROOT密码长度至少为 4 位", parent=self)
            return
        if dev_pwd and not dev_username:
            messagebox.showerror("错误", "填写开发者密码时必须同时填写开发者用户名", parent=self)
            return
        if dev_username and not dev_pwd:
            messagebox.showerror("错误", "填写开发者用户名时必须同时填写开发者密码", parent=self)
            return
        if dev_username:
            if not re.match(r'^[\u4e00-\u9fa5A-Za-z0-9_\- ]{1,32}$', dev_username):
                messagebox.showerror(
                    "错误",
                    "开发者用户名只能包含中文、字母、数字、下划线、空格、短横线，长度 1～32",
                    parent=self)
                return
            if len(dev_pwd) < 4:
                messagebox.showerror("错误", "开发者密码长度至少为 4 位", parent=self)
                return

        if not uid1 or not uid2:
            messagebox.showerror("错误", "必须填写两把物理密钥的 UID", parent=self)
            return

        keys = [(uid1, perm1, name1), (uid2, perm2, name2)]
        has_admin = any(p in ['Administrator', 'Both'] for _, p, _ in keys)
        has_root = any(p in ['ROOT', 'Both'] for _, p, _ in keys)
        if not has_admin or not has_root:
            messagebox.showerror(
                "错误",
                "密钥权限组合不合法！\n"
                "必须至少包含一个 Administrator(或Both) 和一个 ROOT(或Both)。",
                parent=self)
            return
        if uid1 == uid2:
            messagebox.showerror("错误", "两把密钥的 UID 不能相同", parent=self)
            return

        for uid in [uid1, uid2]:
            if not all(c in '0123456789ABCDEF' for c in uid) or len(uid) not in (8, 14):
                messagebox.showerror(
                    "错误",
                    f"UID {uid} 格式错误！\n必须是 8 位或 14 位十六进制。",
                    parent=self)
                return

        if not path_data_root or not path_log_dir or not path_main_dir or not path_restore_dir:
            messagebox.showerror("错误", "数据库路径不能为空", parent=self)
            return

        try:
            aes_key = os.urandom(32)
            config = {}
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)

            config['admin_password_hash'] = hash_password(admin_pwd)
            config['root_password_hash'] = hash_password(root_pwd)
            config['uid_encryption_key'] = base64.b64encode(aes_key).decode('utf-8')
            config['api_port'] = port
            config['server_ip'] = ip
            config['config_version'] = config.get('config_version', 0) + 1

            # 使用用户界面填写的路径，并覆盖旧配置
            config['paths'] = {
                'data_root': path_data_root,
                'log_dir': path_log_dir,
                'main_data_dir': path_main_dir,
                'restore_dir': path_restore_dir
            }
            
            if 'api' not in config:
                config['api'] = {
                    'v1_base': 'https://data.railgo.zenglingkun.cn/api',
                    'v2_base': 'https://rg-api.zenglingkun.cn/api/v2',
                    'emu_base': 'https://emu.railgo.zenglingkun.cn'
                }

            uid_passwords = config.get('uid_passwords', {})
            if dev_username and dev_pwd:
                iv = os.urandom(16)
                cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv),
                                backend=default_backend())
                enc = cipher.encryptor()
                padder = padding.PKCS7(128).padder()
                padded = padder.update(dev_pwd.encode('utf-8')) + padder.finalize()
                ct = enc.update(padded) + enc.finalize()
                uid_passwords[dev_username] = base64.b64encode(iv + ct).decode('utf-8')
            config['uid_passwords'] = uid_passwords

            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            admin_uids, root_uids = [], []
            if perm1 == 'Both':
                admin_uids.append(uid1); root_uids.append(uid1)
            elif perm1 == 'Administrator':
                admin_uids.append(uid1)
            else:
                root_uids.append(uid1)
            if perm2 == 'Both':
                admin_uids.append(uid2); root_uids.append(uid2)
            elif perm2 == 'Administrator':
                admin_uids.append(uid2)
            else:
                root_uids.append(uid2)

            with open(ENV_FILE, 'w', encoding='utf-8') as f:
                if admin_uids:
                    f.write(f"ADMIN_UID={','.join(admin_uids)}\n")
                if root_uids:
                    f.write(f"ROOT_UID={','.join(root_uids)}\n")

            ct1 = 'M1' if len(uid1) == 8 else 'NTAG'
            ct2 = 'M1' if len(uid2) == 8 else 'NTAG'
            with open(KEY_STATUS_FILE, 'w', encoding='utf-8') as f:
                f.write(f"{uid1}|{ct1}|{perm1}|{name1}|TRUE\n")
                f.write(f"{uid2}|{ct2}|{perm2}|{name2}|TRUE\n")
                if dev_username:
                    f.write(f"{dev_username}|--|Developer|{dev_username}|TRUE\n")

            with open(NAME_FILE, 'w', encoding='utf-8') as f:
                if name1:
                    f.write(f"NAME_{uid1}={name1}\n")
                if name2:
                    f.write(f"NAME_{uid2}={name2}\n")
                f.write(f"TYPE_{uid1}={ct1}\n")
                f.write(f"TYPE_{uid2}={ct2}\n")

            messagebox.showinfo(
                "部署成功",
                "所有配置已成功写入！\n请启动服务器端程序。",
                parent=self)
            self.destroy()
        except Exception as e:
            messagebox.showerror(
                "部署失败",
                f"写入配置文件时发生错误：\n{e}",
                parent=self)


if __name__ == "__main__":
    app = DeployApp()
    app.mainloop()