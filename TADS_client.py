# -*- coding: utf-8 -*-
"""
普通用户版 - TADS 列车到发时刻数据中心客户端
通过 HTTP API 访问服务器数据，本地不存储任何数据
作者：Michael
"""

import os
import sys
import json
import base64
import hashlib
import datetime
import socket
import subprocess
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Listbox, EXTENDED
import ctypes
import requests

# ------------------ 配置 ------------------
API_BASE_URL = "http://192.168.100.103:10076"   # 请修改为管理员电脑的实际 IP 和端口

# ------------------ 保留原常量 ------------------
ADMIN_PASSWORD_HASH     = "NiQQVpW/qkyW6tCt88og3Ho3tIInp1G9zthEPBpX9+khnHePawBolpvu/CQ97vX5"
DEVELOPER_PASSWORD_HASH = "NQ2IlFiC7aCRNDWjy+BG4/ntWb99xh214rp5b6XpG1i5JGVlR+k+ckIiyNKRtO8l"
ROOT_PASSWORD_HASH      = "j6Ic3SypiBHs+rOuVCm8Tv4U8Ydw0xxbqbMNZbNce7sLmM3OIwK30tcn0Fv118Wt"
EXPECTED_KEY_HASH       = "30ed5be94cd62b11946be4a72cee7414128cda12ae59a7f2f2b5a6687e5fef13"
EXPECTED_USB_SERIAL     = ""

RAIL_RHYTHM_ROOT   = r"E:\数据库\TADS_Data\分数据\RailRhythm12306"
CONVERT_SCRIPT      = os.path.join(RAIL_RHYTHM_ROOT, "convert_to_tads.py")
AUTO_UPDATE_SCRIPT  = os.path.join(RAIL_RHYTHM_ROOT, "auto_update.py")
TRAIN_DATA_DIR      = os.path.join(RAIL_RHYTHM_ROOT, "train_data")

DATA_ROOT    = r"E:\数据库\TADS_Data"
LOG_DIR      = os.path.join(DATA_ROOT, "log")
MAIN_DATA_DIR = os.path.join(DATA_ROOT, "主数据")
RESTORE_DIR   = os.path.join(DATA_ROOT, "还原点")
DATA_FILE     = os.path.join(MAIN_DATA_DIR, "data.json")
LOG_FILE      = os.path.join(LOG_DIR, "operations.log")
ERROR_LOG     = os.path.join(LOG_DIR, "error.log")

# ------------------ 原工具函数 ------------------
def verify_password(input_pwd, stored_hash_b64):
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

def test_physical_key():
    return True  # 普通用户版不检查物理密钥

def test_port_silent(host='localhost', port=10045, timeout=0.2):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

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

# ------------------ 核心应用类（通过 API 访问数据） ------------------
class TADSApp:
    def __init__(self, api_base_url=API_BASE_URL):
        self.api_base = api_base_url
        self.current_identity = "普通用户"
        self.is_admin = False
        self.is_developer = False
        self.is_root = False
        self.data = None
        self.restore_points = []
        self.stats = None
        self.api_password = None
        self.current_page = "主界面"
        self.api_available = False
        self._loading_data = False  # 新增：加载状态标志

        threading.Thread(target=self._load_initial_data, daemon=True).start()

    def _load_initial_data(self):
        """后台加载初始数据"""
        self._loading_data = True
        self.load_data_from_api()
        self.update_stats_from_api()
        try:
            resp = requests.get(f"{self.api_base}/api/health", timeout=3)
            self.api_available = resp.status_code == 200
        except:
            self.api_available = False
        self._loading_data = False

    # ---------- 数据加载 ----------
    def load_data_from_api(self):
        """从 API 加载数据（并行请求优化版）"""
        try:
            import concurrent.futures
            
            # 1. 获取车次列表
            resp = requests.get(f"{self.api_base}/api/trains", timeout=10)
            if resp.status_code != 200:
                self.data = {"stations": [], "trains": []}
                return
            train_list = resp.json()
            
            if not train_list:
                self.data = {"stations": [], "trains": []}
                return
            
            # 2. 并行获取所有车次详情
            def fetch_detail(item):
                try:
                    detail_resp = requests.get(
                        f"{self.api_base}/api/train/{item['number']}", 
                        timeout=10
                    )
                    if detail_resp.status_code == 200:
                        return detail_resp.json()
                    return None
                except:
                    return None
            
            trains = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                future_to_item = {executor.submit(fetch_detail, item): item for item in train_list}
                for future in concurrent.futures.as_completed(future_to_item):
                    detail = future.result()
                    if detail is not None:
                        trains.append(detail)
            
            # 3. 获取车站列表
            stations_resp = requests.get(f"{self.api_base}/api/stations", timeout=10)
            stations = stations_resp.json() if stations_resp.status_code == 200 else []
            
            self.data = {
                "stations": stations,
                "trains": trains,
                "version": "1.0",
                "last_updated": datetime.datetime.now().isoformat()
            }
        except Exception as e:
            self.data = {"stations": [], "trains": []}
            self.write_error_log(f"从 API 加载数据失败: {e}")

    def update_restore_points_from_api(self):
        if self.api_password is None:
            self.restore_points = []
            return
        try:
            resp = requests.get(f"{self.api_base}/api/admin/restore/list", params={"password": self.api_password}, timeout=10)
            if resp.status_code == 200:
                self.restore_points = resp.json()
            else:
                self.restore_points = []
        except:
            self.restore_points = []

    def update_stats_from_api(self):
        try:
            resp = requests.get(f"{self.api_base}/api/stats", timeout=10)
            if resp.status_code == 200:
                self.stats = resp.json()
            else:
                self.stats = None
        except:
            self.stats = None

    # ---------- 查询方法 ----------
    def get_train(self, number):
        if self.data and 'trains' in self.data:
            for t in self.data['trains']:
                if t['base_number'] == number:
                    return t
        return None

    def get_station_id_by_name(self, name):
        if self.data and 'stations' in self.data:
            for s in self.data['stations']:
                if s['name'] == name:
                    return s['id']
        return None

    def get_station_name_by_id(self, sid):
        if self.data and 'stations' in self.data:
            for s in self.data['stations']:
                if s['id'] == sid:
                    return s['name']
        return None

    def search(self, keyword):
        try:
            resp = requests.get(f"{self.api_base}/api/search", params={"q": keyword}, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            else:
                return []
        except:
            return []

    # ---------- 日志 ----------
    def get_recent_logs(self, lines=30, password=None):
        if password is None:
            password = self.api_password
        if password is None:
            return "需要管理员密码"
        try:
            resp = requests.get(f"{self.api_base}/api/logs", params={"password": password, "lines": lines}, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("logs", "")
            else:
                # 返回具体错误信息
                try:
                    err = resp.json().get("error", resp.text)
                except:
                    err = resp.text
                return f"获取日志失败 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return f"请求异常: {e}"

    # ---------- 写操作 ----------
    def _set_admin_password(self, pwd):
        self.api_password = pwd

    def _do_post(self, endpoint, data, password=None):
        """通用 POST 请求，返回 (success, message)"""
        if password is None:
            password = self.api_password
        if password is None:
            return False, "未设置管理员密码"
        data['password'] = password
        try:
            resp = requests.post(f"{self.api_base}{endpoint}", json=data, timeout=30)
            if resp.status_code == 200:
                return True, resp.json().get("message", "操作成功")
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except:
                    err = resp.text
                return False, f"服务器错误 (HTTP {resp.status_code}): {err}"
        except Exception as e:
            return False, f"网络异常: {e}"

    def add_train(self, number, password=None):
        success, msg = self._do_post("/api/admin/add_train", {"number": number}, password)
        if success:
            # 使用异步加载，不阻塞界面
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

    # ---------- 还原点 ----------
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

    def update_restore_points(self):
        self.update_restore_points_from_api()

    # ---------- 更新数据 ----------
    def update_train_data(self, password=None):
        if password is None:
            password = self.api_password
        if password is None:
            return {"success": False, "error": "需要管理员密码"}
        try:
            resp = requests.post(f"{self.api_base}/api/admin/update_data", json={"password": password}, timeout=300)
            if resp.status_code == 200:
                threading.Thread(target=self.load_data_from_api, daemon=True).start()
                return resp.json()
            else:
                try:
                    err = resp.json().get("error", resp.text)
                except:
                    err = resp.text
                return {"success": False, "error": f"更新失败 (HTTP {resp.status_code}): {err}"}
        except Exception as e:
            return {"success": False, "error": f"网络异常: {e}"}

    # ---------- 日志记录 ----------
    def log_action(self, action, detail=""):
        pass

    def write_log(self, message):
        pass

    def write_error_log(self, message):
        print(f"错误: {message}")

    # ---------- 身份管理 ----------
    def set_identity(self, identity, password=None):
        self.current_identity = identity
        if identity == "TADS Administrator":
            self.is_admin = True
            self.is_developer = False
            self.is_root = False
            if password:
                self._set_admin_password(password)
        elif identity == "TADS Developer":
            self.is_admin = False
            self.is_developer = True
            self.is_root = False
            if password and self.api_password is None:
                self._set_admin_password(password)
        elif identity == "TADS Root":
            self.is_admin = False
            self.is_developer = False
            self.is_root = True
            if password and self.api_password is None:
                self._set_admin_password(password)
        else:
            self.is_admin = False
            self.is_developer = False
            self.is_root = False
            self.current_identity = "普通用户"

    def get_current_identity(self):
        return self.current_identity

# ------------------ 主窗口 ------------------
class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app = TADSApp(api_base_url=API_BASE_URL)
        self.title("TADS 列车到发时刻数据中心客户端")
        self.geometry("1400x850")
        self.minsize(1200, 750)
        self.configure(bg='#f0f0f0')
        self.is_fullscreen = False

        # 菜单栏
        menubar = tk.Menu(self)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="全屏", command=self.toggle_fullscreen)
        menubar.add_cascade(label="视图", menu=view_menu)
        self.config(menu=menubar)

        # 状态栏
        self.status_frame = tk.Frame(self, bg='#d9d9d9', height=30)
        self.status_frame.pack(side=tk.TOP, fill=tk.X)
        self.status_label = tk.Label(self.status_frame, text="", font=('微软雅黑', 9), bg='#d9d9d9')
        self.status_label.pack(side=tk.LEFT, padx=5)
        self.update_status()

        # 主面板
        main_panel = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5, bg='#f0f0f0')
        main_panel.pack(fill=tk.BOTH, expand=True)

        # 左侧导航
        self.left_nav = tk.Frame(main_panel, bg='#2c3e50', width=200)
        main_panel.add(self.left_nav, width=200, minsize=180)

        # 右侧容器
        self.right_container = tk.Frame(main_panel, bg='#f0f0f0')
        main_panel.add(self.right_container, width=1000, minsize=800)

        # 标签栏
        tab_bar_frame = tk.Frame(self.right_container, bg='#d0d0d0', height=45)
        tab_bar_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 2))
        tab_bar_frame.pack_propagate(False)
        self.tab_bar_frame = tab_bar_frame
        self.tab_container = tk.Frame(tab_bar_frame, bg='#d0d0d0')
        self.tab_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tab_container.bind("<Configure>", self._on_tab_container_resize)

        # 内容区域
        self.content_area = tk.Frame(self.right_container, bg='#f0f0f0')
        self.content_area.pack(fill=tk.BOTH, expand=True)

        # 标签管理
        self.tabs = {}
        self.tab_counter = 0
        self.current_tab_id = None

        # 导航按钮
        nav_buttons = [
            ("主页", self.open_home_tab),
            ("编辑", self.open_edit_tab),
            ("查看", self.open_view_tab),
            ("查询", self.open_query_tab),
            ("提权", self.open_privilege_tab),
            ("日志", self.open_log_tab),
            ("还原点", self.open_restore_tab)
        ]
        for text, cmd in nav_buttons:
            btn = tk.Button(self.left_nav, text=text, command=cmd,
                            font=('微软雅黑', 11), bg='#34495e', fg='white',
                            activebackground='#1abc9c', activeforeground='white',
                            relief=tk.FLAT, bd=0, anchor='w', padx=20, pady=12)
            btn.pack(fill=tk.X, pady=2)

        tk.Frame(self.left_nav, bg='#2c3e50').pack(fill=tk.BOTH, expand=True)

        self.open_home_tab()
        self.after(5000, self.refresh_status)

    # ---------- 辅助方法 ----------
    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes('-fullscreen', self.is_fullscreen)

    def update_status(self):
        now = datetime.datetime.now().strftime("%Y/%m/%d-%H:%M")
        identity = self.app.get_current_identity()
        hub_open = test_port_silent()
        hub_status = "运行中" if hub_open else "未运行"
        hub_count = get_hub_count() if hub_open else 0
        api_status = "已连接" if self.app.api_available else "未连接"
        status_text = (f"当前页面：{self.app.current_page} | 身份：{identity} | 系统时间：{now} | "
                       f"中枢站：{hub_status} | 访问人数：{hub_count}人 | API：{api_status}")
        self.status_label.config(text=status_text)

    def refresh_status(self):
        self.update_status()
        self.after(5000, self.refresh_status)

    # ---------- 密码验证 ----------
    def _get_admin_password(self, purpose="操作"):
        if self.app.api_password is not None:
            try:
                resp = requests.get(f"{self.app.api_base}/api/logs", params={"password": self.app.api_password, "lines": 1}, timeout=5)
                if resp.status_code == 200:
                    return self.app.api_password
                else:
                    self.app.api_password = None
            except:
                self.app.api_password = None
        top = tk.Toplevel(self)
        top.title("管理员验证")
        top.geometry("320x140")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text=f"请输入管理员密码（{purpose}）:", font=('微软雅黑', 10)).pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        pwd_entry.pack(pady=5)
        result = tk.StringVar()

        def do_verify():
            pwd = pwd_entry.get()
            try:
                resp = requests.get(f"{self.app.api_base}/api/logs", params={"password": pwd, "lines": 1}, timeout=5)
                if resp.status_code == 200:
                    self.app.api_password = pwd
                    result.set(pwd)
                    top.destroy()
                else:
                    # 显示具体错误
                    try:
                        err = resp.json().get("error", resp.text)
                    except:
                        err = resp.text
                    messagebox.showerror("错误", f"密码验证失败 (HTTP {resp.status_code}): {err}", parent=top)
            except Exception as e:
                messagebox.showerror("错误", f"无法连接到服务器: {e}", parent=top)

        def on_cancel():
            result.set(None)
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="确定", command=do_verify, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

        self.wait_window(top)
        pwd = result.get()
        return pwd if pwd else None

    # ---------- 标签管理 ----------
    def show_placeholder(self):
        if hasattr(self, 'tab_bar_frame'):
            self.tab_bar_frame.pack_forget()
        for widget in self.content_area.winfo_children():
            widget.destroy()
        container = tk.Frame(self.content_area, bg='#f0f0f0')
        container.pack(fill=tk.BOTH, expand=True)
        big_font = ('微软雅黑', 28, 'bold')
        title_label = tk.Label(container, text="欢迎使用\nTADS列车到发时刻数据中心客户端", font=big_font, bg='#f0f0f0', justify='center')
        title_label.pack(expand=True, pady=(50, 0))
        small_font = ('微软雅黑', 10)
        small_text = (
            "请合法合规使用本系统\n"
            "本客户端通过 API 连接服务器，所有数据存储在服务器端\n"
            "如需修改数据，请联系管理员获取密码\n\n"
            "附属公司：龙岩市量子跃动有限责任公司\n"
            "开发者/负责人：Michael、linchenlang\n"
            "(linchenlang@outlook.com)"
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
        tab_card = tk.Frame(self.tab_container, bg='#e0e0e0', relief=tk.RAISED, bd=1,
                            width=preferred_width, height=38)
        tab_card.pack(side=tk.LEFT, fill=tk.NONE, expand=False, padx=1, pady=2)
        tab_card.pack_propagate(False)
        title_label = tk.Label(tab_card, text=title, font=font, bg='#e0e0e0', anchor='w')
        title_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 2), pady=2)
        if closable:
            close_btn = tk.Button(tab_card, text="×", font=('微软雅黑', 10, 'bold'),
                                  bg='#e0e0e0', fg='#666', relief=tk.FLAT,
                                  command=lambda tid=tab_id: self.close_tab(tid),
                                  width=2, height=1)
            close_btn.place(relx=1.0, x=-4, y=2, anchor='ne')
        else:
            close_btn = None
        self.tabs[tab_id] = {
            'title': title,
            'content_frame': content_frame,
            'tab_card': tab_card,
            'title_label': title_label,
            'close_btn': close_btn,
            'preferred_width': preferred_width
        }
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
        if self.current_tab_id == tab_id:
            other_id = None
            for tid in self.tabs:
                if tid != tab_id:
                    other_id = tid
                    break
            if other_id is not None:
                self.switch_tab(other_id)
        data = self.tabs[tab_id]
        data['tab_card'].destroy()
        data['content_frame'].destroy()
        del self.tabs[tab_id]
        self.reflow_tabs()
        if self.current_tab_id == tab_id and self.tabs:
            first_id = next(iter(self.tabs))
            self.switch_tab(first_id)
        elif not self.tabs:
            self.show_placeholder()
            self.current_tab_id = None
            self.app.current_page = "无标签"
            self.update_status()
        self.update_status()

    # ---------- 构建主页 ----------
    def build_home_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        tk.Label(frame, text="欢迎使用 TADS 列车到发时刻数据中心客户端", font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=10)
        home_text = scrolledtext.ScrolledText(frame, font=('Consolas', 12), wrap=tk.WORD, bg='white', height=20)
        home_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        home_text.config(state='disabled')
        frame.home_text = home_text
        self._display_welcome_to_text(home_text)
        return frame

    def _display_welcome_to_text(self, text_widget):
        text_widget.config(state='normal')
        text_widget.delete(1.0, tk.END)
        self.app.update_stats_from_api()
        last_write = ""
        if self.app.data and 'last_updated' in self.app.data:
            last_write = self.app.data['last_updated']
        else:
            last_write = "无数据"
        info = f"""\n\n
                                                                  T A D S  列  车  到  发  时  刻  数  据  中  心  客  户  端
                                                                  Train Arrival & Departure Schedule Data Center Client 
                                                                                          T A D S

                                                                             · 数据库最后更新：{last_write}
"""
        if self.app.stats:
            s = self.app.stats
            info += f"                                                                             · 数据库记录车站数：{s.get('station_count', 0)} 个\n"
            info += f"                                                                             · 数据库记录车次数：{s.get('train_count', 0)} 个\n"
            if s.get('train_count', 0) > 0:
                info += f"                                                                               平均每趟车停靠 {s.get('avg_stops', 0)} 个站\n"
            if s.get('busy_station_name'):
                info += f"                                                                               经过列车最多的车站：{s['busy_station_name']} ({s.get('busy_station_count', 0)}趟)\n"
        else:
            info += "                                                                             · 数据库尚未加载或数据为空。\n"
        info += "\n                                                                             （普通用户版，数据通过 API 访问）"
        text_widget.insert(tk.END, info)
        text_widget.config(state='disabled')

    def display_welcome(self):
        for tid, data in self.tabs.items():
            if data['title'] == "主页":
                frame = data['content_frame']
                if hasattr(frame, 'home_text'):
                    self._display_welcome_to_text(frame.home_text)

    # ---------- 编辑框架 ----------
    def build_edit_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        current_identity = self.app.get_current_identity()
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

        def update_data_wrapper():
            self._update_data()
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-更新数据")
        tk.Button(op_frame, text="从 RailRhythm 更新数据", command=update_data_wrapper, width=30).grid(row=4, column=0, columnspan=3, pady=10)

        stop_form_frame = tk.Frame(frame, bg='#f0f0f0')
        stop_form_frame.pack(fill=tk.X, pady=5)
        frame.stop_form_frame = stop_form_frame

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

    # ---------- 编辑功能实现 ----------
    def _add_train(self, entry):
        number = entry.get().strip()
        if not number:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        if re.search(r'[<>:"/\\|?*]', number):
            messagebox.showerror("错误", "车次号包含非法字符", parent=self)
            return
        if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
            pwd = self.app.api_password
        else:
            pwd = self._get_admin_password("新增车次")
        if pwd is None:
            return
        success, msg = self.app.add_train(number, pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self.display_welcome()
            entry.delete(0, tk.END)
            self.app.update_stats_from_api()
            # 延迟刷新状态，等待数据加载
            self.after(1000, self.refresh_status)
        else:
            messagebox.showerror("错误", f"添加失败: {msg}", parent=self)

    def _del_train(self, entry):
        number = entry.get().strip()
        if not number:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        train = self.app.get_train(number)
        if not train:
            messagebox.showerror("错误", "未找到该车次", parent=self)
            return
        if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
            pwd = self.app.api_password
        else:
            pwd = self._get_admin_password("删除车次")
        if pwd is None:
            return
        if not messagebox.askyesno("确认", f"确认删除 {number} 及其所有停站？", parent=self):
            return
        success, msg = self.app.delete_train(number, pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self.display_welcome()
            entry.delete(0, tk.END)
            self.app.update_stats_from_api()
            self.after(1000, self.refresh_status)
        else:
            messagebox.showerror("错误", f"删除失败: {msg}", parent=self)

    def _show_add_stop_form(self, parent_frame, entry_train):
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
            station = entry_station.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入站名", parent=self)
                return
            arrive = entry_arrive.get().strip() or None
            depart = entry_depart.get().strip() or None
            day_str = entry_day.get().strip()
            day_offset = int(day_str) if day_str.isdigit() else 0
            if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
                pwd = self.app.api_password
            else:
                pwd = self._get_admin_password("录入停站")
            if pwd is None:
                return
            success, msg = self.app.add_stop(train_num, station, arrive, depart, day_offset, pwd)
            if success:
                messagebox.showinfo("成功", msg, parent=self)
                self.display_welcome()
                for widget in parent_frame.stop_form_frame.winfo_children():
                    widget.destroy()
                self.app.update_stats_from_api()
                self.after(1000, self.refresh_status)
            else:
                messagebox.showerror("错误", f"录入失败: {msg}", parent=self)

    def _show_del_stop_form(self, parent_frame, entry_train):
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
            try:
                idx = int(tk.simpledialog.askstring("删除", "请输入要删除的序号:", parent=self))
                if idx is None:
                    return
                if idx < 1 or idx > len(train['stops']):
                    messagebox.showerror("错误", "序号无效", parent=self)
                    return
                if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
                    pwd = self.app.api_password
                else:
                    pwd = self._get_admin_password("删除停站")
                if pwd is None:
                    return
                if messagebox.askyesno("确认删除", f"确认删除序号 {idx} 的停站？", parent=self):
                    success, msg = self.app.delete_stop(train_num, idx, pwd)
                    if success:
                        messagebox.showinfo("成功", msg, parent=self)
                        self.display_welcome()
                        self._show_del_stop_form(parent_frame, entry_train)
                        self.app.update_stats_from_api()
                        self.after(1000, self.refresh_status)
                    else:
                        messagebox.showerror("错误", f"删除失败: {msg}", parent=self)
            except:
                pass

    def _update_data(self):
        if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
            pwd = self.app.api_password
        else:
            pwd = self._get_admin_password("更新数据")
        if pwd is None:
            return
        current_tab = self.current_tab_id
        display = None
        if current_tab is not None and current_tab in self.tabs:
            frame = self.tabs[current_tab]['content_frame']
            if hasattr(frame, 'edit_display'):
                display = frame.edit_display
                display.config(state='normal')
                display.delete(1.0, tk.END)
                display.insert(tk.END, "正在请求更新数据...\n")
                display.update()
        
        # 在后台线程执行更新
        def do_update():
            result = self.app.update_train_data(pwd)
            if result.get('success'):
                self.after(0, lambda: messagebox.showinfo("成功", "数据更新完成！", parent=self))
                if display:
                    self.after(0, lambda: display.insert(tk.END, "更新完成。\n"))
                    self.after(0, lambda: display.config(state='disabled'))
                self.after(0, self.app.update_stats_from_api)
                self.after(0, self.display_welcome)
                self.after(1000, self.refresh_status)
            else:
                error_msg = result.get('error', '未知错误')
                self.after(0, lambda: messagebox.showerror("错误", f"数据更新失败: {error_msg}", parent=self))
                if display:
                    self.after(0, lambda: display.insert(tk.END, f"错误: {error_msg}\n"))
                    self.after(0, lambda: display.config(state='disabled'))
        
        threading.Thread(target=do_update, daemon=True).start()

    # ---------- 查看框架 ----------
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
        if not self.app.data or not self.app.data.get('trains'):
            self._set_view_table(frame, ['名次', '车次', '停站数'], [])
            return
        ranked = sorted(self.app.data['trains'], key=lambda t: len(t.get('stops', [])), reverse=True)
        top = ranked[:20]
        rows = [(str(i+1), t['base_number'], str(len(t.get('stops', [])))) for i, t in enumerate(top)]
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
            train = self.app.get_train(number)
            if not train:
                self._set_view_table(frame, ['序号', '站名', '到达', '出发', '跨天'], [])
                return
            columns = ['序号', '站名', '到达', '出发', '跨天']
            rows = []
            for i, stop in enumerate(train.get('stops', [])):
                name = self.app.get_station_name_by_id(stop['station_id'])
                rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or '', str(stop.get('day_offset', 0))))
            self._set_view_table(frame, columns, rows)
        entry.bind('<Return>', lambda e: do_view())
        tk.Button(f, text="查看", command=do_view, width=12).pack(side=tk.LEFT, padx=5)

    def _view_all_trains(self, frame):
        if not self._ensure_admin():
            return
        if not self.app.data:
            self._set_view_table(frame, ['车次', '类型', '停站数'], [])
            return
        columns = ['车次', '类型', '停站数']
        rows = [(t['base_number'], t.get('type', '未知'), str(len(t.get('stops', [])))) for t in self.app.data.get('trains', [])]
        self._set_view_table(frame, columns, rows)

    # ---------- 查询框架 ----------
    def build_query_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        sub_frame = tk.Frame(frame, bg='#f0f0f0')
        sub_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        btn_list = [
            ("车次停站数量", self._q_stop_count),
            ("车次全部经停详情", self._q_train_detail),
            ("某站经过的所有车次", self._q_station_trains),
            ("站点时刻表（含上一/下一班）", self._q_station_schedule),
            ("车次/站点匹配校验", self._q_match),
            ("全局搜索引擎", self._q_search),
            ("车次当前理论位置", self._q_current_position),
            ("两站间今日列车运行", self._q_station_to_station),
            ("车站↔车次查询（含子功能）", self._q_bidirectional)
        ]
        for text, cmd in btn_list:
            def make_callback(cmd, frame, title_suffix):
                def callback():
                    cmd(frame)
                    if self.current_tab_id is not None:
                        self.update_tab_title(self.current_tab_id, f"查询-{title_suffix}")
                return callback
            btn = tk.Button(sub_frame, text=text,
                            command=make_callback(cmd, frame, text),
                            font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                            width=26, anchor='w', padx=5)
            btn.pack(pady=2)

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

    # 查询子功能（安全访问 data）
    def _q_stop_count(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(f, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self._set_query_content(frame, "未找到该车次")
                return
            self._set_query_content(frame, f"{number} 停靠 {len(train.get('stops', []))} 个站")
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_train_detail(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(f, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self._set_query_content(frame, "未找到该车次")
                return
            columns = ['序号', '站名', '到达', '出发']
            rows = []
            for i, stop in enumerate(train.get('stops', [])):
                name = self.app.get_station_name_by_id(stop['station_id'])
                rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or ''))
            self._set_query_table(frame, columns, rows)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_station_trains(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(f, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return
            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                self._set_query_content(frame, "未找到该车站")
                return
            found = []
            if self.app.data:
                for train in self.app.data.get('trains', []):
                    for stop in train.get('stops', []):
                        if stop['station_id'] == sid:
                            found.append((train, stop))
                            break
            if not found:
                self._set_query_content(frame, f"没有车次经过 '{station}'")
                return
            columns = ['车次', '到达', '出发', '跨天']
            rows = []
            def sort_key(item):
                stop = item[1]
                t = stop.get('depart') or stop.get('arrive')
                if t:
                    try:
                        dt = datetime.datetime.strptime(t, '%H:%M')
                        dt = dt.replace(day=dt.day + stop.get('day_offset', 0))
                        return dt
                    except:
                        pass
                return datetime.datetime.max
            for train, stop in sorted(found, key=sort_key):
                arrive = stop.get('arrive') if stop.get('arrive') else "始发"
                depart = stop.get('depart') if stop.get('depart') else "终到"
                day_info = "次日" if stop.get('day_offset', 0) == 1 else "当天"
                rows.append((train['base_number'], arrive, depart, day_info))
            self._set_query_table(frame, columns, rows)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_station_schedule(self, frame):
        # 清空显示区域
        for widget in frame.display_frame.winfo_children():
            widget.destroy()

        # 输入框
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(f, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)

        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return

            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                self._set_query_content(frame, "未找到该车站")
                return

            # 找出所有经过该站的车次
            found = []
            if self.app.data:
                for train in self.app.data.get('trains', []):
                    for stop in train.get('stops', []):
                        if stop['station_id'] == sid:
                            found.append((train, stop))
                            break

            if not found:
                self._set_query_content(frame, f"没有车次经过 '{station}'")
                return

            now = datetime.datetime.now()
            # 构建每个停站的绝对时间（日期+时间）
            stops_with_time = []
            for train, stop in found:
                t = stop.get('depart') or stop.get('arrive')
                if not t:
                    continue
                try:
                    time_obj = datetime.datetime.strptime(t, '%H:%M').time()
                    day_off = stop.get('day_offset', 0)
                    base_date = now.date()
                    abs_date = base_date + datetime.timedelta(days=day_off)
                    abs_dt = datetime.datetime.combine(abs_date, time_obj)
                    stops_with_time.append((train, stop, abs_dt))
                except Exception as e:
                    print(f"解析时间失败: {t}, 错误: {e}")
                    continue

            if not stops_with_time:
                self._set_query_content(frame, "该站没有有效时刻数据")
                return

            # 按绝对时间排序
            stops_with_time.sort(key=lambda x: x[2])

            # 找出上一班和下一班
            prev_item = None
            next_item = None
            for train, stop, abs_dt in stops_with_time:
                if abs_dt < now:
                    prev_item = (train, stop, abs_dt)
                else:
                    next_item = (train, stop, abs_dt)
                    break

            # 构建 header
            header = f"当前时间: {now.strftime('%H:%M')}\n"
            if prev_item:
                train, stop, abs_dt = prev_item
                t = stop.get('depart') or stop.get('arrive')
                if abs_dt.date() < now.date():
                    date_mark = "（昨日）"
                elif abs_dt.date() > now.date():
                    date_mark = "（次日）"
                else:
                    date_mark = ""
                header += f"上一班车: {train['base_number']}  {t}{date_mark}\n"
            else:
                header += "上一班车: 无\n"

            if next_item:
                train, stop, abs_dt = next_item
                t = stop.get('depart') or stop.get('arrive')
                if abs_dt.date() < now.date():
                    date_mark = "（昨日）"
                elif abs_dt.date() > now.date():
                    date_mark = "（次日）"
                else:
                    date_mark = ""
                header += f"下一班车: {train['base_number']}  {t}{date_mark}\n"
            else:
                header += "下一班车: 无\n"

            header += "=" * 50 + "\n所有经过该站的车次:\n"

            # 清空显示区域，重新构建
            for widget in frame.display_frame.winfo_children():
                widget.destroy()

            # 添加 header 标签
            header_label = tk.Label(frame.display_frame, text=header,
                                   font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT)
            header_label.pack(fill=tk.X, padx=5, pady=2)

            # 构建表格
            columns = ['序号', '车次', '到达', '出发', '跨天']
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

            for idx, (train, stop, abs_dt) in enumerate(stops_with_time, 1):
                arrive = stop.get('arrive') if stop.get('arrive') else "始发"
                depart = stop.get('depart') if stop.get('depart') else "终到"
                day_info = "次日" if stop.get('day_offset', 0) == 1 else "当天"
                tree.insert('', 'end', values=(str(idx), train['base_number'], arrive, depart, day_info))

        entry.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_match(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_train = tk.Entry(f, font=('微软雅黑', 10), width=12)
        entry_train.pack(side=tk.LEFT, padx=5)
        tk.Label(f, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_station = tk.Entry(f, font=('微软雅黑', 10), width=12)
        entry_station.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry_train.get().strip()
            station = entry_station.get().strip()
            if not number or not station:
                messagebox.showwarning("提示", "请输入车次和车站", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self._set_query_content(frame, "未找到该车次")
                return
            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                self._set_query_content(frame, "未找到该车站")
                return
            match = any(stop['station_id'] == sid for stop in train.get('stops', []))
            self._set_query_content(frame, f"{number} {'经停' if match else '不经停'} {station}")
        entry_train.bind('<Return>', lambda e: do_query())
        entry_station.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="匹配", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_search(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="关键词:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(f, font=('微软雅黑', 10), width=20)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            keyword = entry.get().strip()
            if not keyword:
                messagebox.showwarning("提示", "请输入关键词", parent=self)
                return
            results = self.app.search(keyword)
            if not results:
                self._set_query_content(frame, "未找到匹配项")
                return
            columns = ['类型', '名称', '详情']
            rows = [(r['type'], r['name'], r['detail']) for r in results]
            self._set_query_table(frame, columns, rows)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="搜索", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_current_position(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(f, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self._set_query_content(frame, "未找到该车次")
                return
            stops = train.get('stops', [])
            if len(stops) < 2:
                self._set_query_content(frame, "该车次停站不足，无法判断区间")
                return
            now = datetime.datetime.now()
            today = now.date()
            def build_time_table(base_date):
                table = []
                last_time = None
                for stop in stops:
                    arrive_raw = stop.get('arrive')
                    depart_raw = stop.get('depart')
                    day_off = stop.get('day_offset', 0)
                    arrive_dt = None
                    depart_dt = None
                    if arrive_raw:
                        try:
                            dt = datetime.datetime.strptime(arrive_raw, '%H:%M')
                            arrive_dt = datetime.datetime.combine(base_date, dt.time()) + datetime.timedelta(days=day_off)
                        except:
                            pass
                    if depart_raw:
                        try:
                            dt = datetime.datetime.strptime(depart_raw, '%H:%M')
                            depart_dt = datetime.datetime.combine(base_date, dt.time()) + datetime.timedelta(days=day_off)
                        except:
                            pass
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
                        'station_name': self.app.get_station_name_by_id(stop['station_id']),
                        'arrive': arrive_dt,
                        'depart': depart_dt
                    })
                return table
            times_today = build_time_table(today)
            first_depart = times_today[0]['depart'] or times_today[0]['arrive']
            last_arrive = times_today[-1]['arrive'] or times_today[-1]['depart']
            today_running = first_depart and last_arrive and first_depart <= now <= last_arrive
            yesterday = today - datetime.timedelta(days=1)
            times_yesterday = build_time_table(yesterday)
            first_depart_y = times_yesterday[0]['depart'] or times_yesterday[0]['arrive']
            last_arrive_y = times_yesterday[-1]['arrive'] or times_yesterday[-1]['depart']
            yesterday_running = first_depart_y and last_arrive_y and first_depart_y <= now <= last_arrive_y
            if yesterday_running:
                times = times_yesterday; date_label = "昨天"
            elif today_running:
                times = times_today; date_label = "今天"
            else:
                if first_depart and first_depart > now:
                    msg = f"今天的 '{number}' 尚未从始发站 '{times_today[0]['station_name']}' 发车\n计划发车时间：{first_depart.strftime('%Y-%m-%d %H:%M')}"
                elif last_arrive and last_arrive < now:
                    msg = f"今天的 '{number}' 已到达终点站 '{times_today[-1]['station_name']}'\n到达时间：{last_arrive.strftime('%Y-%m-%d %H:%M')}"
                else:
                    msg = "无法确定该车次当前位置（可能数据不全或时间基准异常）"
                self._set_query_content(frame, msg)
                return
            text = f"{date_label} 的 '{number}' 时刻表:\n"
            text += "站名         到达    出发\n"
            text += "---------------------------\n"
            for st in times:
                arrive = st['arrive'].strftime('%H:%M') if st['arrive'] else ''
                depart = st['depart'].strftime('%H:%M') if st['depart'] else ''
                text += f"{st['station_name']:<12} {arrive:<6} {depart:<6}\n"
            pos_msg = ""
            for i, st in enumerate(times):
                if st['arrive'] and st['depart'] and st['arrive'] <= now <= st['depart']:
                    pos_msg = f"\n当前位置: 正在停靠 '{st['station_name']}' 站\n到达：{st['arrive'].strftime('%H:%M')}  出发：{st['depart'].strftime('%H:%M')}"
                    if st['depart'] > now:
                        wait = int((st['depart'] - now).total_seconds() // 60)
                        pos_msg += f"\n距离发车还有：{wait} 分钟"
                    break
            if not pos_msg:
                for i in range(len(times)-1):
                    cur = times[i]; nxt = times[i+1]
                    depart_cur = cur['depart'] or cur['arrive']
                    arrive_next = nxt['arrive'] or nxt['depart']
                    if depart_cur and arrive_next and depart_cur <= now < arrive_next:
                        pos_msg = f"\n当前位置: 正在从 '{cur['station_name']}' 前往 '{nxt['station_name']}' 的途中\n预计到达 '{nxt['station_name']}' 时间：{arrive_next.strftime('%H:%M')}\n距离到达还有：{int((arrive_next - now).total_seconds() // 60)} 分钟"
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
            self._set_query_scrolledtext(frame, text)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_station_to_station(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(fill=tk.X, pady=10)
        tk.Label(f, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_start = tk.Entry(f, font=('微软雅黑', 10), width=12)
        entry_start.pack(side=tk.LEFT, padx=5)
        tk.Label(f, text="终止站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_end = tk.Entry(f, font=('微软雅黑', 10), width=12)
        entry_end.pack(side=tk.LEFT, padx=5)

        def do_query():
            start = entry_start.get().strip()
            end = entry_end.get().strip()
            if not start or not end:
                messagebox.showwarning("提示", "请输入起始站和终止站", parent=self)
                return
            start_id = self.app.get_station_id_by_name(start)
            end_id = self.app.get_station_id_by_name(end)
            if start_id is None or end_id is None:
                self._set_query_content(frame, "未找到车站")
                return
            candidates = []
            if self.app.data:
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
                self._set_query_content(frame, f"没有从 '{start}' 到 '{end}' 方向的车次")
                return
            now = datetime.datetime.now()
            today = now.date()
            results = []
            for train, s_stop, e_stop in candidates:
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
                    'date_label': date_label
                })
            results.sort(key=lambda x: x['start_time'])
            columns = ['车次', f'{start}发车', f'{end}到达', '状态']
            rows = []
            for r in results:
                s_str = r['start_time'].strftime('%H:%M')
                e_str = r['end_time'].strftime('%H:%M')
                if r['date_label'] == "昨天":
                    s_str += "(昨)"
                    e_str += "(昨)"
                rows.append((r['train'], s_str, e_str, r['status']))
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
                header += f"刚过掉: {just_passed['train']}（{t} 到达 {end}）"
            else:
                header += "刚过掉: 无"
            if coming_soon:
                t = coming_soon['start_time'].strftime('%H:%M')
                if coming_soon['date_label'] == "昨天":
                    t += "(昨)"
                header += f"\n马上进入: {coming_soon['train']}（{t} 从 {start} 发车）"
            else:
                header += "\n马上进入: 无"
            for widget in frame.display_frame.winfo_children():
                widget.destroy()
            lbl = tk.Label(frame.display_frame, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT)
            lbl.pack(fill=tk.X, padx=5, pady=2)
            self._set_query_table(frame, columns, rows)
        entry_start.bind('<Return>', lambda e: do_query())
        entry_end.bind('<Return>', lambda e: do_query())
        tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def _q_bidirectional(self, frame):
        for widget in frame.display_frame.winfo_children():
            widget.destroy()
        f = tk.Frame(frame.display_frame, bg='#f0f0f0')
        f.pack(pady=20)
        tk.Label(f, text="车站↔车次查询子功能:", font=('微软雅黑', 11), bg='#f0f0f0').pack(pady=5)
        def show_sub1():
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "查询-车次 → 始发/终点")
            for widget in frame.display_frame.winfo_children():
                widget.destroy()
            ff = tk.Frame(frame.display_frame, bg='#f0f0f0')
            ff.pack(fill=tk.X, pady=10)
            tk.Label(ff, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry = tk.Entry(ff, font=('微软雅黑', 10), width=15)
            entry.pack(side=tk.LEFT, padx=5)
            def do_query():
                number = entry.get().strip()
                if not number:
                    messagebox.showwarning("提示", "请输入车次号", parent=self)
                    return
                train = self.app.get_train(number)
                if not train:
                    self._set_query_content(frame, "未找到该车次")
                    return
                start = self.app.get_station_name_by_id(train.get('start_station'))
                end = self.app.get_station_name_by_id(train.get('end_station'))
                self._set_query_content(frame, f"{number} 始发: {start} 终点: {end}")
            entry.bind('<Return>', lambda e: do_query())
            tk.Button(ff, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)
            tk.Button(ff, text="返回", command=lambda: self._q_bidirectional(frame), width=12).pack(side=tk.LEFT, padx=5)

        def show_sub2():
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "查询-起始站 → 所有始发车次")
            for widget in frame.display_frame.winfo_children():
                widget.destroy()
            ff = tk.Frame(frame.display_frame, bg='#f0f0f0')
            ff.pack(fill=tk.X, pady=10)
            tk.Label(ff, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry = tk.Entry(ff, font=('微软雅黑', 10), width=15)
            entry.pack(side=tk.LEFT, padx=5)
            def do_query():
                station = entry.get().strip()
                if not station:
                    messagebox.showwarning("提示", "请输入车站名", parent=self)
                    return
                sid = self.app.get_station_id_by_name(station)
                if sid is None:
                    self._set_query_content(frame, "未找到该车站")
                    return
                trains = []
                if self.app.data:
                    trains = [t for t in self.app.data.get('trains', []) if t.get('start_station') == sid]
                if not trains:
                    self._set_query_content(frame, f"没有从 '{station}' 始发的车次")
                    return
                columns = ['车次', '终点']
                rows = [(t['base_number'], self.app.get_station_name_by_id(t.get('end_station'))) for t in trains]
                self._set_query_table(frame, columns, rows)
            entry.bind('<Return>', lambda e: do_query())
            tk.Button(ff, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)
            tk.Button(ff, text="返回", command=lambda: self._q_bidirectional(frame), width=12).pack(side=tk.LEFT, padx=5)

        def show_sub3():
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "查询-起点+终点 → 车次")
            for widget in frame.display_frame.winfo_children():
                widget.destroy()
            ff = tk.Frame(frame.display_frame, bg='#f0f0f0')
            ff.pack(fill=tk.X, pady=10)
            tk.Label(ff, text="起点:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry_start = tk.Entry(ff, font=('微软雅黑', 10), width=12)
            entry_start.pack(side=tk.LEFT, padx=5)
            tk.Label(ff, text="终点:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry_end = tk.Entry(ff, font=('微软雅黑', 10), width=12)
            entry_end.pack(side=tk.LEFT, padx=5)
            def do_query():
                start = entry_start.get().strip()
                end = entry_end.get().strip()
                if not start or not end:
                    messagebox.showwarning("提示", "请输入起点和终点", parent=self)
                    return
                start_id = self.app.get_station_id_by_name(start)
                end_id = self.app.get_station_id_by_name(end)
                if start_id is None or end_id is None:
                    self._set_query_content(frame, "未找到车站")
                    return
                trains = []
                if self.app.data:
                    trains = [t for t in self.app.data.get('trains', []) if t.get('start_station') == start_id and t.get('end_station') == end_id]
                if not trains:
                    self._set_query_content(frame, f"没有从 '{start}' 始发、'{end}' 终到的车次")
                    return
                columns = ['车次', '类型']
                rows = [(t['base_number'], t.get('type', '未知')) for t in sorted(trains, key=lambda x: x['base_number'])]
                self._set_query_table(frame, columns, rows)
            entry_start.bind('<Return>', lambda e: do_query())
            entry_end.bind('<Return>', lambda e: do_query())
            tk.Button(ff, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)
            tk.Button(ff, text="返回", command=lambda: self._q_bidirectional(frame), width=12).pack(side=tk.LEFT, padx=5)

        tk.Button(f, text="1. 车次 → 始发/终点", command=show_sub1, width=26).pack(pady=3)
        tk.Button(f, text="2. 起始站 → 所有始发车次", command=show_sub2, width=26).pack(pady=3)
        tk.Button(f, text="3. 起点+终点 → 车次", command=show_sub3, width=26).pack(pady=3)

    # ---------- 提权框架 ----------
    def build_privilege_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        tk.Label(frame, text="提权操作", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=10)
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Windows administrator", command=self._elevate_windows, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS administrator", command=self._elevate_admin, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS Developer", command=self._elevate_developer, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS Root", command=self._elevate_root, width=26).pack(pady=3)

        return frame

    def _elevate_windows(self):
        messagebox.showinfo("提示", "普通用户版不支持本地 Windows 提权", parent=self)

    def _elevate_admin(self):
        top = tk.Toplevel(self)
        top.title("TADS Administrator 验证")
        top.geometry("320x140")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="请输入 TADS Administrator 密码:", font=('微软雅黑', 10)).pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        pwd_entry.pack(pady=5)

        def do_verify():
            pwd = pwd_entry.get()
            if verify_password(pwd, ADMIN_PASSWORD_HASH):
                self.app.set_identity("TADS Administrator", pwd)
                top.destroy()
                self.refresh_status()
                self.update_edit_status()
                messagebox.showinfo("成功", "已提升为 TADS Administrator", parent=self)
            else:
                messagebox.showerror("错误", "密码错误", parent=top)

        def on_cancel():
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

    def _elevate_developer(self):
        top = tk.Toplevel(self)
        top.title("TADS Developer 验证")
        top.geometry("320x140")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="请输入 TADS Developer 密码:", font=('微软雅黑', 10)).pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        pwd_entry.pack(pady=5)

        def do_verify():
            pwd = pwd_entry.get()
            if verify_password(pwd, DEVELOPER_PASSWORD_HASH):
                self.app.set_identity("TADS Developer", pwd)
                top.destroy()
                self.refresh_status()
                self.update_edit_status()
                messagebox.showinfo("成功", "已提升为 TADS Developer", parent=self)
            else:
                messagebox.showerror("错误", "密码错误", parent=top)

        def on_cancel():
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

    def _elevate_root(self):
        top = tk.Toplevel(self)
        top.title("TADS Root 验证")
        top.geometry("320x140")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="请输入 TADS Root 密码:", font=('微软雅黑', 10)).pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        pwd_entry.pack(pady=5)

        def do_verify():
            pwd = pwd_entry.get()
            if verify_password(pwd, ROOT_PASSWORD_HASH):
                self.app.set_identity("TADS Root", pwd)
                top.destroy()
                self.refresh_status()
                self.update_edit_status()
                messagebox.showinfo("成功", "已提升为 TADS Root", parent=self)
            else:
                messagebox.showerror("错误", "密码错误", parent=top)

        def on_cancel():
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

    def _ensure_admin(self):
        """确保当前用户是管理员或Root，否则弹出验证框，返回是否通过"""
        current_identity = self.app.get_current_identity()
        if current_identity in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            return True
        result = self.verify_admin_in_panel()
        if current_identity in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            return True
        else:
            return False

    def verify_admin_in_panel(self, callback=None):
        """弹出管理员密码验证模态框（完全复刻管理员版）"""
        # 如果已经是管理员/开发者/Root，直接通过
        current_identity = self.app.get_current_identity()
        if current_identity in ["TADS Administrator", "TADS Developer", "TADS Root"]:
            if callback:
                callback()
            return True
            
        top = tk.Toplevel(self)
        top.title("管理员验证")
        top.geometry("320x140")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="请输入管理员密码:", font=('微软雅黑', 10)).pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        pwd_entry.pack(pady=5)

        result_var = tk.BooleanVar(value=False)

        def do_verify():
            pwd = pwd_entry.get()
            if verify_password(pwd, ADMIN_PASSWORD_HASH):
                self.app.set_identity("TADS Administrator", pwd)
                self.app.log_action("验证", "管理员密码通过")
                result_var.set(True)
                top.destroy()
                self.refresh_status()
                self.display_welcome()
                self.update_edit_status()
                if callback:
                    callback()
            else:
                messagebox.showerror("错误", "密码错误", parent=top)

        def on_cancel():
            result_var.set(False)
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

        self.wait_window(top)
        return result_var.get()

    # ---------- 日志框架 ----------
    def build_log_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        tk.Label(frame, text="日志查看", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=5)

        def refresh_log_wrapper():
            self._refresh_log_in_frame(frame)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "日志-刷新日志")
        tk.Button(frame, text="刷新日志", command=refresh_log_wrapper, width=20).pack(pady=5)

        log_text = scrolledtext.ScrolledText(frame, font=('Consolas', 10), wrap=tk.WORD, bg='white', height=20)
        log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_text.config(state='disabled')
        frame.log_text = log_text
        self._refresh_log_in_frame(frame)
        return frame

    def _refresh_log_in_frame(self, frame):
        if not self._ensure_admin():
            return
        logs = self.app.get_recent_logs(30, self.app.api_password)
        if hasattr(frame, 'log_text'):
            text_widget = frame.log_text
            text_widget.config(state='normal')
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, logs)
            text_widget.config(state='disabled')

    def update_edit_status(self):
        """更新所有编辑标签页的状态显示"""
        current_identity = self.app.get_current_identity()
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

    # ---------- 还原点框架 ----------
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
        if not self._ensure_admin():
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
        if not self._ensure_admin():
            return
        if len(self.app.restore_points) >= 3:
            messagebox.showinfo("提示", "还原点已达上限（3个）", parent=self)
            return
        if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
            pwd = self.app.api_password
        else:
            pwd = self._get_admin_password("添加还原点")
        if pwd is None:
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
            success, msg = self.app.add_restore_point(name, pwd)
            if success:
                messagebox.showinfo("成功", msg, parent=self)
                top.destroy()
                self._refresh_restore_list()
            else:
                messagebox.showerror("错误", f"添加失败: {msg}", parent=top)
        tk.Button(top, text="确认", command=do_add, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _restore_from_point(self):
        if not self._ensure_admin():
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
        if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
            pwd = self.app.api_password
        else:
            pwd = self._get_admin_password("恢复还原点")
        if pwd is None:
            return
        if not messagebox.askyesno("确认", f"从 {name} 恢复？", parent=self):
            return
        success, msg = self.app.restore_from_point(name, pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self.display_welcome()
            self._refresh_restore_list()
        else:
            messagebox.showerror("错误", f"恢复失败: {msg}", parent=self)

    def _edit_restore(self):
        if not self._ensure_admin():
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
        if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
            pwd = self.app.api_password
        else:
            pwd = self._get_admin_password("编辑还原点")
        if pwd is None:
            return
        choice = messagebox.askquestion("编辑", f"删除 {name}？\n点击“是”删除，“否”重命名", parent=self)
        if choice == 'yes':
            if messagebox.askyesno("确认删除", f"删除 {name}？", parent=self):
                success, msg = self.app.delete_restore_point(name, pwd)
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
                if new_name in self.app.restore_points:
                    messagebox.showerror("错误", "名称已存在", parent=top)
                    return
                success, msg = self.app.delete_restore_point(name, pwd)
                if not success:
                    messagebox.showerror("错误", f"删除旧名称失败: {msg}", parent=top)
                    return
                success2, msg2 = self.app.add_restore_point(new_name, pwd)
                if success2:
                    messagebox.showinfo("成功", f"已重命名为 {new_name}", parent=self)
                    top.destroy()
                    self._refresh_restore_list()
                else:
                    messagebox.showerror("错误", f"添加新名称失败: {msg2}", parent=top)
            tk.Button(top, text="确认", command=do_rename, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _format_restore(self):
        if not self._ensure_admin():
            return
        if not messagebox.askyesno("确认", "删除所有还原点？", parent=self):
            return
        if self.app.get_current_identity() in ["TADS Administrator", "TADS Developer", "TADS Root"] and self.app.api_password:
            pwd = self.app.api_password
        else:
            pwd = self._get_admin_password("格式化还原点")
        if pwd is None:
            return
        success, msg = self.app.format_restore_points(pwd)
        if success:
            messagebox.showinfo("成功", msg, parent=self)
            self._refresh_restore_list()
        else:
            messagebox.showerror("错误", f"格式化失败: {msg}", parent=self)

    # ---------- 导航按钮打开方法 ----------
    def open_home_tab(self):
        frame = self.build_home_frame()
        self.add_tab("主页", frame, closable=True)

    def open_edit_tab(self):
        if not self._ensure_admin():
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

    def open_log_tab(self):
        if not self._ensure_admin():
            return
        frame = self.build_log_frame()
        self.add_tab("日志", frame, closable=True)

    def open_restore_tab(self):
        if not self._ensure_admin():
            return
        frame = self.build_restore_frame()
        self.add_tab("还原点", frame, closable=True)

# ---------- 启动入口 ----------
if __name__ == "__main__":
    root = MainWindow()
    root.mainloop()