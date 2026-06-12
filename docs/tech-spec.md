# ConflictCompass — 技术规格书

## 1. 技术选型

| 层级 | 技术 | 版本要求 | 理由 |
|------|------|---------|------|
| 前端 | 原生 HTML + CSS + JS | — | 零框架依赖，启动快，维护简单 |
| 后端 | Python Flask | ≥3.10 | 轻量 Web 框架，适合小工具 |
| AI 服务 | Anthropic Claude API | SDK ≥0.54 | 话术质量高，合规判断可靠 |
| 数据库 | SQLite | —（Python 内置） | 零配置，本地存储，无需安装 |
| 启动 | Windows Batch (.bat) | Windows 10+ | 目标用户最友好的启动方式 |

## 2. 项目结构

```
ConflictCompass/
├── start.bat                  # 一键启动脚本
├── requirements.txt           # Python 依赖
├── server.py                  # Flask 后端服务（单文件）
├── CLAUDE.md                  # AI 开发指引
├── static/                    # 前端静态资源
│   ├── index.html             # 主页面
│   ├── style.css              # 全局样式
│   └── app.js                 # 前端交互逻辑
├── data/                      # 配置数据
│   ├── compliance_rules.json  # 合规红线规则
│   └── taboo_words.json       # 禁忌词词典
├── docs/                      # 项目文档
│   ├── requirements.md        # 需求文档
│   ├── tech-spec.md           # 本文件
│   ├── design-guide.md        # 设计规范
│   ├── implementation-plan.md # 实施计划
│   └── api-spec.md            # API 接口规范
└── devlog/                    # 开发日志
    └── YYYY-MM-DD.md          # 每日开发日志
```

## 3. 架构设计

```
┌──────────────┐     HTTP/JSON      ┌──────────────┐     REST API      ┌──────────────┐
│   浏览器      │ ◄────────────────► │  Flask       │ ◄───────────────► │  Claude API  │
│  (前端 SPA)   │                    │  server.py   │                    │  (Anthropic) │
└──────────────┘                    └──────┬───────┘                    └──────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │   SQLite     │
                                    │  (本地数据库)  │
                                    └──────────────┘
```

- **前端负责**：页面渲染、用户交互、API 调用、结果展示
- **后端负责**：Prompt 构建、Claude API 调用、合规规则匹配、数据库读写
- **数据库负责**：历史记录持久化、场景模板存储

## 4. 数据库设计

### 表：scripts（话术历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| lifecycle_stage | TEXT | 生命周期阶段 |
| scenario | TEXT | 具体场景 |
| level | TEXT | 对方职级 |
| emotion | TEXT | 对方情绪 |
| tone | TEXT | 期望语气 |
| extra_info | TEXT | 补充信息 |
| content | TEXT | 话术正文（JSON：开场+核心+收尾） |
| predictions | TEXT | 对方反应预判（JSON） |
| optimization | TEXT | 优化后版本（JSON，可为空） |
| created_at | TIMESTAMP | 创建时间 |

### 表：templates（场景模板）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT | 模板名称 |
| lifecycle_stage | TEXT | 所属生命周期 |
| scenario | TEXT | 场景描述 |
| default_tone | TEXT | 默认语气 |
| default_notes | TEXT | 默认补充说明 |
| is_preset | INTEGER | 是否预置（1=不可删） |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

## 5. 安全考虑

- API Key 通过环境变量 `ANTHROPIC_API_KEY` 传入，不写入代码或配置文件
- 数据库存储在本地，不涉及网络传输
- 所有 AI 调用仅为文本生成，不上传用户数据到第三方（除了 Anthropic API）
- start.bat 中提示用户自行保管 API Key

## 6. 模型建议

- 话术生成/优化：Claude Sonnet（性价比高，话术质量好）
- 合规检查：Claude Sonnet（逻辑判断能力满足需求）
