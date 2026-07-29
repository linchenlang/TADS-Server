# -*- coding: utf-8 -*-
"""
作者：Michael
管理员：Michael
开发者：Michael
ROOT持有人：Michael
物理通行密钥持有人：Michael
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
from flask import Flask, request, jsonify

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
    # 在 Flask 线程中，跳过物理密钥检查（避免 subprocess 异常）
    # 如果是 GUI 主线程，则正常检查
    if threading.current_thread() is threading.main_thread():
        try:
            output = subprocess.check_output("wmic logicaldisk where DriveType=2 get DeviceID", shell=True, encoding='gbk')
            lines = output.strip().splitlines()
            for line in lines:
                line = line.strip()
                if line and line.endswith(':'):
                    drive = line + '\\'
                    key_path = os.path.join(drive, r"Minecraft\4.53GB\网易版我的世界\FeverGames\1.18.36.32\audio\key.env")
                    if os.path.exists(key_path):
                        with open(key_path, 'r', encoding='utf-8') as f:
                            content = ''.join(line.strip() for line in f if line.strip())
                        if content == EXPECTED_KEY_HASH:
                            if EXPECTED_USB_SERIAL:
                                try:
                                    out2 = subprocess.check_output("wmic diskdrive get SerialNumber", shell=True, encoding='gbk')
                                    for sn in out2.strip().splitlines():
                                        sn = sn.strip()
                                        if sn and sn != 'SerialNumber' and sn.replace(' ', '') == EXPECTED_USB_SERIAL.replace(' ', ''):
                                            return True
                                except:
                                    pass
                                return False
                            else:
                                return True
        except:
            pass
        return False
    else:
        # Flask 线程中：只要管理员密码正确就通过（物理密钥在 GUI 提权时已验证过）
        return True

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

class TADSApp:
    def __init__(self):
        self.current_identity = "普通用户"
        self.is_admin = False
        self.is_developer = False
        self.is_root = False
        self.data = None
        self.restore_points = []
        self.stats = None
        self.current_page = "主界面"

        for d in [LOG_DIR, MAIN_DATA_DIR, RESTORE_DIR]:
            if not os.path.exists(d):
                os.makedirs(d)

        self.load_data()
        self.update_restore_points()
        self.update_stats()
        self.update_identity()
        self.log_action("系统启动", f"当前身份：{self.current_identity}")

    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except Exception as e:
                self.write_error_log(f"加载 data.json 失败: {e}")
                self.data = None
        if not self.data:
            self.data = {
                "version": "1.0",
                "last_updated": datetime.datetime.now().isoformat(),
                "stations": [],
                "trains": []
            }
            self.save_data()

    def save_data(self):
        if self.data:
            try:
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                self.write_error_log(f"保存数据失败: {e}")

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

    def update_identity(self):
        if self.is_root:
            self.current_identity = "TADS Root"
            if not test_physical_key():
                self.is_root = False
                self.is_developer = False
                self.current_identity = "TADS Administrator"
                self.log_action("物理密钥断开", "降级为管理员")
        elif self.is_admin:
            self.current_identity = "TADS Administrator"
        elif self.is_developer:
            self.current_identity = "TADS Developer"
        else:
            self.current_identity = "普通用户"

    def verify_admin(self, password):
        """API 验证：只检查密码，不检查物理密钥（GUI 启动时已验证过）"""
        if verify_password(password, ADMIN_PASSWORD_HASH):
            self.is_admin = True
            self.is_developer = False
            self.is_root = False
            self.update_identity()
            self.log_action("API验证", "管理员密码通过")
            return True
        return False

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
        self.log_action("新增车次", f"{number} (编号{new_id})")
        return True

    def delete_train(self, number):
        train = self.get_train(number)
        if not train:
            return False
        self.data['trains'] = [t for t in self.data['trains'] if t['train_id'] != train['train_id']]
        self.save_data()
        self.update_stats()
        self.log_action("删除车次", number)
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
        self.log_action("录入经停站", f"{train_number} 添加车站 {station_name}")
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
        self.log_action("删除停站", f"{train_number} 序号 {index}")
        return True

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
            self.log_action("添加还原点", name)
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
            self.log_action("从还原点恢复", name)
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
        self.log_action("删除还原点", name)
        return True

    def format_restore_points(self):
        try:
            for f in os.listdir(RESTORE_DIR):
                if f.endswith('.json'):
                    os.remove(os.path.join(RESTORE_DIR, f))
            self.restore_points = []
            self.log_action("格式化所有还原点")
            return True
        except:
            return False

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
            self.log_action("更新列车时刻表数据", "成功")
            return {"success": True, "message": "数据更新完成"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search(self, keyword):
        results = []
        for train in self.data.get('trains', []):
            if re.search(re.escape(keyword), train['base_number'], re.I):
                results.append({
                    "type": "车次",
                    "name": train['base_number'],
                    "detail": f"停靠 {len(train.get('stops', []))} 个站"
                })
        for station in self.data.get('stations', []):
            if re.search(re.escape(keyword), station['name'], re.I):
                count = sum(1 for t in self.data['trains'] if any(s['station_id'] == station['id'] for s in t.get('stops', [])))
                results.append({
                    "type": "车站",
                    "name": station['name'],
                    "detail": f"有 {count} 趟车次经过"
                })
        return results

    def get_train(self, number):
        if not self.data or 'trains' not in self.data:
            return None
        for train in self.data['trains']:
            if train['base_number'] == number:
                return train
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

    def log_action(self, action, detail=""):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"[{self.current_identity}] {action}"
        if detail:
            msg += f" – {detail}"
        self.write_log(msg)

    def write_log(self, message):
        try:
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except:
            pass

    def write_error_log(self, message):
        try:
            with open(ERROR_LOG, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except:
            pass

    def get_recent_logs(self, lines=30, password=None):
        if password is None:
            password = self.api_password
        if password is None:
            return "需要管理员密码"
        try:
            # 使用 params 自动编码，确保特殊字符正确处理
            resp = requests.get(
                f"{self.api_base}/api/logs",
                params={"password": password, "lines": lines},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json().get("logs", "")
            else:
                # 返回状态码和响应内容，帮助排查
                return f"获取日志失败 (HTTP {resp.status_code}): {resp.text[:200]}"
        except Exception as e:
            return f"请求异常: {e}"

# ---------- 主窗口（左侧导航 + 右侧标签页） ----------
class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.app = TADSApp()
        self.title("TADS 列车到发时刻数据中心服务器管理系统")
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
        self.api_status = "检测中..."
        self.update_status()

        # 主面板：左侧导航 + 右侧自定义标签区域
        main_panel = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5, bg='#f0f0f0')
        main_panel.pack(fill=tk.BOTH, expand=True)

        # 左侧导航栏
        self.left_nav = tk.Frame(main_panel, bg='#2c3e50', width=200)
        main_panel.add(self.left_nav, width=200, minsize=180)

        # 右侧整体容器
        self.right_container = tk.Frame(main_panel, bg='#f0f0f0')
        main_panel.add(self.right_container, width=1000, minsize=800)

        # ---------- 标签栏 ----------
        tab_bar_frame = tk.Frame(self.right_container, bg='#d0d0d0', height=45)
        tab_bar_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 2))
        tab_bar_frame.pack_propagate(False)
        self.tab_bar_frame = tab_bar_frame

        self.tab_container = tk.Frame(tab_bar_frame, bg='#d0d0d0')
        self.tab_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tab_container.bind("<Configure>", self._on_tab_container_resize)

        # ---------- 内容区域 ----------
        self.content_area = tk.Frame(self.right_container, bg='#f0f0f0')
        self.content_area.pack(fill=tk.BOTH, expand=True)

        # 标签数据管理
        self.tabs = {}
        self.tab_counter = 0
        self.current_tab_id = None
    
        # 创建导航按钮
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

        # 默认打开主页标签
        self.open_home_tab()

        # 定时刷新状态
        self.after(5000, self.refresh_status)
    
        # 新增：定时检查物理密钥（每3秒检查一次）
        self.after(5000, self.check_physical_key_periodically)

        # ---------- API 服务状态与启动 ----------
        try:
            threading.Thread(target=self.start_api_server, daemon=True).start()
        except Exception as e:
            self.api_status = "启动失败"
            self.app.write_error_log(f"API 线程启动异常: {e}")

    # ----------        API服务内嵌       ----------
    # ---------- 内嵌 API 服务（后台线程） ----------
    def start_api_server(self):
        """在后台启动 Flask API，端口 10076，并更新状态"""
        import socket
        import logging

        # 1. 检查端口是否被占用
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('0.0.0.0', 10076))
            sock.close()
        except OSError:
            self.api_status = "端口被占用"
            self.app.write_error_log("API 启动失败：端口 10076 已被占用")
            return

        # 2. 创建 Flask 应用，禁用日志输出
        app = Flask(__name__)
        app.config['JSON_AS_ASCII'] = False
        # 关闭 Flask 默认日志输出到控制台
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        app.logger.disabled = True

        # ---------- 路由定义（与之前完全一致） ----------
        @app.route('/')
        def index():
            return jsonify({
                "service": "TADS API",
                "version": "1.0",
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
                    "POST /api/admin/add_train": "新增车次",
                    "POST /api/admin/delete_train": "删除车次",
                    "POST /api/admin/add_stop": "录入停站",
                    "POST /api/admin/delete_stop": "删除停站",
                    "POST /api/admin/restore/add": "添加还原点",
                    "POST /api/admin/restore/apply": "从还原点恢复",
                    "POST /api/admin/restore/delete": "删除还原点",
                    "POST /api/admin/restore/format": "格式化所有还原点",
                    "POST /api/admin/update_data": "从 RailRhythm 更新数据"
                }
            })

        @app.route('/api/health')
        def health():
            return jsonify({"status": "ok", "timestamp": datetime.datetime.now().isoformat()})

        @app.route('/api/stats')
        def stats():
            stats = self.app.stats
            if stats:
                return jsonify(stats)
            return jsonify({"error": "统计数据不可用"}), 500

        @app.route('/api/trains')
        def list_trains():
            trains = self.app.data.get('trains', [])
            result = [{"number": t['base_number'], "stops": len(t.get('stops', []))} for t in trains]
            return jsonify(result)

        @app.route('/api/train/<string:number>')
        def train_detail(number):
            train = self.app.get_train(number)
            if not train:
                return jsonify({"error": "车次不存在"}), 404
            return jsonify(train)

        @app.route('/api/stations')
        def list_stations():
            return jsonify(self.app.data.get('stations', []))

        @app.route('/api/station/<string:name>/trains')
        def station_trains(name):
            sid = self.app.get_station_id_by_name(name)
            if sid is None:
                return jsonify({"error": "车站不存在"}), 404
            result = []
            for train in self.app.data.get('trains', []):
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
            results = self.app.search(keyword)
            return jsonify(results)

        @app.route('/api/logs')
        def get_logs():
            pwd = request.args.get('password', '')
            if not self.app.verify_admin(pwd):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            lines = int(request.args.get('lines', 30))
            try:
                # 使用绝对路径,确保Flask线程能访问到
                log_file = os.path.join(LOG_DIR, "operations.log")
                if not os.path.exists(log_file):
                    return jsonify({"logs": "日志文件不存在"})
                with open(log_file, 'r', encoding='utf-8') as f:
                    all_lines = f.readlines()
                    if not all_lines:
                        return jsonify({"logs": "日志文件为空"})
                    logs = ''.join(all_lines[-lines:])
                    return jsonify({"logs": logs})
            except Exception as e:
                # 返回详细错误信息,方便调试
                return jsonify({"error": f"读取日志失败: {str(e)}"}), 500

        # ---------- 管理员 POST 操作 ----------
        @app.route('/api/admin/add_train', methods=['POST'])
        def api_add_train():
            data = request.get_json()
            if not data or 'number' not in data or 'password' not in data:
                return jsonify({"error": "缺少必要字段 (number, password)"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.add_train(data['number']):
                return jsonify({"success": True, "message": f"车次 {data['number']} 已添加"})
            return jsonify({"success": False, "error": "添加失败，可能车次已存在或名称非法"}), 400

        @app.route('/api/admin/delete_train', methods=['POST'])
        def api_delete_train():
            data = request.get_json()
            if not data or 'number' not in data or 'password' not in data:
                return jsonify({"error": "缺少必要字段 (number, password)"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.delete_train(data['number']):
                return jsonify({"success": True, "message": f"车次 {data['number']} 已删除"})
            return jsonify({"success": False, "error": "删除失败，车次不存在"}), 404

        @app.route('/api/admin/add_stop', methods=['POST'])
        def api_add_stop():
            data = request.get_json()
            required = ['train_number', 'station_name', 'arrive', 'depart', 'day_offset', 'password']
            if not data or any(k not in data for k in required):
                return jsonify({"error": f"缺少必要字段，需要 {required}"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.add_stop(data['train_number'], data['station_name'], data['arrive'], data['depart'], int(data['day_offset'])):
                return jsonify({"success": True, "message": f"已为 {data['train_number']} 添加停站 {data['station_name']}"})
            return jsonify({"success": False, "error": "添加停站失败，请检查车次号"}), 400

        @app.route('/api/admin/delete_stop', methods=['POST'])
        def api_delete_stop():
            data = request.get_json()
            required = ['train_number', 'index', 'password']
            if not data or any(k not in data for k in required):
                return jsonify({"error": f"缺少必要字段，需要 {required}"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.delete_stop(data['train_number'], int(data['index'])):
                return jsonify({"success": True, "message": f"已删除 {data['train_number']} 的序号 {data['index']} 停站"})
            return jsonify({"success": False, "error": "删除失败，请检查车次号和序号"}), 400

        @app.route('/api/admin/restore/add', methods=['POST'])
        def api_add_restore():
            data = request.get_json()
            if not data or 'name' not in data or 'password' not in data:
                return jsonify({"error": "缺少必要字段 (name, password)"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.add_restore_point(data['name']):
                return jsonify({"success": True, "message": f"还原点 {data['name']} 已添加"})
            return jsonify({"success": False, "error": "添加失败，可能已达上限、名称已存在或非法"}), 400

        @app.route('/api/admin/restore/apply', methods=['POST'])
        def api_restore_apply():
            data = request.get_json()
            if not data or 'name' not in data or 'password' not in data:
                return jsonify({"error": "缺少必要字段 (name, password)"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.restore_from_point(data['name']):
                return jsonify({"success": True, "message": f"已从 {data['name']} 恢复"})
            return jsonify({"success": False, "error": "恢复失败，请检查还原点名称"}), 400

        @app.route('/api/admin/restore/delete', methods=['POST'])
        def api_delete_restore():
            data = request.get_json()
            if not data or 'name' not in data or 'password' not in data:
                return jsonify({"error": "缺少必要字段 (name, password)"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.delete_restore_point(data['name']):
                return jsonify({"success": True, "message": f"已删除还原点 {data['name']}"})
            return jsonify({"success": False, "error": "删除失败，还原点不存在"}), 400

        @app.route('/api/admin/restore/format', methods=['POST'])
        def api_format_restore():
            data = request.get_json()
            if not data or 'password' not in data:
                return jsonify({"error": "缺少 password 字段"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            if self.app.format_restore_points():
                return jsonify({"success": True, "message": "所有还原点已清空"})
            return jsonify({"success": False, "error": "格式化失败"}), 500

        @app.route('/api/admin/update_data', methods=['POST'])
        def api_update_data():
            data = request.get_json()
            if not data or 'password' not in data:
                return jsonify({"error": "缺少 password 字段"}), 400
            if not self.app.verify_admin(data['password']):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            result = self.app.update_train_data()
            return jsonify(result)

        @app.route('/api/admin/restore/list', methods=['GET'])
        def api_restore_list():
            pwd = request.args.get('password', '')
            if not self.app.verify_admin(pwd):
                return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
            return jsonify(self.app.restore_points)

        # 3. 启动 Flask（不输出任何控制台信息）
        try:
            self.api_status = "正常运行"
            app.run(host='0.0.0.0', port=10076, debug=False, use_reloader=False, threaded=True)
        except Exception as e:
            self.api_status = "启动失败"
            self.app.write_error_log(f"Flask 运行异常: {e}")

    # ---------- 辅助方法 ----------
    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes('-fullscreen', self.is_fullscreen)

    def update_status(self):
        now = datetime.datetime.now().strftime("%Y/%m/%d-%H:%M")
        identity = self.app.current_identity
        hub_open = test_port_silent()
        hub_status = "运行中" if hub_open else "未运行"
        hub_count = get_hub_count() if hub_open else 0
        error_msg = ""
        if os.path.exists(ERROR_LOG):
            try:
                with open(ERROR_LOG, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if lines:
                        last = lines[-1].strip()
                        if not re.search(r'U盘序列号|检查路径|文件存在', last):
                            error_msg = last
            except:
                pass
        status_text = (f"当前页面：{self.app.current_page} | 身份：{identity} | 系统时间：{now} | "
                       f"中枢站：{hub_status} | 访问人数：{hub_count}人 | API服务：{self.api_status}")
        if error_msg:
            status_text += f" | 报错：{error_msg}"
        self.status_label.config(text=status_text)

    def refresh_status(self):
        self.update_status()
        self.after(5000, self.refresh_status)

    def check_physical_key_periodically(self):
        """定期检查物理密钥状态，如果Root密钥断开则自动降级"""
        if self.app.is_root:
            if not test_physical_key():
                # 物理密钥断开，执行降级
                self.app.is_root = False
                self.app.is_developer = False
                # 保持管理员身份（因为之前Root拥有管理员权限）
                self.app.is_admin = True
                self.app.update_identity()
                self.app.log_action("物理密钥断开", "自动降级为管理员")
                self.refresh_status()
                self.display_welcome()
                self.update_edit_permission()
                # 弹出提示
                messagebox.showwarning("安全警告", 
                    "物理密钥已断开！\n已自动从 Root 降级为 Administrator。",
                    parent=self)
        # 继续下一次检查
        self.after(5000, self.check_physical_key_periodically)

    def show_placeholder(self):
        """显示占位欢迎信息（当无标签时），并隐藏标签栏"""
        # 隐藏标签栏
        if hasattr(self, 'tab_bar_frame'):
            self.tab_bar_frame.pack_forget()

        # 清空内容区域
        for widget in self.content_area.winfo_children():
            widget.destroy()

        container = tk.Frame(self.content_area, bg='#f0f0f0')
        container.pack(fill=tk.BOTH, expand=True)

        big_font = ('微软雅黑', 28, 'bold')
        title_label = tk.Label(container, text="欢迎使用\nTADS列车到发时刻数据中心服务器管理系统",
                               font=big_font, bg='#f0f0f0', justify='center')
        title_label.pack(expand=True, pady=(50, 0))

        small_font = ('微软雅黑', 10)
        small_text = (
            "请合法合规使用本系统\n"
            "部分功能被限制需要管理员及以上权限才可使用，不要尝试暴力破解\n"
            "如不符合规定使用本系统造成的任何后果自负，我司对此不负任何责任\n"
            "有疑问请联系上级主管部门或Root令牌持有者\n\n"
            "附属公司：龙岩市量子跃动有限责任公司\n"
            "开发者/负责人/公司CEO：Michael、linchenlang\n"
            "(linchenlang@outlook.com)"
        )
        small_label = tk.Label(container, text=small_text, font=small_font,
                               bg='#f0f0f0', justify='center')
        small_label.pack(expand=True, pady=(20, 50))

        self.placeholder_container = container

    def hide_placeholder(self):
        """隐藏占位内容，并恢复显示标签栏（确保在内容区域上方）"""
        if hasattr(self, 'placeholder_container') and self.placeholder_container:
            self.placeholder_container.destroy()
            delattr(self, 'placeholder_container')

        if hasattr(self, 'tab_bar_frame'):
            # 强制将标签栏放置在内容区域之前（上方）
            self.tab_bar_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 2), before=self.content_area)
            self.tab_bar_frame.update_idletasks()

    # ---------- 自定义标签页核心管理 ----------
    def add_tab(self, title, content_frame, closable=True):
        self.hide_placeholder()   # 隐藏占位
        tab_id = self.tab_counter
        self.tab_counter += 1

        DEFAULT_WIDTH = 160
        font = ('微软雅黑', 10)

        # 测量标题文字宽度，决定首选宽度
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

        # 标题标签，填满整个卡片
        title_label = tk.Label(tab_card, text=title, font=font, bg='#e0e0e0', anchor='w')
        title_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 2), pady=2)

        # 关闭按钮：使用 place 定位，始终在右上角，不会因卡片宽度变化而隐藏
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
            # 最小宽度保证关闭按钮可见
            min_widths.append(100)  # 固定最小宽度，确保关闭按钮区域

        if not tab_cards:
            return

        padding = 2  # 间距
        total_preferred = sum(preferred_widths) + padding * (len(tab_cards) - 1)
        available_width = container_width

        if total_preferred <= available_width:
            # 使用首选宽度
            for card, pref in zip(tab_cards, preferred_widths):
                card.config(width=pref)
        else:
            # 需要压缩：按比例缩小，但不小于最小宽度
            total_available = available_width - padding * (len(tab_cards) - 1)
            total_min = sum(min_widths)
            if total_available < total_min:
                # 即使全部最小也放不下，则统一设置为最小宽度，超出部分会被裁剪（但不会遮挡按钮）
                for card, min_w in zip(tab_cards, min_widths):
                    card.config(width=min_w)
                # 强制更新
                self.tab_container.update_idletasks()
                return

            # 按比例压缩
            factor = total_available / total_preferred
            new_widths = []
            for pref, min_w in zip(preferred_widths, min_widths):
                w = int(pref * factor)
                if w < min_w:
                    w = min_w
                new_widths.append(w)

            # 检查总宽度是否仍超出，若超出则强制缩小部分卡片到最小
            total_new = sum(new_widths) + padding * (len(tab_cards) - 1)
            if total_new > available_width:
                # 计算需要减去的多余部分，按比例从最大的卡片减去
                excess = total_new - available_width
                # 简单处理：将多余的宽度从最大的卡片上扣除，但不得低于最小宽度
                # 我们可以反复从当前最大宽度的卡片减去1，直到总宽度符合，但为了效率，可以一次性按比例减少
                # 简单方法：再次按比例压缩，但以最小宽度为底线
                # 这里我们直接设置所有卡片为平均宽度（但保证最小）
                avg_width = (available_width - padding * (len(tab_cards) - 1)) // len(tab_cards)
                for card in tab_cards:
                    card.config(width=max(avg_width, 100))
            else:
                for card, w in zip(tab_cards, new_widths):
                    card.config(width=w)

        self.tab_container.update_idletasks()

    def _on_tab_container_resize(self, event):
        """容器大小变化时重新调整标签宽度（防抖动）"""
        # 延迟执行，避免频繁触发
        if hasattr(self, '_resize_after_id'):
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(100, self.reflow_tabs)

    def update_tab_title(self, tab_id, new_title):
        if tab_id in self.tabs:
            data = self.tabs[tab_id]
            data['title'] = new_title
            data['title_label'].config(text=new_title)
            # 重新计算首选宽度
            font = ('微软雅黑', 10)
            temp_label = tk.Label(self.tab_container, text=new_title, font=font)
            text_width = temp_label.winfo_reqwidth() + 20
            temp_label.destroy()
            close_width = 20 if data['close_btn'] else 0
            new_preferred = text_width + close_width
            new_preferred = max(new_preferred, 80)
            new_preferred = min(new_preferred, 220)
            data['preferred_width'] = new_preferred
            # 重新布局
            self.reflow_tabs()
            if self.current_tab_id == tab_id:
                self.app.current_page = new_title
                self.update_status()

    def switch_tab(self, tab_id):
        """切换到指定标签"""
        if tab_id not in self.tabs:
            return

        # 隐藏所有内容
        for tid, data in self.tabs.items():
            data['content_frame'].place_forget()
            # 更新卡片样式
            card = data['tab_card']
            card.configure(bg='#e0e0e0')
            if data['title_label']:
                data['title_label'].configure(bg='#e0e0e0')
            if data['close_btn']:
                data['close_btn'].configure(bg='#e0e0e0')

        # 显示当前内容
        current = self.tabs[tab_id]
        current['content_frame'].place(in_=self.content_area, x=0, y=0, relwidth=1, relheight=1)
        # 高亮卡片
        current['tab_card'].configure(bg='#ffffff')
        if current['title_label']:
            current['title_label'].configure(bg='#ffffff')
        if current['close_btn']:
            current['close_btn'].configure(bg='#ffffff')

        self.current_tab_id = tab_id
        self.app.current_page = current['title']
        self.update_status()

    def close_tab(self, tab_id):
        """关闭指定标签页（允许关闭所有标签）"""
        if tab_id not in self.tabs:
            return

        # 如果当前关闭的是当前标签，先切换到其他标签（如果有）
        if self.current_tab_id == tab_id:
            other_id = None
            for tid in self.tabs:
                if tid != tab_id:
                    other_id = tid
                    break
            if other_id is not None:
                self.switch_tab(other_id)

        # 移除标签数据
        data = self.tabs[tab_id]
        data['tab_card'].destroy()
        data['content_frame'].destroy()
        del self.tabs[tab_id]

        # 重新布局剩余标签
        self.reflow_tabs()

        # 如果当前标签是关闭的那个，且还有其他标签，则切换到第一个
        if self.current_tab_id == tab_id and self.tabs:
            first_id = next(iter(self.tabs))
            self.switch_tab(first_id)
        elif not self.tabs:
            # 没有标签了，显示占位内容
            self.show_placeholder()
            self.current_tab_id = None
            self.app.current_page = "无标签"
            self.update_status()

        self.update_status()

        self.update_status()

    # ---------- 权限检查辅助 ----------
    def _ensure_admin(self):
        """确保当前用户是管理员或Root，否则弹出验证框，返回是否通过"""
        if self.app.is_admin or self.app.is_root:
            return True
        result = self.verify_admin_in_panel()
        if self.app.is_admin or self.app.is_root:
            return True
        else:
            return False

    def verify_admin_in_panel(self, callback=None):
        """弹出管理员密码验证模态框"""
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
            if verify_password(pwd, ADMIN_PASSWORD_HASH) and test_physical_key():
                self.app.is_admin = True
                self.app.is_developer = False
                self.app.is_root = False
                self.app.update_identity()
                self.app.log_action("验证", "管理员密码通过")
                result_var.set(True)
                top.destroy()
                self.refresh_status()
                self.display_welcome()
                if callback:
                    callback()
            else:
                messagebox.showerror("错误", "密码或物理密钥错误", parent=top)

        def on_cancel():
            result_var.set(False)
            top.destroy()

        btn_frame = tk.Frame(top)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="取消", command=on_cancel, width=10).pack(side=tk.LEFT, padx=10)

        self.wait_window(top)
        return result_var.get()

    def prompt_password(self, title, stored_hash, callback):
        """通用密码验证弹窗"""
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry("320x140")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text=f"请输入{title}:", font=('微软雅黑', 10)).pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20, font=('微软雅黑', 10))
        pwd_entry.pack(pady=5)

        def do_verify():
            pwd = pwd_entry.get()
            if verify_password(pwd, stored_hash):
                top.destroy()
                callback()
            else:
                messagebox.showerror("错误", "密码错误", parent=top)

        tk.Button(top, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    # ---------- 构建各个功能的内容框架（返回 ttk.Frame） ----------
    def build_home_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        tk.Label(frame, text="欢迎使用 TADS 列车到发时刻数据中心服务器管理系统", font=('微软雅黑', 16, 'bold'), bg='#f0f0f0').pack(pady=10)
        home_text = scrolledtext.ScrolledText(frame, font=('Consolas', 12), wrap=tk.WORD, bg='white', height=20)
        home_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        home_text.config(state='disabled')
        frame.home_text = home_text
        self._display_welcome_to_text(home_text)
        return frame

    def _display_welcome_to_text(self, text_widget):
        text_widget.config(state='normal')
        text_widget.delete(1.0, tk.END)
        last_write = "\n\n"
        if os.path.exists(DATA_FILE):
            mtime = os.path.getmtime(DATA_FILE)
            last_write = datetime.datetime.fromtimestamp(mtime).strftime("%Y/%m/%d-%H:%M")
        else:
            last_write = "无数据文件"
        info = f"""\n\n
                                                         T A D S  列  车  到  发  时  刻  数  据  中  心  服  务  器  管  理  系  统
                                                         Train Arrival & Departure Schedule Data Center Server Management System
                                                                                          T A D S

                                                                          · 数据库最后修改日期：{last_write}
"""
        if self.app.stats:
            s = self.app.stats
            info += f"                                                                          · 数据库记录车站数：{s['station_count']} 个\n"
            info += f"                                                                          · 数据库记录车次数：{s['train_count']} 个\n"
            if s['train_count'] > 0:
                info += f"                                                                            平均每趟车停靠 {s['avg_stops']} 个站\n"
            if s.get('busy_station_name'):
                info += f"                                                                            经过列车最多的车站：{s['busy_station_name']} ({s['busy_station_count']}趟)\n"
        else:
            info += "                                                                          · 数据库尚未加载或数据为空。\n"
        text_widget.insert(tk.END, info)
        text_widget.config(state='disabled')

    def display_welcome(self):
        """更新所有主页标签的内容"""
        for tid, data in self.tabs.items():
            if data['title'] == "主页":
                frame = data['content_frame']
                if hasattr(frame, 'home_text'):
                    self._display_welcome_to_text(frame.home_text)

    # ---------- 编辑框架 ----------
    def build_edit_frame(self):
        frame = ttk.Frame(self.content_area, padding=10)
        status_label = tk.Label(frame, text="当前身份：管理员（可编辑）" if (self.app.is_admin or self.app.is_root) else "当前身份：普通用户（需要管理员权限）",
                                font=('微软雅黑', 10), bg='#f0f0f0')
        status_label.pack(pady=5)

        op_frame = tk.Frame(frame, bg='#f0f0f0')
        op_frame.pack(fill=tk.X, pady=10)

        # 新增车次
        tk.Label(op_frame, text="新增车次:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=0, column=0, padx=5, pady=3, sticky='e')
        entry_new_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_new_train.grid(row=0, column=1, padx=5, pady=3)
        def add_train_wrapper():
            self._add_train(entry_new_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-新增车次")
        tk.Button(op_frame, text="确认新增", command=add_train_wrapper, width=12).grid(row=0, column=2, padx=5, pady=3)

        # 删除车次
        tk.Label(op_frame, text="删除车次:", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=1, column=0, padx=5, pady=3, sticky='e')
        entry_del_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_del_train.grid(row=1, column=1, padx=5, pady=3)
        def del_train_wrapper():
            self._del_train(entry_del_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-删除车次")
        tk.Button(op_frame, text="确认删除", command=del_train_wrapper, width=12).grid(row=1, column=2, padx=5, pady=3)

        # 录入停站
        tk.Label(op_frame, text="录入停站(车次):", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=2, column=0, padx=5, pady=3, sticky='e')
        entry_add_stop_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_add_stop_train.grid(row=2, column=1, padx=5, pady=3)
        def show_add_stop_wrapper():
            self._show_add_stop_form(frame, entry_add_stop_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-录入停站")
        tk.Button(op_frame, text="显示录入表单", command=show_add_stop_wrapper, width=14).grid(row=2, column=2, padx=5, pady=3)

        # 删除停站
        tk.Label(op_frame, text="删除停站(车次):", bg='#f0f0f0', font=('微软雅黑', 10)).grid(row=3, column=0, padx=5, pady=3, sticky='e')
        entry_del_stop_train = tk.Entry(op_frame, font=('微软雅黑', 10), width=15)
        entry_del_stop_train.grid(row=3, column=1, padx=5, pady=3)
        def show_del_stop_wrapper():
            self._show_del_stop_form(frame, entry_del_stop_train)
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-删除停站")
        tk.Button(op_frame, text="显示删除列表", command=show_del_stop_wrapper, width=14).grid(row=3, column=2, padx=5, pady=3)

        # 更新数据按钮
        def update_data_wrapper():
            self._update_data()
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "编辑-更新数据")
        tk.Button(op_frame, text="从 RailRhythm 更新数据", command=update_data_wrapper, width=30).grid(row=4, column=0, columnspan=3, pady=10)

        # 停站表单区域
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
        self.app.save_data()
        self.app.update_stats()
        self.app.log_action("新增车次", f"{number} (编号{new_id})")
        messagebox.showinfo("成功", "已录入数据库", parent=self)
        self.display_welcome()
        entry.delete(0, tk.END)

    def _del_train(self, entry):
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
            self.app.save_data()
            self.app.update_stats()
            self.app.log_action("删除车次", number)
            messagebox.showinfo("成功", f"{number} 的所有停站数据已从数据库抹除", parent=self)
            self.display_welcome()
            entry.delete(0, tk.END)
        do_remove()

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
            self.app.save_data()
            self.app.update_stats()
            self.app.log_action("录入经停站", f"{train_num} 添加车站 {station}")
            messagebox.showinfo("成功", "已录入", parent=self)
            self.display_welcome()
            for widget in parent_frame.stop_form_frame.winfo_children():
                widget.destroy()
        tk.Button(parent_frame.stop_form_frame, text="确认录入", command=confirm_add, width=15).pack(pady=5)

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
                if messagebox.askyesno("确认删除", f"确认删除序号 {idx} 的停站？", parent=self):
                    del train['stops'][idx-1]
                    if train['stops']:
                        train['start_station'] = train['stops'][0]['station_id']
                        train['end_station'] = train['stops'][-1]['station_id']
                    else:
                        train['start_station'] = None
                        train['end_station'] = None
                    self.app.save_data()
                    self.app.update_stats()
                    self.app.log_action("删除停站", train_num)
                    messagebox.showinfo("成功", "已删除停站", parent=self)
                    self.display_welcome()
                    self._show_del_stop_form(parent_frame, entry_train)
            except:
                pass
        tk.Button(parent_frame.stop_form_frame, text="输入序号删除", command=remove_by_index, width=15).pack(pady=5)

    def _update_data(self):
        if not os.path.exists(RAIL_RHYTHM_ROOT):
            messagebox.showerror("错误", f"找不到 RailRhythm 目录：{RAIL_RHYTHM_ROOT}", parent=self)
            return
        if not os.path.exists(AUTO_UPDATE_SCRIPT):
            messagebox.showerror("错误", f"找不到 auto_update.py：{AUTO_UPDATE_SCRIPT}", parent=self)
            return
        def do_update():
            try:
                # 获取当前编辑标签的显示控件
                current_tab = self.current_tab_id
                if current_tab is not None and current_tab in self.tabs:
                    frame = self.tabs[current_tab]['content_frame']
                    if hasattr(frame, 'edit_display'):
                        display = frame.edit_display
                        display.config(state='normal')
                        display.delete(1.0, tk.END)
                        display.insert(tk.END, "开始更新列车时刻表数据...\n")
                    else:
                        display = None
                else:
                    display = None
                old_cwd = os.getcwd()
                os.chdir(RAIL_RHYTHM_ROOT)
                result = subprocess.run([sys.executable, AUTO_UPDATE_SCRIPT], capture_output=True, text=True, timeout=300)
                os.chdir(old_cwd)
                if result.returncode != 0:
                    raise Exception(f"自动更新脚本执行失败（退出码：{result.returncode}）")
                if not os.path.exists(TRAIN_DATA_DIR):
                    raise Exception(f"train_data 目录不存在：{TRAIN_DATA_DIR}")
                result2 = subprocess.run([sys.executable, CONVERT_SCRIPT, TRAIN_DATA_DIR, DATA_FILE],
                                         capture_output=True, text=True, timeout=300)
                if result2.returncode != 0:
                    raise Exception("数据转换失败")
                self.app.load_data()
                self.app.update_stats()
                self.display_welcome()
                self.app.log_action("更新列车时刻表数据", "成功")
                messagebox.showinfo("成功", "数据更新完成！", parent=self)
                if display:
                    display.insert(tk.END, "更新完成。\n")
                    display.config(state='disabled')
            except Exception as e:
                messagebox.showerror("错误", f"数据更新失败: {e}", parent=self)
                self.app.write_error_log(f"更新数据异常: {e}")
                if display:
                    display.insert(tk.END, f"错误: {e}\n")
                    display.config(state='disabled')
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
        if not self.app.data or not self.app.data['trains']:
            self._set_view_table(frame, ['名次', '车次', '停站数'], [])
            return
        ranked = sorted(self.app.data['trains'], key=lambda t: len(t['stops']), reverse=True)
        top = ranked[:20]
        rows = [(str(i+1), t['base_number'], str(len(t['stops']))) for i, t in enumerate(top)]
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
            for i, stop in enumerate(train['stops']):
                name = self.app.get_station_name_by_id(stop['station_id'])
                rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or '', str(stop.get('day_offset', 0))))
            self._set_view_table(frame, columns, rows)
        entry.bind('<Return>', lambda e: do_view())
        tk.Button(f, text="查看", command=do_view, width=12).pack(side=tk.LEFT, padx=5)

    def _view_all_trains(self, frame):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showinfo("提示", "需要管理员权限", parent=self)
            return
        columns = ['车次', '类型', '停站数']
        rows = [(t['base_number'], t.get('type', '未知'), str(len(t['stops']))) for t in self.app.data['trains']]
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

    # 查询子功能（实现与原逻辑相同，仅将输出定向到 frame.display_frame）
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
            self._set_query_content(frame, f"{number} 停靠 {len(train['stops'])} 个站")
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
            for i, stop in enumerate(train['stops']):
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
            for train in self.app.data['trains']:
                for stop in train['stops']:
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
                t = stop['depart'] or stop['arrive']
                if t:
                    try:
                        dt = datetime.datetime.strptime(t, '%H:%M')
                        dt = dt.replace(day=dt.day + stop.get('day_offset', 0))
                        return dt
                    except:
                        pass
                return datetime.datetime.max
            for train, stop in sorted(found, key=sort_key):
                arrive = stop['arrive'] if stop['arrive'] else "始发"
                depart = stop['depart'] if stop['depart'] else "终到"
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
            for train in self.app.data['trains']:
                for stop in train['stops']:
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
            match = any(stop['station_id'] == sid for stop in train['stops'])
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
            results = []
            for train in self.app.data['trains']:
                if re.search(re.escape(keyword), train['base_number'], re.I):
                    results.append(('车次', train['base_number'], f"停靠 {len(train['stops'])} 个站"))
            for station in self.app.data['stations']:
                if re.search(re.escape(keyword), station['name'], re.I):
                    count = sum(1 for t in self.app.data['trains'] if any(s['station_id'] == station['id'] for s in t['stops']))
                    results.append(('车站', station['name'], f"有 {count} 趟车次经过"))
            if not results:
                self._set_query_content(frame, "未找到匹配项")
                return
            columns = ['类型', '名称', '详情']
            self._set_query_table(frame, columns, results)
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
            stops = train['stops']
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

        # 定义子功能函数，它们内部会更新当前标签标题
        def show_sub1():
            # 更新标题
            if self.current_tab_id is not None:
                self.update_tab_title(self.current_tab_id, "查询-车次 → 始发/终点")
            # 原有的显示内容代码...
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
                trains = [t for t in self.app.data['trains'] if t.get('start_station') == sid]
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
                trains = [t for t in self.app.data['trains'] if t.get('start_station') == start_id and t.get('end_station') == end_id]
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

        def show_sub2():
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
                trains = [t for t in self.app.data['trains'] if t.get('start_station') == sid]
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
                trains = [t for t in self.app.data['trains'] if t.get('start_station') == start_id and t.get('end_station') == end_id]
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
        tk.Button(btn_frame, text="Windows administrator", command=self.elevate_windows, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS administrator", command=self.elevate_tads_admin, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS Developer", command=self.elevate_developer, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS Root", command=self.elevate_root, width=26).pack(pady=3)
        return frame

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
        if self.app.is_admin:
            messagebox.showinfo("提示", "已是管理员", parent=self)
            return
        def do_elevate():
            self.app.is_admin = True
            self.app.is_developer = False
            self.app.is_root = False
            self.app.update_identity()
            self.app.log_action("提权", "成为管理员")
            messagebox.showinfo("成功", "已提升为 TADS Administrator", parent=self)
            self.refresh_status()
            self.display_welcome()
        if not self.verify_admin_in_panel(do_elevate):
            return

    def elevate_developer(self):
        if self.app.is_developer:
            messagebox.showinfo("提示", "已是开发者", parent=self)
            return
        self.prompt_password("开发者密码", DEVELOPER_PASSWORD_HASH, callback=self._set_developer)

    def _set_developer(self):
        self.app.is_developer = True
        self.app.is_admin = False
        self.app.is_root = False
        self.app.update_identity()
        self.app.log_action("提权", "成为开发者")
        messagebox.showinfo("成功", "已提升为 Developer", parent=self)
        self.refresh_status()
        self.display_welcome()

    def elevate_root(self):
        if self.app.is_root:
            messagebox.showinfo("提示", "已是Root", parent=self)
            return
        def do_elevate():
            self.app.is_root = True
            self.app.is_admin = True
            self.app.is_developer = True
            self.app.update_identity()
            self.app.log_action("提权", "成为Root")
            messagebox.showinfo("成功", "已提升为 Root", parent=self)
            self.refresh_status()
            self.display_welcome()
        if not self.verify_admin_in_panel(do_elevate):
            return

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
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showinfo("提示", "需要管理员或Root权限", parent=self)
            return
        if hasattr(frame, 'log_text'):
            text_widget = frame.log_text
            text_widget.config(state='normal')
            text_widget.delete(1.0, tk.END)
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    last30 = lines[-30:] if lines else []
                    content = "最近30条日志:\n\n" + ''.join(last30)
            else:
                content = "暂无日志"
            text_widget.insert(tk.END, content)
            text_widget.config(state='disabled')

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
        self.app.update_restore_points()
        # 查找当前标签页中的 listbox
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
            backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(self.app.data, f, ensure_ascii=False, indent=2)
            self.app.restore_points.append(name)
            self.app.log_action("添加还原点", name)
            messagebox.showinfo("成功", f"已添加还原点 {name}", parent=self)
            top.destroy()
            self._refresh_restore_list()
        tk.Button(top, text="确认", command=do_add, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _restore_from_point(self):
        # 获取当前标签页中的 listbox
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
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.app.data = data
            self.app.save_data()
            self.app.update_stats()
            self.app.log_action("从还原点恢复", name)
            messagebox.showinfo("成功", f"已从 {name} 恢复", parent=self)
            self.display_welcome()
        except Exception as e:
            messagebox.showerror("错误", f"恢复失败: {e}", parent=self)

    def _edit_restore(self):
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
        choice = messagebox.askquestion("编辑", f"删除 {name}？\n点击“是”删除，“否”重命名", parent=self)
        if choice == 'yes':
            if messagebox.askyesno("确认删除", f"删除 {name}？", parent=self):
                backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                self.app.restore_points.remove(name)
                self.app.log_action("删除还原点", name)
                messagebox.showinfo("成功", f"已删除 {name}", parent=self)
                self._refresh_restore_list()
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
                old_file = os.path.join(RESTORE_DIR, f"{name}.json")
                new_file = os.path.join(RESTORE_DIR, f"{new_name}.json")
                try:
                    os.rename(old_file, new_file)
                    self.app.restore_points = [new_name if x == name else x for x in self.app.restore_points]
                    self.app.log_action("重命名还原点", f"{name} -> {new_name}")
                    messagebox.showinfo("成功", f"已重命名为 {new_name}", parent=self)
                    top.destroy()
                    self._refresh_restore_list()
                except Exception as e:
                    messagebox.showerror("错误", f"重命名失败: {e}", parent=self)
            tk.Button(top, text="确认", command=do_rename, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def _format_restore(self):
        if not messagebox.askyesno("确认", "删除所有还原点？", parent=self):
            return
        def do_format():
            for f in os.listdir(RESTORE_DIR):
                if f.endswith('.json'):
                    os.remove(os.path.join(RESTORE_DIR, f))
            self.app.restore_points = []
            self.app.log_action("格式化所有还原点")
            messagebox.showinfo("成功", "已删除所有还原点", parent=self)
            self._refresh_restore_list()
        do_format()

    # ---------- 导航按钮的打开方法（带权限检查） ----------
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

    def _tab_exists(self, title):
        for tid, data in self.tabs.items():
            if data['title'] == title:
                return True
        return False

    def _switch_to_tab_by_title(self, title):
        for tid, data in self.tabs.items():
            if data['title'] == title:
                self.switch_tab(tid)
                return

    # ---------- 更新编辑权限状态（用于显示） ----------
    def update_edit_permission(self):
        # 更新所有编辑标签的状态标签
        for tid, data in self.tabs.items():
            if data['title'] == "编辑":
                frame = data['content_frame']
                if hasattr(frame, 'status_label'):
                    if self.app.is_admin or self.app.is_root:
                        frame.status_label.config(text="当前身份：管理员（可编辑）", fg='green')
                    else:
                        frame.status_label.config(text="当前身份：普通用户（需要管理员权限）", fg='red')

    # ---------- 查看 Tab ----------
    def build_view_tab(self):
        frame = self.tab_view
        # 放置按钮
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=10, padx=10)
        tk.Button(btn_frame, text="车次排行榜（停站数）", command=self.view_rank, width=26).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="查看车次所有经停站", command=self.view_train_stops, width=26).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="查看所有车次时刻表（需管理员）", command=self.view_all_trains, width=26).pack(side=tk.LEFT, padx=5)

        # 显示区域（树形表格）
        self.view_tree_frame = tk.Frame(frame, bg='#f0f0f0')
        self.view_tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # 初始为空
        self.view_tree = None

    def set_view_table(self, columns, rows):
        # 清空并重建树形表格
        for widget in self.view_tree_frame.winfo_children():
            widget.destroy()
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        tree = ttk.Treeview(self.view_tree_frame, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=120)
        scrollbar = ttk.Scrollbar(self.view_tree_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.view_tree = tree
        for row in rows:
            tree.insert('', 'end', values=row)

    def view_rank(self):
        if not self.app.data or not self.app.data['trains']:
            self.set_view_table(['名次', '车次', '停站数'], [])
            return
        ranked = sorted(self.app.data['trains'], key=lambda t: len(t['stops']), reverse=True)
        top = ranked[:20]
        rows = [(str(i+1), t['base_number'], str(len(t['stops']))) for i, t in enumerate(top)]
        self.set_view_table(['名次', '车次', '停站数'], rows)

    def view_train_stops(self):
        # 清空树，显示输入框
        for widget in self.view_tree_frame.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.view_tree_frame, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="输入车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_view():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self.set_view_table(['序号', '站名', '到达', '出发', '跨天'], [])
                return
            columns = ['序号', '站名', '到达', '出发', '跨天']
            rows = []
            for i, stop in enumerate(train['stops']):
                name = self.app.get_station_name_by_id(stop['station_id'])
                rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or '', str(stop.get('day_offset', 0))))
            self.set_view_table(columns, rows)
        entry.bind('<Return>', lambda e: do_view())
        tk.Button(frame, text="查看", command=do_view, width=12).pack(side=tk.LEFT, padx=5)

    def view_all_trains(self):
        if not self.app.is_admin:
            messagebox.showinfo("提示", "需要管理员权限", parent=self)
            return
        columns = ['车次', '类型', '停站数']
        rows = [(t['base_number'], t.get('type', '未知'), str(len(t['stops']))) for t in self.app.data['trains']]
        self.set_view_table(columns, rows)

    # ---------- 查询 Tab ----------
    def build_query_tab(self):
        frame = self.tab_query
        # 左侧子菜单按钮
        sub_frame = tk.Frame(frame, bg='#f0f0f0')
        sub_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        btn_list = [
            ("车次停站数量", self.q_stop_count),
            ("车次全部经停详情", self.q_train_detail),
            ("某站经过的所有车次", self.q_station_trains),
            ("站点时刻表（含上一/下一班）", self.q_station_schedule),
            ("车次/站点匹配校验", self.q_match),
            ("全局搜索引擎", self.q_search),
            ("车次当前理论位置", self.q_current_position),
            ("两站间今日列车运行", self.q_station_to_station),
            ("车站↔车次查询（含子功能）", self.q_bidirectional)
        ]
        for text, cmd in btn_list:
            btn = tk.Button(sub_frame, text=text, command=cmd,
                            font=('微软雅黑', 10), bg='#ecf0f1', relief=tk.RAISED, bd=1,
                            width=26, anchor='w', padx=5)
            btn.pack(pady=2)

        # 右侧显示区域
        self.query_display = tk.Frame(frame, bg='#f0f0f0')
        self.query_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        # 初始显示提示
        self.set_query_content("请从左侧选择查询功能")

    def set_query_content(self, text):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        if isinstance(text, str):
            lbl = tk.Label(self.query_display, text=text, font=('微软雅黑', 12), bg='#f0f0f0')
            lbl.pack(pady=20)
        else:
            # 可能是tree或其他控件，由调用者处理
            pass

    def set_query_table(self, columns, rows):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        style = ttk.Style()
        style.configure("Treeview", font=('微软雅黑', 11))
        style.configure("Treeview.Heading", font=('微软雅黑', 11, 'bold'))
        tree = ttk.Treeview(self.query_display, columns=columns, show='headings', selectmode='browse')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, anchor='center', width=120)
        scrollbar = ttk.Scrollbar(self.query_display, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for row in rows:
            tree.insert('', 'end', values=row)
        self.query_tree = tree

    def set_query_scrolledtext(self, text):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        st = scrolledtext.ScrolledText(self.query_display, font=('Consolas', 11), wrap=tk.WORD, bg='white')
        st.pack(fill=tk.BOTH, expand=True)
        st.insert(tk.END, text)
        st.config(state='disabled')

    # ---------- 查询子功能（原方法移植，修改输出到 query_display） ----------
    def q_stop_count(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self.set_query_content("未找到该车次")
                return
            self.set_query_content(f"{number} 停靠 {len(train['stops'])} 个站")
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_train_detail(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self.set_query_content("未找到该车次")
                return
            columns = ['序号', '站名', '到达', '出发']
            rows = []
            for i, stop in enumerate(train['stops']):
                name = self.app.get_station_name_by_id(stop['station_id'])
                rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or ''))
            self.set_query_table(columns, rows)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_station_trains(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return
            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                self.set_query_content("未找到该车站")
                return
            found = []
            for train in self.app.data['trains']:
                for stop in train['stops']:
                    if stop['station_id'] == sid:
                        found.append((train, stop))
                        break
            if not found:
                self.set_query_content(f"没有车次经过 '{station}'")
                return
            columns = ['车次', '到达', '出发', '跨天']
            rows = []
            def sort_key(item):
                stop = item[1]
                t = stop['depart'] or stop['arrive']
                if t:
                    try:
                        dt = datetime.datetime.strptime(t, '%H:%M')
                        dt = dt.replace(day=dt.day + stop.get('day_offset', 0))
                        return dt
                    except:
                        pass
                return datetime.datetime.max
            for train, stop in sorted(found, key=sort_key):
                arrive = stop['arrive'] if stop['arrive'] else "始发"
                depart = stop['depart'] if stop['depart'] else "终到"
                day_info = "次日" if stop.get('day_offset', 0) == 1 else "当天"
                rows.append((train['base_number'], arrive, depart, day_info))
            self.set_query_table(columns, rows)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_station_schedule(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            station = entry.get().strip()
            if not station:
                messagebox.showwarning("提示", "请输入车站名", parent=self)
                return
            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                self.set_query_content("未找到该车站")
                return
            found = []
            for train in self.app.data['trains']:
                for stop in train['stops']:
                    if stop['station_id'] == sid:
                        found.append((train, stop))
                        break
            if not found:
                self.set_query_content(f"没有车次经过 '{station}'")
                return
            now = datetime.datetime.now()
            prev_item = None; next_item = None
            prev_time = None; next_time = None
            for train, stop in found:
                t = stop['depart'] or stop['arrive']
                if not t:
                    continue
                try:
                    dt = datetime.datetime.strptime(t, '%H:%M')
                    dt = dt.replace(day=now.day + stop.get('day_offset', 0))
                    if dt < now:
                        if prev_time is None or dt > prev_time:
                            prev_time = dt
                            prev_item = (train, stop)
                    else:
                        if next_time is None or dt < next_time:
                            next_time = dt
                            next_item = (train, stop)
                except:
                    pass
            header = f"当前时间: {now.strftime('%H:%M')}\n"
            if prev_item:
                train, stop = prev_item
                t = stop['depart'] or stop['arrive']
                day_info = " (次日)" if stop.get('day_offset', 0) == 1 else ""
                header += f"上一班车: {train['base_number']}  {t}{day_info}\n"
            else:
                header += "上一班车: 无\n"
            if next_item:
                train, stop = next_item
                t = stop['depart'] or stop['arrive']
                day_info = " (次日)" if stop.get('day_offset', 0) == 1 else ""
                header += f"下一班车: {train['base_number']}  {t}{day_info}\n"
            else:
                header += "下一班车: 无\n"
            header += "="*50 + "\n所有经过该站的车次:\n"
            columns = ['序号', '车次', '到达', '出发', '跨天']
            rows = []
            for idx, (train, stop) in enumerate(found, 1):
                arrive = stop['arrive'] if stop['arrive'] else "始发"
                depart = stop['depart'] if stop['depart'] else "终到"
                day_info = "次日" if stop.get('day_offset', 0) == 1 else "当天"
                rows.append((str(idx), train['base_number'], arrive, depart, day_info))
            # 显示带标题的表格
            for widget in self.query_display.winfo_children():
                widget.destroy()
            lbl = tk.Label(self.query_display, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT)
            lbl.pack(fill=tk.X, padx=5, pady=2)
            self.set_query_table(columns, rows)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_match(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_train = tk.Entry(frame, font=('微软雅黑', 10), width=12)
        entry_train.pack(side=tk.LEFT, padx=5)
        tk.Label(frame, text="车站名:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_station = tk.Entry(frame, font=('微软雅黑', 10), width=12)
        entry_station.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry_train.get().strip()
            station = entry_station.get().strip()
            if not number or not station:
                messagebox.showwarning("提示", "请输入车次和车站", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self.set_query_content("未找到该车次")
                return
            sid = self.app.get_station_id_by_name(station)
            if sid is None:
                self.set_query_content("未找到该车站")
                return
            match = any(stop['station_id'] == sid for stop in train['stops'])
            self.set_query_content(f"{number} {'经停' if match else '不经停'} {station}")
        entry_train.bind('<Return>', lambda e: do_query())
        entry_station.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="匹配", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_search(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="关键词:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(frame, font=('微软雅黑', 10), width=20)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            keyword = entry.get().strip()
            if not keyword:
                messagebox.showwarning("提示", "请输入关键词", parent=self)
                return
            results = []
            for train in self.app.data['trains']:
                if re.search(re.escape(keyword), train['base_number'], re.I):
                    results.append(('车次', train['base_number'], f"停靠 {len(train['stops'])} 个站"))
            for station in self.app.data['stations']:
                if re.search(re.escape(keyword), station['name'], re.I):
                    count = sum(1 for t in self.app.data['trains'] if any(s['station_id'] == station['id'] for s in t['stops']))
                    results.append(('车站', station['name'], f"有 {count} 趟车次经过"))
            if not results:
                self.set_query_content("未找到匹配项")
                return
            columns = ['类型', '名称', '详情']
            self.set_query_table(columns, results)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="搜索", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_current_position(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="车次号:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry = tk.Entry(frame, font=('微软雅黑', 10), width=15)
        entry.pack(side=tk.LEFT, padx=5)
        def do_query():
            number = entry.get().strip()
            if not number:
                messagebox.showwarning("提示", "请输入车次号", parent=self)
                return
            train = self.app.get_train(number)
            if not train:
                self.set_query_content("未找到该车次")
                return
            stops = train['stops']
            if len(stops) < 2:
                self.set_query_content("该车次停站不足，无法判断区间")
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
                self.set_query_content(msg)
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
            self.set_query_scrolledtext(text)
        entry.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_station_to_station(self):
        for widget in self.query_display.winfo_children():
            widget.destroy()
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(fill=tk.X, pady=10)
        tk.Label(frame, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_start = tk.Entry(frame, font=('微软雅黑', 10), width=12)
        entry_start.pack(side=tk.LEFT, padx=5)
        tk.Label(frame, text="终止站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
        entry_end = tk.Entry(frame, font=('微软雅黑', 10), width=12)
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
                self.set_query_content("未找到车站")
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
                self.set_query_content(f"没有从 '{start}' 到 '{end}' 方向的车次")
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

            # 计算刚过掉和马上进入
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

            # 显示带标题的表格
            for widget in self.query_display.winfo_children():
                widget.destroy()
            lbl = tk.Label(self.query_display, text=header, font=('微软雅黑', 10), bg='#f0f0f0', justify=tk.LEFT)
            lbl.pack(fill=tk.X, padx=5, pady=2)
            self.set_query_table(columns, rows)

        entry_start.bind('<Return>', lambda e: do_query())
        entry_end.bind('<Return>', lambda e: do_query())
        tk.Button(frame, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)

    def q_bidirectional(self):
        # 因为查询子功能较多，这里直接显示子菜单（在原查询Tab右侧再嵌套子菜单）
        for widget in self.query_display.winfo_children():
            widget.destroy()
        # 显示三个子功能的按钮
        frame = tk.Frame(self.query_display, bg='#f0f0f0')
        frame.pack(pady=20)
        tk.Label(frame, text="车站↔车次查询子功能:", font=('微软雅黑', 11), bg='#f0f0f0').pack(pady=5)

        def show_sub1():
            # 车次→始发/终点
            for widget in self.query_display.winfo_children():
                widget.destroy()
            f = tk.Frame(self.query_display, bg='#f0f0f0')
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
                    self.set_query_content("未找到该车次")
                    return
                start = self.app.get_station_name_by_id(train.get('start_station'))
                end = self.app.get_station_name_by_id(train.get('end_station'))
                self.set_query_content(f"{number} 始发: {start} 终点: {end}")
            entry.bind('<Return>', lambda e: do_query())
            tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)
            tk.Button(f, text="返回", command=self.q_bidirectional, width=12).pack(side=tk.LEFT, padx=5)

        def show_sub2():
            # 起始站→所有始发车次
            for widget in self.query_display.winfo_children():
                widget.destroy()
            f = tk.Frame(self.query_display, bg='#f0f0f0')
            f.pack(fill=tk.X, pady=10)
            tk.Label(f, text="起始站:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry = tk.Entry(f, font=('微软雅黑', 10), width=15)
            entry.pack(side=tk.LEFT, padx=5)
            def do_query():
                station = entry.get().strip()
                if not station:
                    messagebox.showwarning("提示", "请输入车站名", parent=self)
                    return
                sid = self.app.get_station_id_by_name(station)
                if sid is None:
                    self.set_query_content("未找到该车站")
                    return
                trains = [t for t in self.app.data['trains'] if t.get('start_station') == sid]
                if not trains:
                    self.set_query_content(f"没有从 '{station}' 始发的车次")
                    return
                columns = ['车次', '终点']
                rows = [(t['base_number'], self.app.get_station_name_by_id(t.get('end_station'))) for t in trains]
                self.set_query_table(columns, rows)
            entry.bind('<Return>', lambda e: do_query())
            tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)
            tk.Button(f, text="返回", command=self.q_bidirectional, width=12).pack(side=tk.LEFT, padx=5)

        def show_sub3():
            # 起点+终点→车次
            for widget in self.query_display.winfo_children():
                widget.destroy()
            f = tk.Frame(self.query_display, bg='#f0f0f0')
            f.pack(fill=tk.X, pady=10)
            tk.Label(f, text="起点:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry_start = tk.Entry(f, font=('微软雅黑', 10), width=12)
            entry_start.pack(side=tk.LEFT, padx=5)
            tk.Label(f, text="终点:", bg='#f0f0f0', font=('微软雅黑', 10)).pack(side=tk.LEFT, padx=5)
            entry_end = tk.Entry(f, font=('微软雅黑', 10), width=12)
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
                    self.set_query_content("未找到车站")
                    return
                trains = [t for t in self.app.data['trains'] if t.get('start_station') == start_id and t.get('end_station') == end_id]
                if not trains:
                    self.set_query_content(f"没有从 '{start}' 始发、'{end}' 终到的车次")
                    return
                columns = ['车次', '类型']
                rows = [(t['base_number'], t.get('type', '未知')) for t in sorted(trains, key=lambda x: x['base_number'])]
                self.set_query_table(columns, rows)
            entry_start.bind('<Return>', lambda e: do_query())
            entry_end.bind('<Return>', lambda e: do_query())
            tk.Button(f, text="查询", command=do_query, width=12).pack(side=tk.LEFT, padx=5)
            tk.Button(f, text="返回", command=self.q_bidirectional, width=12).pack(side=tk.LEFT, padx=5)

        tk.Button(frame, text="1. 车次 → 始发/终点", command=show_sub1, width=26).pack(pady=3)
        tk.Button(frame, text="2. 起始站 → 所有始发车次", command=show_sub2, width=26).pack(pady=3)
        tk.Button(frame, text="3. 起点+终点 → 车次", command=show_sub3, width=26).pack(pady=3)

    # ---------- 提权 Tab ----------
    def build_privilege_tab(self):
        frame = self.tab_privilege
        tk.Label(frame, text="提权操作", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=10)
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Windows administrator", command=self.elevate_windows, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS administrator", command=self.elevate_tads_admin, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS Developer", command=self.elevate_developer, width=26).pack(pady=3)
        tk.Button(btn_frame, text="TADS Root", command=self.elevate_root, width=26).pack(pady=3)

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
        if self.app.is_admin:
            messagebox.showinfo("提示", "已是管理员", parent=self)
            return
        def do_elevate():
            self.app.is_admin = True
            self.app.is_developer = False
            self.app.is_root = False
            self.app.update_identity()
            self.app.log_action("提权", "成为管理员")
            messagebox.showinfo("成功", "已提升为 TADS Administrator", parent=self)
            self.refresh_status()
            self.display_welcome()
            self.update_edit_permission()
        if not self.verify_admin_in_panel(do_elevate):
            return

    def elevate_developer(self):
        if self.app.is_developer:
            messagebox.showinfo("提示", "已是开发者", parent=self)
            return
        # 弹出密码验证框
        self.prompt_password("开发者密码", DEVELOPER_PASSWORD_HASH, callback=self._set_developer)

    def _set_developer(self):
        self.app.is_developer = True
        self.app.is_admin = False
        self.app.is_root = False
        self.app.update_identity()
        self.app.log_action("提权", "成为开发者")
        messagebox.showinfo("成功", "已提升为 Developer", parent=self)
        self.refresh_status()
        self.display_welcome()
        self.update_edit_permission()

    def _set_root(self):
        self.app.is_root = True
        self.app.is_admin = True
        self.app.is_developer = True
        self.app.update_identity()
        self.app.log_action("提权", "成为Root")
        messagebox.showinfo("成功", "已提升为 Root", parent=self)
        self.refresh_status()
        self.display_welcome()
        self.update_edit_permission()

    def elevate_root(self):
        if self.app.is_root:
            messagebox.showinfo("提示", "已是Root", parent=self)
            return
        # 修复：使用 Root 密码验证
        self.prompt_password("Root密码", ROOT_PASSWORD_HASH, callback=self._set_root)

    def verify_admin_in_panel(self, callback=None):
        # 弹出密码验证框（可复用）
        if self.app.is_root:
            if callback:
                callback()
            return True
        # 创建一个模态框
        top = tk.Toplevel(self)
        top.title("管理员验证")
        top.geometry("300x120")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="请输入管理员密码:").pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20)
        pwd_entry.pack(pady=5)
        def do_verify():
            pwd = pwd_entry.get()
            if verify_password(pwd, ADMIN_PASSWORD_HASH) and test_physical_key():
                self.app.is_admin = True
                self.app.update_identity()
                self.app.log_action("验证", "管理员密码通过")
                top.destroy()
                self.refresh_status()
                self.display_welcome()
                self.update_edit_permission()
                if callback:
                    callback()
            else:
                messagebox.showerror("错误", "密码或物理密钥错误", parent=top)
        tk.Button(top, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)
        return False

    def prompt_password(self, title, stored_hash, callback):
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry("300x120")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text=f"请输入{title}:").pack(pady=10)
        pwd_entry = tk.Entry(top, show='*', width=20)
        pwd_entry.pack(pady=5)
        def do_verify():
            pwd = pwd_entry.get()
            if verify_password(pwd, stored_hash):
                top.destroy()
                callback()
            else:
                messagebox.showerror("错误", "密码错误", parent=top)
        tk.Button(top, text="验证", command=do_verify, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    # ---------- 日志 Tab ----------
    def build_log_tab(self):
        frame = self.tab_log
        tk.Label(frame, text="日志查看", font=('微软雅黑', 12), bg='#f0f0f0').pack(pady=5)
        tk.Button(frame, text="刷新日志", command=self.refresh_log, width=20).pack(pady=5)
        self.log_text = scrolledtext.ScrolledText(frame, font=('Consolas', 10), wrap=tk.WORD, bg='white')
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text.config(state='disabled')
        self.refresh_log()

    def refresh_log(self):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showinfo("提示", "需要管理员或Root权限", parent=self)
            return
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                last30 = lines[-30:] if lines else []
                text = "最近30条日志:\n\n" + ''.join(last30)
        else:
            text = "暂无日志"
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, text)
        self.log_text.config(state='disabled')

    # ---------- 还原点 Tab ----------
    def build_restore_tab(self):
        frame = self.tab_restore
        # 操作按钮
        btn_frame = tk.Frame(frame, bg='#f0f0f0')
        btn_frame.pack(fill=tk.X, pady=5, padx=10)
        tk.Button(btn_frame, text="添加还原点（上限3个）", command=self.add_restore, width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="从还原点恢复", command=self.restore_from_point, width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="编辑还原点（删除/重命名）", command=self.edit_restore, width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="格式化所有还原点", command=self.format_restore, width=20).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="刷新列表", command=self.refresh_restore_list, width=20).pack(side=tk.LEFT, padx=5)

        # 列表显示
        self.restore_list_frame = tk.Frame(frame, bg='#f0f0f0')
        self.restore_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.refresh_restore_list()

    def refresh_restore_list(self):
        self.app.update_restore_points()
        for widget in self.restore_list_frame.winfo_children():
            widget.destroy()
        listbox = Listbox(self.restore_list_frame, font=('微软雅黑', 12), selectmode=EXTENDED)
        listbox.pack(fill=tk.BOTH, expand=True)
        for name in self.app.restore_points:
            listbox.insert(tk.END, name)
        self.restore_listbox = listbox

    def add_restore(self):
        if len(self.app.restore_points) >= 3:
            messagebox.showinfo("提示", "还原点已达上限（3个）", parent=self)
            return
        # 弹出输入框
        top = tk.Toplevel(self)
        top.title("添加还原点")
        top.geometry("300x120")
        top.transient(self)
        top.grab_set()
        tk.Label(top, text="还原点名称:").pack(pady=10)
        entry = tk.Entry(top, width=20)
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
            backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(self.app.data, f, ensure_ascii=False, indent=2)
            self.app.restore_points.append(name)
            self.app.log_action("添加还原点", name)
            messagebox.showinfo("成功", f"已添加还原点 {name}", parent=self)
            top.destroy()
            self.refresh_restore_list()
        tk.Button(top, text="确认", command=do_add, width=10).pack(side=tk.LEFT, padx=20, pady=10)
        tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def restore_from_point(self):
        selection = self.restore_listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请选择还原点", parent=self)
            return
        name = self.restore_listbox.get(selection[0])
        if not messagebox.askyesno("确认", f"从 {name} 恢复？", parent=self):
            return
        backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
        if not os.path.exists(backup_file):
            messagebox.showerror("错误", "文件丢失", parent=self)
            return
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.app.data = data
            self.app.save_data()
            self.app.update_stats()
            self.app.log_action("从还原点恢复", name)
            messagebox.showinfo("成功", f"已从 {name} 恢复", parent=self)
            self.display_welcome()
        except Exception as e:
            messagebox.showerror("错误", f"恢复失败: {e}", parent=self)

    def edit_restore(self):
        selection = self.restore_listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请选择还原点", parent=self)
            return
        name = self.restore_listbox.get(selection[0])
        choice = messagebox.askquestion("编辑", f"删除 {name}？\n点击“是”删除，“否”重命名", parent=self)
        if choice == 'yes':
            if messagebox.askyesno("确认删除", f"删除 {name}？", parent=self):
                backup_file = os.path.join(RESTORE_DIR, f"{name}.json")
                if os.path.exists(backup_file):
                    os.remove(backup_file)
                self.app.restore_points.remove(name)
                self.app.log_action("删除还原点", name)
                messagebox.showinfo("成功", f"已删除 {name}", parent=self)
                self.refresh_restore_list()
        else:
            # 重命名
            top = tk.Toplevel(self)
            top.title("重命名还原点")
            top.geometry("300x120")
            top.transient(self)
            top.grab_set()
            tk.Label(top, text="新名称:").pack(pady=10)
            entry = tk.Entry(top, width=20)
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
                try:
                    os.rename(old_file, new_file)
                    self.app.restore_points = [new_name if x == name else x for x in self.app.restore_points]
                    self.app.log_action("重命名还原点", f"{name} -> {new_name}")
                    messagebox.showinfo("成功", f"已重命名为 {new_name}", parent=self)
                    top.destroy()
                    self.refresh_restore_list()
                except Exception as e:
                    messagebox.showerror("错误", f"重命名失败: {e}", parent=self)
            tk.Button(top, text="确认", command=do_rename, width=10).pack(side=tk.LEFT, padx=20, pady=10)
            tk.Button(top, text="取消", command=top.destroy, width=10).pack(side=tk.RIGHT, padx=20, pady=10)

    def format_restore(self):
        if not messagebox.askyesno("确认", "删除所有还原点？", parent=self):
            return
        def do_format():
            for f in os.listdir(RESTORE_DIR):
                if f.endswith('.json'):
                    os.remove(os.path.join(RESTORE_DIR, f))
            self.app.restore_points = []
            self.app.log_action("格式化所有还原点")
            messagebox.showinfo("成功", "已删除所有还原点", parent=self)
            self.refresh_restore_list()
        if not self.verify_admin_in_panel(do_format):
            return

    # ---------- 导航切换方法（点击左侧按钮） ----------
    def show_home(self):
        self.notebook.select(self.tab_home)
        self.app.current_page = "主页"
        self.update_status()

    def show_edit(self):
        if not self.app.is_admin:
            messagebox.showinfo("提示", "需要管理员权限，请先提权", parent=self)
        self.notebook.select(self.tab_edit)
        self.app.current_page = "编辑"
        self.update_status()
        self.update_edit_permission()

    def show_view(self):
        self.notebook.select(self.tab_view)
        self.app.current_page = "查看"
        self.update_status()

    def show_query(self):
        self.notebook.select(self.tab_query)
        self.app.current_page = "查询"
        self.update_status()

    def show_privilege(self):
        self.notebook.select(self.tab_privilege)
        self.app.current_page = "提权"
        self.update_status()

    def show_log(self):
        if not (self.app.is_admin or self.app.is_root):
            messagebox.showinfo("提示", "需要管理员或Root权限", parent=self)
        self.notebook.select(self.tab_log)
        self.app.current_page = "日志"
        self.update_status()
        self.refresh_log()

    def show_restore(self):
        if not self.app.is_admin:
            messagebox.showinfo("提示", "需要管理员权限，请先提权", parent=self)
        self.notebook.select(self.tab_restore)
        self.app.current_page = "还原点"
        self.update_status()

    # ---------- 编辑功能的具体实现（复用原逻辑） ----------
    def add_train_from_entry(self):
        number = self.entry_new_train.get().strip()
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
        self.app.save_data()
        self.app.update_stats()
        self.app.log_action("新增车次", f"{number} (编号{new_id})")
        messagebox.showinfo("成功", "已录入数据库", parent=self)
        self.display_welcome()
        self.entry_new_train.delete(0, tk.END)

    def remove_train_from_entry(self):
        number = self.entry_del_train.get().strip()
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
            self.app.save_data()
            self.app.update_stats()
            self.app.log_action("删除车次", number)
            messagebox.showinfo("成功", f"{number} 的所有停站数据已从数据库抹除", parent=self)
            self.display_welcome()
            self.entry_del_train.delete(0, tk.END)
        if not self.app.is_root:
            if not self.verify_admin_in_panel(do_remove):
                return
        else:
            do_remove()

    def show_add_stop_form(self):
        train_num = self.entry_add_stop_train.get().strip()
        if not train_num:
            messagebox.showwarning("提示", "请输入车次号", parent=self)
            return
        train = self.app.get_train(train_num)
        if not train:
            messagebox.showerror("错误", "未找到该车次", parent=self)
            return
        # 清空之前的表单
        for widget in self.stop_form_frame.winfo_children():
            widget.destroy()
        tk.Label(self.stop_form_frame, text=f"为 {train_num} 录入停站", bg='#f0f0f0', font=('微软雅黑', 11)).pack(pady=5)
        row_frame = tk.Frame(self.stop_form_frame, bg='#f0f0f0')
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
            self.app.save_data()
            self.app.update_stats()
            self.app.log_action("录入经停站", f"{train_num} 添加车站 {station}")
            messagebox.showinfo("成功", "已录入", parent=self)
            self.display_welcome()
            for widget in self.stop_form_frame.winfo_children():
                widget.destroy()
        tk.Button(self.stop_form_frame, text="确认录入", command=confirm_add, width=15).pack(pady=5)

    def show_del_stop_form(self):
        train_num = self.entry_del_stop_train.get().strip()
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
        def do_delete():
            columns = ['序号', '站名', '到达', '出发', '跨天']
            rows = []
            for i, stop in enumerate(train['stops']):
                name = self.app.get_station_name_by_id(stop['station_id'])
                rows.append((str(i+1), name, stop.get('arrive') or '', stop.get('depart') or '', str(stop.get('day_offset', 0))))
            # 在编辑Tab的显示区域显示列表，并提供选择删除
            self.edit_display.config(state='normal')
            self.edit_display.delete(1.0, tk.END)
            self.edit_display.insert(tk.END, "选择要删除的停站（点击序号）:\n")
            for i, row in enumerate(rows):
                self.edit_display.insert(tk.END, f"{row[0]}. {row[1]}  {row[2]}->{row[3]} (跨{row[4]})\n")
            self.edit_display.config(state='disabled')
            # 绑定点击事件：暂不支持点击，改用输入序号删除
            def remove_by_index():
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
                        self.app.save_data()
                        self.app.update_stats()
                        self.app.log_action("删除停站", train_num)
                        messagebox.showinfo("成功", "已删除停站", parent=self)
                        self.display_welcome()
                        self.show_del_stop_form()
                except:
                    pass
            tk.Button(self.stop_form_frame, text="输入序号删除", command=remove_by_index, width=15).pack(pady=5)
        if not self.app.is_root:
            if not self.verify_admin_in_panel(do_delete):
                return
        else:
            do_delete()

    def update_data(self):
        if not os.path.exists(RAIL_RHYTHM_ROOT):
            messagebox.showerror("错误", f"找不到 RailRhythm 目录：{RAIL_RHYTHM_ROOT}", parent=self)
            return
        if not os.path.exists(AUTO_UPDATE_SCRIPT):
            messagebox.showerror("错误", f"找不到 auto_update.py：{AUTO_UPDATE_SCRIPT}", parent=self)
            return
        def do_update():
            try:
                self.edit_display.config(state='normal')
                self.edit_display.delete(1.0, tk.END)
                self.edit_display.insert(tk.END, "开始更新列车时刻表数据...\n")
                old_cwd = os.getcwd()
                os.chdir(RAIL_RHYTHM_ROOT)
                result = subprocess.run([sys.executable, AUTO_UPDATE_SCRIPT], capture_output=True, text=True, timeout=300)
                os.chdir(old_cwd)
                if result.returncode != 0:
                    raise Exception(f"自动更新脚本执行失败（退出码：{result.returncode}）")
                if not os.path.exists(TRAIN_DATA_DIR):
                    raise Exception(f"train_data 目录不存在：{TRAIN_DATA_DIR}")
                result2 = subprocess.run([sys.executable, CONVERT_SCRIPT, TRAIN_DATA_DIR, DATA_FILE],
                                         capture_output=True, text=True, timeout=300)
                if result2.returncode != 0:
                    raise Exception("数据转换失败")
                self.app.load_data()
                self.app.update_stats()
                self.display_welcome()
                self.app.log_action("更新列车时刻表数据", "成功")
                messagebox.showinfo("成功", "数据更新完成！", parent=self)
                self.edit_display.insert(tk.END, "更新完成。\n")
            except Exception as e:
                messagebox.showerror("错误", f"数据更新失败: {e}", parent=self)
                self.app.write_error_log(f"更新数据异常: {e}")
                self.edit_display.insert(tk.END, f"错误: {e}\n")
            finally:
                self.edit_display.config(state='disabled')
        threading.Thread(target=do_update, daemon=True).start()

if __name__ == "__main__":
    root = MainWindow()
    root.mainloop()