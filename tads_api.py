# -*- coding: utf-8 -*-
"""
TADS API 服务（独立运行版）
从 TADS_server.py 抽离，端口：10076
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
import ctypes
from flask import Flask, request, jsonify

# ---------- 常量配置 ----------
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

# ---------- 工具函数 ----------
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
        return True

# ---------- TADSApp 类 ----------
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


# ---------- 创建 Flask 应用 ----------
app = Flask(__name__)
tads = TADSApp()


# ---------- 路由 ----------
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
            "GET /api/admin/restore/list": "还原点列表（需管理员密码）",
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
    stats = tads.stats
    if stats:
        return jsonify(stats)
    return jsonify({"error": "统计数据不可用"}), 500


@app.route('/api/trains')
def list_trains():
    trains = tads.data.get('trains', [])
    result = [{"number": t['base_number'], "stops": len(t.get('stops', []))} for t in trains]
    return jsonify(result)


@app.route('/api/train/<string:number>')
def train_detail(number):
    train = tads.get_train(number)
    if not train:
        return jsonify({"error": "车次不存在"}), 404
    return jsonify(train)


@app.route('/api/stations')
def list_stations():
    return jsonify(tads.data.get('stations', []))


@app.route('/api/station/<string:name>/trains')
def station_trains(name):
    sid = tads.get_station_id_by_name(name)
    if sid is None:
        return jsonify({"error": "车站不存在"}), 404
    result = []
    for train in tads.data.get('trains', []):
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
    results = tads.search(keyword)
    return jsonify(results)


@app.route('/api/logs')
def get_logs():
    pwd = request.args.get('password', '')
    if not tads.verify_admin(pwd):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    lines = int(request.args.get('lines', 30))
    try:
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
        return jsonify({"error": f"读取日志失败: {str(e)}"}), 500


@app.route('/api/admin/restore/list', methods=['GET'])
def api_restore_list():
    pwd = request.args.get('password', '')
    if not tads.verify_admin(pwd):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    return jsonify(tads.restore_points)


# ---------- 管理员 POST 操作 ----------
@app.route('/api/admin/add_train', methods=['POST'])
def api_add_train():
    data = request.get_json()
    if not data or 'number' not in data or 'password' not in data:
        return jsonify({"error": "缺少必要字段 (number, password)"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.add_train(data['number']):
        return jsonify({"success": True, "message": f"车次 {data['number']} 已添加"})
    return jsonify({"success": False, "error": "添加失败，可能车次已存在或名称非法"}), 400


@app.route('/api/admin/delete_train', methods=['POST'])
def api_delete_train():
    data = request.get_json()
    if not data or 'number' not in data or 'password' not in data:
        return jsonify({"error": "缺少必要字段 (number, password)"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.delete_train(data['number']):
        return jsonify({"success": True, "message": f"车次 {data['number']} 已删除"})
    return jsonify({"success": False, "error": "删除失败，车次不存在"}), 404


@app.route('/api/admin/add_stop', methods=['POST'])
def api_add_stop():
    data = request.get_json()
    required = ['train_number', 'station_name', 'arrive', 'depart', 'day_offset', 'password']
    if not data or any(k not in data for k in required):
        return jsonify({"error": f"缺少必要字段，需要 {required}"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.add_stop(data['train_number'], data['station_name'], data['arrive'], data['depart'], int(data['day_offset'])):
        return jsonify({"success": True, "message": f"已为 {data['train_number']} 添加停站 {data['station_name']}"})
    return jsonify({"success": False, "error": "添加停站失败，请检查车次号"}), 400


@app.route('/api/admin/delete_stop', methods=['POST'])
def api_delete_stop():
    data = request.get_json()
    required = ['train_number', 'index', 'password']
    if not data or any(k not in data for k in required):
        return jsonify({"error": f"缺少必要字段，需要 {required}"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.delete_stop(data['train_number'], int(data['index'])):
        return jsonify({"success": True, "message": f"已删除 {data['train_number']} 的序号 {data['index']} 停站"})
    return jsonify({"success": False, "error": "删除失败，请检查车次号和序号"}), 400


@app.route('/api/admin/restore/add', methods=['POST'])
def api_add_restore():
    data = request.get_json()
    if not data or 'name' not in data or 'password' not in data:
        return jsonify({"error": "缺少必要字段 (name, password)"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.add_restore_point(data['name']):
        return jsonify({"success": True, "message": f"还原点 {data['name']} 已添加"})
    return jsonify({"success": False, "error": "添加失败，可能已达上限、名称已存在或非法"}), 400


@app.route('/api/admin/restore/apply', methods=['POST'])
def api_restore_apply():
    data = request.get_json()
    if not data or 'name' not in data or 'password' not in data:
        return jsonify({"error": "缺少必要字段 (name, password)"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.restore_from_point(data['name']):
        return jsonify({"success": True, "message": f"已从 {data['name']} 恢复"})
    return jsonify({"success": False, "error": "恢复失败，请检查还原点名称"}), 400


@app.route('/api/admin/restore/delete', methods=['POST'])
def api_delete_restore():
    data = request.get_json()
    if not data or 'name' not in data or 'password' not in data:
        return jsonify({"error": "缺少必要字段 (name, password)"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.delete_restore_point(data['name']):
        return jsonify({"success": True, "message": f"已删除还原点 {data['name']}"})
    return jsonify({"success": False, "error": "删除失败，还原点不存在"}), 400


@app.route('/api/admin/restore/format', methods=['POST'])
def api_format_restore():
    data = request.get_json()
    if not data or 'password' not in data:
        return jsonify({"error": "缺少 password 字段"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    if tads.format_restore_points():
        return jsonify({"success": True, "message": "所有还原点已清空"})
    return jsonify({"success": False, "error": "格式化失败"}), 500


@app.route('/api/admin/update_data', methods=['POST'])
def api_update_data():
    data = request.get_json()
    if not data or 'password' not in data:
        return jsonify({"error": "缺少 password 字段"}), 400
    if not tads.verify_admin(data['password']):
        return jsonify({"error": "管理员密码错误或物理密钥失效"}), 403
    result = tads.update_train_data()
    return jsonify(result)


# ---------- 启动入口 ----------
if __name__ == '__main__':
    # 检查端口是否被占用
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(('0.0.0.0', 10076))
        sock.close()
    except OSError:
        print("错误：端口 10076 已被占用")
        sys.exit(1)
    
    print("=" * 60)
    print("TADS API 服务启动（独立运行版）")
    print("监听端口: 10076")
    print(f"数据文件: {DATA_FILE}")
    print(f"日志文件: {LOG_FILE}")
    print("=" * 60)
    print("访问 http://127.0.0.1:10076 查看根路径")
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=10076, debug=False, threaded=True)