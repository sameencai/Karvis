# Karvis
git clone → ./setup.sh → 填几个 Key → y 启动
→ 自动获得公网 URL → 复制到企微后台 → 开始用
运行在企业微信上的个人 AI 生活助手。后端 DeepSeek LLM + Qwen Flash 多模型架构，数据存储在你自己的 Obsidian Vault（OneDrive 同步）。

## 它能做什么

- **消息记录**：文字、语音、图片、视频、链接 → 自动存入 Obsidian
- **智能分类**：自动归档到工作笔记/情感日记/生活趣事/碎碎念
- **链接内容解析**：分享链接自动抓取网页正文，回复基于全文理解而非标题猜测
- **每日打卡**：4 个问题引导复盘，写入 Daily Note
- **待办管理**：自然语言增删查，支持截止日期和定时提醒
- **读书/影视笔记**：书摘、感想、AI 总结
- **情绪日记**：每天自动从消息中提取情绪，生成结构化分析
- **周报/月报**：自动发现碎片关联，生成洞察
- **主动陪伴**：智能关怀推送——有事才发，没事不发（五层防骚扰机制）
- **轻推系统**：沉默检测、情绪跟进、连续记录鼓励
- **习惯干预**：微习惯实验框架
- **决策复盘**：记录 → 到期提醒 → 回顾闭环
- **语音日记**：长语音自动整理为结构化日记
- **主题深潜**：跨时间线搜索全历史数据，生成深度分析报告
- **Agent Loop**：多轮自主搜索+分析（LLM 驱动的内部工具链）

## 架构

```
企业微信 → /wework (Flask, 解密/去重/ASR)
    ↓ 异步转发
/process → brain.process()
    ├── 加载 State + Prompts（三级缓存）
    ├── 多模型路由 → JSON 决策
    │   ├── Flash (Qwen)  — 轻量任务（陪伴推送）
    │   ├── Main  (DeepSeek V3.2 thinking=off) — 日常路由
    │   └── Think (DeepSeek V3.2 thinking=on)  — 深度分析
    ├── Skill 分发 → 执行操作
    └── 写回 State + Memory + 决策日志

/system → 定时任务
    ├── 晨报 / 晚间签到 / 日报
    ├── 情绪日记 / 周报 / 月报
    ├── 待办提醒 / 轻推检测
    ├── 主动陪伴检查（每 2 小时）
    └── 缓存刷新
```

## 快速开始（10 分钟上手）

Karvis 支持两种运行模式，新用户推荐 **Lite 模式**，只需 DeepSeek Key + 企微即可跑起来：

| 模式 | 数据存储 | 需要配置 | 适合 |
|---|---|---|---|
| **Lite 模式**（推荐新手） | 本地文件 `data/` | DeepSeek Key + 企微 | 快速体验，10 分钟部署 |
| **完整模式** | OneDrive → Obsidian | 上面 + Azure AD + OneDrive | 数据永久同步到 Obsidian |

### Step 0：准备两样东西

在动手之前，先准备好这两样：

**① DeepSeek API Key**（2 分钟）

1. 前往 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册
2. 创建 API Key，复制保存
3. 充值（日常使用约 0.5-2 元/天）

**② 企业微信自建应用**（5 分钟）

1. 前往 [企业微信管理后台](https://work.weixin.qq.com/) 注册（个人也可以注册，选「个人」类型，微信扫码即可）
2. 记下你的 **企业 ID**（Corp ID）：「我的企业」页面底部
3. 创建自建应用：管理后台 → 应用管理 → 自建 → 创建应用
4. 记下应用的 **AgentId**（详情页顶部）和 **Secret**（详情页 → 查看）
5. 配置「接收消息」：应用详情 → 接收消息 → 设置 API 接收
   - URL 先空着（等下一步拿到公网地址再填）
   - **Token** 和 **EncodingAESKey**：点随机生成，**复制保存好**

> 到这里你应该有 6 个值：DeepSeek API Key、企业 ID、Agent ID、Secret、Token、EncodingAESKey

### Step 1：克隆项目 & 一键安装

```bash
git clone https://github.com/sameencai/Karvis.git
cd Karvis
chmod +x setup.sh
./setup.sh
```

脚本会引导你完成：
- ✅ 检查 Python 环境
- ✅ 安装依赖
- ✅ 交互式填写配置（把 Step 0 准备好的值粘贴进去）
- ✅ 自动安装内网穿透工具 (cloudflared)
- ✅ 启动 Karvis + 生成公网 URL

> **Tips**：OneDrive 相关配置直接回车跳过即可，Lite 模式不需要。

### Step 2：配置企微回调

脚本启动成功后，会显示一个公网 URL，类似：

```
https://example-words-here.trycloudflare.com
```

回到企微管理后台 → 你的应用 → 接收消息 → API 接收：
- **URL** 填：`https://你的公网地址/wework`（注意末尾加 `/wework`）
- Token 和 EncodingAESKey 就是 Step 0 中生成的那两个
- 点击保存（企微会发验证请求，Karvis 会自动通过）

### Step 3：发条消息试试！

打开企业微信 → 找到你创建的 Karvis 应用 → 发一条消息，比如「你好」。

如果一切正常，Karvis 会回复你 🎉

### 其他安装方式

<details>
<summary>Docker 部署</summary>

```bash
git clone https://github.com/sameencai/Karvis.git
cd Karvis
cp .env.example cloud_function/.env
# 编辑 cloud_function/.env，填入 Step 0 准备好的配置
docker-compose up -d
```

Docker 启动后还需要自行配置内网穿透（见下方说明）。

</details>

<details>
<summary>手动安装</summary>

```bash
git clone https://github.com/sameencai/Karvis.git
cd Karvis/cloud_function
pip install -r requirements.txt
cp ../.env.example .env
# 编辑 .env，填入 Step 0 准备好的配置
python app.py
```

手动启动后还需要自行运行内网穿透：

```bash
# 推荐 cloudflared（免注册、免配置）
cloudflared tunnel --url http://localhost:9000

# 或者 ngrok / frp 等其他工具
```

</details>

> **关于 Lite 模式**：不配置 OneDrive 时自动启用，笔记保存在 `cloud_function/data/` 目录。内置定时调度器自动运行，无需单独部署 scheduler。随时可以配置 OneDrive 无缝切换到完整模式。
>
> **关于本地运行**：Lite 模式需要电脑保持开机和网络连接。想要 24/7 稳定运行？参考下方「部署到腾讯云 SCF」章节。

### 前置条件汇总

**必须**：
1. **Python 3.9+**（macOS/Linux 通常自带，`python3 --version` 检查）
2. **[DeepSeek](https://platform.deepseek.com/) API Key**（注册即送额度）
3. **[企业微信](https://work.weixin.qq.com/) 自建应用**（个人也可注册，免费）

**可选**（增强功能，先跳过也没关系）：
- [阿里云百炼](https://bailian.console.aliyun.com/) Qwen API — 主动陪伴功能，留空则降级到 DeepSeek
- [腾讯云 ASR](https://console.cloud.tencent.com/asr) — 语音识别，留空则语音功能不可用
- [心知天气](https://www.seniverse.com/) API — 晨报天气信息，留空则跳过
- OneDrive + Azure AD — 数据同步到 Obsidian，建议体验 Lite 模式后再配

---

## 详细配置指南

> 以下内容面向想使用完整功能（OneDrive 同步、腾讯云部署）的用户。如果只是想先体验 Lite 模式，上面的「快速开始」就够了。

### 部署到腾讯云 SCF（生产环境推荐）

本地运行适合体验，但生产使用建议部署到腾讯云 SCF（免费额度足够个人使用）：

1. 在 [腾讯云 SCF 控制台](https://console.cloud.tencent.com/scf) 创建 **Web 函数**（Python 3.9，128-256MB 内存，180s 超时）
2. 上传 `cloud_function/` 目录下所有文件
3. 在函数配置 → 环境变量中填入 `.env` 中的所有变量
4. 部署后获得公网 URL，填入 `PROCESS_ENDPOINT_URL` 环境变量
5. 配置企微回调 URL 指向 SCF 的 `/wework` 路径
6. 另外创建 **Event 函数**（上传 `scheduler/` 目录），配置定时触发器

> **费用提示**：SCF 免费额度 = 每月 40 万 GBs + 100 万次调用，个人使用远远够。

---

### 企业微信（WeChat Work）

Karvis 通过企业微信的「自建应用」接收和发送消息。

**第一步：注册企业微信**

1. 前往 [企业微信管理后台](https://work.weixin.qq.com/) 注册
2. 个人用也可以注册——选择「个人」类型，只需微信扫码即可
3. 注册后记下你的 **企业 ID**（Corp ID），在「我的企业」页面底部

**第二步：创建自建应用**

1. 管理后台 → 应用管理 → 自建 → 创建应用
2. 填写应用名称（如 "Karvis"），上传 logo，选择可见范围
3. 创建后记下：
   - **AgentId**：应用详情页顶部
   - **Secret**：应用详情页 → 查看 Secret

**第三步：配置消息接收**

1. 应用详情页 → 接收消息 → 设置 API 接收
2. 填入你的 SCF 公网 URL + `/wework`（如 `https://xxx.tencentscf.com/wework`）
3. 自定义 **Token** 和 **EncodingAESKey**（点击随机生成）
4. 保存后企微会发一个验证请求，你的 `/wework` GET 端点需要正确返回

**对应的环境变量：**

```bash
WEWORK_CORP_ID=ww1234567890abcdef     # 企业 ID
WEWORK_AGENT_ID=1000003                # 应用 AgentId
WEWORK_CORP_SECRET=your-app-secret     # 应用 Secret
WEWORK_TOKEN=your-callback-token       # 接收消息的 Token
WEWORK_ENCODING_AES_KEY=your-aes-key   # 接收消息的 EncodingAESKey
```

> **提示**：如果你是企业管理员，可以在「可信域名」和「可信 IP」中添加 SCF 的 IP 段。个人用户一般不需要。

---

### 腾讯云（SCF 云函数 + ASR 语音识别）

Karvis 部署在腾讯云 SCF（Serverless Cloud Function），语音识别用腾讯云 ASR。

**SCF 部署**

1. 前往 [腾讯云 SCF 控制台](https://console.cloud.tencent.com/scf)
2. 创建 **Web 函数**：
   - 运行环境：Python 3.9
   - 内存：128MB（推荐 256MB）
   - 超时：180 秒（部分功能如 book.summary 需要较长时间）
   - 触发方式：API 网关触发
3. 上传 `cloud_function/` 目录下所有文件
4. 在函数配置 → 环境变量中填入 `.env` 中的所有变量
5. 部署后获得公网 URL（如 `https://service-xxx.gz.tencentscf.com`）
6. 将此 URL + `/process` 填入 `PROCESS_ENDPOINT_URL` 环境变量

**定时调度器（Scheduler）**

1. 另外创建一个 **Event 函数**（参考 `scheduler/` 目录）
2. 上传 `scheduler/` 下的代码
3. 在环境变量中设置 `KARVIS_SYSTEM_URL` = 你的主函数 URL + `/system`
4. 配置定时触发器（参考 `scheduler/serverless.yml` 中的 cron 表达式）

**ASR 语音识别（可选但推荐）**

1. 前往 [腾讯云 ASR 控制台](https://console.cloud.tencent.com/asr) 开通服务
2. 创建 API 密钥：[访问密钥管理](https://console.cloud.tencent.com/cam/capi)
3. 记下 **APPID**（账号信息页）、**SecretId**、**SecretKey**

```bash
TENCENT_APPID=1234567890               # 腾讯云 APPID
TENCENT_SECRET_ID=AKIDxxxxxxxx         # API SecretId
TENCENT_SECRET_KEY=xxxxxxxx            # API SecretKey
```

> **费用提示**：SCF 免费额度 = 每月 40 万 GBs + 100 万次调用，个人使用远远够。ASR 每月 10 小时免费额度。

---

### DeepSeek API（主力模型）

DeepSeek V3.2 是 Karvis 的主力 LLM，负责消息路由、报告生成、对话互动。

1. 前往 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册
2. 创建 API Key
3. 充值（日常使用约 0.5-2 元/天）

```bash
DEEPSEEK_API_KEY=sk-xxxxxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v3.2
```

**替代方案**：如果你使用腾讯云 lkeap（知识引擎）等兼容 OpenAI API 的平台，只需修改 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_API_KEY` 即可。任何兼容 OpenAI Chat Completions 接口的模型都可以接入。

---

### 阿里云百炼（Qwen Flash，轻量模型）

Qwen Flash 用于主动陪伴消息生成等轻量任务，响应快（1-3s）、成本低。

1. 前往 [阿里云百炼](https://bailian.console.aliyun.com/) 开通服务
2. 创建 API Key：控制台 → API Keys → 创建
3. 选择模型：推荐 `qwen-plus-latest`（兼顾速度和质量）

```bash
QWEN_API_KEY=sk-xxxxxxxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus-latest
```

> **可选**：如果不配置 Qwen，主动陪伴功能会自动降级到 DeepSeek（稍慢但仍可用）。

> **替代方案**：任何兼容 OpenAI API 的轻量模型都可以替代 Qwen Flash，只需修改以上三个变量。

---

### OneDrive（Obsidian Vault 存储）

Karvis 通过 Microsoft Graph API 读写 OneDrive 上的 Obsidian Vault。

**注册 Azure 应用**

1. 前往 [Azure App 注册](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. 新注册 → 填写名称（如 "Karvis OneDrive"）
3. 受支持的账户类型：「任何组织目录中的帐户和个人 Microsoft 帐户」
4. 重定向 URI：`https://login.microsoftonline.com/common/oauth2/nativeclient`
5. 记下 **Application (client) ID**

**配置 API 权限**

1. 应用详情 → API 权限 → 添加权限 → Microsoft Graph → 委托的权限
2. 添加：`Files.ReadWrite`、`offline_access`
3. 点击「代表 xxx 授予管理员同意」（如果有权限的话）

**获取 Refresh Token**

1. 在浏览器中打开授权 URL（替换 `{CLIENT_ID}`）：
   ```
   https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient&scope=Files.ReadWrite%20offline_access
   ```
2. 登录并授权后，浏览器会跳转到一个带 `code=xxx` 的 URL，复制 code
3. 用 code 换取 refresh_token：
   ```bash
   curl -X POST https://login.microsoftonline.com/common/oauth2/v2.0/token \
     -d "client_id={CLIENT_ID}" \
     -d "code={AUTH_CODE}" \
     -d "redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient" \
     -d "grant_type=authorization_code" \
     -d "scope=Files.ReadWrite offline_access"
   ```
4. 响应中的 `refresh_token` 就是你需要的

**配置 Client Secret**

1. 应用详情 → 证书和密码 → 新客户端密码 → 添加
2. 记下生成的 **密码值**（只显示一次！）

```bash
ONEDRIVE_CLIENT_ID=your-azure-app-client-id
ONEDRIVE_CLIENT_SECRET=your-azure-app-secret
ONEDRIVE_REFRESH_TOKEN=your-refresh-token
OBSIDIAN_BASE=/应用/remotely-save/YourVault   # OneDrive 上的 Vault 路径
```

> **Vault 路径**：这是你的 Obsidian Vault 在 OneDrive 上的路径。如果你用 remotely-save 插件同步，路径通常是 `/应用/remotely-save/你的Vault名`。可以在 OneDrive 网页版中查看实际路径。

---

### 心知天气（可选）

用于晨报中注入天气信息。

1. 前往 [心知天气](https://www.seniverse.com/) 注册（免费版即可）
2. 控制台 → 产品管理 → 复制 API Key

```bash
SENIVERSE_KEY=your-api-key
WEATHER_CITY=北京                       # 你所在的城市
```

---

## 目录结构

```
karvis/
├── setup.sh                  # 一键安装脚本
├── Dockerfile                # Docker 构建文件
├── docker-compose.yml        # Docker Compose 配置
├── cloud_function/           # 主函数代码
│   ├── app.py                # Flask 网关（消息接收/ASR/链接解析/陪伴检查/内置调度器）
│   ├── brain.py              # 核心大脑：多模型路由 → LLM → Skill 分发
│   ├── memory.py             # 记忆管理：缓存 + 压缩 + CRUD
│   ├── config.py             # 统一配置（环境变量）
│   ├── storage.py            # 统一存储接口（自动选择 OneDrive / 本地）
│   ├── onedrive_io.py        # OneDrive Graph API 读写
│   ├── local_io.py           # 本地文件读写（Lite 模式）
│   ├── skill_loader.py       # Skill 热加载器
│   ├── wework_crypto.py      # 企微消息加解密
│   ├── requirements.txt
│   ├── scf_bootstrap         # SCF 启动脚本
│   └── skills/               # 技能模块（14 个）
│       ├── note_save.py
│       ├── checkin_flow.py
│       ├── todo_manage.py
│       ├── classify_archive.py
│       ├── daily_report.py
│       ├── book_notes.py
│       ├── media_notes.py
│       ├── mood_diary.py
│       ├── weekly_review.py
│       ├── monthly_review.py
│       ├── habit_coach.py
│       ├── decision_track.py
│       ├── voice_journal.py
│       ├── deep_dive.py
│       └── internal_ops.py
├── scheduler/                # 定时调度器（SCF Event 函数，Lite 模式不需要）
├── prompts/                  # Prompt 模板
│   ├── SOUL.md.example
│   ├── SKILLS.md.example
│   └── RULES.md.example
├── docs/                     # 设计文档
├── .env.example
├── .gitignore
└── LICENSE
```

## 新增 Skill

1. 在 `cloud_function/skills/` 下创建 `your_skill.py`
2. 末尾声明 `SKILL_REGISTRY = {"your.skill": handler_fn}`
3. 更新 OneDrive 上的 `SKILLS.md`（描述参数）和 `RULES.md`（触发规则）
4. 部署代码，等缓存刷新或手动 `curl /system -d '{"action":"refresh_cache"}'`

无需修改 `brain.py`，skill_loader 会自动发现。

## 技术细节

- **三层多模型路由**：Flash（Qwen，轻量任务）/ Main（DeepSeek V3.2 thinking=off，日常路由）/ Think（DeepSeek V3.2 thinking=on，深度分析）
- **三级缓存**：内存 → /tmp → OneDrive（Prompt TTL 30min，State TTL 5min）
- **先回复后保存**：LLM 决策完成后先发送回复，再写入 State/Memory
- **对话压缩**：短期记忆超过 10 条时自动压缩为摘要
- **Agent Loop**：LLM 通过 `continue: true` 触发多轮自主分析（最多 5 轮）
- **决策日志**：每次 LLM 决策记录到 JSONL，便于调试和审查
- **主动陪伴**：五层防骚扰（安静时间/近期互动/推送间隔/每日上限/无信号跳过），Flash 模型生成关怀消息
- **链接内容解析**：HTTP 抓取 + BeautifulSoup，支持微信文章/通用网页，失败优雅降级

详见 [docs/设计决策.md](docs/设计决策.md)。

---

## Vibe Coding 注意事项

> Vibe Coding（氛围编程）是指用自然语言向 AI 描述需求，AI 生成代码的开发方式。如果你不是程序员但想基于 Karvis 做二次开发，以下是一些实用建议。

### 什么是 Vibe Coding

[Andrej Karpathy 提出的概念](https://x.com/karpathy/status/1886192184808149383)：你像产品经理一样描述"我想要什么"，AI 工具（如 Cursor、Claude）帮你写代码。不需要你精通编程语言，但需要你会「把需求说清楚」。

### 推荐工具

- [Cursor](https://cursor.com/) — 最流行的 AI 编程 IDE，支持对话式开发
- [Claude](https://claude.ai/) — 适合讨论架构设计、理解代码逻辑
- [Windsurf](https://codeium.com/windsurf) — 类似 Cursor 的替代品

### 开发 Karvis 的建议

**1. 先理解架构再动手**

把 `docs/项目概览.md` 和 `docs/设计决策.md` 喂给 AI，让它先理解整个项目。不要上来就让 AI 改代码——它需要先知道"为什么这样设计"。

**2. 改 Prompt 优先于改代码**

Karvis 的大部分行为由三个 Prompt 文件控制：
- `SOUL.md` — AI 的人设（性格、称呼、语气）
- `RULES.md` — 决策规则（什么消息触发什么 skill）
- `SKILLS.md` — 技能列表（有哪些 skill 可用）

想让 Karvis 改变行为？**先改 Prompt 试试**，80% 的需求不需要改代码。例如：
- 想让 AI 更活泼 → 改 `SOUL.md`
- 想让 AI 对某类消息做不同处理 → 改 `RULES.md`
- 想新增一个技能的触发条件 → 改 `SKILLS.md` + `RULES.md`

**3. 新增 Skill 是最安全的扩展方式**

如果确实需要新功能：
1. 描述需求："帮我创建一个新 skill，功能是 xxx，参数是 yyy"
2. 让 AI 参考现有 skill（如 `note_save.py`）的写法
3. AI 会在 `skills/` 下生成新文件，不会改动核心代码

**4. 不要轻易改这些文件**

- `brain.py` — 核心路由引擎，改错了整个系统瘫痪
- `memory.py` — 记忆管理，改错了可能丢数据
- `storage.py` / `onedrive_io.py` / `local_io.py` — 存储层，改错了文件读写全挂

如果非要改，先让 AI 解释现有代码，确认理解后再动手。改完后用 `docs/测试指南.md` 中的测试用例验证。

**5. 环境变量别写死在代码里**

所有密钥和配置都通过环境变量传入（见 `.env.example`）。如果 AI 在代码里硬编码了 API Key 或 URL，立刻要求它改成 `os.environ.get()`。

**6. 每次只改一个功能**

AI 很容易"过度热情"地一次改很多文件。明确告诉它："只改 xxx，其他文件不要动"。改完测试通过再做下一个。

**7. 善用文档作为上下文**

把以下文件喂给你的 AI 编程工具：
- `docs/项目概览.md` — 全景了解
- `docs/设计决策.md` — 理解为什么这样做
- `docs/测试指南.md` — 知道怎么验证改动
- `.env.example` — 知道有哪些配置项

**8. 调试的正确姿势**

遇到问题时，把 SCF 日志（或终端输出）的错误信息直接贴给 AI，它通常能定位原因。Karvis 的日志设计得很详细（每个模块都有 `[模块名]` 前缀），方便追踪。

---

## License

[MIT](LICENSE)
