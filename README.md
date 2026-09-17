# 产品套图生成服务

Docker 化的产品套图（Product Photo-Set）生成 SaaS：上传 1-2 张产品图，按预设的"季节 / 场景细节 / 产品 / 区域"模板库生成电商风格的场景化产品图，并内置一个 OpenAI / Claude 兼容的 API 中转层。

## 目录结构

```
product-image-service/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── backend/                     # FastAPI 服务
│   ├── requirements.txt
│   ├── seed_data/templates.json # 由圣诞灯串表格转换来的24条系统预置模板
│   └── app/
│       ├── main.py              # 应用入口 + 定时清理任务
│       ├── config.py            # 所有可配置项（环境变量）
│       ├── models.py            # User / Template / GenerationJob / GlobalConfig
│       ├── schemas.py           # Pydantic 请求/响应模型
│       ├── auth.py              # JWT 登录鉴权
│       ├── crud.py              # 额度/权限相关的查询辅助函数
│       ├── seed.py              # 启动时把 seed_data 灌入系统模板
│       ├── routers/
│       │   ├── auth.py          # 注册/登录/me/中转密钥
│       │   ├── templates.py     # 模板的增删改查 + 多选筛选
│       │   ├── generate.py      # 生成套图 + 历史记录 + 批量打包下载
│       │   ├── admin.py         # 用户管理 / 全局配置 / 统计
│       │   └── relay.py         # /v1/chat/completions 等 OpenAI 兼容接口
│       └── services/
│           ├── image_gen.py     # 拼装提示词 + 调用图片生成模型
│           ├── storage.py       # 文件落盘 / 15天过期清理 / zip打包
│           └── relay_client.py  # OpenAI 直通 + Claude<->OpenAI 格式互转（含流式）
└── frontend/                    # 原生 HTML/CSS/JS，无需构建
    ├── index.html                主应用：筛选模板 -> 生成 -> 历史记录
    ├── admin.html                管理后台
    └── js/ , css/
```

## 快速开始

```bash
cp .env.example .env
# 按需编辑 .env（尤其是 SECRET_KEY；OPENAI_API_KEY 留空则用占位图演示模式）
docker compose up -d --build
```

访问 `http://<服务器IP>:8411`。**第一个注册的账号自动成为管理员**。

## 核心功能与实现对照

| 你的需求 | 实现位置 |
|---|---|
| 首个注册账号自动成为管理员 | `routers/auth.py::register`（`db.query(User).count()==0`） |
| 默认端口 8411 | `Dockerfile` / `docker-compose.yml` / `config.py` |
| 上传1-2张图生成套图 | `routers/generate.py::generate`，校验 `1<=len(images)<=2` |
| 模板先分季节，再有场景细节/产品/区域/提示词 | `models.Template`（season/scene/product/region 四个索引字段）|
| 按季节/产品/场景细节多选搜索模板 | `GET /api/templates?season=..&scene=..`（重复参数=多选），前端筛选面板为 chip 多选 |
| 按模板原样生成 / 逐字段自定义后生成 | `use_template_as_is` 开关 + 8 个 override 字段（主体/风格/摄影/氛围/背景/光线/负面/参数）|
| 保存为自定义模板 | `save_as_template` + `template_name`，写入 `Template(owner_id=当前用户)` |
| 图片本地保存，15天自动过期删除 | `services/storage.py::cleanup_expired`，`main.py` 用 APScheduler 每 `CLEANUP_INTERVAL_HOURS` 小时跑一次 |
| 批量打包下载 | `POST /api/generations/batch-download` 返回 zip |
| 用户各自的模板可改，管理员模板只读 | `Template.is_system` + `crud.template_editable_by` |
| 管理员可看所有人的模板与统计 | `routers/admin.py::all_templates` / `stats` |
| 单张成本默认0.3，每人每日额度默认50，均可配置 | `GlobalConfig` 全局默认 + `User.cost_per_image`/`User.daily_quota` 个人覆盖，管理后台可改 |
| 统计每人生成数量与成本，管理员可见 | `routers/admin.py::stats` / `list_users` |
| OpenAI/Claude 兼容中转 API，按 model 路由，统一 OpenAI 格式返回（含流式） | `routers/relay.py` + `services/relay_client.py` |
| 每个用户专属 `rk-` 中转密钥，可随时重置（旧密钥立即失效） | `User.relay_key` + `POST /api/auth/relay-key/regenerate` |

## 套图模板种子数据

你上传的《圣诞灯串提示词库.xlsx》已经被 `backend/seed_data/templates.json` 承载（24 条：室内 8 场景 + 室内细节 4 条 + 室外 9 场景 + 室外特写 3 条特写），服务启动时自动作为**系统模板**导入（`is_system=True`，普通用户不可编辑/删除，管理员可以）。

要继续录入其它品类（比如别的节日、别的产品）的模板表格，最简单的方式是复用同一张表结构（场景/细节、季节、产品、区域、主体描述四个提示词模块），再跑一遍：

```bash
python3 convert_seed.py   # 已附在交付包里，改一下 SRC/OUT 路径即可复用
```

也可以直接用管理员账号在前端"生成套图"面板里手填 8 个字段，保存为系统模板（需要在 `POST /api/templates?as_system=true` 上做，目前前端 UI 里管理员创建系统模板的入口还没做按钮，可以在 `admin.html` 里加一个"新建系统模板"表单，或者直接调 API）。

## 图片生成模型是"可插拔"的

`backend/app/services/image_gen.py` 里的 `generate_images()` 默认调用 OpenAI 的 `images/edits`（`gpt-image-1`），把你上传的产品图作为参考图传进去，`compose_prompt()` 会把模板的 8 个字段拼回类似表格里"【主体】…【风格】…"的格式喂给模型。

- **没配置 `OPENAI_API_KEY` 时**，会自动降级成本地用 Pillow 画的占位图（把拼好的提示词打印在图上），这样整个链路（上传->选模板->生成->扣额度->存档->15天过期->打包下载）都能在没有任何真实 API Key 的情况下跑通、demo、联调前端。
- 如果你实际用的是 Midjourney、即梦、SeeDream、Gemini 之类别的图片模型，只需要改这一个文件里的 `_call_openai_image_edit`，其余业务逻辑（配额、模板、历史记录）不用动。

## API 中转层

```bash
curl https://dailybonushub.com/v1/chat/completions \
  -H "Authorization: Bearer rk-你的中转密钥" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

- `model` 以 `claude` 开头 -> 转发到 `ANTHROPIC_BASE_URL`，请求/响应/流式 SSE 都在 `services/relay_client.py` 里做了 OpenAI<->Anthropic 格式互转。
- 其它 model（`gpt-*`、`o3` 等）-> 直接透传到 `OPENAI_BASE_URL`。
- 鉴权用的是用户自己的 `rk-` key（`routers/relay.py::get_relay_user`），不会暴露服务器上配置的真实 `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`。
- 真实上游 Key 通过部署时的环境变量注入，**从不下发给客户端**。

当前只实现了 `/v1/chat/completions` 和 `/v1/models`；如果需要 `/v1/images/generations`、`/v1/embeddings` 等，可以在 `routers/relay.py` 里按同样的模式加。

## 数据模型要点

- `GenerationJob.prompt_snapshot_json` 存的是**生成那一刻**实际用的8个字段快照 —— 就算之后模板被改了/删了，历史记录里看到的还是当时真实生成用的提示词。
- 额度判断用的是"今日（UTC）已产生的成功生成成本之和 + 本次预计花费 <= daily_quota"，在 `routers/generate.py` 里下单前校验。
- 过期清理是"软删除友好"的：只删过期的 `GenerationJob` 行和它对应的图片文件，不影响模板、用户、统计里的历史成本汇总（`admin/stats` 里的累计成本是所有历史成功记录之和，不受清理影响，因为清理只删 `GenerationJob` 行本身——如果你想要"过期后也不再计入累计成本"，那清理时得改成只删文件不删行，这个可以按你实际需要再调）。

## 已知限制 / 后续可以加的

- 密码/JWT 目前用的是最基础的 `passlib[bcrypt]` + `python-jose`，生产环境务必换掉 `.env` 里的 `SECRET_KEY`。
- 存储是本地磁盘（挂载到 `./data`），没有做 S3/OSS 之类的对象存储，单机够用，多副本部署需要改成对象存储。
- 没有做邮箱验证、找回密码、频率限制（rate limit）。
- 管理员创建系统模板目前只有 API，没有前端表单（见上文）。
- `/v1` 中转层没有做按 token 计费/限流，只有套图生成走了配额系统；如果也想让中转 API 调用计入额度，需要在 `routers/relay.py` 里接入 `crud.used_today` 之类的逻辑。
