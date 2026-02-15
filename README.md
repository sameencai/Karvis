# Karvis

运行在企业微信上的个人 AI 生活助手。

给 Karvis 发消息，它帮你记录生活、管理待办、每日复盘、情绪追踪、周报月报——所有数据都存在你自己手里。

## 它能做什么

- **消息记录**：文字、语音、图片、视频、链接 → 自动存档
- **智能分类**：自动归档到工作笔记/情感日记/生活趣事/碎碎念
- **链接解析**：分享链接自动抓取全文，回复基于内容理解
- **每日打卡**：4 个问题引导复盘，写入日记
- **待办管理**：自然语言增删查，支持截止日期和定时提醒
- **读书/影视笔记**：书摘、感想、AI 总结
- **情绪日记**：每天自动从消息中提取情绪，生成分析
- **周报/月报**：自动发现碎片关联，生成洞察
- **主动陪伴**：有事才发，没事不发（五层防骚扰）
- **语音日记**：长语音自动整理为结构化日记
- **主题深潜**：跨时间线搜索全历史，生成深度分析报告
- **财务管理**：iCost 数据导入、收支查询、资产快照、月报自动生成（LLM 洞察）

## 快速开始（10 分钟）

### Step 0：准备两样东西

**① DeepSeek API Key**（2 分钟）

1. 前往 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册（或 [腾讯云知识引擎 lkeap](https://console.cloud.tencent.com/lkeap)）
2. 创建 API Key，复制保存
3. 充值（日常约 0.5-2 元/天）

**② 企业微信自建应用**（5 分钟）

1. 前往 [企业微信管理后台](https://work.weixin.qq.com/) 注册（个人可注册，选「个人」类型，微信扫码即可）
2. 记下你的 **企业 ID**（Corp ID）：「我的企业」页面底部
3. 创建自建应用：管理后台 → 应用管理 → 自建 → 创建应用
4. 记下应用的 **AgentId**（详情页顶部）和 **Secret**（详情页 → 查看）
5. 配置「接收消息」：应用详情 → 接收消息 → 设置 API 接收
   - URL 先空着（等拿到公网地址再填）
   - **Token** 和 **EncodingAESKey**：点随机生成，**复制保存好**
6. 配置「企业可信IP」：应用详情页 → 企业可信IP → 填入你的**公网 IP**
   - 终端运行 `curl ifconfig.me` 获取
   - 换了网络环境需更新此 IP

> 到这里你应该有 6 个值：DeepSeek API Key、企业 ID、Agent ID、Secret、Token、EncodingAESKey

### Step 1：一键安装

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

> OneDrive 相关配置直接回车跳过，先用 Lite 模式体验。

### Step 2：配置企微回调

脚本启动成功后会显示一个公网 URL，类似：

```
https://example-words-here.trycloudflare.com
```

回到企微管理后台 → 你的应用 → 接收消息 → API 接收：
- **URL** 填：`https://你的公网地址/wework`（注意末尾加 `/wework`）
- Token 和 EncodingAESKey 就是 Step 0 中生成的
- 点击保存

### Step 3：发条消息试试！

打开企业微信 → 找到你创建的 Karvis 应用 → 发一条消息，比如「你好」。

如果一切正常，Karvis 会回复你 🎉

---

## 你的数据在哪里

Lite 模式下，所有数据都保存在项目根目录的 **`my_life/`** 文件夹：

```
my_life/
├── 00-Inbox/
│   ├── Quick-Notes.md          ← 你发的所有消息
│   └── Todo.md                 ← 待办事项
├── 01-Daily/                   ← 日记、周报、月报
├── 02-Notes/                   ← 归档笔记
│   ├── 读书笔记/
│   ├── 影视笔记/
│   ├── 情感日记/
│   ├── 工作笔记/
│   └── 生活趣事/
├── 03-Finance/                 ← 财务数据
│   ├── finance_data.json       ← 收支/资产/工资数据
│   ├── inbox/                  ← iCost 导入目录
│   └── reports/                ← 月报归档
└── _Karvis/
    ├── prompts/                ← AI 人设（可自定义）
    │   ├── SOUL.md             ← 性格、语气
    │   ├── RULES.md            ← 决策规则
    │   └── SKILLS.md           ← 技能列表
    ├── memory/
    │   └── memory.md           ← AI 的长期记忆
    └── logs/
        └── decisions.jsonl     ← 决策日志
```

> 想让 AI 更活泼？编辑 `my_life/_Karvis/prompts/SOUL.md`。
> 想同步到 Obsidian？配置 OneDrive 即可无缝切换，数据结构完全一致。

---

## 架构

```
企业微信 → /wework (Flask, 解密/去重/ASR)
    ↓ 异步转发
/process → brain.process()
    ├── 加载 State + Prompts（三级缓存）
    ├── 多模型路由 → JSON 决策
    │   ├── Flash (Qwen)  — 轻量任务
    │   ├── Main  (DeepSeek V3.2 thinking=off) — 日常路由
    │   └── Think (DeepSeek V3.2 thinking=on)  — 深度分析
    ├── Skill 分发 → 执行操作
    └── 写回 State + Memory + 决策日志

/system → 定时任务（内置调度器自动运行）
    ├── 晨报 / 晚间签到 / 日报
    ├── 情绪日记 / 周报 / 月报
    ├── 待办提醒 / 轻推检测
    ├── 主动陪伴检查（每 2 小时）
    ├── 财务月报（每月 8 号）
    └── 缓存刷新
```

---

## 其他安装方式

<details>
<summary>Docker 部署</summary>

```bash
git clone https://github.com/sameencai/Karvis.git
cd Karvis
cp .env.example src/.env
# 编辑 src/.env，填入 Step 0 准备好的配置
cd deploy
docker-compose up -d
```

Docker 启动后需自行配置内网穿透。

</details>

<details>
<summary>手动安装</summary>

```bash
git clone https://github.com/sameencai/Karvis.git
cd Karvis/src
pip install -r requirements.txt
cp ../.env.example .env
# 编辑 .env，填入 Step 0 准备好的配置
python app.py
```

手动启动后运行内网穿透：

```bash
cloudflared tunnel --url http://localhost:9000
```

</details>

---

## 两种运行模式

| 模式 | 数据存储 | 需要配置 | 适合 |
|---|---|---|---|
| **Lite 模式**（默认） | 本地 `my_life/` | DeepSeek Key + 企微 | 快速体验 |
| **完整模式** | OneDrive → Obsidian | 上面 + Azure AD + OneDrive | 数据永久同步到 Obsidian |

> **Lite 模式说明**：不配置 OneDrive 时自动启用。内置定时调度器自动运行，无需额外部署。
> 电脑需保持开机和网络连接。想 24/7 运行？参考下方「部署到腾讯云 SCF」。

---

## 进阶配置

> 以下内容面向想使用完整功能的用户。只是体验 Lite 模式的话，上面就够了。

### 部署到腾讯云 SCF（生产环境）

本地运行适合体验，生产使用建议部署到腾讯云 SCF（免费额度足够个人使用）：

1. 在 [腾讯云 SCF 控制台](https://console.cloud.tencent.com/scf) 创建 **Web 函数**（Python 3.9，256MB 内存，180s 超时）
2. 上传 `src/` 目录下所有文件
3. 在函数配置 → 环境变量中填入 `.env` 中的所有变量
4. 部署后获得公网 URL，填入 `PROCESS_ENDPOINT_URL` 环境变量
5. 配置企微回调 URL 指向 SCF 的 `/wework` 路径
6. 另外创建 **Event 函数**（上传 `deploy/scheduler/` 目录），配置定时触发器

### 企业微信详细配置

<details>
<summary>展开查看</summary>

**第一步：注册企业微信**

1. 前往 [企业微信管理后台](https://work.weixin.qq.com/) 注册
2. 个人也可注册——选「个人」类型，微信扫码即可
3. 记下 **企业 ID**（Corp ID）：「我的企业」页面底部

**第二步：创建自建应用**

1. 管理后台 → 应用管理 → 自建 → 创建应用
2. 填写应用名称（如 "Karvis"），上传 logo，选择可见范围
3. 记下 **AgentId**（详情页顶部）和 **Secret**（详情页 → 查看）

**第三步：配置消息接收**

1. 应用详情页 → 接收消息 → 设置 API 接收
2. 填入公网 URL + `/wework`
3. 自定义 **Token** 和 **EncodingAESKey**（点随机生成）
4. 保存后企微会发验证请求，Karvis 会自动通过

**对应的环境变量：**

```bash
WEWORK_CORP_ID=ww1234567890abcdef     # 企业 ID
WEWORK_AGENT_ID=1000003                # 应用 AgentId
WEWORK_CORP_SECRET=your-app-secret     # 应用 Secret
WEWORK_TOKEN=your-callback-token       # 接收消息的 Token
WEWORK_ENCODING_AES_KEY=your-aes-key   # 接收消息的 EncodingAESKey
```

</details>

### OneDrive 配置（Obsidian 同步）

<details>
<summary>展开查看</summary>

Karvis 通过 Microsoft Graph API 读写 OneDrive 上的 Obsidian Vault。

**注册 Azure 应用**

1. 前往 [Azure App 注册](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. 新注册 → 名称如 "Karvis OneDrive"
3. 账户类型：「任何组织目录中的帐户和个人 Microsoft 帐户」
4. 重定向 URI：`https://login.microsoftonline.com/common/oauth2/nativeclient`
5. 记下 **Application (client) ID**

**配置 API 权限**

1. API 权限 → 添加权限 → Microsoft Graph → 委托的权限
2. 添加：`Files.ReadWrite`、`offline_access`

**获取 Refresh Token**

1. 浏览器打开（替换 `{CLIENT_ID}`）：
   ```
   https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id={CLIENT_ID}&response_type=code&redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient&scope=Files.ReadWrite%20offline_access
   ```
2. 登录授权后，浏览器跳转到带 `code=xxx` 的 URL，复制 code
3. 换取 refresh_token：
   ```bash
   curl -X POST https://login.microsoftonline.com/common/oauth2/v2.0/token \
     -d "client_id={CLIENT_ID}" \
     -d "code={AUTH_CODE}" \
     -d "redirect_uri=https://login.microsoftonline.com/common/oauth2/nativeclient" \
     -d "grant_type=authorization_code" \
     -d "scope=Files.ReadWrite offline_access"
   ```

**配置 Client Secret**

1. 证书和密码 → 新客户端密码 → 添加
2. 记下密码值

```bash
ONEDRIVE_CLIENT_ID=your-client-id
ONEDRIVE_CLIENT_SECRET=your-secret
ONEDRIVE_REFRESH_TOKEN=your-refresh-token
OBSIDIAN_BASE=/应用/remotely-save/YourVault
```

</details>

### 可选服务

<details>
<summary>阿里云百炼 Qwen（主动陪伴功能）</summary>

```bash
QWEN_API_KEY=sk-xxxxxxxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus-latest
```

不配则主动陪伴降级到 DeepSeek。任何兼容 OpenAI API 的模型都可替代。

</details>

<details>
<summary>腾讯云 ASR（语音识别）</summary>

```bash
TENCENT_APPID=1234567890
TENCENT_SECRET_ID=AKIDxxxxxxxx
TENCENT_SECRET_KEY=xxxxxxxx
```

不配则语音功能不可用。每月 10 小时免费。

</details>

<details>
<summary>心知天气（晨报天气）</summary>

```bash
SENIVERSE_KEY=your-api-key
WEATHER_CITY=深圳
```

不配则晨报跳过天气信息。

</details>

---

## 项目结构

```
Karvis/
├── README.md                # 你在看的这个
├── setup.sh                 # 一键安装脚本
├── .env.example             # 配置模板
│
├── src/                     # 源码
│   ├── app.py               # Flask 网关
│   ├── brain.py             # 核心大脑（多模型路由 → LLM → Skill 分发）
│   ├── memory.py            # 记忆管理
│   ├── config.py            # 统一配置
│   ├── storage.py           # 存储接口（自动选择 OneDrive / 本地）
│   ├── local_io.py          # 本地存储
│   ├── onedrive_io.py       # OneDrive 存储
│   ├── wework_crypto.py     # 企微消息加解密
│   ├── skill_loader.py      # Skill 热加载
│   ├── finance_utils.py     # 财务数据工具
│   ├── prompts_example/     # Prompt 模板（首次启动时复制到 my_life/）
│   └── skills/              # 技能模块（19 个）
│
├── my_life/                 # 你的数字生活（自动生成，不上传 GitHub）
│   ├── 00-Inbox/            # 收件箱
│   ├── 01-Daily/            # 日记
│   ├── 02-Notes/            # 归档笔记
│   └── _Karvis/             # AI 配置与记忆
│
├── deploy/                  # 部署文件（高级用户）
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── scf_bootstrap
│   └── scheduler/           # SCF 定时调度器
│
├── docs/                    # 开发者文档
└── assets/                  # 截图等资源
```

## 新增 Skill

1. 在 `src/skills/` 下创建 `your_skill.py`
2. 末尾声明 `SKILL_REGISTRY = {"your.skill": handler_fn}`
3. 更新 `my_life/_Karvis/prompts/SKILLS.md` 和 `RULES.md`
4. 重启 Karvis 即可

无需修改 `brain.py`，skill_loader 会自动发现。

## 自定义 AI 人设

编辑 `my_life/_Karvis/prompts/` 下的三个文件：

- **SOUL.md** — AI 的性格（称呼、语气、态度）
- **RULES.md** — 决策规则（什么消息触发什么技能）
- **SKILLS.md** — 技能清单（有哪些技能可用）

> 改 Prompt 就能改变 80% 的行为，不需要改代码。

---

## License

[MIT](LICENSE)
