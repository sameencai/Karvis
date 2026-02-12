# -*- coding: utf-8 -*-
"""
Karvis 消息网关
职责：接收企微消息 → 下载媒体/ASR → 构造 payload → 交给 brain.process()
不做任何业务判断，所有逻辑由大脑决定。
"""
from flask import Flask, request
import json
import time
import sys
import hashlib
import base64
import requests
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

from config import (
    CORP_ID, CORP_SECRET, AGENT_ID,
    WEWORK_TOKEN, ENCODING_AES_KEY,
    TENCENT_APPID, TENCENT_SECRET_ID, TENCENT_SECRET_KEY,
    ATTACHMENTS_PATH, MSG_CACHE_EXPIRE_SECONDS,
    DEFAULT_USER_ID, STATE_FILE,
    WEATHER_API_KEY, WEATHER_CITY
)
import os

# 异步处理端点的公网 URL（SCF 部署后填入，用于企微 5 秒超时的异步转发）
PROCESS_ENDPOINT_URL = os.environ.get("PROCESS_ENDPOINT_URL", "http://127.0.0.1:9000/process")
from wework_crypto import WXBizMsgCrypt
from onedrive_io import OneDriveIO
import brain

app = Flask(__name__)


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# ============ 企微 access_token 缓存 ============
_wework_token_cache = {"token": None, "expire_time": 0}


def get_wework_access_token():
    now = time.time()
    if _wework_token_cache["token"] and _wework_token_cache["expire_time"] > now:
        return _wework_token_cache["token"]
    url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORP_ID}&corpsecret={CORP_SECRET}"
    resp = requests.get(url, timeout=10)
    result = resp.json()
    if result.get("errcode") == 0:
        _wework_token_cache["token"] = result["access_token"]
        _wework_token_cache["expire_time"] = now + result["expires_in"] - 200
        return result["access_token"]
    _log(f"[企微] token 获取失败: {result}")
    return None


# ============ 消息发送 ============

def send_wework_message(user_id, content):
    """发送企业微信文本消息"""
    token = get_wework_access_token()
    if not token:
        return False
    url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
    data = {
        "touser": user_id,
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {"content": content}
    }
    resp = requests.post(url, json=data, timeout=10)
    result = resp.json()
    ok = result.get("errcode") == 0
    if not ok:
        _log(f"[回复] 发送失败: {result}")
    return ok


# ============ 消息去重 ============
_processed_msg_cache = {}


def is_duplicate_msg(msg_id):
    if not msg_id:
        return False
    now = time.time()
    # 清理过期
    expired = [k for k, v in _processed_msg_cache.items() if v < now]
    for k in expired:
        del _processed_msg_cache[k]
    if msg_id in _processed_msg_cache:
        _log(f"[去重] 跳过: {msg_id}")
        return True
    _processed_msg_cache[msg_id] = now + MSG_CACHE_EXPIRE_SECONDS
    return False


# ============ 媒体下载 ============

def download_wework_media(media_id):
    """从企微下载临时素材，返回 (bytes, content_type) 或 (None, None)"""
    token = get_wework_access_token()
    if not token:
        return None, None
    url = f"https://qyapi.weixin.qq.com/cgi-bin/media/get?access_token={token}&media_id={media_id}"
    resp = requests.get(url, timeout=30)
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" in content_type or "text/plain" in content_type:
        _log(f"[素材] 下载失败: {resp.text[:200]}")
        return None, None
    _log(f"[素材] 下载成功: size={len(resp.content)}, type={content_type}")
    return resp.content, content_type


# ============ 附件上传 ============

BEIJING_TZ = timezone(timedelta(hours=8))


def generate_attachment_name(msg_type, ext):
    ts = datetime.now(BEIJING_TZ).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{msg_type}.{ext}"


def upload_attachment(data, msg_type, ext, content_type="application/octet-stream"):
    """上传附件到 OneDrive，返回完整路径或 None"""
    filename = generate_attachment_name(msg_type, ext)
    onedrive_path = f"{ATTACHMENTS_PATH}/{filename}"
    ok = OneDriveIO.upload_binary(onedrive_path, data, content_type)
    return onedrive_path if ok else None


# ============ ASR 语音识别 ============

def recognize_voice(audio_data, voice_format="amr"):
    """腾讯云录音文件识别极速版，降级到一句话识别"""
    import hmac

    if not TENCENT_APPID:
        _log("[ASR] 未配置 APPID，降级到一句话识别")
        return _recognize_voice_sentence(audio_data)

    try:
        timestamp = int(time.time())
        params = {
            "convert_num_mode": 1,
            "engine_type": "16k_zh",
            "filter_dirty": 0,
            "filter_modal": 0,
            "filter_punc": 0,
            "first_channel_only": 1,
            "secretid": TENCENT_SECRET_ID,
            "speaker_diarization": 0,
            "timestamp": timestamp,
            "voice_format": voice_format,
            "word_info": 0,
        }
        query_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        sign_str = f"POSTasr.cloud.tencent.com/asr/flash/v1/{TENCENT_APPID}?{query_str}"
        signature = base64.b64encode(
            hmac.new(TENCENT_SECRET_KEY.encode('utf-8'),
                     sign_str.encode('utf-8'), hashlib.sha1).digest()
        ).decode('utf-8')

        url = f"https://asr.cloud.tencent.com/asr/flash/v1/{TENCENT_APPID}?{query_str}"
        headers = {
            "Host": "asr.cloud.tencent.com",
            "Authorization": signature,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(audio_data)),
        }
        resp = requests.post(url, headers=headers, data=audio_data, timeout=30)
        result = resp.json()
        _log(f"[ASR极速版] code={result.get('code')}")

        if result.get("code") != 0:
            _log(f"[ASR极速版] 失败: {result.get('message')}")
            return _recognize_voice_sentence(audio_data)

        flash_result = result.get("flash_result", [])
        if flash_result:
            text = flash_result[0].get("text", "")
            _log(f"[ASR极速版] 识别: {text[:80]}")
            return text if text else None
        return None
    except Exception as e:
        _log(f"[ASR极速版] 异常: {e}")
        return _recognize_voice_sentence(audio_data)


def _recognize_voice_sentence(audio_data):
    """降级：腾讯云一句话识别"""
    try:
        from tencentcloud.common import credential
        from tencentcloud.common.profile.client_profile import ClientProfile
        from tencentcloud.common.profile.http_profile import HttpProfile
        from tencentcloud.asr.v20190614 import asr_client, models

        cred = credential.Credential(TENCENT_SECRET_ID, TENCENT_SECRET_KEY)
        httpProfile = HttpProfile()
        httpProfile.endpoint = "asr.tencentcloudapi.com"
        httpProfile.reqTimeout = 30
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile

        client = asr_client.AsrClient(cred, "", clientProfile)
        req = models.SentenceRecognitionRequest()
        req.EngSerViceType = "16k_zh"
        req.SourceType = 1
        req.VoiceFormat = "amr"
        req.Data = base64.b64encode(audio_data).decode('utf-8')
        req.DataLen = len(audio_data)

        resp = client.SentenceRecognition(req)
        _log(f"[ASR一句话] 成功: {resp.Result[:50] if resp.Result else 'empty'}")
        return resp.Result
    except Exception as e:
        _log(f"[ASR一句话] 失败: {e}")
        return None


# ============ XML 消息解析 ============

def parse_wechat_message(xml_data):
    """解析企微 XML 消息"""
    root = ET.fromstring(xml_data)
    msg_type = root.find('MsgType').text
    from_user = root.find('FromUserName').text
    result = {'msg_type': msg_type, 'from_user': from_user}

    msg_id = root.find('MsgId')
    if msg_id is not None:
        result['msg_id'] = msg_id.text

    if msg_type == 'text':
        result['content'] = root.find('Content').text
    elif msg_type == 'image':
        media_id = root.find('MediaId')
        if media_id is not None:
            result['media_id'] = media_id.text
    elif msg_type == 'voice':
        media_id = root.find('MediaId')
        fmt = root.find('Format')
        if media_id is not None:
            result['media_id'] = media_id.text
        if fmt is not None:
            result['format'] = fmt.text
    elif msg_type == 'video':
        media_id = root.find('MediaId')
        if media_id is not None:
            result['media_id'] = media_id.text
    elif msg_type == 'link':
        for tag in ('Title', 'Description', 'Url'):
            node = root.find(tag)
            if node is not None:
                result[tag.lower()] = node.text

    return result


# ============ F1: 链接内容抓取 ============

import re

_URL_PATTERN = re.compile(
    r'https?://[^\s<>"\')\]]+',
    re.IGNORECASE
)


def _extract_url(text):
    """
    从文本中提取 URL。
    仅当文本主体是 URL 时才提取（纯 URL 或 URL + 少量描述文字）。
    避免对正常聊天中偶尔出现的 URL 做不必要的抓取。
    """
    text = text.strip()
    match = _URL_PATTERN.search(text)
    if not match:
        return None
    url = match.group(0)
    # 只有当 URL 占文本大部分时才抓取（纯 URL 或 URL + 简短描述）
    non_url_text = text.replace(url, "").strip()
    if len(non_url_text) <= 30:
        return url
    return None

def _fetch_link_content(url):
    """
    F1: 抓取链接正文内容，失败返回空字符串（优雅降级）。
    支持微信公众号文章、普通网页。截断到 2000 字符。
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=5,
                           allow_redirects=True, verify=True)
        resp.encoding = resp.apparent_encoding or 'utf-8'

        if resp.status_code != 200:
            _log(f"[链接抓取] HTTP {resp.status_code}: {url[:80]}")
            return ""

        content_type = resp.headers.get('Content-Type', '')
        if 'text/html' not in content_type and 'text/plain' not in content_type:
            _log(f"[链接抓取] 非网页内容({content_type}): {url[:80]}")
            return ""

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 移除无用标签
        for tag in soup.find_all(['script', 'style', 'nav', 'header',
                                   'footer', 'aside', 'iframe']):
            tag.decompose()

        # 优先取 article 标签（通用）或微信文章专用结构
        article = (soup.find('article')
                   or soup.find('div', class_='rich_media_content')
                   or soup.find('body'))

        if not article:
            _log(f"[链接抓取] 无法提取正文: {url[:80]}")
            return ""

        text = article.get_text(separator='\n', strip=True)
        result = text[:2000] if text else ""
        _log(f"[链接抓取] 成功: {len(result)} 字符, url={url[:80]}")
        return result
    except Exception as e:
        _log(f"[链接抓取] 异常({e}): {url[:80]}")
        return ""


# ============ 消息 → Payload 转换（网关核心） ============

def build_payload(msg):
    """
    将企微原始消息转换为 Karvis payload。
    处理媒体下载、附件上传、ASR，但不做任何业务判断。
    返回 payload dict。
    """
    msg_type = msg['msg_type']
    user_id = msg.get('from_user', '')
    payload = {"user_id": user_id}

    if msg_type == 'text':
        content = msg.get('content', '')
        if content.startswith('/help') or content.startswith('帮助'):
            # 帮助命令直接在网关层处理
            return None, 'Karvis 🤖\n\n发送任何内容，我会帮你记录到 Obsidian。\n支持：文字、图片、语音、视频、链接\n\n打卡相关：说"打卡"开始每日复盘'
        payload["type"] = "text"
        payload["text"] = content
        # F1: 检测纯 URL 文本，自动抓取网页正文
        url = _extract_url(content)
        if url:
            page_content = _fetch_link_content(url)
            if page_content:
                payload["page_content"] = page_content
                payload["detected_url"] = url
        return payload, None

    elif msg_type == 'image':
        media_id = msg.get('media_id', '')
        if not media_id:
            return None, "无法获取图片"
        data, content_type = download_wework_media(media_id)
        if not data:
            return None, "图片下载失败"
        ext = "jpg"
        if "png" in (content_type or ""):
            ext = "png"
        elif "gif" in (content_type or ""):
            ext = "gif"
        attachment = upload_attachment(data, "img", ext, content_type or "image/jpeg")
        if not attachment:
            return None, "图片上传失败"
        payload["type"] = "image"
        payload["attachment"] = attachment
        return payload, None

    elif msg_type == 'voice':
        media_id = msg.get('media_id', '')
        audio_format = msg.get('format', 'amr')
        if not media_id:
            return None, "无法获取语音"
        data, content_type = download_wework_media(media_id)
        if not data:
            return None, "语音下载失败"
        ext = audio_format.lower() if audio_format else "amr"
        attachment = upload_attachment(data, "voice", ext, content_type or "audio/amr")
        recognized_text = recognize_voice(data, voice_format=ext) or ""
        payload["type"] = "voice"
        payload["text"] = recognized_text
        payload["attachment"] = attachment or ""
        return payload, None

    elif msg_type == 'video':
        media_id = msg.get('media_id', '')
        if not media_id:
            return None, "无法获取视频"
        data, content_type = download_wework_media(media_id)
        if not data:
            return None, "视频下载失败"
        size_mb = len(data) / (1024 * 1024)
        _log(f"[视频] 大小={size_mb:.1f}MB")
        attachment = upload_attachment(data, "video", "mp4", content_type or "video/mp4")
        if not attachment:
            return None, "视频上传失败"
        payload["type"] = "video"
        payload["attachment"] = attachment
        return payload, None

    elif msg_type == 'link':
        payload["type"] = "link"
        payload["title"] = msg.get('title', '链接')
        payload["url"] = msg.get('url', '')
        payload["description"] = msg.get('description', '')[:200]
        # F1: 抓取网页正文内容
        if payload["url"]:
            payload["content"] = _fetch_link_content(payload["url"])
        return payload, None

    else:
        return None, f"暂不支持该消息类型: {msg_type}"


# ============ 消息处理主流程 ============

def handle_message(msg, user_id):
    """
    网关主处理流程：
    1. 构造 payload（含媒体处理）
    2. 交给 brain.process()
    3. 发送回复
    """
    try:
        payload, quick_reply = build_payload(msg)

        # 帮助命令或媒体处理失败
        if payload is None:
            if quick_reply and user_id:
                send_wework_message(user_id, quick_reply)
            return

        # 交给大脑（传入发送回调，实现先回复后保存）
        def _send_reply(text):
            if user_id:
                send_wework_message(user_id, text)

        result = brain.process(payload, send_fn=_send_reply)
        reply = result.get("reply") if result else None
        already_sent = result.get("already_sent", False) if result else False

        # 如果 brain 已经通过 send_fn 发送，不再重复发送
        if reply and user_id and not already_sent:
            send_wework_message(user_id, reply)

    except Exception as e:
        _log(f"[网关] 处理异常: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        if user_id:
            send_wework_message(user_id, "处理消息时出错了，请稍后重试")


# ============ 加解密器 ============
wx_crypt = WXBizMsgCrypt(WEWORK_TOKEN, ENCODING_AES_KEY, CORP_ID)


# ============ Flask 路由 ============

@app.route('/wework', methods=['GET', 'POST'])
def wework():
    """企业微信入口"""
    if request.method == 'GET':
        msg_signature = request.args.get('msg_signature', '')
        timestamp = request.args.get('timestamp', '')
        nonce = request.args.get('nonce', '')
        echostr = request.args.get('echostr', '')
        reply = wx_crypt.verify_url(msg_signature, timestamp, nonce, echostr)
        return reply if reply else "verify failed"

    if request.method == 'POST':
        try:
            xml_data = request.data.decode('utf-8')
            _log("[企微] 收到 POST")

            msg_signature = request.args.get('msg_signature', '')
            timestamp = request.args.get('timestamp', '')
            nonce = request.args.get('nonce', '')

            # 解密
            root = ET.fromstring(xml_data)
            encrypt_node = root.find('Encrypt')
            if encrypt_node is not None:
                decrypted_xml = wx_crypt.decrypt_msg(
                    msg_signature, timestamp, nonce, encrypt_node.text)
                if not decrypted_xml:
                    _log("[企微] 解密失败")
                    return "success"
                msg = parse_wechat_message(decrypted_xml)
            else:
                msg = parse_wechat_message(xml_data)

            user_id = msg.get('from_user', '')
            msg_id = msg.get('msg_id', '')
            _log(f"[企微] user={user_id}, type={msg['msg_type']}, id={msg_id}")

            # 消息去重
            if msg_id and is_duplicate_msg(msg_id):
                return "success"

            # 异步处理：通过公网 URL 调用自己的 /process 端点
            # 这会触发一个全新的 SCF 请求，不受企微 5 秒超时影响
            payload_data = json.dumps({
                "msg": msg,
                "user_id": user_id
            }, ensure_ascii=False)

            def fire_and_forget():
                try:
                    resp = requests.post(
                        PROCESS_ENDPOINT_URL,
                        data=payload_data.encode('utf-8'),
                        headers={"Content-Type": "application/json"},
                        timeout=300  # 等完整响应，日报等重任务可能需要更久
                    )
                    _log(f"[触发] /process 返回: {resp.status_code}")
                except Exception as e:
                    _log(f"[触发] /process 调用异常: {e}")

            t = threading.Thread(target=fire_and_forget)
            t.start()

            # 等一小段时间确保请求已发出（TCP 握手完成）
            time.sleep(0.3)

            _log(f"[企微] 已触发 /process，立即返回 success")
            return "success"

        except Exception as e:
            _log(f"[企微] 错误: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
            return "success"

    return "success"


@app.route('/process', methods=['POST'])
def process_endpoint():
    """内部异步处理端点：接收消息并调用 brain 处理"""
    try:
        data = request.get_json(force=True)
        msg = data.get("msg", {})
        user_id = data.get("user_id", "")
        _log(f"[/process] 开始处理 type={msg.get('msg_type')}, user={user_id}")
        handle_message(msg, user_id)
        _log(f"[/process] 处理完成")
        return "ok"
    except Exception as e:
        _log(f"[/process] 异常: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return "error"


@app.route('/system', methods=['POST'])
def system_endpoint():
    """系统端点：定时器/手动触发的 system action"""
    try:
        data = request.get_json(force=True)
        action = data.get("action", "")
        _log(f"[/system] action={action}")

        if action == "refresh_cache":
            from memory import _prompt_cache
            _prompt_cache.invalidate()
            _log("[/system] 缓存已全部清除")
            return json.dumps({"ok": True, "action": "refresh_cache"})

        if action == "todo_remind":
            # 提醒检查：纯扫描逻辑，不经过 LLM
            target_user = data.get("user_id", DEFAULT_USER_ID)
            from skills.todo_manage import check_reminders
            state = OneDriveIO.read_json(STATE_FILE) or {}
            result = check_reminders(state)
            messages = result.get("messages", [])
            state_updates = result.get("state_updates", {})
            # 推送消息
            for msg in messages:
                send_wework_message(target_user, msg)
            # 写回 state
            if state_updates:
                for k, v in state_updates.items():
                    state[k] = v
                OneDriveIO.write_json(STATE_FILE, state)
                _log(f"[/system] todo_remind state 已更新")
            _log(f"[/system] todo_remind 完成, 推送 {len(messages)} 条")
            return json.dumps({"ok": True, "action": "todo_remind", "sent": len(messages)})

        if action in ("morning_report", "evening_checkin", "daily_report"):
            # 需要 LLM 生成内容的系统动作 — 注入上下文数据
            target_user = data.get("user_id", DEFAULT_USER_ID)

            # 读取待办和速记作为上下文（O-007）
            context = {}
            try:
                from config import TODO_FILE, QUICK_NOTES_FILE
                todo_content = OneDriveIO.read_text(TODO_FILE)
                if todo_content:
                    context["todo"] = todo_content[:2000]
                quick_notes = OneDriveIO.read_text(QUICK_NOTES_FILE)
                if quick_notes:
                    context["quick_notes"] = quick_notes[:1000]
            except Exception as e:
                _log(f"[/system] 读取上下文失败（不影响主流程）: {e}")

            # F3: 时间胶囊 — morning_report 注入历史同日记录
            if action == "morning_report":
                try:
                    context["time_capsule"] = _build_time_capsule()
                except Exception as e:
                    _log(f"[/system] 时间胶囊读取失败（不影响主流程）: {e}")

                # V3-F13: 天气信息流 — morning_report 注入天气
                try:
                    weather = _build_weather_context()
                    if weather:
                        context["weather"] = weather
                except Exception as e:
                    _log(f"[/system] 天气获取失败（不影响主流程）: {e}")

                # V3-F15: 决策复盘 — morning_report 注入到期决策
                try:
                    from skills.decision_track import get_due_decisions
                    from memory import read_state_cached
                    _state = read_state_cached() or {}
                    due_decisions = get_due_decisions(_state)
                    if due_decisions:
                        context["due_decisions"] = due_decisions
                except Exception as e:
                    _log(f"[/system] 到期决策读取失败（不影响主流程）: {e}")

                # V3-F11: 习惯干预 — morning_report 注入活跃实验 + 过期检测
                try:
                    from skills.habit_coach import check_experiment_expiry, get_experiment_summary_for_review
                    from memory import read_state_cached
                    _state = read_state_cached() or {}
                    # 检查实验是否到期
                    expiry_msg = check_experiment_expiry(_state)
                    if expiry_msg:
                        context["experiment_expired"] = expiry_msg
                    # 注入活跃实验摘要
                    exp_summary = get_experiment_summary_for_review(_state)
                    if exp_summary:
                        context["active_experiment"] = exp_summary
                except Exception as e:
                    _log(f"[/system] 实验上下文读取失败（不影响主流程）: {e}")

            # F5: 轻推信号 — morning_report / evening_checkin 注入 nudge 信息
            if action in ("morning_report", "evening_checkin"):
                try:
                    context["nudge"] = _build_nudge_context()
                except Exception as e:
                    _log(f"[/system] nudge 上下文读取失败（不影响主流程）: {e}")

            # V3-F12: 每日 Top 3 — evening_checkin 注入今天的 Top 3
            if action == "evening_checkin":
                try:
                    from memory import read_state_cached
                    _state = read_state_cached() or {}
                    daily_top3 = _state.get("daily_top3", {})
                    today_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d")
                    if daily_top3 and daily_top3.get("date") == today_str:
                        context["daily_top3"] = daily_top3
                except Exception as e:
                    _log(f"[/system] daily_top3 读取失败（不影响主流程）: {e}")

            payload = {
                "type": "system",
                "action": action,
                "user_id": target_user,
                "context": context
            }
            result = brain.process(payload)
            reply = result.get("reply") if result else None
            if reply:
                send_wework_message(target_user, reply)
            _log(f"[/system] {action} 完成, reply={'有' if reply else '无'}")
            return json.dumps({"ok": True, "action": action, "has_reply": bool(reply)})

        if action == "mood_generate":
            # F1: 情绪日记自动生成（直接调用 skill，不走 LLM）
            target_user = data.get("user_id", DEFAULT_USER_ID)
            from skills.mood_diary import execute as mood_execute
            from memory import read_state_cached, write_state_and_update_cache
            state = read_state_cached() or {}
            result = mood_execute(data, state)
            # mood_diary 会更新 state.mood_scores，写回
            write_state_and_update_cache(state)
            reply = result.get("reply") if result else None
            if reply:
                send_wework_message(target_user, reply)
            _log(f"[/system] mood_generate 完成, reply={'有' if reply else '无'}")
            return json.dumps({"ok": True, "action": "mood_generate", "has_reply": bool(reply)})

        if action == "weekly_review":
            # F4: 周回顾自动生成（直接调用 skill，不走 LLM）
            target_user = data.get("user_id", DEFAULT_USER_ID)
            from skills.weekly_review import execute as weekly_execute
            from memory import read_state_cached, write_state_and_update_cache
            state = read_state_cached() or {}
            result = weekly_execute(data, state)
            write_state_and_update_cache(state)
            reply = result.get("reply") if result else None
            if reply:
                send_wework_message(target_user, reply)
            _log(f"[/system] weekly_review 完成, reply={'有' if reply else '无'}")
            return json.dumps({"ok": True, "action": "weekly_review", "has_reply": bool(reply)})

        if action == "nudge_check":
            # F5: 独立轻推检测（每天 14:00）— 纯规则，不走 LLM
            target_user = data.get("user_id", DEFAULT_USER_ID)
            messages = _run_nudge_check()
            for msg in messages:
                send_wework_message(target_user, msg)
            _log(f"[/system] nudge_check 完成, 推送 {len(messages)} 条")
            return json.dumps({"ok": True, "action": "nudge_check", "sent": len(messages)})

        if action == "monthly_review":
            # F6: 月度成长回顾（每月末 22:00）
            target_user = data.get("user_id", DEFAULT_USER_ID)
            from skills.monthly_review import execute as monthly_execute
            from memory import read_state_cached, write_state_and_update_cache
            state = read_state_cached() or {}
            result = monthly_execute(data, state)
            write_state_and_update_cache(state)
            reply = result.get("reply") if result else None
            if reply:
                send_wework_message(target_user, reply)
            _log(f"[/system] monthly_review 完成, reply={'有' if reply else '无'}")
            return json.dumps({"ok": True, "action": "monthly_review", "has_reply": bool(reply)})

        if action == "companion_check":
            # F2: 智能陪伴检查（8-23点每2小时）— 有事才发，没事静默
            target_user = data.get("user_id", DEFAULT_USER_ID)
            message = _run_companion_check(target_user)
            if message:
                send_wework_message(target_user, message)
                _log(f"[/system] companion_check 完成, 已推送")
            else:
                _log(f"[/system] companion_check 完成, 无需推送")
            return json.dumps({"ok": True, "action": "companion_check",
                               "sent": 1 if message else 0})

        _log(f"[/system] 未知 action: {action}")
        return json.dumps({"ok": False, "error": f"unknown action: {action}"})

    except Exception as e:
        _log(f"[/system] 异常: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        return json.dumps({"ok": False, "error": str(e)})


@app.route('/', methods=['GET'])
def health():
    """健康检查"""
    return "Karvis is alive"


# ============ 时间胶囊辅助函数 ============

def _build_time_capsule():
    """
    F3: 读取历史同日的笔记，供 morning_report 注入。
    返回 dict: {"7d_ago": {...}, "30d_ago": {...}, "365d_ago": {...}}
    """
    from config import QUICK_NOTES_FILE, DAILY_NOTES_DIR
    from concurrent.futures import ThreadPoolExecutor

    today = datetime.now(BEIJING_TZ).date()
    offsets = {
        "7d_ago": 7,
        "30d_ago": 30,
        "365d_ago": 365,
    }

    capsule = {}
    files_to_read = {}

    for key, days in offsets.items():
        past_date = today - timedelta(days=days)
        date_str = past_date.strftime("%Y-%m-%d")
        files_to_read[f"{key}_daily"] = (date_str, f"{DAILY_NOTES_DIR}/{date_str}.md")

    # 也需要从 Quick-Notes 中提取历史日期条目
    files_to_read["quick_notes"] = (None, QUICK_NOTES_FILE)

    # 并发读取
    results = {}
    try:
        from brain import _executor
        executor = _executor
    except ImportError:
        executor = ThreadPoolExecutor(max_workers=4)

    futures = {k: executor.submit(OneDriveIO.read_text, v[1]) for k, v in files_to_read.items()}

    for k, fut in futures.items():
        try:
            results[k] = fut.result(timeout=15) or ""
        except Exception:
            results[k] = ""

    qn_text = results.get("quick_notes", "")

    for key, days in offsets.items():
        past_date = today - timedelta(days=days)
        date_str = past_date.strftime("%Y-%m-%d")

        daily_content = results.get(f"{key}_daily", "")
        # 从 Quick-Notes 提取该日期条目
        qn_entries = _extract_date_entries_for_capsule(qn_text, date_str)

        content_parts = []
        if qn_entries:
            content_parts.append(qn_entries[:500])
        if daily_content:
            # 只取日报总结部分，不取原始记录
            if "## 📊 今日总结" in daily_content:
                summary_section = daily_content.split("## 📊 今日总结")[1]
                end_idx = summary_section.find("\n## ")
                if end_idx >= 0:
                    summary_section = summary_section[:end_idx]
                content_parts.append(summary_section.strip()[:500])

        if content_parts:
            capsule[key] = {
                "date": date_str,
                "notes": "\n\n".join(content_parts)[:800]
            }
        else:
            capsule[key] = None

    return capsule


def _extract_date_entries_for_capsule(text, date_str):
    """从 Quick-Notes 中提取指定日期的条目（时间胶囊用）"""
    if not text:
        return ""
    entries = []
    sections = text.split("\n## ")
    for section in sections[1:]:
        first_line = section.split("\n")[0].strip()
        if first_line.startswith(date_str):
            # 只取内容，不取时间戳头
            body = "\n".join(section.split("\n")[1:]).strip()
            if body and body != "---":
                entries.append(body)
    return "\n".join(entries[:5])  # 最多 5 条


# ============ F5: 轻推系统辅助函数 ============

def _build_nudge_context():
    """
    F5: 构建 nudge 上下文信号，注入 morning_report / evening_checkin 的 context。
    读取 state 中的 nudge_state + mood_scores，返回 dict。
    """
    from memory import read_state_cached
    state = read_state_cached() or {}

    nudge = state.get("nudge_state", {})
    mood_scores = state.get("mood_scores", [])

    # 昨天的情绪评分
    today = datetime.now(BEIJING_TZ).date()
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_mood = None
    for s in mood_scores:
        if s.get("date") == yesterday_str:
            yesterday_mood = {"score": s.get("score"), "label": s.get("label", "")}
            break

    # 连续记录天数
    streak = nudge.get("streak", 0)

    # 距上次消息的小时数
    last_msg_date = nudge.get("last_message_date", "")
    hours_since_last = None
    if last_msg_date:
        try:
            last_dt = datetime.strptime(last_msg_date, "%Y-%m-%d")
            last_dt = last_dt.replace(tzinfo=BEIJING_TZ)
            now = datetime.now(BEIJING_TZ)
            hours_since_last = round((now - last_dt).total_seconds() / 3600, 1)
        except Exception:
            pass

    # 需要跟进的人（距上次提到超过 7 天 + 之前有负面情绪记录）
    people_to_follow = []
    people_last = nudge.get("people_last_mentioned", {})
    for name, last_date_str in people_last.items():
        try:
            last_d = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            if (today - last_d).days >= 7:
                people_to_follow.append(name)
        except Exception:
            pass

    # 打卡统计
    checkin_stats = state.get("checkin_stats", {})

    return {
        "yesterday_mood": yesterday_mood,
        "streak": streak,
        "last_message_hours_ago": hours_since_last,
        "people_to_follow_up": people_to_follow,
        "checkin_streak": checkin_stats.get("streak", 0),
    }


def _run_nudge_check():
    """
    F5: 独立轻推检测（每天 14:00 执行）— 纯规则引擎，不走 LLM。
    返回要推送的消息列表。
    """
    from memory import read_state_cached
    state = read_state_cached() or {}

    nudge = state.get("nudge_state", {})
    mood_scores = state.get("mood_scores", [])
    messages = []

    today = datetime.now(BEIJING_TZ).date()
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    # 场景1: 沉默检测 — 今天 14:00 之前无消息
    last_msg_date = nudge.get("last_message_date", "")
    if last_msg_date != today_str:
        messages.append("今天很安静呀，是忙还是累了？随时可以来聊两句~")

    # 场景2: 情绪跟进 — 昨天 mood_score ≤ 4
    for s in mood_scores:
        if s.get("date") == yesterday_str and s.get("score") is not None:
            if s["score"] <= 4:
                label = s.get("label", "")
                hint = f"（{label}）" if label else ""
                messages.append(f"昨天好像有点低落{hint}，今天好点了吗？")
            break

    # 场景3: 连续记录鼓励
    streak = nudge.get("streak", 0)
    if streak > 0 and streak % 7 == 0:
        messages.append(f"你已经连续记录 {streak} 天了！这个习惯太棒了 ✨")
    elif streak == 3:
        messages.append("连续记录 3 天了~坚持下去，会看到很棒的变化！")

    return messages


# ============ F2: 主动陪伴系统 ============

def _parse_companion_datetime(time_str):
    """解析 nudge_state 中的时间字符串，返回 datetime 或 None"""
    if not time_str:
        return None
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        return dt.replace(tzinfo=BEIJING_TZ)
    except Exception:
        return None


def _run_companion_check(user_id):
    """
    F2: 每 2 小时执行一次的智能陪伴检查。
    核心原则: 有事才发，没事 return None 静默跳过。
    返回: 消息文本 或 None
    """
    from memory import read_state_cached, write_state_and_update_cache
    from config import (COMPANION_SILENT_HOURS, COMPANION_INTERVAL_HOURS,
                        COMPANION_MAX_DAILY, COMPANION_RECENT_HOURS)

    state = read_state_cached() or {}
    nudge = state.get("nudge_state", {})
    now = datetime.now(BEIJING_TZ)

    # ── 防骚扰层 ──

    # 安静时间双保险（cron 已排除 0-7，代码再兜底）
    if now.hour < 8:
        _log(f"[Companion] 安静时间({now.hour}:00), 跳过")
        return None

    # 最近 N 小时内有过互动 → 不需要主动关怀
    last_msg_time = _parse_companion_datetime(nudge.get("last_message_time"))
    if last_msg_time and (now - last_msg_time).total_seconds() < COMPANION_RECENT_HOURS * 3600:
        _log(f"[Companion] 近期有互动({nudge.get('last_message_time')}), 跳过")
        return None

    # 上次陪伴推送距今不足 N 小时 → 跳过
    last_companion = _parse_companion_datetime(nudge.get("last_companion_time"))
    if last_companion and (now - last_companion).total_seconds() < COMPANION_INTERVAL_HOURS * 3600:
        _log(f"[Companion] 推送间隔不足({nudge.get('last_companion_time')}), 跳过")
        return None

    # 今天已推送 ≥ N 次 → 停止
    companion_count = nudge.get("companion_count_today", 0)
    if companion_count >= COMPANION_MAX_DAILY:
        _log(f"[Companion] 今日已推送{companion_count}次, 达到上限, 跳过")
        return None

    # ── 信号收集 ──
    signals = []

    # 信号 1: 长时间沉默（超过 N 小时没消息）
    if last_msg_time:
        silent_hours = (now - last_msg_time).total_seconds() / 3600
        if silent_hours > COMPANION_SILENT_HOURS:
            signals.append({
                "type": "silence",
                "detail": f"已经 {silent_hours:.0f} 小时没消息"
            })

    # 信号 2: 待办提醒
    pending_todos = _check_pending_todos(user_id)
    if pending_todos:
        signals.append({
            "type": "todo_reminder",
            "detail": f"有 {len(pending_todos)} 个待办未完成",
            "items": pending_todos[:3]
        })

    # 信号 3: 情绪跟进（昨天情绪低落且今天还没跟进）
    yesterday_mood = nudge.get("yesterday_mood_score")
    mood_followed = nudge.get("mood_followed_today", False)
    if yesterday_mood and int(yesterday_mood) <= 4 and not mood_followed:
        signals.append({
            "type": "mood_followup",
            "detail": f"昨天情绪评分 {yesterday_mood}/10"
        })

    # ── 决策: 没有信号就静默 ──
    if not signals:
        _log(f"[Companion] 无触发信号, 静默跳过")
        return None

    _log(f"[Companion] 触发信号: {json.dumps(signals, ensure_ascii=False)[:200]}")

    # ── 收集上下文，生成关怀消息 ──
    context = _build_companion_context(state, user_id)
    message = _generate_companion_message(signals, context, state)

    if message:
        # 更新计数器
        nudge["last_companion_time"] = now.strftime("%Y-%m-%d %H:%M")
        nudge["companion_count_today"] = companion_count + 1
        if any(s["type"] == "mood_followup" for s in signals):
            nudge["mood_followed_today"] = True
        state["nudge_state"] = nudge
        write_state_and_update_cache(state)
        _log(f"[Companion] 消息已生成, 计数={companion_count + 1}")

    return message


def _build_companion_context(state, user_id):
    """
    F2: 为陪伴消息收集丰富上下文（soul + memory + 速记 + 待办 + 近期对话）。
    并发读取，控制总耗时。
    """
    from concurrent.futures import ThreadPoolExecutor
    from config import SOUL_FILE, MEMORY_FILE, QUICK_NOTES_FILE, TODO_FILE

    context = {}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            "soul": executor.submit(OneDriveIO.read_text, SOUL_FILE),
            "memory": executor.submit(OneDriveIO.read_text, MEMORY_FILE),
            "quick_notes": executor.submit(OneDriveIO.read_text, QUICK_NOTES_FILE),
            "todo": executor.submit(OneDriveIO.read_text, TODO_FILE),
        }
        for key, future in futures.items():
            try:
                content = future.result(timeout=5)
                if content:
                    if key == "quick_notes":
                        lines = content.strip().split('\n')
                        recent = lines[-20:] if len(lines) > 20 else lines
                        context[key] = '\n'.join(recent)
                    else:
                        context[key] = content
            except Exception as e:
                _log(f"[Companion] 读取 {key} 失败: {e}")

    # 近期对话（从 state 中取）
    recent_msgs = state.get("recent_messages", [])
    if recent_msgs:
        context["recent_messages"] = recent_msgs[-5:]

    return context


def _generate_companion_message(signals, context, state):
    """
    F2: 基于信号 + 上下文，调 Qwen Flash 生成自然的关怀消息。
    注入 soul + memory + 近期速记，让消息更有温度和个性。
    """
    # 组装 system prompt
    system_parts = []

    # 1. Soul（人设）
    soul = context.get("soul", "")
    if soul:
        system_parts.append(f"## 你的人设\n{soul}")

    # 2. Memory（长期记忆）
    memory = context.get("memory", "")
    if memory:
        system_parts.append(f"## 你对用户的了解\n{memory}")

    # 3. 任务指令
    system_parts.append("""## 任务
你正在做一次主动关怀检查。根据下面的「触发信号」和「近期上下文」，生成一条发给用户的关怀消息。

要求：
- 1-2 句话，简短自然
- 符合你的人设
- 待办提醒 → 简要提及具体内容，语气轻松不施压
- 沉默关怀 → 结合近期速记中用户在做的事来聊，有话题感
- 情绪跟进 → 关心但不追问，留空间
- 不要 emoji，不要"我注意到"等机器人用语
- 直接输出消息文本，不要任何 JSON 格式""")

    system_prompt = '\n\n'.join(system_parts)

    # 组装 user message
    user_parts = []

    # 触发信号
    signal_text = json.dumps(signals, ensure_ascii=False)
    user_parts.append(f"**触发信号**: {signal_text}")

    # 近期速记
    quick_notes = context.get("quick_notes", "")
    if quick_notes:
        user_parts.append(f"**近期速记**:\n{quick_notes}")

    # 待办列表
    todo = context.get("todo", "")
    if todo:
        user_parts.append(f"**待办清单**:\n{todo}")

    # 近期对话
    recent_msgs = context.get("recent_messages", [])
    if recent_msgs:
        msg_text = '\n'.join([f"- {m.get('role','')}: {m.get('text','')[:80]}"
                              for m in recent_msgs])
        user_parts.append(f"**最近对话**:\n{msg_text}")

    # 当前时间
    now = datetime.now(BEIJING_TZ)
    period = "上午" if now.hour < 12 else ("下午" if now.hour < 18 else "晚上")
    user_parts.append(f"**当前时间**: {now.strftime('%Y-%m-%d %H:%M')} {period}")

    user_message = '\n\n'.join(user_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    _log(f"[Companion] 调用 Flash 生成关怀消息, signals={len(signals)}")
    return brain.call_llm(messages, model_tier="flash", max_tokens=200,
                          temperature=0.7)


def _check_pending_todos(user_id):
    """F2: 从 Todo.md 读取未完成待办"""
    try:
        from config import TODO_FILE
        todo_content = OneDriveIO.read_text(TODO_FILE)
        if not todo_content:
            return []
        pending = []
        for line in todo_content.split('\n'):
            line = line.strip()
            if line.startswith('- [ ]'):
                pending.append(line[5:].strip())
        return pending
    except Exception as e:
        _log(f"[Companion] 读取待办失败: {e}")
        return []


# ============ V3-F13: 天气信息流辅助函数 ============

def _build_weather_context():
    """
    V3-F13: 获取天气信息，供 morning_report 注入。
    使用心知天气 API（免费版），返回 dict 或空 dict。
    """
    if not WEATHER_API_KEY:
        return {}
    try:
        resp = requests.get(
            "https://api.seniverse.com/v3/weather/daily.json",
            params={
                "key": WEATHER_API_KEY,
                "location": WEATHER_CITY,
                "language": "zh-Hans",
                "unit": "c",
                "start": 0,
                "days": 1
            },
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()["results"][0]["daily"][0]
            weather = {
                "city": WEATHER_CITY,
                "weather_day": data.get("text_day", ""),
                "weather_night": data.get("text_night", ""),
                "high": data.get("high", ""),
                "low": data.get("low", ""),
            }
            _log(f"[Weather] {WEATHER_CITY}: {weather['weather_day']} {weather['low']}~{weather['high']}°C")
            return weather
        else:
            _log(f"[Weather] API 返回非 200: {resp.status_code} {resp.text[:100]}")
    except Exception as e:
        _log(f"[Weather] 获取天气失败: {e}")
    return {}


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000, threaded=True)
