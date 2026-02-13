#!/bin/bash
# ============================================================
#  Karvis 一键安装脚本
#  用法: git clone ... && cd Karvis && ./setup.sh
# ============================================================

set -e

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║         Karvis 安装向导 (Lite 模式)          ║${NC}"
echo -e "${CYAN}${BOLD}║   你的 AI 生活助手，住在企业微信里            ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ============ Step 0: 检查 Python ============
echo -e "${BOLD}[1/5] 检查 Python 环境...${NC}"

PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
fi

if [ -z "$PYTHON_CMD" ]; then
    echo -e "${RED}未找到 Python！请先安装 Python 3.9+${NC}"
    echo "  macOS:   brew install python3"
    echo "  Ubuntu:  sudo apt install python3 python3-pip"
    echo "  Windows: https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    echo -e "${RED}Python 版本过低: $PY_VERSION（需要 3.9+）${NC}"
    exit 1
fi

echo -e "  ${GREEN}✓ Python $PY_VERSION${NC}"

# ============ Step 1: 安装依赖 ============
echo ""
echo -e "${BOLD}[2/5] 安装 Python 依赖...${NC}"

cd "$(dirname "$0")/cloud_function"

$PYTHON_CMD -m pip install -r requirements.txt -q 2>&1 | tail -1
echo -e "  ${GREEN}✓ 依赖安装完成${NC}"

# ============ Step 2: 配置环境变量 ============
echo ""
echo -e "${BOLD}[3/5] 配置环境变量${NC}"

ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    echo -e "  ${YELLOW}已存在 .env 文件，跳过配置（如需修改请手动编辑）${NC}"
else
    echo ""
    echo -e "${CYAN}接下来需要填写几个必要的配置。${NC}"
    echo -e "${CYAN}不确定的项可以直接回车跳过，之后手动编辑 cloud_function/.env${NC}"
    echo ""

    # DeepSeek
    echo -e "${BOLD}── DeepSeek API (必填) ──${NC}"
    echo -e "  注册地址: ${CYAN}https://platform.deepseek.com/${NC}"
    read -p "  DeepSeek API Key: " DEEPSEEK_KEY
    DEEPSEEK_KEY=${DEEPSEEK_KEY:-"sk-your-deepseek-api-key"}

    # 企微
    echo ""
    echo -e "${BOLD}── 企业微信 (必填) ──${NC}"
    echo -e "  管理后台: ${CYAN}https://work.weixin.qq.com/wework_admin/frame${NC}"
    read -p "  企业 ID (Corp ID): " WEWORK_CORP_ID
    WEWORK_CORP_ID=${WEWORK_CORP_ID:-"your-corp-id"}
    read -p "  应用 Secret: " WEWORK_SECRET
    WEWORK_SECRET=${WEWORK_SECRET:-"your-corp-secret"}
    read -p "  应用 Agent ID: " WEWORK_AGENT_ID
    WEWORK_AGENT_ID=${WEWORK_AGENT_ID:-"1000003"}
    read -p "  回调 Token: " WEWORK_TOKEN
    WEWORK_TOKEN=${WEWORK_TOKEN:-"your-callback-token"}
    read -p "  EncodingAESKey: " WEWORK_AES
    WEWORK_AES=${WEWORK_AES:-"your-encoding-aes-key"}

    # 用户 ID
    echo ""
    echo -e "${BOLD}── 用户配置 ──${NC}"
    read -p "  你的企微用户 ID (定时推送目标): " USER_ID
    USER_ID=${USER_ID:-"YourWeWorkUserID"}

    # OneDrive (可选)
    echo ""
    echo -e "${BOLD}── OneDrive (可选，Lite 模式可跳过) ──${NC}"
    echo -e "  ${YELLOW}跳过此步 = 使用本地文件存储（推荐先体验）${NC}"
    read -p "  OneDrive Client ID (回车跳过): " OD_CLIENT_ID
    OD_CLIENT_ID=${OD_CLIENT_ID:-""}
    OD_CLIENT_SECRET=""
    OD_REFRESH_TOKEN=""
    if [ -n "$OD_CLIENT_ID" ]; then
        read -p "  OneDrive Client Secret: " OD_CLIENT_SECRET
        read -p "  OneDrive Refresh Token: " OD_REFRESH_TOKEN
    fi

    # 写入 .env
    cat > "$ENV_FILE" << ENVEOF
# Karvis 环境变量配置（由 setup.sh 自动生成）

# --- DeepSeek API ---
DEEPSEEK_API_KEY=${DEEPSEEK_KEY}
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v3.2

# --- Qwen Flash API（可选，留空则降级到 DeepSeek） ---
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus-latest

# --- OneDrive（留空 = Lite 本地模式） ---
ONEDRIVE_CLIENT_ID=${OD_CLIENT_ID}
ONEDRIVE_CLIENT_SECRET=${OD_CLIENT_SECRET}
ONEDRIVE_REFRESH_TOKEN=${OD_REFRESH_TOKEN}

# --- 企业微信 ---
WEWORK_CORP_ID=${WEWORK_CORP_ID}
WEWORK_AGENT_ID=${WEWORK_AGENT_ID}
WEWORK_CORP_SECRET=${WEWORK_SECRET}
WEWORK_TOKEN=${WEWORK_TOKEN}
WEWORK_ENCODING_AES_KEY=${WEWORK_AES}

# --- 腾讯云 ASR（语音识别，可选） ---
TENCENT_APPID=
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=

# --- 其他 ---
OBSIDIAN_BASE=/应用/remotely-save/EmptyVault
DEFAULT_USER_ID=${USER_ID}
PROCESS_ENDPOINT_URL=http://127.0.0.1:9000/process

# --- 心知天气（可选） ---
SENIVERSE_KEY=
WEATHER_CITY=深圳
ENVEOF

    echo -e "  ${GREEN}✓ .env 已生成${NC}"
fi

# ============ Step 3: 检查存储模式 ============
echo ""
echo -e "${BOLD}[4/5] 检查存储模式...${NC}"

if grep -q "ONEDRIVE_CLIENT_ID=$" "$ENV_FILE" 2>/dev/null || grep -q 'ONEDRIVE_CLIENT_ID=""' "$ENV_FILE" 2>/dev/null || ! grep -q "ONEDRIVE_CLIENT_ID" "$ENV_FILE" 2>/dev/null; then
    echo -e "  ${CYAN}📁 Lite 模式: 笔记保存在本地 cloud_function/data/ 目录${NC}"
    echo -e "  ${YELLOW}   后续想同步到 Obsidian？配置 OneDrive 即可无缝切换${NC}"
else
    echo -e "  ${GREEN}☁️  OneDrive 模式: 笔记自动同步到 Obsidian Vault${NC}"
fi

# ============ Step 4: 启动提示 ============
echo ""
echo -e "${BOLD}[5/5] 安装完成!${NC}"
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║              安装成功!                       ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  启动 Karvis:"
echo -e "    ${CYAN}cd cloud_function && $PYTHON_CMD app.py${NC}"
echo ""
echo -e "  启动后:"
echo -e "    1. Karvis 监听 ${BOLD}http://localhost:9000${NC}"
echo -e "    2. 定时任务自动运行（内置调度器）"
echo -e "    3. 配置企微回调 URL 指向此地址"
echo ""
echo -e "  ${YELLOW}提示: 本地运行需要公网可访问的 URL 给企微回调${NC}"
echo -e "  ${YELLOW}推荐使用 ngrok 或 frp 做内网穿透:${NC}"
echo -e "    ${CYAN}ngrok http 9000${NC}"
echo ""
echo -e "  ${BOLD}详细教程见 README.md${NC}"
echo ""

# 询问是否立即启动
read -p "是否立即启动 Karvis? (y/N): " START_NOW
if [[ "$START_NOW" == "y" || "$START_NOW" == "Y" ]]; then
    echo ""
    echo -e "${GREEN}启动中...${NC}"
    $PYTHON_CMD app.py
fi
