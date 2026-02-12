# -*- coding: utf-8 -*-
"""
统一 OneDrive 读写层
所有文件操作走这里，解决：
  1. token 重复获取（带缓存）
  2. 并发写入覆盖（集中管理）
  3. 大文件分片上传
  4. HTTP 连接复用（Session keep-alive，减少 TLS 握手）
"""
import time
import json
import threading
import requests
from requests.adapters import HTTPAdapter
from config import (
    ONEDRIVE_CLIENT_ID, ONEDRIVE_CLIENT_SECRET, ONEDRIVE_REFRESH_TOKEN
)

import sys
def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# 全局 Session：复用 TCP 连接 + TLS 会话，避免每次请求重新握手
_graph_session = requests.Session()
_graph_adapter = HTTPAdapter(
    pool_connections=6,     # 连接池大小（匹配线程池 max_workers）
    pool_maxsize=6,
    max_retries=0           # 重试由我们自己控制
)
_graph_session.mount("https://graph.microsoft.com", _graph_adapter)

# token 刷新用独立 session
_auth_session = requests.Session()


class OneDriveIO:
    """OneDrive 统一读写，带 token 缓存"""

    _token_cache = {"token": None, "expire_time": 0}
    _token_lock = threading.Lock()

    # ---- token 管理 ----

    @classmethod
    def get_token(cls):
        """获取 access_token（带内存缓存，线程安全）"""
        now = time.time()
        if cls._token_cache["token"] and cls._token_cache["expire_time"] > now:
            return cls._token_cache["token"]

        with cls._token_lock:
            # double-check：拿锁后再检查一次，避免多线程重复刷新
            now = time.time()
            if cls._token_cache["token"] and cls._token_cache["expire_time"] > now:
                return cls._token_cache["token"]

            _log("[OneDrive] 开始刷新 token...")
            t0 = time.time()
            url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
            data = {
                "client_id": ONEDRIVE_CLIENT_ID,
                "client_secret": ONEDRIVE_CLIENT_SECRET,
                "refresh_token": ONEDRIVE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
                "scope": "Files.ReadWrite offline_access"
            }
            try:
                resp = _auth_session.post(url, data=data, timeout=30)
                t1 = time.time()
                result = resp.json()
                token = result.get("access_token")
                if token:
                    expires_in = result.get("expires_in", 3600)
                    cls._token_cache = {
                        "token": token,
                        "expire_time": now + expires_in - 120
                    }
                    _log(f"[OneDrive] token 刷新成功: {t1-t0:.1f}s")
                    return token
                _log(f"[OneDrive] token 获取失败({t1-t0:.1f}s): {result}")
            except Exception as e:
                _log(f"[OneDrive] token 请求异常({time.time()-t0:.1f}s): {e}")
            return None

    # ---- 文本文件读写 ----

    @classmethod
    def read_text(cls, file_path, _retries=3):
        """读取文本文件，返回字符串。文件不存在返回空字符串，失败返回 None
        
        超时策略：连接 5s + 读取 10s，超时立即重试（换新连接）
        """
        token = cls.get_token()
        if not token:
            return None
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:{file_path}:/content"
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(1, _retries + 1):
            try:
                t0 = time.time()
                resp = _graph_session.get(url, headers=headers, timeout=(5, 10))
                elapsed = time.time() - t0
                if resp.status_code == 200:
                    _log(f"[OneDrive] 读取OK {file_path}: {elapsed:.1f}s")
                    return resp.text
                elif resp.status_code == 404:
                    return ""
                _log(f"[OneDrive] 读取失败 {file_path}: {resp.status_code} ({elapsed:.1f}s)")
                return None
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, ConnectionError) as e:
                _log(f"[OneDrive] 读取超时(第{attempt}次) {file_path}: {time.time()-t0:.1f}s")
                if attempt < _retries:
                    continue  # 立即重试，不 sleep
                return None
            except Exception as e:
                _log(f"[OneDrive] 读取异常 {file_path}: {e}")
                return None

    @classmethod
    def write_text(cls, file_path, content, _retries=3):
        """写入文本文件（覆盖），带重试，返回 True/False
        
        超时策略：连接 5s + 读取 15s，超时立即重试
        """
        token = cls.get_token()
        if not token:
            return False
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:{file_path}:/content"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "text/plain; charset=utf-8"
        }
        data = content.encode('utf-8')
        for attempt in range(1, _retries + 1):
            try:
                t0 = time.time()
                resp = _graph_session.put(url, headers=headers, data=data, timeout=(5, 15))
                elapsed = time.time() - t0
                ok = resp.status_code in (200, 201)
                if not ok:
                    _log(f"[OneDrive] 写入失败 {file_path}: {resp.status_code} ({elapsed:.1f}s)")
                else:
                    _log(f"[OneDrive] 写入OK {file_path}: {elapsed:.1f}s")
                return ok
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, ConnectionError) as e:
                _log(f"[OneDrive] 写入超时(第{attempt}次) {file_path}: {time.time()-t0:.1f}s")
                if attempt < _retries:
                    continue  # 立即重试
                return False
            except Exception as e:
                _log(f"[OneDrive] 写入异常 {file_path}: {e}")
                return False

    # ---- JSON 文件读写 ----

    @classmethod
    def read_json(cls, file_path):
        """读取 JSON 文件，返回 dict/list。文件不存在返回空 dict，失败返回 None"""
        text = cls.read_text(file_path)
        if text is None:
            return None
        if not text.strip():
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            _log(f"[OneDrive] JSON 解析失败 {file_path}: {e}")
            return None

    @classmethod
    def write_json(cls, file_path, data):
        """写入 JSON 文件"""
        content = json.dumps(data, ensure_ascii=False, indent=2)
        return cls.write_text(file_path, content)

    # ---- 追加到文件指定 section ----

    @classmethod
    def append_to_section(cls, file_path, section_header, content):
        """
        追加内容到文件的指定 section（以 ## 开头）。
        如果 section 存在，追加到该 section 末尾；
        如果不存在，在文件末尾添加新 section。
        """
        existing = cls.read_text(file_path)
        if existing is None:
            return False

        if section_header in existing:
            parts = existing.split(section_header, 1)
            before = parts[0]
            after = parts[1]
            next_section_idx = after.find("\n## ")
            if next_section_idx >= 0:
                section_content = after[:next_section_idx]
                rest = after[next_section_idx:]
                new_content = before + section_header + section_content.rstrip() + "\n" + content + "\n" + rest
            else:
                new_content = before + section_header + after.rstrip() + "\n" + content + "\n"
        else:
            new_content = existing.rstrip() + f"\n\n{section_header}\n{content}\n"

        return cls.write_text(file_path, new_content)

    # ---- 追加到 Quick-Notes（带去重） ----

    @classmethod
    def append_to_quick_notes(cls, file_path, message):
        """追加一条笔记到 Quick-Notes，格式化为 ## 时间戳 + 内容"""
        from datetime import datetime, timezone, timedelta

        existing = cls.read_text(file_path)
        if existing is None:
            return False

        if not existing.strip():
            existing = "# Quick Notes\n\n快速笔记，从微信同步。\n\n---\n\n"

        # 内容去重：检查最近 5 条
        sections = existing.split('## ')
        for section in sections[1:6]:
            lines = section.strip().split('\n')
            if len(lines) >= 2:
                content_lines = '\n'.join(lines[1:]).strip().rstrip('-').strip()
                if content_lines == message.strip():
                    _log(f"[Quick-Notes] 内容重复，跳过: {message[:30]}...")
                    return True

        # 追加新条目
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M")
        new_entry = f"## {now}\n\n{message}\n\n---\n\n"

        lines = existing.split('\n')
        header_end = 0
        for i, line in enumerate(lines):
            if line.strip() == "---":
                header_end = i + 1
                break

        new_content = '\n'.join(lines[:header_end]) + '\n\n' + new_entry + '\n'.join(lines[header_end:])
        return cls.write_text(file_path, new_content)

    # ---- 二进制文件上传 ----

    @classmethod
    def upload_binary(cls, file_path, data, content_type="application/octet-stream"):
        """统一二进制上传入口（自动选择简单/分片上传）"""
        if len(data) <= 4 * 1024 * 1024:
            return cls._upload_small(file_path, data, content_type)
        else:
            return cls._upload_large(file_path, data)

    @classmethod
    def _upload_small(cls, file_path, data, content_type):
        """简单上传（≤4MB）"""
        token = cls.get_token()
        if not token:
            return False
        url = f"https://graph.microsoft.com/v1.0/me/drive/root:{file_path}:/content"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type
        }
        try:
            resp = _graph_session.put(url, headers=headers, data=data, timeout=60)
            ok = resp.status_code in (200, 201)
            _log(f"[OneDrive] 上传 {file_path} size={len(data)} status={resp.status_code}")
            return ok
        except Exception as e:
            _log(f"[OneDrive] 上传异常 {file_path}: {e}")
            return False

    @classmethod
    def _upload_large(cls, file_path, data):
        """分片上传（>4MB，每片 3.2MB）"""
        token = cls.get_token()
        if not token:
            return False

        url = f"https://graph.microsoft.com/v1.0/me/drive/root:{file_path}:/createUploadSession"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        body = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
        try:
            resp = _graph_session.post(url, headers=headers, json=body, timeout=30)
            if resp.status_code != 200:
                _log(f"[OneDrive] 创建上传会话失败: {resp.status_code}")
                return False
            upload_url = resp.json().get("uploadUrl")
            if not upload_url:
                return False
        except Exception as e:
            _log(f"[OneDrive] 创建上传会话异常: {e}")
            return False

        chunk_size = 3276800
        total_size = len(data)
        _log(f"[OneDrive] 分片上传 {file_path} total={total_size}")

        for start in range(0, total_size, chunk_size):
            end = min(start + chunk_size, total_size)
            chunk = data[start:end]
            chunk_headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end-1}/{total_size}"
            }
            try:
                resp = requests.put(upload_url, headers=chunk_headers,
                                    data=chunk, timeout=60)
                if resp.status_code not in (200, 201, 202):
                    _log(f"[OneDrive] 分片失败: {resp.status_code}")
                    return False
            except Exception as e:
                _log(f"[OneDrive] 分片异常: {e}")
                return False

        _log(f"[OneDrive] 分片上传完成: {file_path}")
        return True
