# TADS 列车到发时刻数据中心

[![Version](https://img.shields.io/badge/version-v26.8.8-red.svg)](https://github.com/linchenlang/TADS-Server/tags)
[![Python](https://img.shields.io/badge/python-3.8%2B-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-stable-brightgreen.svg)]()

---

## 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
  - [服务端部署](#服务端部署)
  - [客户端部署](#客户端部署)
- [配置说明](#配置说明)
- [API概览](#api概览)
- [项目结构](#项目结构)
- [贡献指南](#贡献指南)
- [许可证](#许可证)
- [联系方式](#联系方式)

---

## 项目简介

**TADS（Train Arrival & Departure Schedule Data Center）** 是一套面向企业内部使用的列车时刻数据管理与查询系统，采用客户端/服务器（C/S）架构，提供轻量级、易部署、权限可控的时刻数据管理解决方案。

系统适用于铁路、地铁、物流等企业或部门，支持多用户并发访问，具备完整的权限管理、数据备份与审计能力，无需依赖外部数据库即可运行。

**新版本（v26.8.8）主要增强：**
- 支持 **V2 实时数据接口**（正晚点、车站大屏、检票口/站台/出站口、列车组图片）
- **物理密钥认证**升级为 PN532 NFC 读卡器（支持 M1 卡和 NTAG215 卡）
- **双模式查询**（本地数据 / 外部 API 实时数据一键切换）
- 客户端完整实现所有服务端查询功能

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **数据管理** | 车次与车站的增删改，经停站（含到发时间、跨天标识）录入与删除，数据实时持久化 |
| **多维度查询** | 9种查询方式：车次停站数、车次经停详情（含检票口/站台/出站口）、车站过路车次、站点时刻表（含上一/下一班）、匹配校验、全局搜索、车次当前位置推算、站间车次查询、车次-车站双向查询 |
| **实时正晚点** | 调用 V2 接口获取列车实时状态，显示晚点/提前分钟数，自动标注“预计正点/晚点” |
| **车站大屏** | 实时展示车站出发/到达信息，包含检票口、出站口及晚点附加信息 |
| **列车组图片** | 显示车厢分布图，双击可放大查看，支持多车厢滚动 |
| **四级权限体系** | 普通用户 → 开发者（标识身份） → 管理员 → Root，逐级提升操作权限，敏感操作需密码验证 |
| **物理密钥认证** | Root 和管理员需通过 NFC 读卡器（PN532）验证 M1 卡（4字节 UID）或 NTAG215 卡（7字节 UID），拔出后自动降级 |
| **双模式查询** | 客户端和服务端均支持一键切换“本地数据”与“外部 API 实时数据”模式 |
| **还原点备份** | 支持最多3个还原点的创建、恢复、删除与格式化，防止误操作导致数据丢失 |
| **操作审计** | 所有关键操作（登录、提权、数据变更、还原点操作）均记录日志，支持导出 CSV |

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                                 客户端层（TADS_client）                           │
│  ┌─────────────────────────┐        ┌─────────────────────────────────────────┐ │
│  │   Tkinter GUI           │        │   API 代理（V1/V2）                     │ │
│  │   双模式查询开关         │        │   本地数据 / 外部 API 实时模式          │ │
│  └───────────┬─────────────┘        └─────────────────┬───────────────────────┘ │
│              │ HTTP Request                          │ HTTP Request              │
│              └────────────────┬─────────────────────┘                           │
│                               ▼                                                │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                    API 服务层（Flask）                                      │ │
│  │                    监听端口：10076                                          │ │
│  │                    绑定地址：0.0.0.0                                        │ │
│  └────────────────────────────┬───────────────────────────────────────────────┘ │
│                               ▼                                                │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                        服务端层（TADS_server）                              │ │
│  │   ┌──────────────┐  ┌─────────────┐  ┌────────────────────────────────┐   │ │
│  │   │ 数据管理     │  │ 查询引擎   │  │ 权限控制（NFC物理密钥验证）    │   │ │
│  │   └──────────────┘  └─────────────┘  └────────────────────────────────┘   │ │
│  └────────────────────────────┬───────────────────────────────────────────────┘ │
│                               ▼                                                │
│  ┌────────────────────────────────────────────────────────────────────────────┐ │
│  │                          数据层                                             │ │
│  │   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │ │
│  │   │ data.json   │  │ 还原点/*.json│  │ log/*.log    │  │ config.json  │  │ │
│  │   │ (主数据)    │  │ (备份数据)   │  │ (审计日志)   │  │ (配置+密钥)  │  │ │
│  │   └─────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │ │
│  └────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                 │
│  外部数据源（V1/V2 API）：rg-api.zenglingkun.cn, kyfw.12306.cn 等              │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 开发语言 | Python 3.8+ |
| Web API | Flask（内嵌于服务端） |
| 桌面界面 | Tkinter（标准库） |
| 客户端通信 | Requests |
| 数据存储 | JSON文件 |
| 密码认证 | SHA256 + 随机盐（16字节） |
| 硬件认证 | PN532 NFC 读卡器（串口通信） |
| 打包工具 | PyInstaller |

---

## 快速开始

### 服务端部署

**前置条件：**
- Windows 7/10/11（推荐以管理员身份运行）
- 固定局域网IP地址（供客户端访问）
- （可选）PN532 NFC 读卡器（用于物理密钥认证）

**步骤：**

```bash
# 1. 下载 TADS_server.exe
# 2. 以管理员身份运行
右键 TADS_server.exe → "以管理员身份运行"

# 3. 确认启动成功
# 控制台显示 "TADS API 服务启动（独立运行版）"
# 界面显示主窗口，状态栏显示 "API服务：正常运行"
```

服务端启动后，数据目录自动创建于 `E:\数据库\TADS_Data\`。

**首次使用需进行管理员提权：**
- 点击左侧导航栏 "提权"
- 点击 "TADS administrator"
- 输入预设管理员密码，并按照提示将 M1 卡放在读卡器上验证
- 如需 Root 权限，需 NTAG215 卡验证

---

### 客户端部署

**前置条件：**
- Windows 7/10/11
- 能够访问服务端IP和端口10076
- （可选）PN532 NFC 读卡器（用于客户端物理密钥验证）

**步骤：**

```bash
# 1. 下载 TADS_client.exe
# 2. 配置服务器地址（需在打包前修改源码，详见配置说明）
# 3. 双击运行
```

> 客户端为绿色软件，无需安装，本地不存储任何数据。

---

## 配置说明

### 客户端服务器地址配置

客户端 `TADS_client.py` 中常量 `DEFAULT_SERVER_IP` 和 `DEFAULT_SERVER_PORT`：

```python
DEFAULT_SERVER_IP = "192.168.100.101"
DEFAULT_SERVER_PORT = 10076
```

修改后使用 PyInstaller 重新打包。

---

### 客户端打包命令（使用 PyInstaller）

```bash
python -m PyInstaller --onefile --windowed --icon=ic_directions_train_128_28252.ico --name=TADS_Client --collect-all=serial --collect-all=cryptography --collect-all=requests --hidden-import=ctypes --hidden-import=tkinter --hidden-import=tkinter.ttk --hidden-import=PIL --hidden-import=PIL.Image --hidden-import=PIL.ImageTk --hidden-import=typing --hidden-import=typing_extensions --hidden-import=serial --hidden-import=serial.tools --hidden-import=serial.tools.list_ports --hidden-import=serial.serialwin32 --hidden-import=_winapi TADS_client.py
```

> 说明：图标文件 `ic_directions_train_128_28252.ico` 需与 `TADS_client.py` 置于同一目录下。

---

### 服务器端打包命令（使用 PyInstaller）

```bash
python -m PyInstaller --onefile --windowed --icon=ic_directions_train_128_28252.ico --name=TADS_Server --collect-all=serial --collect-all=cryptography --collect-all=flask --collect-all=jinja2 --collect-all=markupsafe --collect-all=click --hidden-import=ctypes --hidden-import=tkinter --hidden-import=tkinter.ttk --hidden-import=typing --hidden-import=typing_extensions --hidden-import=serial --hidden-import=serial.tools --hidden-import=serial.tools.list_ports --hidden-import=serial.serialwin32 --hidden-import=_winapi TADS_server.py
```

> 说明：图标文件 `ic_directions_train_128_28252.ico` 需与 `TADS_server.py` 置于同一目录下。

---

### 数据目录修改（服务端）

服务端 `TADS_server.py` 中常量 `DATA_ROOT` 默认为：

```python
DATA_ROOT = r"E:\数据库\TADS_Data"
```

如需更改，修改后重新打包 `TADS_server.exe`。

### 端口修改

默认API端口为 `10076`，如需修改请更改 `app.run(port=10076)` 后重新打包。

---

## API概览

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/` | 无 | 服务信息与端点列表 |
| GET | `/api/health` | 无 | 健康检查 |
| GET | `/api/stats` | 无 | 统计信息 |
| GET | `/api/trains` | 无 | 所有车次（精简） |
| GET | `/api/train/{number}` | 无 | 车次详情 |
| GET | `/api/stations` | 无 | 所有车站 |
| GET | `/api/station/{name}/trains` | 无 | 经过某站的车次 |
| GET | `/api/search` | 无 | 全局搜索（q=关键词） |
| GET | `/api/logs` | 管理员 | 获取最近日志 |
| GET | `/api/admin/restore/list` | 管理员 | 还原点列表 |
| POST | `/api/admin/add_train` | 管理员 | 新增车次 |
| POST | `/api/admin/delete_train` | 管理员 | 删除车次 |
| POST | `/api/admin/add_stop` | 管理员 | 录入经停站 |
| POST | `/api/admin/delete_stop` | 管理员 | 删除经停站 |
| POST | `/api/admin/restore/add` | 管理员 | 添加还原点 |
| POST | `/api/admin/restore/apply` | 管理员 | 从还原点恢复 |
| POST | `/api/admin/restore/delete` | 管理员 | 删除还原点 |
| POST | `/api/admin/restore/format` | 管理员 | 清空还原点 |
| POST | `/api/admin/update_data` | 管理员 | 更新数据 |
|......|......|......|......|

---

## 项目结构

```
TADS/
├── TADS_server.py              # 服务端主程序（含GUI + API）
├── TADS_client.py              # 客户端主程序
├── docs/
│   ├── 技术设计文档.md
│   ├── 用户手册.md
│   ├── 安装与部署指南.md
│   └── API接口文档.md
├── build/                      # PyInstaller构建目录（可选）
└── dist/                       # 可执行文件输出目录
    ├── TADS_server.exe
    └── TADS_client.exe
```

数据运行时目录（自动创建）：

```
E:\数据库\TADS_Data\
├── 主数据\
│   └── data.json
├── 还原点\
│   └── *.json
├── 分数据\
│   └── RailRhythm12306\         # 可选数据源
└── log\
    ├── operations.log
    └── error.log
```

---

## 贡献指南

本系统为内部项目，暂不接受外部代码贡献。如有问题或建议，请通过以下方式联系：

- 内部GitLab Issue跟踪
- 邮件联系：linchenlang@outlook.com

如需二次开发，请遵循以下规范：

- Python代码遵循PEP8风格
- 所有新增API端点需添加注释说明
- 关键操作需写入日志（`log_action`）
- 提交前测试服务端与客户端兼容性

---

## 许可证

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

本项目使用 Apache License 2.0 许可证，详情请见：[LICENSE](LICENSE)

---

## 联系方式

| 角色 | 联系方式 |
|------|----------|
| 项目负责人 | Michael |
| 技术联系人 | linchenlang@outlook.com |

## 数据来源

| 名称 | 网址 |
|------|----------|
| RailGo | https://railgo.dev/ |

## 鸣谢

* RailGo及RailGo全体开发人员

* 所有用户

##### 特别鸣谢

* RailGo开发人员之一：辰墨

* TADS-Server开发组所有成员

---

**TADS** — 让列车时刻数据管理更简单、更安全。

© 2026 QS Studio. All rights reserved.
