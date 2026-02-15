# -*- coding: utf-8 -*-
"""
Karvis 记忆管理
负责：
  1. 读取 memory.md（带缓存）
  2. 管理对话滑动窗口（短期记忆）
  3. 更新长期记忆（memory.md）
"""
import time
import sys
import os
import threading
from config import (
    MEMORY_FILE,
    STATE_FILE, RECENT_MESSAGES_LIMIT, PROMPT_CACHE_TTL,
    STATE_CACHE_TTL
)
from storage import IO as OneDriveIO  # 统一存储接口
import json as _json

def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# SCF /tmp 目录持久化（实例存活期间保留）
_TMP_CACHE_DIR = "/tmp/karvis_prompts"

class PromptCache:
    """Memory 文件缓存：内存 → /tmp 磁盘 → OneDrive（三级缓存）"""

    def __init__(self):
        self._cache = {}  # 内存缓存 {file_path: {"content": str, "expire_time": float}}
        self._lock = threading.Lock()
        os.makedirs(_TMP_CACHE_DIR, exist_ok=True)

    def _tmp_path(self, file_path):
        """OneDrive 路径 → /tmp 本地文件名"""
        safe = file_path.replace("/", "_").replace(" ", "_")
        return os.path.join(_TMP_CACHE_DIR, safe)

    def get(self, file_path):
        """读取文件内容（三级缓存：内存 → /tmp → OneDrive）"""
        now = time.time()

        # 1. 内存缓存
        cached = self._cache.get(file_path)
        if cached and cached["expire_time"] > now:
            return cached["content"]

        # 2. /tmp 磁盘缓存（SCF 实例复用时有效，跳过 OneDrive）
        tmp_file = self._tmp_path(file_path)
        try:
            if os.path.exists(tmp_file):
                mtime = os.path.getmtime(tmp_file)
                if now - mtime < PROMPT_CACHE_TTL:
                    with open(tmp_file, "r", encoding="utf-8") as f:
                        content = f.read()
                    with self._lock:
                        self._cache[file_path] = {"content": content, "expire_time": now + PROMPT_CACHE_TTL}
                    return content
        except Exception:
            pass

        # 3. OneDrive 远程读取
        content = OneDriveIO.read_text(file_path)
        if content is not None:
            with self._lock:
                self._cache[file_path] = {"content": content, "expire_time": now + PROMPT_CACHE_TTL}
            # 写入 /tmp 磁盘缓存
            try:
                with open(tmp_file, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass
        return content or ""

    def invalidate(self, file_path=None):
        """清除缓存（全部或指定文件）"""
        with self._lock:
            if file_path:
                self._cache.pop(file_path, None)
                try:
                    tmp_file = self._tmp_path(file_path)
                    if os.path.exists(tmp_file):
                        os.remove(tmp_file)
                except Exception:
                    pass
            else:
                self._cache.clear()
                try:
                    for f in os.listdir(_TMP_CACHE_DIR):
                        os.remove(os.path.join(_TMP_CACHE_DIR, f))
                except Exception:
                    pass


# 全局缓存实例
_prompt_cache = PromptCache()


def load_memory():
    """加载 memory.md"""
    return _prompt_cache.get(MEMORY_FILE)


def format_recent_messages(state):
    """
    从 state 中提取最近 N 条消息，格式化为文本。
    """
    recent = state.get("recent_messages", [])[-RECENT_MESSAGES_LIMIT:]
    if not recent:
        return "（暂无最近对话）"

    lines = []
    for m in recent:
        role_val = m.get("role", "")
        if role_val == "system":
            # 压缩摘要消息，直接显示
            lines.append(m.get("content", ""))
            continue
        role = "用户" if role_val == "user" else "Karvis"
        t = m.get("time", "")
        content = m.get("content", "")
        # 截断过长内容，避免 token 爆炸
        if len(content) > 150:
            content = content[:150] + "..."
        lines.append(f"[{t}] {role}: {content}")
    return "\n".join(lines)


def add_message_to_state(state, role, content):
    """
    往 state 的对话窗口中追加一条消息。
    role: "user" | "karvis"
    超限时触发压缩而非直接丢弃。
    """
    from datetime import datetime, timezone, timedelta
    beijing_tz = timezone(timedelta(hours=8))
    now_str = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M")

    messages = state.setdefault("recent_messages", [])
    messages.append({
        "role": role,
        "content": content[:300],  # 限制单条长度
        "time": now_str
    })

    # 超限时压缩：保留最近 4 条，将最旧的压缩为摘要
    if len(messages) > RECENT_MESSAGES_LIMIT:
        state["recent_messages"] = maybe_compress_messages(messages)


def maybe_compress_messages(messages):
    """
    对话压缩：当消息数超过 RECENT_MESSAGES_LIMIT 时，
    将最旧的消息压缩为一条摘要，保留最近 COMPRESS_KEEP_RECENT 条原始消息。
    
    压缩策略：纯文本摘要，不调用 LLM（节省 token + 延迟）
    """
    COMPRESS_KEEP_RECENT = 4  # 保留最近 4 条原始消息

    if len(messages) <= RECENT_MESSAGES_LIMIT:
        return messages

    # 分割：要压缩的旧消息 + 要保留的新消息
    to_compress = messages[:-COMPRESS_KEEP_RECENT]
    to_keep = messages[-COMPRESS_KEEP_RECENT:]

    # 生成摘要：提取每条消息的关键信息
    summary_parts = []
    for m in to_compress:
        # 跳过已经是摘要的消息
        if m.get("role") == "system" and m.get("content", "").startswith("[对话摘要]"):
            summary_parts.append(m["content"])
            continue
        role = "用户" if m.get("role") == "user" else "Karvis"
        content = m.get("content", "")
        # 截取关键部分
        if len(content) > 50:
            content = content[:50] + "..."
        summary_parts.append(f"{role}: {content}")

    # 构建摘要消息
    time_range = ""
    if to_compress:
        first_time = to_compress[0].get("time", "")
        last_time = to_compress[-1].get("time", "")
        if first_time and last_time:
            time_range = f"({first_time} ~ {last_time})"

    summary_text = f"[对话摘要] {time_range} " + " | ".join(summary_parts)
    # 限制摘要长度
    if len(summary_text) > 500:
        summary_text = summary_text[:500] + "..."

    summary_msg = {
        "role": "system",
        "content": summary_text,
        "time": to_compress[-1].get("time", "") if to_compress else ""
    }

    result = [summary_msg] + to_keep
    _log(f"[记忆] 对话压缩: {len(to_compress)} 条 → 1 条摘要, 保留 {len(to_keep)} 条原始")
    return result


def apply_memory_updates(updates):
    """
    将 LLM 返回的 memory_updates 应用到 memory.md。
    updates 格式: [{"section": "重要的人", "action": "add|update|delete", "content": "小明: 大学室友"}]
    """
    if not updates:
        return

    memory_text = OneDriveIO.read_text(MEMORY_FILE)
    if memory_text is None:
        _log("[记忆] 无法读取 memory.md，跳过记忆更新")
        return

    changed = False
    for item in updates:
        if isinstance(item, str):
            _log(f"[记忆] 跳过非法格式的 memory_update: {item[:50]}")
            continue
        if not isinstance(item, dict):
            continue
        section = item.get("section", "")
        action = item.get("action", "add")
        content = item.get("content", "")
        if not section or not content:
            continue

        section_header = f"## {section}"

        if action == "delete":
            # 从 section 中删除包含关键词的行
            if section_header not in memory_text:
                continue
            parts = memory_text.split(section_header, 1)
            before = parts[0]
            after = parts[1]
            next_idx = after.find("\n## ")
            section_body = after[:next_idx] if next_idx >= 0 else after
            rest = after[next_idx:] if next_idx >= 0 else ""
            # 按行过滤，移除包含 content 关键词的行
            keyword = content.lower()
            lines = section_body.split("\n")
            new_lines = [l for l in lines if keyword not in l.lower()]
            if len(new_lines) != len(lines):
                memory_text = before + section_header + "\n".join(new_lines) + rest
                changed = True
                _log(f"[记忆] 删除: section={section}, keyword={content}")
            continue

        if section_header in memory_text:
            if action == "add":
                # 去重检查：提取关键词（冒号前的名字或前10个字）
                dedup_key = content.split(":")[0].strip().lower() if ":" in content else content[:10].lower()
                parts = memory_text.split(section_header, 1)
                before = parts[0]
                after = parts[1]
                next_idx = after.find("\n## ")
                section_body = after[:next_idx] if next_idx >= 0 else after
                rest = after[next_idx:] if next_idx >= 0 else ""

                # 检查是否已存在相似条目
                existing_lines = section_body.lower()
                if dedup_key in existing_lines:
                    _log(f"[记忆] 去重跳过: section={section}, key={dedup_key}")
                    continue

                memory_text = before + section_header + section_body.rstrip() + f"\n- {content}\n" + rest
                changed = True
            elif action == "update":
                # 替换整个 section 内容
                parts = memory_text.split(section_header, 1)
                before = parts[0]
                after = parts[1]
                next_idx = after.find("\n## ")
                if next_idx >= 0:
                    rest = after[next_idx:]
                    memory_text = before + section_header + f"\n- {content}\n" + rest
                else:
                    memory_text = before + section_header + f"\n- {content}\n"
                changed = True
        else:
            # section 不存在，在末尾添加
            memory_text = memory_text.rstrip() + f"\n\n{section_header}\n- {content}\n"
            changed = True

    if changed:
        ok = OneDriveIO.write_text(MEMORY_FILE, memory_text)
        if ok:
            _log(f"[记忆] memory.md 已更新: {len(updates)} 条")
            # 清除缓存，下次读到最新内容
            _prompt_cache.invalidate(MEMORY_FILE)
        else:
            _log("[记忆] memory.md 写入失败")


# ============ State 本地缓存（O-001） ============
_STATE_TMP_FILE = os.path.join(_TMP_CACHE_DIR, "_state_cache.json")
_state_cache = {"data": None, "expire_time": 0}
_state_lock = threading.Lock()


def read_state_cached():
    """读取 state，优先 /tmp 本地缓存，减少 OneDrive 读取延迟。
    
    缓存层次：内存 → /tmp → OneDrive
    TTL = STATE_CACHE_TTL (5分钟)
    """
    now = time.time()

    # 1. 内存缓存
    with _state_lock:
        if _state_cache["data"] is not None and _state_cache["expire_time"] > now:
            _log("[State] 命中内存缓存")
            # 返回深拷贝，避免调用方修改影响缓存
            import copy
            return copy.deepcopy(_state_cache["data"])

    # 2. /tmp 磁盘缓存
    try:
        if os.path.exists(_STATE_TMP_FILE):
            mtime = os.path.getmtime(_STATE_TMP_FILE)
            if now - mtime < STATE_CACHE_TTL:
                with open(_STATE_TMP_FILE, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                with _state_lock:
                    _state_cache["data"] = data
                    _state_cache["expire_time"] = now + STATE_CACHE_TTL
                _log("[State] 命中 /tmp 缓存")
                import copy
                return copy.deepcopy(data)
    except Exception:
        pass

    # 3. OneDrive 远程读取
    data = OneDriveIO.read_json(STATE_FILE) or {}
    _update_state_cache(data)
    _log("[State] 从 OneDrive 读取")
    import copy
    return copy.deepcopy(data)


def _update_state_cache(state):
    """更新 state 的内存和 /tmp 缓存"""
    now = time.time()
    with _state_lock:
        _state_cache["data"] = state
        _state_cache["expire_time"] = now + STATE_CACHE_TTL
    try:
        with open(_STATE_TMP_FILE, "w", encoding="utf-8") as f:
            _json.dump(state, f, ensure_ascii=False)
    except Exception:
        pass


def write_state_and_update_cache(state):
    """写入 state 到 OneDrive 并同时更新本地缓存"""
    OneDriveIO.write_json(STATE_FILE, state)
    _update_state_cache(state)
