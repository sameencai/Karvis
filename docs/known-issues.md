---
tags: [karvis, issues]
updated: 2026-02-12
---

# Karvis — 已知问题与迭代方向

## 已修复

| ID | 问题 | 修复方式 |
|----|------|----------|
| I-001 | LLM 不触发 memory_updates | RULES.md 加强记忆管理规则 |
| I-002 | SOUL.md 硬编码身份信息 | 改为框架式引用，个人信息统一到 memory.md |
| I-004 | apply_memory_updates 无去重 | add 前检查关键词是否已存在 |
| I-005 | memory_updates 不支持 delete | 新增 delete action |
| I-008 | 用户消息可能无回复 | brain.py 兜底 + RULES.md 规则双保险 |
| I-009 | scheduler 变量名不一致导致定时任务全部失败 | `index.py` 中 `JARVIS_SYSTEM_URL` → `KARVIS_SYSTEM_URL` |
| I-010 | media.create/book.create 已有文件时丢弃 thought 内容 | 代码自动转发 thought() + RULES.md 双保险（DD-016） |

## 待观察

| ID | 优先级 | 问题 | 备注 |
|----|--------|------|------|
| I-003 | P3 | memory.md 缓存延迟：手动编辑后 30 分钟内不生效 | 定时器每 30 分钟刷新；可手动 curl refresh_cache |
| I-006 | P3 | 短期记忆丢失风险 | state 写入失败时 recent_messages 丢失，已加重试缓解 |
| I-007 | P3 | 旧 state 中 role="jarvis" 兼容 | 显示时统一映射为 "Karvis" |

## 已实现的规划

| ID | 描述 |
|----|------|
| F-001 | 定时推送：scheduler + /system endpoint + check_reminders 直接调用 |
| F-002 | SOUL.md 去硬编码 |
| F-003 | 记忆 add 去重 |
| F-004 | 记忆 delete 支持 |
| O-001 | 响应速度优化：state 三级缓存（内存→/tmp→OneDrive, TTL 5min）+ 先回复后保存（send_fn callback） |
| O-002 | 闲聊能力：RULES.md 新增"闲聊与日常互动"规则，`skill=ignore` 时 LLM 生成自然回复 |
| O-003 | 决策日志：每次决策追加 JSONL 到 `logs/decisions.jsonl`，含 thinking/skill/reply/elapsed |
| O-004 | 对话压缩：超过 10 条时将旧消息压缩为 `[对话摘要]`，保留最近 4 条原始消息 |
| O-007 | 定时推送上下文注入：/system 端点读取 Todo.md + Quick-Notes.md 注入 payload.context |
| O-010 | Skill 热加载：各模块声明 SKILL_REGISTRY + skill_loader.py 自动扫描注册 |
| DD-009 | Quick-Notes 统一收件箱：所有消息先写 Quick-Notes，再可选 classify.archive 归档 |
| DD-015 | OneDrive 路径迁移：支持 remotely-save 手机同步 |
| DD-016 | media.create/book.create 已有文件自动转发 thought，防止数据丢失 |
| V2-F1 | 情绪日记（mood.generate）：每天 22:00 从当天消息自动提取情绪，生成结构化分析 |
| V2-F2 | 人际关系动态追踪：RULES.md 增强，提到重要的人时自动更新 memory.md 关系动态 |
| V2-F3 | 时间胶囊：morning_report 注入 7/30/365 天前历史数据 |
| V2-F7 | 情境感知回应：RULES.md 增强，闲聊时参考人际动态和 mood_scores 给出有温度的回复 |
| V2-F8 | 打卡数据深度利用：mood_scores 融入情绪日记、打卡评分优先于 AI 推断 |
| V2-F4 | 碎片连线+周报：每周日自动从 7 天数据中发现模式关联，生成周回顾 |
| V2-F5 | 轻推系统（nudge）：沉默检测、情绪跟进、连续记录鼓励；morning_report/evening_checkin 注入 nudge 信号 + 独立 nudge_check(14:00) |
| V2-F6 | 月度成长回顾：每月末自动汇总情绪曲线、人际变化、高光低谷、成长洞察 |
| V3-F12 | 每日 Top 3（Intention Setting）：morning_report 引导设定 → state.daily_top3 存储 → evening_checkin 回顾完成情况 → brain.py 状态摘要展示 |
| V3-F13 | 外部信息流（天气）：心知天气 API → morning_report 注入 context.weather → RULES.md 引导自然融入问候 |
| V3-F11 | 习惯干预系统：微习惯实验框架 → habit.propose/nudge/status/complete → 触发检测+追踪+周一提议 |
| V3-F15 | 决策复盘系统：decision.record/review/list → 记录决策 → 到期 morning_report 注入 → 复盘闭环 |
| V3-F14 | 语音日记（voice.journal）：长语音(>200字) ASR 文本 → LLM 二次分析（主题/情绪/事件/人物/洞察）→ 结构化日记写入 `02-Notes/语音日记/` |
| V3-F16 | 主题深潜（deep.dive）：跨时间线搜索全历史数据（Quick-Notes+归档+memory+决策日志）→ LLM 生成深度分析报告 |
| V3-F10 | 对话式任务 Agent Loop：brain.py 多轮循环（最多5轮）+ internal.read/search/list 内部工具 + LLM `continue` 字段控制 |
| 0212-F1 | 链接内容解析：HTTP 抓取 + BeautifulSoup 解析网页正文（微信文章/通用网页），纯 URL 文本自动检测，失败优雅降级（DD-018） |
| 0212-F2 | 主动陪伴系统：companion_check 每 2h 智能检查，五层防骚扰（安静时间/近期互动/推送间隔/每日上限/无信号跳过），Flash LLM 生成关怀消息（DD-019） |
| 0212-F3 | 三层多模型路由：Flash(Qwen Flash) + Main(DeepSeek V3.2 thinking=off) + Think(DeepSeek V3.2 thinking=on)，统一 `call_llm()` 入口 + Flash 降级兜底（DD-017） |
| DD-003-v2 | DeepSeek 模型回归 V3.2：利用 `enable_thinking` 参数按需控制思维链，thinking=off 速度持平 V3-0324 但输出价格降 62%（DD-003 修订） |

## 优化迭代方向

### P1 — 功能增强

| ID | 方向 | 说明 | 复杂度 |
|----|------|------|:------:|
| O-005 | **图片理解** | 当前图片只是存附件，LLM 看不到图片内容。可接入多模态模型（DeepSeek-VL）对图片做描述，再传给路由 LLM | 中 |
| O-006 | **语音识别优化** | ASR 纠偏目前靠 LLM。可以在 ASR 层加置信度过滤：低置信度时自动降级到一句话识别，减少 LLM 纠偏负担 | 低 |

### P2 — 架构演进

| ID | 方向 | 说明 | 复杂度 |
|----|------|------|:------:|
| O-008 | **OneDrive → 本地 DB** | OneDrive 网络是最大瓶颈。高频读写的 state.json 可以迁移到 COS/Redis/云数据库，只保留笔记文件在 OneDrive（给 Obsidian 用） | 高 |
| O-009 | **Prompt 工程自动化** | 当前 RULES.md 手写维护。可以构建一个 RULES 测试框架：输入样本消息 → 验证 LLM 输出是否符合预期 skill/params | 中 |
| O-011 | **多用户支持** | 当前硬编码 DEFAULT_USER_ID，所有数据共享同一套文件。如果要给其他人用，需要 user_id → 独立 state/memory 的映射 | 高 |
