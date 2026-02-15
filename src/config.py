# -*- coding: utf-8 -*-
"""
Karvis 统一配置
所有凭证、路径、常量集中管理，不再散落在各模块中。
凭证通过环境变量注入，本地开发可使用 .env 文件。
"""
import os

# ============ DeepSeek API (Tier 2/3: Main + Think) ============
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v3.2")  # 支持 thinking 双模式

# ============ Qwen Flash API (Tier 1: Flash) ============
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")
QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-flash")

# ============ Qwen VL (视觉理解) ============
QWEN_VL_MODEL = os.environ.get("QWEN_VL_MODEL", "qwen-vl-max")  # 复用 QWEN_API_KEY 和 QWEN_BASE_URL

# ============ OneDrive ============
ONEDRIVE_CLIENT_ID = os.environ.get("ONEDRIVE_CLIENT_ID", "")
ONEDRIVE_CLIENT_SECRET = os.environ.get("ONEDRIVE_CLIENT_SECRET", "")
ONEDRIVE_REFRESH_TOKEN = os.environ.get("ONEDRIVE_REFRESH_TOKEN", "")

# ============ 企业微信（WeWork 应用） ============
CORP_ID = os.environ.get("WEWORK_CORP_ID", "")
AGENT_ID = int(os.environ.get("WEWORK_AGENT_ID", "0"))
CORP_SECRET = os.environ.get("WEWORK_CORP_SECRET", "")
WEWORK_TOKEN = os.environ.get("WEWORK_TOKEN", "")
ENCODING_AES_KEY = os.environ.get("WEWORK_ENCODING_AES_KEY", "")

# ============ 腾讯云 ASR ============
TENCENT_APPID = os.environ.get("TENCENT_APPID", "")
TENCENT_SECRET_ID = os.environ.get("TENCENT_SECRET_ID", "")
TENCENT_SECRET_KEY = os.environ.get("TENCENT_SECRET_KEY", "")

# ============ Obsidian 路径（OneDrive 上的路径） ============
OBSIDIAN_BASE = os.environ.get("OBSIDIAN_BASE", "/应用/remotely-save/EmptyVault")
INBOX_PATH = f"{OBSIDIAN_BASE}/00-Inbox"
QUICK_NOTES_FILE = f"{INBOX_PATH}/Quick-Notes.md"
STATE_FILE = f"{INBOX_PATH}/.ai-life-state.json"
TODO_FILE = f"{INBOX_PATH}/Todo.md"
DAILY_NOTES_DIR = f"{OBSIDIAN_BASE}/01-Daily"
ATTACHMENTS_PATH = f"{INBOX_PATH}/attachments"
MISC_FILE = f"{INBOX_PATH}/碎碎念.md"

# 笔记归档目录
BOOK_NOTES_DIR = f"{OBSIDIAN_BASE}/02-Notes/读书笔记"
MEDIA_NOTES_DIR = f"{OBSIDIAN_BASE}/02-Notes/影视笔记"
WORK_NOTES_DIR = f"{OBSIDIAN_BASE}/02-Notes/工作笔记"
EMOTION_NOTES_DIR = f"{OBSIDIAN_BASE}/02-Notes/情感日记"
FUN_NOTES_DIR = f"{OBSIDIAN_BASE}/02-Notes/生活趣事"
VOICE_JOURNAL_DIR = f"{OBSIDIAN_BASE}/02-Notes/语音日记"  # V3-F14

# Karvis memory（OneDrive 上的路径，SOUL/SKILLS/RULES 已迁入 prompts.py）
KARVIS_BASE = f"{OBSIDIAN_BASE}/_Karvis"
MEMORY_FILE = f"{KARVIS_BASE}/memory/memory.md"
DECISION_LOG_FILE = f"{KARVIS_BASE}/logs/decisions.jsonl"

# ============ 心知天气 API（V3-F13：外部信息流） ============
WEATHER_API_KEY = os.environ.get("SENIVERSE_KEY", "")
WEATHER_CITY = os.environ.get("WEATHER_CITY", "北京")

# ============ 运行参数 ============
MSG_CACHE_EXPIRE_SECONDS = 60
CHECKIN_TIMEOUT_SECONDS = 43200  # 12 小时
RECENT_MESSAGES_LIMIT = 10       # 短期记忆保留条数
PROMPT_CACHE_TTL = 1800          # prompt 文件缓存 30 分钟
STATE_CACHE_TTL = 300            # state 本地缓存 5 分钟（O-001）
DEFAULT_USER_ID = os.environ.get("DEFAULT_USER_ID", "YourWeWorkUserID")

# ============ 主动陪伴参数 ============
COMPANION_SILENT_HOURS = 4       # 沉默超过 N 小时才触发
COMPANION_INTERVAL_HOURS = 4     # 两次陪伴推送最小间隔
COMPANION_MAX_DAILY = 3          # 每天最多推送 N 次主动陪伴
COMPANION_RECENT_HOURS = 2       # 最近 N 小时内有互动则跳过
