# -*- coding: utf-8 -*-
"""
TADS 物理密钥一键迁移脚本
功能：从旧的 .env 和 name.env 中读取所有数据，
直接生成并写入新的 key_status.env（无需手动在工具里逐条录入）
"""
import os
import sys

# ================== 路径配置 ==================
APP_CONFIG_DIR = os.path.join(os.getenv('APPDATA'), 'TADS', 'Server', 'config')
if not os.path.exists(APP_CONFIG_DIR):
    os.makedirs(APP_CONFIG_DIR)

ENV_PATH = os.path.join(APP_CONFIG_DIR, ".env")
NAME_PATH = os.path.join(APP_CONFIG_DIR, "name.env")
STATUS_PATH = os.path.join(APP_CONFIG_DIR, "key_status.env")


def read_env_file():
    """读取主验证配置文件"""
    admin_uids = []
    root_uids = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    if key == 'ADMIN_UID' and val:
                        admin_uids = [uid.strip().upper() for uid in val.split(',') if uid.strip()]
                    elif key == 'ROOT_UID' and val:
                        root_uids = [uid.strip().upper() for uid in val.split(',') if uid.strip()]
    return admin_uids, root_uids


def read_name_env():
    """读取旧的名称和类型文件"""
    name_map = {}
    card_types = {}
    if os.path.exists(NAME_PATH):
        with open(NAME_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, val = line.split('=', 1)
                    key = key.strip()
                    val = val.strip()
                    if key.startswith('NAME_'):
                        uid = key[5:].strip().upper()
                        name_map[uid] = val
                    elif key.startswith('TYPE_'):
                        uid = key[5:].strip().upper()
                        card_types[uid] = val
    return name_map, card_types


def build_status_data(admin_uids, root_uids, name_map, card_types):
    """构建新的完整状态数据格式: UID|卡类型|权限等级|名称|启用状态"""
    # 使用字典合并去重，同一个 UID 同时存在于两个列表时权限设为 Both
    merged = {}
    for uid in admin_uids:
        if uid in root_uids:
            permission = 'Both'
        else:
            permission = 'Administrator'
        merged[uid] = {"permission": permission}

    # 处理 ROOT 单独存在的 UID
    for uid in root_uids:
        if uid not in merged:
            merged[uid] = {"permission": 'ROOT'}

    # 为每条记录补全其他字段
    result = []
    for uid, info in merged.items():
        # 推断卡类型
        if uid in card_types:
            card_type = card_types[uid]
        elif len(uid) == 14:
            card_type = "NTAG"
        elif len(uid) == 8:
            card_type = "M1"
        else:
            card_type = "未知"

        # 获取名称
        name = name_map.get(uid, "")

        result.append(f"{uid}|{card_type}|{info['permission']}|{name}|TRUE")

    return result


def main():
    print("=" * 60)
    print("TADS 物理密钥一键迁移脚本")
    print("=" * 60)

    # 1. 读取旧配置
    admin_uids, root_uids = read_env_file()
    name_map, card_types = read_name_env()

    print(f"从 .env 中读取到管理员 UID 数量: {len(admin_uids)}")
    print(f"从 .env 中读取到 ROOT UID 数量: {len(root_uids)}")
    print(f"从 name.env 中读取到名称/类型记录: {len(name_map)}")

    # 2. 构建新数据
    status_lines = build_status_data(admin_uids, root_uids, name_map, card_types)

    if not status_lines:
        print("\n❌ 未读取到任何有效数据，请检查 .env 文件是否正确。")
        sys.exit(1)

    # 3. 写入新文件
    try:
        with open(STATUS_PATH, 'w', encoding='utf-8') as f:
            for line in status_lines:
                f.write(line + "\n")
        print(f"\n✅ 成功！已迁移 {len(status_lines)} 个密钥到新的 key_status.env")
        print(f"文件位置: {STATUS_PATH}")
        print("\n迁移记录如下:")
        for line in status_lines:
            print(f"  - {line}")
    except Exception as e:
        print(f"\n❌ 写入失败: {e}")
        sys.exit(1)

    print("\n💡 提示：现在打开 TADS 物理密钥管理系统，列表会自动显示以上所有密钥！")


if __name__ == "__main__":
    main()