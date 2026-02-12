# -*- coding: utf-8 -*-
"""
Skill: weekly.review
每周自动生成周回顾：从过去 7 天数据中发现模式、关联和情绪趋势。
写入 01-Daily/周报-{起始日期}.md

数据源：
1. Quick-Notes（7 天条目）
2. 归档笔记（emotion/fun/work 各天 + 碎碎念）
3. Daily Note（日报 + 打卡）
4. 情绪日记（mood_score + key_moments）
5. 决策日志（skill 使用统计）
6. state.mood_scores（情绪评分数组）
"""
import sys
import json
from datetime import datetime, timezone, timedelta
from config import (
    QUICK_NOTES_FILE, DAILY_NOTES_DIR,
    EMOTION_NOTES_DIR, WORK_NOTES_DIR, FUN_NOTES_DIR,
    MISC_FILE, DECISION_LOG_FILE
)
from onedrive_io import OneDriveIO

BEIJING_TZ = timezone(timedelta(hours=8))


def _log(msg):
    print(msg, file=sys.stderr, flush=True)


def execute(params, state):
    """
    生成周回顾。

    params:
        date: str — 可选，指定周日日期 YYYY-MM-DD，默认本周日（如果今天不是周日则取上周日）
    """
    date_str = (params.get("date") or "").strip()
    if not date_str:
        today = datetime.now(BEIJING_TZ).date()
        # 找到本周日（weekday: Mon=0 ... Sun=6）
        days_since_sunday = (today.weekday() + 1) % 7
        sunday = today - timedelta(days=days_since_sunday)
        date_str = sunday.strftime("%Y-%m-%d")

    # 计算周一到周日
    try:
        end_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return {"success": False, "reply": f"日期格式错误：{date_str}"}

    start_date = end_date - timedelta(days=6)
    period_str = f"{start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}"
    dates = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    _log(f"[weekly.review] 生成周报: {period_str}")

    # 1. 并发收集 7 天数据
    data = _collect_week_data(dates, state)

    if not data["notes"].strip():
        _log("[weekly.review] 本周没有记录")
        return {"success": True, "reply": f"本周（{period_str}）没有记录，无法生成周报"}

    # 2. AI 分析
    from brain import call_deepseek
    analysis = _ai_analyze_week(data, period_str, dates, call_deepseek)

    if not analysis:
        return {"success": False, "reply": "AI 周报分析失败"}

    # 3. 构建 Markdown
    review_md = _build_weekly_review(period_str, start_date.strftime("%Y-%m-%d"), analysis, data)

    # 4. 写入文件
    file_path = f"{DAILY_NOTES_DIR}/周报-{start_date.strftime('%Y-%m-%d')}.md"
    ok = _write_weekly_review(file_path, review_md)

    if ok:
        _log(f"[weekly.review] 周报已写入: {file_path}")
        mood_avg = analysis.get("mood_avg", "?")
        insight = analysis.get("insight", "")[:60]
        return {
            "success": True,
            "reply": f"📅 周回顾已生成（{period_str}）\n情绪均分：{mood_avg}/10\n{insight}"
        }
    else:
        return {"success": False, "reply": "周报写入失败"}


def _collect_week_data(dates, state):
    """并发收集 7 天的所有数据"""
    from concurrent.futures import ThreadPoolExecutor

    # 构建要读取的文件列表
    files_to_read = {
        "quick_notes": QUICK_NOTES_FILE,
        "misc": MISC_FILE,
        "decisions": DECISION_LOG_FILE,
    }
    for d in dates:
        files_to_read[f"daily_{d}"] = f"{DAILY_NOTES_DIR}/{d}.md"
        files_to_read[f"emotion_{d}"] = f"{EMOTION_NOTES_DIR}/{d}.md"
        files_to_read[f"fun_{d}"] = f"{FUN_NOTES_DIR}/{d}.md"
        files_to_read[f"work_{d}"] = f"{WORK_NOTES_DIR}/{d}.md"

    # 并发读取（复用 brain 的全局线程池）
    results = {}
    try:
        from brain import _executor
        executor = _executor
    except ImportError:
        executor = ThreadPoolExecutor(max_workers=6)

    futures = {k: executor.submit(OneDriveIO.read_text, v) for k, v in files_to_read.items()}

    for k, fut in futures.items():
        try:
            results[k] = fut.result(timeout=30) or ""
        except Exception:
            results[k] = ""

    # 组装各天的笔记
    all_parts = []
    day_summaries = {}

    for d in dates:
        day_parts = []

        # Quick-Notes 该日条目
        qn_entries = _extract_date_entries(results["quick_notes"], d)
        if qn_entries:
            day_parts.append(qn_entries)

        # 归档笔记
        for key, label in [("emotion", "情感"), ("fun", "趣事"), ("work", "工作")]:
            content = results.get(f"{key}_{d}", "").strip()
            if content:
                day_parts.append(f"[{label}] {content[:500]}")

        # 碎碎念该日条目
        misc_entries = _extract_date_entries(results["misc"], d)
        if misc_entries:
            day_parts.append(f"[碎碎念] {misc_entries[:300]}")

        # Daily Note（日报+打卡）
        daily = results.get(f"daily_{d}", "").strip()
        if daily:
            # 提取日报总结
            if "## 📊 今日总结" in daily:
                summary_section = daily.split("## 📊 今日总结")[1]
                end_idx = summary_section.find("\n## ")
                if end_idx >= 0:
                    summary_section = summary_section[:end_idx]
                day_parts.append(f"[日报] {summary_section.strip()[:400]}")
            # 提取打卡
            if "## 每日复盘" in daily:
                checkin_section = daily.split("## 每日复盘")[1]
                end_idx = checkin_section.find("\n## ")
                if end_idx >= 0:
                    checkin_section = checkin_section[:end_idx]
                day_parts.append(f"[打卡] {checkin_section.strip()[:400]}")

        if day_parts:
            day_text = "\n".join(day_parts)
            all_parts.append(f"=== {d} ===\n{day_text}")
            day_summaries[d] = day_text

    notes = "\n\n".join(all_parts)

    # 提取情绪评分
    mood_scores = []
    for entry in state.get("mood_scores", []):
        if entry.get("date") in dates:
            mood_scores.append(entry)

    # 提取决策日志统计
    decision_stats = _extract_decision_stats(results["decisions"], dates)

    return {
        "notes": notes,
        "day_summaries": day_summaries,
        "mood_scores": mood_scores,
        "decision_stats": decision_stats,
        "dates": dates,
    }


def _extract_date_entries(text, date_str):
    """从 Markdown 文件中提取指定日期的条目"""
    if not text:
        return ""
    entries = []
    sections = text.split("\n## ")
    for section in sections[1:]:
        first_line = section.split("\n")[0].strip()
        if first_line.startswith(date_str):
            entries.append("## " + section.strip())
    return "\n\n".join(entries)


def _extract_decision_stats(text, dates):
    """从 JSONL 决策日志中统计本周 skill 使用分布"""
    if not text:
        return {}
    date_set = set(dates)
    skill_counts = {}
    total = 0
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts = entry.get("ts", "")
            if ts[:10] in date_set:
                skill = entry.get("skill", "unknown")
                skill_counts[skill] = skill_counts.get(skill, 0) + 1
                total += 1
        except Exception:
            pass
    return {"skill_counts": skill_counts, "total_decisions": total}


def _ai_analyze_week(data, period_str, dates, call_deepseek):
    """调用 AI 分析周数据"""
    parts = [f"分析以下 {period_str} 一周的记录，生成周回顾。"]

    # 情绪评分
    if data["mood_scores"]:
        parts.append("\n【情绪评分数据】")
        for s in data["mood_scores"]:
            parts.append(f"- {s.get('date','?')}: {s.get('score','?')}/10 ({s.get('source','?')}) {s.get('label','')}")

    # 决策统计
    stats = data["decision_stats"]
    if stats.get("total_decisions"):
        parts.append(f"\n【本周互动统计】共 {stats['total_decisions']} 次决策")
        for skill, count in sorted(stats["skill_counts"].items(), key=lambda x: -x[1])[:10]:
            parts.append(f"- {skill}: {count}次")

    # 各天记录
    if data["notes"]:
        # 截断到合理长度（7 天数据可能很长）
        notes_text = data["notes"][:6000]
        parts.append(f"\n【本周记录】\n{notes_text}")

    parts.append(f"""
返回 JSON（不要 markdown 代码块标记）：
{{
  "mood_trend": [
    {{"date": "MM-DD", "score": 7, "keyword": "2字情绪词"}}
  ],
  "mood_avg": 7.1,
  "connections": [
    {{"title": "3-6字标题", "detail": "2-3句分析，发现跨天的模式和关联"}},
    {{"title": "标题2", "detail": "..."}}
  ],
  "stats": {{
    "total_messages": 23,
    "categories": {{"fun": 8, "emotion": 5, "work": 3, "misc": 4}},
    "top_people": [{{"name": "人名", "count": 3}}],
    "keywords": ["关键词1", "关键词2", "关键词3"]
  }},
  "insight": "1-2句本周最核心的洞察，像朋友一样",
  "suggestions": ["下周建议1", "下周建议2", "下周建议3"]
}}

规则：
- mood_trend 按日期排列，没有评分的日子用 null
- connections 是本周最有价值的 2-4 个"碎片连线"——找出不同天/不同事件之间的隐藏关联
- stats 统计消息数、分类分布、提及最多的人名、关键词
- insight 要具体深刻，不要泛泛而谈
- suggestions 要可执行，基于本周的模式给出
- 语气温暖真诚，像老朋友的周末复盘""")

    prompt = "\n".join(parts)

    response = call_deepseek([
        {"role": "system", "content": "你是一位温暖的生活观察者。从用户一周的碎片记录中发现模式和关联，帮助他看见自己。返回严格 JSON。"},
        {"role": "user", "content": prompt}
    ], max_tokens=1200, temperature=0.7)

    if not response:
        return None

    # 解析 JSON
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except Exception:
                pass
    _log(f"[weekly.review] AI 分析 JSON 解析失败: {text[:200]}")
    return None


def _build_weekly_review(period_str, start_date_str, analysis, data):
    """构建周回顾 Markdown"""
    mood_trend = analysis.get("mood_trend", [])
    mood_avg = analysis.get("mood_avg", "?")
    connections = analysis.get("connections", [])
    stats = analysis.get("stats", {})
    insight = analysis.get("insight", "")
    suggestions = analysis.get("suggestions", [])

    lines = [
        "---",
        "type: weekly-review",
        f"period: {period_str}",
        f"mood_avg: {mood_avg}",
        "generated: true",
        "---",
        "",
        f"# 📅 周回顾 · {period_str}",
        "",
    ]

    # 情绪曲线
    lines.extend([
        "## 🌡️ 情绪曲线",
        "",
        "| 日期 | 评分 | 来源 | 关键词 |",
        "|------|:----:|------|--------|",
    ])

    # 用 mood_scores 中的 source 补充
    score_map = {s.get("date"): s for s in data.get("mood_scores", [])}
    for item in mood_trend:
        d = item.get("date", "")
        score = item.get("score")
        keyword = item.get("keyword", "")
        # 匹配完整日期
        full_date = None
        for date_str in data.get("dates", []):
            if date_str.endswith(d) or d in date_str:
                full_date = date_str
                break
        source_info = score_map.get(full_date, {})
        source = source_info.get("source", "AI")
        score_str = str(score) if score is not None else "-"
        lines.append(f"| {d} | {score_str} | {source} | {keyword} |")

    # 找最高最低
    valid_scores = [item for item in mood_trend if item.get("score") is not None]
    if valid_scores:
        highest = max(valid_scores, key=lambda x: x["score"])
        lowest = min(valid_scores, key=lambda x: x["score"])
        lines.append("")
        lines.append(f"平均：{mood_avg} · 最高：{highest['date']}({highest['score']}) · 最低：{lowest['date']}({lowest['score']})")
    lines.append("")

    # 碎片连线
    if connections:
        lines.append("## 🔗 碎片连线")
        lines.append("")
        for i, conn in enumerate(connections, 1):
            title = conn.get("title", "")
            detail = conn.get("detail", "")
            lines.append(f"{i}. **{title}**：{detail}")
            lines.append("")

    # 数据统计
    lines.append("## 📊 数据统计")
    lines.append("")

    total_messages = stats.get("total_messages", 0)
    categories = stats.get("categories", {})
    top_people = stats.get("top_people", [])
    keywords = stats.get("keywords", [])

    lines.append(f"- 本周消息数：{total_messages} 条")
    if categories:
        cat_parts = [f"{_cat_label(k)} {v}" for k, v in categories.items()]
        lines.append(f"- 归档分类：{' · '.join(cat_parts)}")
    if top_people:
        people_parts = [f"{p['name']}({p['count']}次)" for p in top_people]
        lines.append(f"- 提及最多的人：{'、'.join(people_parts)}")
    if keywords:
        lines.append(f"- 关键词：{' · '.join(keywords)}")

    # 决策统计
    decision_stats = data.get("decision_stats", {})
    if decision_stats.get("total_decisions"):
        lines.append(f"- 互动次数：{decision_stats['total_decisions']} 次")

    lines.append("")

    # 本周洞察
    if insight:
        lines.extend([
            "## 💡 本周洞察",
            "",
            insight,
            "",
        ])

    # 下周建议
    if suggestions:
        lines.extend([
            "## 🎯 下周建议",
            "",
        ])
        for s in suggestions:
            lines.append(f"- [ ] {s}")
        lines.append("")

    # 尾部
    now_str = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M")
    lines.extend([
        "---",
        "",
        f"*🤖 基于 {total_messages} 条消息 + {len(data.get('mood_scores', []))} 天情绪数据自动生成于 {now_str}*",
    ])

    return "\n".join(lines)


def _cat_label(key):
    """归档分类 key → 中文标签"""
    labels = {"fun": "生活趣事", "emotion": "情感日记", "work": "工作笔记", "misc": "碎碎念"}
    return labels.get(key, key)


def _write_weekly_review(file_path, content):
    """写入周报文件（覆盖式，每周只生成一份）"""
    return OneDriveIO.write_text(file_path, content)


# Skill 热加载注册表
SKILL_REGISTRY = {
    "weekly.review": execute,
}
