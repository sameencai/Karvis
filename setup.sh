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

    # 必填项读取函数（不允许为空）
    read_required() {
        local prompt="$1"
        local value=""
        while true; do
            read -p "$prompt" value
            # 去除首尾空格
            value=$(echo "$value" | xargs)
            if [ -n "$value" ]; then
                break
            fi
            echo -e "  ${RED}此项为必填，不能为空${NC}" >&2
        done
        echo "$value"
    }

    # DeepSeek
    echo -e "${BOLD}── DeepSeek API (必填) ──${NC}"
    echo -e "  ${CYAN}[1] DeepSeek 官方  https://platform.deepseek.com/${NC}"
    echo -e "  ${CYAN}[2] 腾讯云 lkeap   https://console.cloud.tencent.com/lkeap${NC}"
    echo -e "  ${CYAN}[3] 其他兼容平台（手动输入 Base URL）${NC}"
    read -p "  选择 API 来源 [1/2/3，默认 1]: " DS_SOURCE
    DS_SOURCE=${DS_SOURCE:-"1"}

    case "$DS_SOURCE" in
        2)
            DEEPSEEK_BASE_URL="https://api.lkeap.cloud.tencent.com/v1"
            echo -e "  ${GREEN}✓ 使用腾讯云 lkeap${NC}"
            ;;
        3)
            read -p "  请输入 Base URL: " DEEPSEEK_BASE_URL
            DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL:-"https://api.deepseek.com/v1"}
            ;;
        *)
            DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
            echo -e "  ${GREEN}✓ 使用 DeepSeek 官方${NC}"
            ;;
    esac

    DEEPSEEK_KEY=$(read_required "  DeepSeek API Key: ")

    # 企微
    echo ""
    echo -e "${BOLD}── 企业微信 (必填) ──${NC}"
    echo -e "  管理后台: ${CYAN}https://work.weixin.qq.com/wework_admin/frame${NC}"
    echo -e "  ${YELLOW}⚠ 重要: 应用的「企业可信IP」必须留空，否则消息发不出去${NC}"
    WEWORK_CORP_ID=$(read_required "  企业 ID (Corp ID): ")
    WEWORK_SECRET=$(read_required "  应用 Secret: ")
    read -p "  应用 Agent ID [默认 1000003]: " WEWORK_AGENT_ID
    WEWORK_AGENT_ID=${WEWORK_AGENT_ID:-"1000003"}
    WEWORK_TOKEN=$(read_required "  回调 Token: ")
    WEWORK_AES=$(read_required "  EncodingAESKey: ")

    # 用户 ID
    echo ""
    echo -e "${BOLD}── 用户配置 ──${NC}"
    read -p "  你的企微用户 ID (定时推送目标，可回车跳过): " USER_ID
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
DEEPSEEK_BASE_URL=${DEEPSEEK_BASE_URL}
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
echo -e "${BOLD}[4/6] 检查存储模式...${NC}"

if grep -q "ONEDRIVE_CLIENT_ID=$" "$ENV_FILE" 2>/dev/null || grep -q 'ONEDRIVE_CLIENT_ID=""' "$ENV_FILE" 2>/dev/null || ! grep -q "ONEDRIVE_CLIENT_ID" "$ENV_FILE" 2>/dev/null; then
    echo -e "  ${CYAN}📁 Lite 模式: 笔记保存在本地 cloud_function/data/ 目录${NC}"
    echo -e "  ${YELLOW}   后续想同步到 Obsidian？配置 OneDrive 即可无缝切换${NC}"
else
    echo -e "  ${GREEN}☁️  OneDrive 模式: 笔记自动同步到 Obsidian Vault${NC}"
fi

# ============ Step 4: 安装内网穿透工具 ============
echo ""
echo -e "${BOLD}[5/6] 检查内网穿透工具...${NC}"

TUNNEL_CMD=""
if command -v cloudflared &>/dev/null; then
    TUNNEL_CMD="cloudflared"
    echo -e "  ${GREEN}✓ cloudflared 已安装${NC}"
elif command -v ngrok &>/dev/null; then
    TUNNEL_CMD="ngrok"
    echo -e "  ${GREEN}✓ ngrok 已安装${NC}"
else
    echo -e "  ${YELLOW}未找到内网穿透工具，正在安装 cloudflared（免注册、免配置）...${NC}"
    if command -v brew &>/dev/null; then
        brew install cloudflared 2>&1 | tail -3
        if command -v cloudflared &>/dev/null; then
            TUNNEL_CMD="cloudflared"
            echo -e "  ${GREEN}✓ cloudflared 安装成功${NC}"
        fi
    elif command -v apt-get &>/dev/null; then
        sudo apt-get install -y cloudflared 2>&1 | tail -3
        if command -v cloudflared &>/dev/null; then
            TUNNEL_CMD="cloudflared"
            echo -e "  ${GREEN}✓ cloudflared 安装成功${NC}"
        fi
    fi

    if [ -z "$TUNNEL_CMD" ]; then
        echo -e "  ${RED}自动安装失败，请手动安装: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/${NC}"
        echo -e "  ${YELLOW}或安装 ngrok: brew install ngrok${NC}"
    fi
fi

# ============ Step 5: 启动提示 ============
echo ""
echo -e "${BOLD}[6/6] 安装完成!${NC}"
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║              安装成功!                       ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BOLD}详细教程见 README.md${NC}"
echo ""

# 询问是否立即启动
read -p "是否立即启动 Karvis? (y/N): " START_NOW
if [[ "$START_NOW" == "y" || "$START_NOW" == "Y" ]]; then
    echo ""

    # 启动 Karvis
    echo -e "${GREEN}启动 Karvis...${NC}"
    $PYTHON_CMD app.py &
    KARVIS_PID=$!
    sleep 2

    # 检查 Karvis 是否启动成功
    if ! kill -0 $KARVIS_PID 2>/dev/null; then
        echo -e "${RED}Karvis 启动失败，请检查日志${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✓ Karvis 已启动 (PID: $KARVIS_PID)${NC}"

    # 启动内网穿透
    if [ "$TUNNEL_CMD" == "cloudflared" ]; then
        echo ""
        echo -e "${GREEN}启动内网穿透 (cloudflared)...${NC}"
        echo -e "${CYAN}等待生成公网 URL...${NC}"
        echo ""
        # cloudflared 输出 URL 到 stderr
        cloudflared tunnel --url http://localhost:9000 2>&1 &
        TUNNEL_PID=$!
        
        # 等待 URL 出现（cloudflared 需要几秒请求隧道）
        echo -e "  ${YELLOW}等待隧道建立...${NC}"
        TUNNEL_URL=""
        for i in $(seq 1 20); do
            sleep 1
            # 尝试从 cloudflared 的 metrics 端口获取 URL
            TUNNEL_URL=$(curl -s http://127.0.0.1:20241/metrics 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | head -1)
            if [ -n "$TUNNEL_URL" ]; then
                break
            fi
        done

        echo ""
        if [ -n "$TUNNEL_URL" ]; then
            echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
            echo -e "${GREEN}${BOLD}║  公网 URL 已生成!                                            ║${NC}"
            echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
            echo ""
            echo -e "  你的公网地址: ${CYAN}${BOLD}${TUNNEL_URL}${NC}"
            echo ""
            echo -e "  ${BOLD}去企微后台 → 应用 → 接收消息 → API 接收 → URL 填:${NC}"
            echo -e "  ${CYAN}${BOLD}${TUNNEL_URL}/wework${NC}"
            echo ""
            echo -e "  填好后在企微里给应用发条消息试试!"
        else
            echo -e "${YELLOW}隧道正在建立中，请在上方日志中找到类似这样的 URL:${NC}"
            echo -e "  ${CYAN}https://xxx-xxx-xxx.trycloudflare.com${NC}"
            echo ""
            echo -e "  去企微后台 → 应用 → 接收消息 → API 接收 → URL 填:"
            echo -e "  ${CYAN}https://xxx-xxx-xxx.trycloudflare.com/wework${NC}"
        fi
        echo ""
        echo -e "  按 Ctrl+C 停止所有服务"

        # 等待用户中断
        trap "kill $KARVIS_PID $TUNNEL_PID 2>/dev/null; exit 0" INT TERM
        wait $KARVIS_PID

    elif [ "$TUNNEL_CMD" == "ngrok" ]; then
        echo ""
        echo -e "${GREEN}启动内网穿透 (ngrok)...${NC}"
        echo -e "${YELLOW}如果 ngrok 要求 authtoken，请访问 https://dashboard.ngrok.com/get-started/your-authtoken${NC}"
        echo ""
        ngrok http 9000 &
        TUNNEL_PID=$!
        trap "kill $KARVIS_PID $TUNNEL_PID 2>/dev/null; exit 0" INT TERM
        wait $KARVIS_PID
    else
        echo ""
        echo -e "${YELLOW}没有内网穿透工具，Karvis 仅在本地可用 (http://localhost:9000)${NC}"
        echo -e "${YELLOW}请手动安装 cloudflared 后运行: cloudflared tunnel --url http://localhost:9000${NC}"
        wait $KARVIS_PID
    fi
fi
