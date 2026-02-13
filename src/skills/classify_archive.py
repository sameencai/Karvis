# -*- coding: utf-8 -*-
"""
Skill: classify.archive
将消息按分类归档到对应的 Obsidian 笔记目录。
分类由 LLM 在决策时直接给出，无需二次 AI 调用。

分类:
  work → 02-Notes/工作笔记/{YYYY-MM-DD}.md
  emotion → 02-Notes/情感日记/{YYYY-MM-DD}.md
  fun → 02-Notes/生活趣事/{YYYY-MM-DD}.md
  misc → 00-Inbox/碎碎念.md
"""
import sys
from datetime import datetime, timezone, timedelta
from config import (
    WORK_NOTES_DIR, EMOTION_NOTES_DIR, FUN_NOTES_DIR, MISC_FILE
)
from storage import IO as OneDriveIO

BEIJING_TZ = timezone(timedelta(hours=8))

CATEGORY_MAP = {
    "work": {"dir": WORK_NOTES_DIR, "emoji": "💼", "label": "工作笔记"},
    "emotion": {"dir": EMOTION_NOTES_DIR, "emoji": "💭", "label": "情感日记"},
    "fun": {"dir": FUN_NOTES_DIR, "emoji": "😂", "label": "生活趣事"},
    "misc": {"emoji": "📝", "label": "碎碎念"},
}


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def execute(params, state):
    """
    将消息归档到对应分类。

    params:
        category: str — work/emotion/fun/misc
        title: str — AI 生成的简短标题（10字以内）
        content: str — 消息内容
        attachment: str — 可选，附件路径
    """
    category = (params.get("category") or "misc").strip().lower()
    title = (params.get("title") or "").strip()
    content = (params.get("content") or "").strip()
    attachment = (params.get("attachment") or "").strip()

    if not content and not attachment:
        return {"success": False, "reply": "没有可归档的内容"}

    if category not in CATEGORY_MAP:
        category = "misc"

    cat_info = CATEGORY_MAP[category]
    now = datetime.now(BEIJING_TZ)
    time_str = now.strftime("%Y-%m-%d %H:%M")
    date_str = now.strftime("%Y-%m-%d")

    # 构建 Markdown 条目
    entry_title = f"### {title}" if title else f"### {time_str}"
    entry_parts = [entry_title, ""]
    if content:
        entry_parts.append(content)
    if attachment:
        relative = attachment
        if "attachments/" in attachment:
            relative = "attachments/" + attachment.split("attachments/")[-1]
        ext = attachment.rsplit(".", 1)[-1].lower() if "." in attachment else ""
        if ext in ("jpg", "jpeg", "png", "gif", "webp", "mp4", "mov"):
            entry_parts.append(f"![[{relative}]]")
        elif ext in ("mp3", "wav", "amr", "silk", "m4a"):
            entry_parts.append(f"🔗 [[{relative}]]")
        else:
            entry_parts.append(f"📎 [[{relative}]]")
    entry_parts.extend([f"*— {time_str}*", "", "---", ""])
    entry = "\n".join(entry_parts)

    if category == "misc":
        # 碎碎念：追加到单文件
        ok = _append_to_misc(entry, time_str, content)
    else:
        # 其他分类：按日期归档
        file_path = f"{cat_info['dir']}/{date_str}.md"
        ok = _append_to_dated_file(file_path, date_str, entry, cat_info)

    if ok:
        _log(f"[classify.archive] 已归档到 {cat_info['label']}: {(title or content)[:40]}")
        return {"success": True}
    else:
        return {"success": False, "reply": f"归档到{cat_info['label']}失败"}


def _append_to_misc(entry, time_str, content):
    """追加到碎碎念.md"""
    existing = OneDriveIO.read_text(MISC_FILE)
    if existing is None:
        return False

    if not existing.strip():
        existing = "# 📝 碎碎念\n\n无法被 AI 归类的零散记录。\n\n---\n"

    # 追加条目（在最后一个 --- 之后）
    new_section = f"\n## {time_str}\n\n{content}\n\n---\n"
    new_content = existing.rstrip() + "\n" + new_section

    return OneDriveIO.write_text(MISC_FILE, new_content)


def _append_to_dated_file(file_path, date_str, entry, cat_info):
    """追加到按日期命名的归档文件"""
    existing = OneDriveIO.read_text(file_path)
    if existing is None:
        return False

    if not existing.strip():
        # 新建文件
        existing = f"# {cat_info['emoji']} {cat_info['label']} — {date_str}\n\n---\n"

    new_content = existing.rstrip() + "\n\n" + entry
    return OneDriveIO.write_text(file_path, new_content)


# Skill 热加载注册表（O-010）
SKILL_REGISTRY = {
    "classify.archive": execute,
}
