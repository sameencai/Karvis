# -*- coding: utf-8 -*-
"""
Karvis 本地文件读写层（Lite 模式）
当未配置 OneDrive 时，使用本地文件系统作为存储后端。
接口与 OneDriveIO 完全对齐，支持无缝切换。
"""
import os
import json
import sys
import threading

def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# 本地存储根目录（默认 ./data，可通过环境变量覆盖）
LOCAL_DATA_DIR = os.environ.get("KARVIS_LOCAL_DATA", os.path.join(os.path.dirname(__file__), "data"))


class LocalFileIO:
    """本地文件存储，API 兼容 OneDriveIO"""

    _lock = threading.Lock()

    @classmethod
    def _resolve_path(cls, file_path):
        """将 OneDrive 风格路径转换为本地绝对路径。
        
        OneDrive 路径格式: /应用/remotely-save/EmptyVault/00-Inbox/Quick-Notes.md
        本地路径: {LOCAL_DATA_DIR}/00-Inbox/Quick-Notes.md
        
        我们把 OBSIDIAN_BASE 前缀映射到 LOCAL_DATA_DIR。
        """
        from config import OBSIDIAN_BASE
        if file_path.startswith(OBSIDIAN_BASE):
            relative = file_path[len(OBSIDIAN_BASE):]
        else:
            relative = file_path
        # 去掉开头的 /
        relative = relative.lstrip("/")
        return os.path.join(LOCAL_DATA_DIR, relative)

    @classmethod
    def get_token(cls):
        """兼容接口 — 本地模式不需要 token"""
        return "local"

    # ---- 文本文件读写 ----

    @classmethod
    def read_text(cls, file_path, _retries=3):
        """读取文本文件，返回字符串。文件不存在返回空字符串，失败返回 None"""
        local_path = cls._resolve_path(file_path)
        try:
            if not os.path.exists(local_path):
                return ""
            with open(local_path, "r", encoding="utf-8") as f:
                content = f.read()
            _log(f"[LocalIO] 读取OK {file_path}")
            return content
        except Exception as e:
            _log(f"[LocalIO] 读取异常 {file_path}: {e}")
            return None

    @classmethod
    def write_text(cls, file_path, content, _retries=3):
        """写入文本文件（覆盖），返回 True/False"""
        local_path = cls._resolve_path(file_path)
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with cls._lock:
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(content)
            _log(f"[LocalIO] 写入OK {file_path}")
            return True
        except Exception as e:
            _log(f"[LocalIO] 写入异常 {file_path}: {e}")
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
            _log(f"[LocalIO] JSON 解析失败 {file_path}: {e}")
            return None

    @classmethod
    def write_json(cls, file_path, data):
        """写入 JSON 文件"""
        content = json.dumps(data, ensure_ascii=False, indent=2)
        return cls.write_text(file_path, content)

    # ---- 追加到文件指定 section ----

    @classmethod
    def append_to_section(cls, file_path, section_header, content):
        """追加内容到文件的指定 section"""
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
        """追加一条笔记到 Quick-Notes"""
        from datetime import datetime, timezone, timedelta

        existing = cls.read_text(file_path)
        if existing is None:
            return False

        if not existing.strip():
            existing = "# Quick Notes\n\n快速笔记，从微信同步。\n\n---\n\n"

        # 内容去重
        sections = existing.split('## ')
        for section in sections[1:6]:
            lines = section.strip().split('\n')
            if len(lines) >= 2:
                content_lines = '\n'.join(lines[1:]).strip().rstrip('-').strip()
                if content_lines == message.strip():
                    _log(f"[LocalIO] 内容重复，跳过: {message[:30]}...")
                    return True

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
        """上传（保存）二进制文件"""
        local_path = cls._resolve_path(file_path)
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "wb") as f:
                f.write(data)
            _log(f"[LocalIO] 二进制写入OK {file_path} size={len(data)}")
            return True
        except Exception as e:
            _log(f"[LocalIO] 二进制写入异常 {file_path}: {e}")
            return False
