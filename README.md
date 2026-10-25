<div align="center">

# 🚄 TADS · 列车数据与查询服务系统
**TADS (Train Arrival & Departure Service System)**

**极客 · 安全 · 极速 — 属于每个人的局域网列车数据中枢**

[![Release](https://img.shields.io/github/v/release/linchenlang/TADS-Server?color=blue&style=flat-square)](https://github.com/linchenlang/TADS-Server/releases)
[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%207%2F10%2F11-success?style=flat-square)](https://www.microsoft.com/windows)
[![Security](https://img.shields.io/badge/Security-AES--GCM%20256%20%7C%20PN532-red?style=flat-square)](#-安全架构设计)

</div>

---

## 📖 目录

- [1. 项目简介](#1-项目简介)
- [2. 适用人群与场景](#2-适用人群与场景)
- [3. 核心功能矩阵](#3-核心功能矩阵)
- [4. 安全架构设计](#4-安全架构设计)
- [5. 系统组件拓扑](#5-系统组件拓扑)
- [6. 界面预览](#6-界面预览)
- [7. 快速开始](#7-快速开始)
- [8. 开发与编译](#8-开发与编译)
- [9. 开源协议与致谢](#9-开源协议与致谢)

---

## 1. 项目简介

**TADS (Train Arrival & Departure Service System)** 是由 **QS Studio** 开发的一款轻量级、全栈自研的列车数据服务系统。

基于 Python + Tkinter + Flask 构建，采用 C/S（客户端/服务端）架构。你只需在局域网内（比如家里的旧笔记本、宿舍的服务器，或者办公内网）部署一次，即可让所有连接的设备瞬间拥有一套精准、实时、无需外网的列车信息查询大屏。

> **设计哲学**：我们拒绝臃肿的云端架构。TADS 致力于将强大的数据检索能力与物理级的安全防护结合，提供开箱即用、零运维成本的局域网查询体验。

---

## 2. 适用人群与场景

无论你是谁，只要你对铁路有一份热爱或需求，TADS 都能成为你的得力助手：

*   🚂 **火车迷 / 运转圈大佬**：随时查询车次全经停详情、正晚点状态、动车组配属、本务机车，甚至在局域网内搭建自己的专属“运转大屏”，用于规划行程和拍车。
*   🎒 **普通旅客 / 通勤者**：在家中或小团队内架设后，通过客户端快速查询两站间的列车运行状态、检票口及车站大屏，免去频繁刷新手机网页的烦恼。
*   🛠️ **相关从业者 / 铁道院校师生**：作为内部培训、数据参考与离线时刻表验证的辅助工具，支持批量抓取与本地数据持久化。
*   💻 **极客与开发者**：作为一个基于原生 Tkinter 和自研加密通信的 C/S 架构参考项目，适合学习局域网服务发现、NFC 硬件交互与无感加密。

---

## 3. 核心功能矩阵

| 模块 | 功能描述 |
| :--- | :--- |
| **实时动态** | 支持接入 V1/V2 双引擎数据源，实时拉取列车正晚点、检票口、站台及列车编组（车厢分布图）。 |
| **车站大屏** | 模拟真实车站电子屏，实时获取出发/到达大屏数据，展示发到时间、检票口及晚点/提前信息。 |
| **全维查询** | 支持站点时刻表（含上一班/下一班）、两站间运行状态、车次当前理论位置推算、始发终到双向查询。 |
| **数据运维** | 支持从外部 API 批量抓取车次停站并更新本地数据库。提供 CSV/JSON 格式的全链路审计日志。 |
| **容灾备份** | 具备还原点快照机制，支持重大变更前的手动数据备份与一键回滚。 |
| **双模切换** | 客户端强制提供“本地离线数据”与“API 实时数据”一键切换，无惧外部接口宕机或断网。 |

---

## 4. 安全架构设计

为了满足内网使用，同时避免数据被局域网内的其他设备窃听，TADS 内置了硬核的立体防御体系：

### 🔐 自研无感加密信道 (AES-GCM 256)
- **原理**：客户端与服务端基于 `root_password_hash` 动态派生网络通信密钥。
- **特性**：全量接口请求与响应在 Flask/Werkzeug 的底层自动完成加解密。防窃听、防篡改、防重放。即使局域网内有人抓包，看到的也全是乱码。服务器端更改密码后，全网客户端自动秒级掉线重连。

### 📡 硬件级多因子身份认证 (MFA)
- **ROOT 级**：`密码` + `NTAG215 物理卡 (7字节 UID)` + `Ed25519 签名验证`。
- **管理员级**：`密码` + `M1 物理卡 (4字节 UID)`。
- **开发者级**：`专属用户名` + `专属密码`（去中心化独立账号体系）。
- **密码安全**：所有密文在本地严格采用 `SHA-256 + 随机盐` 哈希存储。

### 🛡️ 零信任权限与物理防死锁
- **最小权限**：管理员权限被硬编码锁定，只能进行日常维护；高危操作（清空日志、改端口、物理密钥管理）仅限 ROOT。
- **应急防死锁**：物理卡丢失后进入应急挂失模式，**前端仅允许禁用密钥，严禁启用**。宁可在极端情况下锁死系统，也绝不给偷卡者任何提权后门。

---

## 5. 系统组件拓扑

TADS 由四个独立且协同的客户端/服务端程序组成：

```text
├── TADS_Deploy.exe         # 一键部署向导（注入路径、账号及物理卡密文）
├── TADS_Server.exe         # 数据中枢（提供 Flask 加密 API 与 Tkinter 管理面板）
├── TADS-Key_Manager.exe    # 物理密钥与密码管理系统（独立鉴权、熔断、审计）
└── TADS_Client.exe         # 局域网查询终端（自动 UDP 发现、绿色免安装）
```

---

## 6. 界面预览

<img width="1919" height="1031" alt="屏幕截图 2026-10-25 104715" src="https://github.com/user-attachments/assets/00e4c1a6-802e-4248-9dc7-ac683a2e7f2c" />
<img width="1919" height="1030" alt="屏幕截图 2026-10-25 104627" src="https://github.com/user-attachments/assets/b1f7661c-48ef-452b-b7e9-b3ab63e432ed" />
<img width="1919" height="1030" alt="屏幕截图 2026-10-25 104549" src="https://github.com/user-attachments/assets/c40bb6a6-d8a1-41ff-9c4c-9fc1b1260878" />
<img width="1919" height="1031" alt="屏幕截图 2026-10-25 104537" src="https://github.com/user-attachments/assets/bfb370ba-6115-48fe-b4e4-a4d0e9a5f236" />
<img width="1919" height="1030" alt="屏幕截图 2026-10-25 104435" src="https://github.com/user-attachments/assets/09d2cd43-8e5b-44f9-a15d-476ea1ec3fec" />
<img width="1919" height="1032" alt="屏幕截图 2026-10-25 104802" src="https://github.com/user-attachments/assets/b15b6336-3d9b-4da0-a845-b2c9162a914c" />


<div align="center">
  <i>欢迎在 Issues 中提交您的实际部署界面截图！</i>
</div>

---

## 7. 快速开始

### 运行环境要求
- **操作系统**：Windows 7 / 10 / 11
- **网络要求**：局域网固定 IP（确保客户端可通过 UDP 广播发现服务端）
- **硬件要求**：PN532 NFC 读卡器及对应的 M1/NTAG 物理卡（仅服务端与密钥管理需要，纯查询客户端不需要）

### 🚀 三步极速部署

**Step 1：环境初始化**
下载 Releases 中提供的 `TADS_Deploy.exe`，按照向导填写管理员/ROOT 密码，绑定物理卡 UID，并**指定您的业务数据存储路径（如 `E:\数据库\TADS_Data`）**。

**Step 2：启动中枢**
双击运行 `TADS_Server.exe`，系统将自动生成自研通信密钥，并在 `10076` 端口开启加密 API 服务。

**Step 3：分发终端**
将 `TADS_Client.exe` 拷贝至局域网内各终端电脑。双击即运行，客户端会自动发现服务器地址并静默拉取网络密钥，全程免配置。

---

## 8. 开发与编译

如果您希望自行编译或进行二次开发，请确保已安装 Python 3.8+ 及相关依赖。

```bash
# 克隆仓库
git clone https://github.com/linchenlang/TADS-Server.git
cd TADS-Server

# 安装依赖
pip install -r requirements.txt

# 编译构建 (示例：编译服务端)
pyinstaller --onefile --windowed --icon=ic_directions_train_128_28252.ico \
            --add-data "ic_directions_train_128_28252.ico;." \
            --add-data "ding.mp3;." \
            --name=TADS_Server TADS_server.py
```
*(注：建议在 Windows 环境下直接使用 PyInstaller 构建，各组件打包命令详见仓库打包脚本)*

---

## 9. 开源协议与致谢

本项目采用 **[CC BY-NC-SA 4.0 (署名-非商业性使用-相同方式共享 4.0 国际)](LICENSE)** 许可协议。

- ✅ **允许**：个人学习、局域网小团队非盈利部署、二次开发并开源。
- ❌ **禁止**：直接用于商业售卖或闭源商业分发（如有商用需求，请联系 QS Studio 获取商业授权）。

**特别鸣谢**：
- [RailGo](https://railgo.zenglingkun.cn/) 团队提供的外部实时数据接口支持。
- 所有为 TADS 提出建议和测试的社区开发者。

<div align="center">
  <br>
  <b>© 2026 QS Studio. Crafted with Excellence.</b>
</div>
