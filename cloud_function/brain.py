# -*- coding: utf-8 -*-
"""
Karvis 大脑
核心中枢：Prompt 组装 → 多模型路由 → JSON 解析 → Skill 分发 → 记忆更新
"""
import json
import sys
import time as _time
import requests
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL,
    STATE_FILE, CHECKIN_TIMEOUT_SECONDS, DECISION_LOG_FILE
)
from onedrive_io import OneDriveIO
from memory import (
    load_soul, load_skills, load_rules, load_memory,
    format_recent_messages, add_message_to_state, apply_memory_updates,
    read_state_cached, write_state_and_update_cache
)

# 复用线程池，减少线程创建开销
_executor = ThreadPoolExecutor(max_workers=6)

def _log(msg):
    print(msg, file=sys.stderr, flush=True)


# ============ Skill 注册表 ============

def _get_skill_registry():
    """通过 skill_loader 自动发现并加载所有 skill（O-010）"""
    from skill_loader import load_skill_registry
    return load_skill_registry()


# ============ 多模型 LLM 调用层 ============

def _select_model_tier(payload, is_system_action=False, action=None):
    """
    根据请求类型选择模型层级。
    Returns: "flash" | "main" | "think"
    """
    if is_system_action:
        if action in ("morning_report", "evening_checkin",
                       "daily_report", "weekly_review", "monthly_review"):
            return "main"
        if action == "companion_check":
            return "flash"
        return "main"

    # 用户消息: 走 Main（一次调用完成分类+回复）
    return "main"


def _select_skill_model_tier(skill_name):
    """Skill 执行时的模型选择（Agent Loop 中）"""
    if skill_name in ("deep_dive", "decision_track"):
        return "think"
    return "main"


def call_llm(messages, model_tier="main", max_tokens=500,
             temperature=0.3, enable_thinking=None):
    """
    统一 LLM 调用入口，支持三层模型路由 + 自动降级。
    
    Args:
        model_tier: "flash" | "main" | "think"
        enable_thinking: 覆盖 thinking 设置。None = 按 tier 自动决定
    Returns:
        str: LLM 回复文本，失败返回 None
    """
    try:
        if model_tier == "flash":
            return _call_qwen_flash(messages, max_tokens, temperature)

        thinking = enable_thinking
        if thinking is None:
            thinking = (model_tier == "think")

        return _call_deepseek(messages, max_tokens, temperature,
                              enable_thinking=thinking)
    except Exception as e:
        if model_tier == "flash":
            _log(f"[Brain] Qwen Flash 失败: {e}, 降级到 DeepSeek")
            try:
                return _call_deepseek(messages, max_tokens, temperature,
                                      enable_thinking=False)
            except Exception as e2:
                _log(f"[Brain] DeepSeek 降级也失败: {e2}")
                return None
        _log(f"[Brain] LLM 调用失败 (tier={model_tier}): {e}")
        return None


def _call_deepseek(messages, max_tokens=500, temperature=0.3,
                   enable_thinking=False):
    """调用 DeepSeek V3.2，支持 thinking 模式控制"""
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    # V3.2 支持 thinking 模式控制
    if "v3.2" in DEEPSEEK_MODEL:
        data["enable_thinking"] = enable_thinking

    total_chars = sum(len(m.get("content", "")) for m in messages)
    tier_label = "Think" if enable_thinking else "Main"
    _log(f"[Brain][{tier_label}] DeepSeek请求: model={DEEPSEEK_MODEL}, "
         f"thinking={enable_thinking}, prompt_chars={total_chars}, max_tokens={max_tokens}")

    t0 = _time.time()
    resp = requests.post(url, headers=headers, json=data, timeout=60)
    t1 = _time.time()

    if resp.status_code == 200:
        result = resp.json()
        usage = result.get("usage", {})
        _log(f"[Brain][{tier_label}] DeepSeek响应: {t1-t0:.1f}s, "
             f"prompt_tokens={usage.get('prompt_tokens')}, "
             f"completion_tokens={usage.get('completion_tokens')}")
        return result["choices"][0]["message"]["content"]

    _log(f"[Brain][{tier_label}] DeepSeek API 错误: {resp.status_code} - {resp.text[:200]}")
    raise RuntimeError(f"DeepSeek API {resp.status_code}")


def _call_qwen_flash(messages, max_tokens=500, temperature=0.3):
    """调用 Qwen Flash（阿里云百炼），极快极便宜"""
    url = f"{QWEN_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": QWEN_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    total_chars = sum(len(m.get("content", "")) for m in messages)
    _log(f"[Brain][Flash] Qwen请求: model={QWEN_MODEL}, "
         f"prompt_chars={total_chars}, max_tokens={max_tokens}")

    t0 = _time.time()
    resp = requests.post(url, headers=headers, json=data, timeout=30)
    t1 = _time.time()

    if resp.status_code == 200:
        result = resp.json()
        usage = result.get("usage", {})
        _log(f"[Brain][Flash] Qwen响应: {t1-t0:.1f}s, "
             f"prompt_tokens={usage.get('prompt_tokens')}, "
             f"completion_tokens={usage.get('completion_tokens')}")
        return result["choices"][0]["message"]["content"]

    _log(f"[Brain][Flash] Qwen API 错误: {resp.status_code} - {resp.text[:200]}")
    raise RuntimeError(f"Qwen API {resp.status_code}")


# 向后兼容：保留 call_deepseek 别名
def call_deepseek(messages, max_tokens=500, temperature=0.3):
    """向后兼容：等同于 call_llm(tier='main', thinking=off)"""
    return call_llm(messages, model_tier="main", max_tokens=max_tokens,
                    temperature=temperature)


# ============ Prompt 组装 ============

def build_system_prompt(state, prompt_futs=None):
    """组装完整的 System Prompt（并发加载 prompt 文件）
    
    prompt_futs: 可选，外部提前提交的 futures dict，用于与 state 读取并行
    """
    beijing_tz = timezone(timedelta(hours=8))
    current_time = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M %A")

    # 如果外部已提交，直接用；否则自行并发加载
    if prompt_futs is None:
        prompt_futs = {
            "soul": _executor.submit(load_soul),
            "skills": _executor.submit(load_skills),
            "rules": _executor.submit(load_rules),
            "mem": _executor.submit(load_memory),
        }
    soul = prompt_futs["soul"].result()
    skills = prompt_futs["skills"].result()
    rules = prompt_futs["rules"].result()
    mem = prompt_futs["mem"].result()

    recent = format_recent_messages(state)
    state_summary = _build_state_summary(state)

    return f"""{soul}

## 长期记忆
{mem}

## 最近对话
{recent}

## 当前状态
{state_summary}

## 当前时间
{current_time}

{skills}

{rules}

## 输出格式（严格 JSON，不要加 markdown 代码块标记，尽量简短）
{{
  "thinking": "一句话推理",
  "skill": "skill.name",
  "params": {{ }},
  "reply": "简短回复，null 表示不回复",
  "state_updates": {{ }},
  "memory_updates": [],
  "continue": false
}}

continue 说明：仅在使用 internal.* skill（读取/搜索文件）时设为 true，表示还需要更多信息才能完成任务。普通 skill 始终为 false。"""


def _build_state_summary(state):
    """从 state 中提取关键信息，构建给 LLM 看的摘要"""
    parts = []

    # 打卡状态
    if state.get("checkin_pending"):
        step = state.get("checkin_step", 0)
        questions = [
            "今天做了什么？",
            "今天状态打几分？(1-10)",
            "什么事让你纠结？",
            "脑子里最常冒出的念头是什么？"
        ]
        q = questions[step - 1] if 1 <= step <= 4 else "未知"
        parts.append(f"打卡进行中: 第 {step}/4 题, 当前问题: \"{q}\"")
        answers = state.get("checkin_answers", [])
        if answers:
            parts.append(f"已回答 {len(answers)} 题")
    else:
        parts.append("未在打卡")

    # 活跃书籍/影视
    active_book = state.get("active_book", "")
    if active_book:
        parts.append(f"正在读: 《{active_book}》")

    active_media = state.get("active_media", "")
    if active_media:
        parts.append(f"正在看: 《{active_media}》")

    # V3-F12: 每日 Top 3
    daily_top3 = state.get("daily_top3", {})
    if daily_top3 and daily_top3.get("items"):
        beijing_tz = timezone(timedelta(hours=8))
        today_str = datetime.now(beijing_tz).strftime("%Y-%m-%d")
        top3_date = daily_top3.get("date", "")
        items = daily_top3["items"]
        items_str = " / ".join(
            f"{'✅' if i.get('done') else '⬜'} {i.get('text', '')}"
            for i in items
        )
        if top3_date == today_str:
            parts.append(f"今日 Top 3: {items_str}")
        else:
            parts.append(f"昨日({top3_date}) Top 3: {items_str}")

    # V3-F11: 活跃实验
    exp = state.get("active_experiment")
    if exp and exp.get("status") == "active":
        tracking = exp.get("tracking", {})
        triggers_str = "、".join(exp.get("triggers", [])[:3]) if exp.get("triggers") else ""
        parts.append(
            f"活跃实验: 「{exp.get('name', '')}」"
            f"(触发词: {triggers_str}, "
            f"触发{tracking.get('trigger_count', 0)}次/"
            f"接受{tracking.get('accepted_count', 0)}次)"
        )

    # V3-F15: 待复盘决策
    pending_decisions = state.get("pending_decisions", [])
    unreviewed = [d for d in pending_decisions if not d.get("result")]
    if unreviewed:
        beijing_tz = timezone(timedelta(hours=8))
        today_str = datetime.now(beijing_tz).strftime("%Y-%m-%d")
        due = [d for d in unreviewed if d.get("review_date", "9999") <= today_str]
        if due:
            topics = "、".join(f"「{d.get('topic', '')}」" for d in due[:3])
            parts.append(f"到期待复盘决策: {topics}")
        elif len(unreviewed) <= 3:
            topics = "、".join(f"「{d.get('topic', '')}」" for d in unreviewed)
            parts.append(f"待复盘决策({len(unreviewed)}): {topics}")
        else:
            parts.append(f"待复盘决策: {len(unreviewed)} 个")

    return "\n".join(parts) if parts else "无特殊状态"


# ============ 核心处理流程 ============

def process(payload, send_fn=None):
    """
    Karvis 大脑的核心入口。

    参数:
        payload: dict, 结构化消息
            {"type": "text", "text": "...", "user_id": "..."}
            {"type": "voice", "text": "ASR文本", "attachment": "OneDrive路径", "user_id": "..."}
            {"type": "image", "attachment": "OneDrive路径", "user_id": "..."}
            {"type": "video", "attachment": "OneDrive路径", "user_id": "..."}
            {"type": "link", "title": "...", "url": "...", "description": "...", "user_id": "..."}
            {"type": "system", "action": "morning_report|evening_checkin", "user_id": "..."}

    返回:
        {"reply": "回复文本" | None}
    """
    t_start = _time.time()
    _log(f"[Brain] 收到: {json.dumps(payload, ensure_ascii=False)[:200]}")

    # 0. 预热 OneDrive token + Graph API 连接（串行，一举两得）
    #    预热读取会建立到 graph.microsoft.com 的 TLS 连接，后续请求复用
    OneDriveIO.get_token()
    t_token = _time.time()
    _log(f"[Brain][耗时] token预热: {t_token - t_start:.1f}s")

    # 1. 读取 state（优先 /tmp 缓存）和 prompt 文件（并发）
    state_future = _executor.submit(read_state_cached)
    prompt_futs = {
        "soul": _executor.submit(load_soul),
        "skills": _executor.submit(load_skills),
        "rules": _executor.submit(load_rules),
        "mem": _executor.submit(load_memory),
    }

    # 2. 先提取 user_text（不依赖 state 和 prompt，CPU 操作）
    user_text = _extract_user_text(payload)

    # 等 state 结果（可能命中 /tmp 缓存，<1ms）
    state = state_future.result() or {}
    t_state = _time.time()
    _log(f"[Brain][耗时] state读取: {t_state - t_token:.1f}s")

    # 3. 检查打卡超时
    _check_checkin_timeout(state)

    # 4. 记录用户消息到短期记忆 + 更新 nudge_state（F5）
    if user_text and payload.get("type") != "system":
        add_message_to_state(state, "user", user_text)
        _update_nudge_state(state)

    # 5. 构建 prompt 并调用 LLM（prompt_futs 在步骤 1 已提交，此处直接取结果）
    system_prompt = build_system_prompt(state, prompt_futs=prompt_futs)
    t_prompt = _time.time()
    _log(f"[Brain][耗时] prompt组装: {t_prompt - t_state:.1f}s (prompt长度={len(system_prompt)})")

    user_message = _build_user_message(payload)

    # 多模型路由：根据请求类型选择模型层级
    is_system = payload.get("type") == "system"
    action = payload.get("action", "") if is_system else None
    model_tier = _select_model_tier(payload, is_system_action=is_system, action=action)
    _log(f"[Brain] 模型路由: tier={model_tier}, is_system={is_system}, action={action}")

    llm_response = call_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ], model_tier=model_tier)
    t_llm = _time.time()
    _log(f"[Brain][耗时] LLM调用({model_tier}): {t_llm - t_prompt:.1f}s")

    if not llm_response:
        _log("[Brain] LLM 返回空，降级处理")
        # Quick-Notes 统一写入
        if payload.get("type") != "system":
            _save_to_quick_notes(payload, state)
        return {"reply": "已记录到 Obsidian（AI 暂时不可用）"}

    # 6. 解析 LLM 输出
    decision = _parse_llm_output(llm_response)
    if not decision:
        _log(f"[Brain] JSON 解析失败，原始: {llm_response[:300]}")
        if payload.get("type") != "system":
            _save_to_quick_notes(payload, state)
        return {"reply": "已记录到 Obsidian"}

    _log(f"[Brain] 决策: skill={decision.get('skill')}, thinking={decision.get('thinking', '')[:80]}")
    if decision.get("memory_updates"):
        _log(f"[Brain] 记忆更新: {json.dumps(decision['memory_updates'], ensure_ascii=False)[:200]}")

    skill_name = decision.get("skill", "ignore")
    params = decision.get("params", {})
    registry = _get_skill_registry()
    skill_result = None
    skill_handler = registry.get(skill_name)

    # 7. 所有用户消息统一写入 Quick-Notes（原始流水记录）
    #    system 类型、打卡回答除外
    if payload.get("type") != "system" and skill_name not in ("checkin.answer", "checkin.skip", "checkin.cancel", "checkin.start"):
        _save_to_quick_notes(payload, state)

    # 8. 执行 Skill（note.save 已由上面统一处理，跳过）
    if skill_name == "note.save":
        _log(f"[Brain] note.save 已由统一写入处理，跳过 skill 执行")
        skill_result = {"success": True}
    elif skill_handler:
        try:
            skill_result = skill_handler(params, state)
            _log(f"[Brain] Skill {skill_name} 执行完成: {skill_result}")
        except Exception as e:
            _log(f"[Brain] Skill {skill_name} 执行失败: {e}")
            import traceback
            traceback.print_exc(file=sys.stderr)
    else:
        _log(f"[Brain] 未知 Skill: {skill_name}")
    t_skill = _time.time()
    _log(f"[Brain][耗时] Skill执行: {t_skill - t_llm:.1f}s")

    # V3-F10: Agent Loop — 如果 LLM 返回 continue=true 且 skill 返回 agent_context，进入多轮循环
    agent_context = skill_result.get("agent_context") if skill_result and isinstance(skill_result, dict) else None
    if decision.get("continue") and agent_context and skill_name.startswith("internal."):
        decision, skill_result = _run_agent_loop(
            system_prompt, user_message, decision, agent_context, state, registry
        )
        # 更新 skill_name 为最终决策的 skill
        skill_name = decision.get("skill", "ignore")
        t_agent = _time.time()
        _log(f"[Brain][耗时] Agent Loop: {t_agent - t_skill:.1f}s")
        t_skill = t_agent

    # 9. 合并状态更新
    skill_state_updates = None
    if skill_result and isinstance(skill_result, dict):
        skill_state_updates = skill_result.get("state_updates")

    if skill_state_updates:
        state.update(skill_state_updates)
    else:
        llm_state_updates = decision.get("state_updates", {})
        if llm_state_updates:
            state.update(llm_state_updates)

    # 9. 确定最终回复
    skill_reply = skill_result.get("reply") if skill_result and isinstance(skill_result, dict) else None
    reply = skill_reply or decision.get("reply")

    # 兜底：用户消息必须有回复（system 类型除外）
    if not reply and payload.get("type") != "system":
        if decision.get("memory_updates"):
            reply = "记住啦~"
        elif skill_name == "note.save":
            reply = "已记录 ✅"
        elif skill_name == "ignore":
            reply = "收到~"
        else:
            reply = "好的~"

    if reply:
        add_message_to_state(state, "karvis", reply)

    # 10. 先发回复（O-001：用户感知延迟优化），再保存 state/memory
    if send_fn and reply:
        try:
            send_fn(reply)
            _log(f"[Brain] 回复已先行发送，开始后台保存")
        except Exception as e:
            _log(f"[Brain] 先行发送失败: {e}")

    t_save_start = _time.time()
    _save_state_and_memory(state, decision, payload=payload, reply=reply, elapsed=t_save_start - t_start)
    t_end = _time.time()
    _log(f"[Brain][耗时] 保存state: {t_end - t_save_start:.1f}s | 总计: {t_end - t_start:.1f}s")

    return {"reply": reply, "already_sent": bool(send_fn and reply)}


def _save_state_and_memory(state, decision, payload=None, reply=None, elapsed=None):
    """保存 state、更新记忆、写决策日志（并发写，但同步等完成）"""
    futs = []
    futs.append(_executor.submit(_write_state, state))

    memory_updates = decision.get("memory_updates", [])
    if memory_updates:
        futs.append(_executor.submit(_write_memory, memory_updates))

    # 决策日志（O-003）
    futs.append(_executor.submit(_write_decision_log, payload, decision, reply, elapsed))

    # 等全部写完再返回，确保 SCF 不会冻结中途
    for f in futs:
        try:
            f.result(timeout=30)
        except Exception as e:
            _log(f"[Brain] 写入异常: {e}")


def _write_state(state):
    try:
        write_state_and_update_cache(state)
    except Exception as e:
        _log(f"[Brain] state 保存失败: {e}")


def _write_memory(memory_updates):
    try:
        apply_memory_updates(memory_updates)
    except Exception as e:
        _log(f"[Brain] 记忆更新失败: {e}")


def _write_decision_log(payload, decision, reply, elapsed):
    """将每次决策写入 JSONL 日志（追加模式），用于回顾和质量监控"""
    try:
        beijing_tz = timezone(timedelta(hours=8))
        now_str = datetime.now(beijing_tz).strftime("%Y-%m-%d %H:%M:%S")

        # 提取输入摘要
        input_type = payload.get("type", "") if payload else ""
        input_text = ""
        if input_type == "text":
            input_text = payload.get("text", "")[:100]
        elif input_type == "voice":
            input_text = payload.get("text", "")[:100]
        elif input_type == "system":
            input_text = payload.get("action", "")

        entry = {
            "ts": now_str,
            "input_type": input_type,
            "input": input_text,
            "thinking": decision.get("thinking", "")[:100] if decision else "",
            "skill": decision.get("skill", "") if decision else "",
            "reply": (reply or "")[:100],
            "has_memory_updates": bool(decision.get("memory_updates")) if decision else False,
            "elapsed_s": round(elapsed, 1) if elapsed else None,
        }
        line = json.dumps(entry, ensure_ascii=False)

        # 追加到 OneDrive JSONL：读取现有内容 → 追加 → 写回
        existing = OneDriveIO.read_text(DECISION_LOG_FILE) or ""
        new_content = existing + line + "\n"
        OneDriveIO.write_text(DECISION_LOG_FILE, new_content)
        _log(f"[Brain] 决策日志已写入: skill={entry['skill']}")
    except Exception as e:
        _log(f"[Brain] 决策日志写入失败（不影响主流程）: {e}")


# ============ V3-F10: Agent Loop ============

def _run_agent_loop(system_prompt, user_message, first_decision, first_context, state, registry):
    """
    多轮 Agent Loop：LLM 可以连续调用 internal.* skill 获取更多信息，
    直到返回 continue=false 或达到最大轮数。

    返回: (final_decision, final_skill_result)
    """
    MAX_ROUNDS = 5
    ROUND_TIMEOUT = 30

    # 构建对话历史
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
        # 第一轮 LLM 的回复
        {"role": "assistant", "content": json.dumps(first_decision, ensure_ascii=False)},
        # 第一轮 skill 的执行结果
        {"role": "user", "content": json.dumps({
            "type": "agent_step",
            "step": 1,
            "skill_result": first_context
        }, ensure_ascii=False)}
    ]

    last_decision = first_decision
    last_skill_result = {"success": True, "agent_context": first_context}

    for step in range(2, MAX_ROUNDS + 1):
        _log(f"[Brain][AgentLoop] 第 {step} 轮")

        # Agent Loop 中走 Main（后续可按 skill 动态选择 tier）
        llm_response = call_llm(messages, model_tier="main", max_tokens=500, temperature=0.3)
        if not llm_response:
            _log(f"[Brain][AgentLoop] LLM 返回空，终止循环")
            break

        decision = _parse_llm_output(llm_response)
        if not decision:
            _log(f"[Brain][AgentLoop] JSON 解析失败，终止循环")
            break

        last_decision = decision
        skill_name = decision.get("skill", "ignore")
        params = decision.get("params", {})

        _log(f"[Brain][AgentLoop] step={step}, skill={skill_name}, continue={decision.get('continue')}")

        # 如果不再继续，退出循环
        if not decision.get("continue"):
            # 如果最后一步有非 internal skill，执行它
            if skill_name and not skill_name.startswith("internal.") and skill_name != "ignore":
                handler = registry.get(skill_name)
                if handler:
                    try:
                        last_skill_result = handler(params, state)
                    except Exception as e:
                        _log(f"[Brain][AgentLoop] 最终 Skill {skill_name} 执行失败: {e}")
                        last_skill_result = {"success": False}
            break

        # 继续循环：执行 internal.* skill
        handler = registry.get(skill_name)
        if not handler:
            _log(f"[Brain][AgentLoop] 未知 skill: {skill_name}，终止")
            break

        try:
            skill_result = handler(params, state)
            agent_context = skill_result.get("agent_context") if isinstance(skill_result, dict) else None
        except Exception as e:
            _log(f"[Brain][AgentLoop] Skill {skill_name} 异常: {e}")
            agent_context = {"error": str(e)}

        last_skill_result = skill_result or {"success": True}

        # 追加到对话历史
        messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
        messages.append({"role": "user", "content": json.dumps({
            "type": "agent_step",
            "step": step,
            "skill_result": agent_context or {}
        }, ensure_ascii=False)})

    _log(f"[Brain][AgentLoop] 循环结束，最终 skill={last_decision.get('skill')}")
    return last_decision, last_skill_result


# ============ 辅助函数 ============

def _save_to_quick_notes(payload, state):
    """所有用户消息统一写入 Quick-Notes（原始流水记录）"""
    try:
        from skills import note_save
        content = ""
        attachment = ""
        msg_type = payload.get("type", "")

        if msg_type == "text":
            content = payload.get("text", "")
        elif msg_type == "voice":
            content = payload.get("text", "")
            attachment = payload.get("attachment", "")
        elif msg_type == "image":
            attachment = payload.get("attachment", "")
        elif msg_type == "video":
            attachment = payload.get("attachment", "")
        elif msg_type == "link":
            title = payload.get("title", "")
            url = payload.get("url", "")
            desc = payload.get("description", "")
            content = f"[{title}]({url})" if url else title
            if desc:
                content += f"\n\n> {desc}"

        if content or attachment:
            note_save.execute({"content": content, "attachment": attachment}, state)
    except Exception as e:
        _log(f"[Brain] Quick-Notes 统一写入失败（不影响主流程）: {e}")

def _extract_user_text(payload):
    """从 payload 中提取用户文本（用于短期记忆）"""
    msg_type = payload.get("type", "")
    if msg_type == "text":
        return payload.get("text", "")
    elif msg_type == "voice":
        return f"[语音] {payload.get('text', '')}"
    elif msg_type == "image":
        return "[图片]"
    elif msg_type == "video":
        return "[视频]"
    elif msg_type == "link":
        return f"[链接] {payload.get('title', '')}"
    return ""


def _build_user_message(payload):
    """构建发给 LLM 的 user message"""
    msg_type = payload.get("type", "")

    if msg_type == "text":
        data = {"type": "text", "text": payload.get("text", "")}
        # F1: 如果检测到 URL 并抓取了正文，传给 LLM
        page_content = payload.get("page_content", "")
        if page_content:
            data["page_content"] = page_content
            detected_url = payload.get("detected_url", "")
            if detected_url:
                data["detected_url"] = detected_url
        return json.dumps(data, ensure_ascii=False)

    elif msg_type == "voice":
        asr_text = payload.get("text", "")
        return json.dumps({
            "type": "voice",
            "asr_text": asr_text,
            "text_length": len(asr_text),
            "attachment": payload.get("attachment", "")
        }, ensure_ascii=False)

    elif msg_type == "image":
        return json.dumps({
            "type": "image",
            "attachment": payload.get("attachment", "")
        }, ensure_ascii=False)

    elif msg_type == "video":
        return json.dumps({
            "type": "video",
            "attachment": payload.get("attachment", "")
        }, ensure_ascii=False)

    elif msg_type == "link":
        data = {
            "type": "link",
            "title": payload.get("title", ""),
            "url": payload.get("url", ""),
            "description": payload.get("description", "")
        }
        # F1: 如果有抓取到的网页正文，传给 LLM
        page_content = payload.get("content", "")
        if page_content:
            data["page_content"] = page_content
        return json.dumps(data, ensure_ascii=False)

    elif msg_type == "system":
        msg = {
            "type": "system",
            "action": payload.get("action", "")
        }
        # 注入上下文数据（O-007：待办、速记等）
        context = payload.get("context", {})
        if context:
            msg["context"] = context
        return json.dumps(msg, ensure_ascii=False)

    return json.dumps(payload, ensure_ascii=False)


def _parse_llm_output(text):
    """解析 LLM 输出的 JSON（容错处理）"""
    text = text.strip()

    # 去除 markdown 代码块标记
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首行和末行
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 块
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    _log(f"[Brain] 无法解析 JSON: {text[:200]}")
    return None


def _update_nudge_state(state):
    """F5: 每次收到用户消息时更新 nudge_state（连续记录天数 + 精确时间）"""
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    today_str = now.strftime("%Y-%m-%d")

    nudge = state.setdefault("nudge_state", {
        "streak": 0,
        "last_message_date": "",
        "last_message_time": "",
        "last_companion_time": "",
        "companion_count_today": 0,
        "yesterday_mood_score": None,
        "people_last_mentioned": {}
    })

    # 精确到分钟的最后消息时间（companion_check 防骚扰用）
    nudge["last_message_time"] = now.strftime("%Y-%m-%d %H:%M")

    last_date = nudge.get("last_message_date", "")
    if last_date != today_str:
        # 新的一天第一条消息：重置每日计数器
        nudge["companion_count_today"] = 0
        nudge["mood_followed_today"] = False

        if last_date:
            try:
                last_dt = datetime.strptime(last_date, "%Y-%m-%d").date()
                today_dt = datetime.strptime(today_str, "%Y-%m-%d").date()
                if (today_dt - last_dt).days == 1:
                    nudge["streak"] = nudge.get("streak", 0) + 1
                elif (today_dt - last_dt).days > 1:
                    nudge["streak"] = 1
            except Exception:
                nudge["streak"] = 1
        else:
            nudge["streak"] = 1
        nudge["last_message_date"] = today_str


def _check_checkin_timeout(state):
    """检查打卡是否超时"""
    if not state.get("checkin_pending"):
        return

    sent_at = state.get("checkin_sent_at", "")
    if not sent_at:
        return

    try:
        beijing_tz = timezone(timedelta(hours=8))
        now = datetime.now(beijing_tz)
        sent_time = datetime.strptime(sent_at, "%Y-%m-%d %H:%M")
        sent_time = sent_time.replace(tzinfo=beijing_tz)
        diff = (now - sent_time).total_seconds()
        if diff > CHECKIN_TIMEOUT_SECONDS:
            _log(f"[Brain] 打卡超时 ({diff:.0f}s)")
            from skills import checkin_flow
            checkin_flow.finish(state, timeout=True)
    except Exception as e:
        _log(f"[Brain] 打卡超时检查异常: {e}")
