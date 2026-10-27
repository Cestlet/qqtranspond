# 📨 QQ空间动态转发 + 点赞 + 评论 工具

自动监控指定 QQ 用户（或群内所有人）的 QQ 空间动态，通过关键词筛选后，自动执行 **转发 / 点赞 / 评论**。

## 功能特性

- 🔍 **定时监控** — 轮询指定 QQ 用户的最新说说
- 📱 **扫码登录** — 手机 QQ 扫码自动登录，Cookies 自动写入配置，无需手动抓取
- 👥 **群成员全监控** — 自动导入群成员，监控全群空间动态
- 🔑 **关键词过滤** — 支持正向匹配、排除词、必须词
- 📤 **自动转发** — 匹配到的动态自动转发到群或好友
- 👍 **自动点赞** — 对原说说自动点赞
- 💬 **自动评论** — 支持模板评论和 AI 智能评论
- 🤖 **AI 评论** — 接入 DeepSeek / OpenAI 等 API 生成自然评论
- ⚡ **一键启动** — 自动检查配置、导入群成员并启动服务
- 🖥 **Web 管理界面** — 浏览器即可配置和管理
- 📋 **去重记录** — 自动跳过已处理内容，避免重复操作

## 工作原理

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│  QQ空间 API  │◄───│  本工具核心   │───►│  OneBot 服务  │
│ 获取/点赞/评论│    │  调度+过滤    │    │  发送消息     │
└─────────────┘    └──────┬───────┘    └──────┬───────┘
                          │                    │
                          ▼                    ▼
                    ┌────────────┐    ┌──────────────┐
                    │ 评论生成器  │    │  QQ 客户端    │
                    │ 模板/AI    │    │ (Lagrange等)  │
                    └────────────┘    └──────────────┘
```

## 环境要求

- **Python 3.9+**
- **OneBot 实现** — 推荐 [Lagrange.OneBot](https://github.com/LagrangeDev/Lagrange.Core) 或 [go-cqhttp](https://github.com/Mrs4s/go-cqhttp)

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 部署 OneBot 客户端

启动 OneBot 客户端，开启 **HTTP API**（默认端口 5700）。

**Lagrange.OneBot 配置示例** (`appsettings.json`):
```json
{
  "Implementations": [
    {
      "Type": "Http",
      "Host": "127.0.0.1",
      "Port": 5700,
      "AccessToken": ""
    }
  ]
}
```

### 3. 扫码登录

1. 打开 Web 界面，点击「🚀 快速启动」卡片中的 **📱 扫码登录**
2. 用手机 QQ 扫描页面上的二维码并确认登录
3. 登录成功后 **Cookies 与 QQ 号自动写入配置**，无需手动抓取

### 4. 启动工具

```bash
python run.py
```

默认访问 http://localhost:5000

### 5. Web 界面配置

| 步骤 | 标签页 | 操作 |
|------|--------|------|
| 1 | **快速启动** | 点击「📱 扫码登录」，手机 QQ 扫码，配置自动完成 |
| 2 | **OneBot** | 配置地址和端口，测试连接 |
| 3 | **关键词** | 输入筛选关键词（每行一个） |
| 4 | **群来源** | 添加群号，自动导入群成员到监控列表 |
| 5 | **监控列表** | 手动添加或从群导入要监控的 QQ 号 |
| 6 | **转发列表** | 添加目标群（群号）或好友（QQ号） |
| 7 | **动作** | 开启转发/点赞/评论，配置模板或 AI |
| 8 | **快速启动** | 点击「⚡ 一键启动」，自动导入群成员并开始监控 |

## 配置说明

### 关键词格式

| 格式 | 示例 | 说明 |
|------|------|------|
| `关键词` | `抽奖` | 包含该词即匹配 |
| `+必须词` | `+转发` | 必须包含该词 |
| `-排除词` | `-广告` | 包含该词则不转发 |

多个关键词为 **或** 关系（匹配任意一个即可）。

### 评论模板

支持变量替换：

| 变量 | 说明 | 示例 |
|------|------|------|
| `{nickname}` | 发布者昵称 | `小明` |
| `{content}` | 说说前 20 字 | `今天天气真好` |
| `{time}` | 发布时间 | `2024-01-01 12:00` |

模板行尾加 `|权重` 控制选中概率，如 `写得真好！|3`。

### AI 评论

支持任何 OpenAI 兼容的 API：

| 参数 | 说明 |
|------|------|
| API 地址 | 如 `https://api.deepseek.com/v1/chat/completions` |
| API Key | 你的 API 密钥 |
| 模型 | 如 `deepseek-chat`, `gpt-4o-mini` |
| 系统提示词 | 控制评论风格和长度 |

### 完整配置 (`config.yaml`)

```yaml
qzone:
  cookies: "..."           # Qzone Cookie（扫码登录后自动写入，也可手动粘贴）
  uin: "123456"            # 你的 QQ 号（扫码登录后自动写入）
  poll_interval: 60        # 轮询间隔（秒）

onebot:
  host: "127.0.0.1"       # OneBot 地址
  port: 5700               # HTTP API 端口
  access_token: ""         # 访问令牌

keywords:                  # 关键词列表
  - "抽奖"
  - "+转发"
  - "-广告"

monitor_list:              # 监控列表
  - name: "张三"
    uin: "123456789"
    enabled: true

group_sources:             # 群来源（自动导入群成员）
  - group_id: "87654321"
    name: "工作群"
    enabled: true
    auto_import: true

forward_list:              # 转发列表
  - type: "group"
    id: "987654321"
    name: "通知群"
    enabled: true

actions:                   # 动作配置
  forward: true            # 转发
  like: true               # 点赞
  comment: true            # 评论
  comment_mode: "template" # template 或 ai

  comment_templates:       # 评论模板
    - content: "说得好！{nickname}"
      weight: 1
    - content: "写的真不错👍"
      weight: 2

  ai:                      # AI 配置
    enabled: false
    api_url: "https://api.deepseek.com/v1/chat/completions"
    api_key: ""
    model: "deepseek-chat"
    system_prompt: "你是一个QQ空间的评论助手..."
    max_tokens: 100
    temperature: 0.8
```

## 使用场景

### 场景：监控全群成员的空间动态

1. 在 **群来源** 中添加群号，开启自动导入
2. 启动后工具自动将群成员加入监控列表
3. 设置关键词过滤
4. 匹配到的动态自动转发/点赞/评论

### 场景：AI 自动评论

1. 在 **动作** 标签页开启评论
2. 切换到 **AI 模式**
3. 填入 DeepSeek / OpenAI 等 API 信息
4. 调整系统提示词控制评论风格
5. 保存配置后启动

## 命令行参数

```bash
python run.py --help

选项:
  --port PORT      Web 端口 (默认 5000)
  --host HOST      监听地址 (默认 0.0.0.0)
  --config PATH    配置文件路径 (默认 config.yaml)
  --no-web         仅后台模式，不启动 Web 界面
  --debug          调试模式
```

## 项目结构

```
qqtranspond/
├── run.py                  # 入口文件
├── config.yaml             # 配置文件
├── requirements.txt        # Python 依赖
├── README.md               # 使用文档
├── src/
│   ├── config.py           # 配置加载/保存
│   ├── qzone.py            # QQ空间 API（获取/点赞/评论）
│   ├── filter.py           # 关键词过滤
│   ├── sender.py           # OneBot 消息发送
│   ├── scheduler.py        # 轮询调度器
│   ├── comment_gen.py      # 评论生成（模板 & AI）
│   ├── group_import.py     # 群成员导入
│   ├── db.py               # 去重数据库
│   └── web/
│       └── app.py          # Flask Web 界面
├── templates/
│   └── index.html          # 前端页面
├── static/
│   └── style.css           # 样式
└── data/
    └── forwarded.db        # 操作记录（自动生成）
```

## 常见问题

**Q: 获取不到说说？**
- Cookies 可能已过期，在 Web 界面重新点击「📱 扫码登录」
- 目标用户设置了空间访问权限（仅好友可见）

**Q: 点赞/评论失败？**
- 确认 Cookies 有足够的权限
- Qzone API 对操作频率有限制，建议 `poll_interval` 不要设太短
- 评论内容请不要包含敏感词

**Q: OneBot 连接失败？**
- 确认 OneBot 客户端已启动
- 检查端口号和 AccessToken 是否匹配

**Q: 如何监控群内所有人？**
- 在「群来源」标签页添加群号，启动后自动导入群成员
- 或手动从群导入成员（点击「从群导入成员」按钮）

## 免责声明

本工具仅供个人学习研究使用。请遵守 QQ 平台及 QQ 空间使用协议，合理控制请求频率，勿用于任何违法或骚扰用途。使用者需自行承担使用风险。

## License

MIT