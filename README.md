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
| 首个注册账号自动成为管理员并自动通过审核 | `routers/auth.py::register`（`db.query(User).count()==0`） |
| 默认端口 8411 | `Dockerfile` / `docker-compose.yml` / `config.py` |
| 注册后需管理员审核才能登录 | `User.is_approved` + 登录时校验（`routers/auth.py::login`），管理后台"待审核用户"通过/拒绝 |
| 上传1-2张图生成套图 | `routers/generate.py::generate`，校验 `1<=len(images)<=2` |
| 模板先分季节，再有场景细节/产品/区域/提示词；不同产品按季节+产品归类 | `models.Template`（season/scene/product/region 四个索引字段），前端模板列表按"季节｜产品"分组展示 |
| 筛选顺序：先选季节 -> 读取产品 -> 出现场景/细节 -> 出现区域 | `GET /api/templates/filters` 做成级联（每个维度的可选值按已选的其它维度动态计算），前端 `groupProduct`/`groupScene`/`groupRegion` 逐级显现 |
| 套图可多选，每个套图可单独设置生成数量（默认1） | 前端 `SELECTED_TEMPLATES: Map<id, {template, count}>`，"已选套图"面板里每个套图一个数量输入框 |
| 单选套图时可修改提示词；多选时按各自原样生成 | `singleTplControls` 仅在恰好选中1个模板时显示 |
| 按模板原样生成 / 逐字段自定义后生成 | `use_template_as_is` 开关 + 8 个 override 字段（主体/风格/摄影/氛围/背景/光线/负面/参数）|
| 保存为自定义模板，名称按"季节-产品-场景/细节-区域"用"-"分段，方便后续按段筛选 | `save_as_template` + `template_name`（前端 `computeSuggestedName()` 自动建议这个格式，可编辑） |
| 图片本地保存，15天自动过期删除 | `services/storage.py::cleanup_expired`，`main.py` 用 APScheduler 每 `CLEANUP_INTERVAL_HOURS` 小时跑一次 |
| 批量打包下载 | `POST /api/generations/batch-download` 返回 zip |
| 用户各自的模板可改，管理员模板只读 | `Template.is_system` + `crud.template_editable_by` |
| 管理员可看所有人的模板与统计 | `routers/admin.py::all_templates` / `stats` |
| 单张成本默认0.3，每人每日额度默认50，均可配置 | `GlobalConfig` 全局默认 + `User.cost_per_image`/`User.daily_quota` 个人覆盖，管理后台可改 |
| 统计每人生成数量与成本，管理员可见 | `routers/admin.py::stats` / `list_users` |
| 图片生成按 OpenAI 规范传 size/quality/n/output_format/background | 前端生成面板的尺寸/质量/格式/背景下拉框 -> `routers/generate.py` 的 `img_*` 表单字段 -> `services/image_gen.py::generate_images` |
| API 配置改为调用远程中转服务器（不再直接存 OpenAI/Anthropic 密钥） | `GlobalConfig.remote_relay_base_url` / `remote_relay_api_key`，管理后台"设置·中转访问"可改，`services/image_gen.py` 调 `{base_url}/images/edits`，`services/relay_client.py` + `routers/relay.py` 反向代理 `/v1/chat/completions`、`/v1/images/generations`、`/v1/images/edits`、`/v1/models` |
| 每个用户专属 `rk-` 中转密钥，可随时重置（旧密钥立即失效） | `User.relay_key` + `POST /api/auth/relay-key/regenerate`（这是本服务自己签发给终端用户的密钥，和管理员配置的上游中转密钥是两回事） |

## 套图模板种子数据

你上传的《圣诞灯串提示词库.xlsx》已经被 `backend/seed_data/templates.json` 承载（24 条：室内 8 场景 + 室内细节 4 条 + 室外 9 场景 + 室外特写 3 条特写），服务启动时自动作为**系统模板**导入（`is_system=True`，普通用户不可编辑/删除，管理员可以）。

要继续录入其它品类（比如别的节日、别的产品）的模板表格，最简单的方式是复用同一张表结构（场景/细节、季节、产品、区域、主体描述四个提示词模块），再跑一遍：

```bash
python3 convert_seed.py   # 已附在交付包里，改一下 SRC/OUT 路径即可复用
```

也可以直接用管理员账号在前端"生成套图"面板里手填 8 个字段，保存为系统模板（需要在 `POST /api/templates?as_system=true` 上做，目前前端 UI 里管理员创建系统模板的入口还没做按钮，可以在 `admin.html` 里加一个"新建系统模板"表单，或者直接调 API）。

## 图片生成：现在直接调用你已有的远程中转服务

之前的版本是本服务自己直接持有 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` 去调 OpenAI/Anthropic。现在改成了**调用你已经在跑的那个远程中转服务**（ai-relay，端口 8511 那个项目），本服务本身不再保存任何真实的 OpenAI/Anthropic 密钥，只保存一个指向那个中转服务的 `Base URL` + `rk-` 密钥。

配置方式：管理员登录后台 -> "设置·中转访问"，填：
- **Base URL**：`http://<你的中转服务器>:8511/v1`
- **中转密钥**：在那个中转服务自己的"设置 -> 中转访问"页面里生成的 `rk-xxxxxxxx`

保存后立即生效（存在数据库里，不用重新部署容器）。也可以在 `.env` 里预填 `REMOTE_RELAY_BASE_URL`/`REMOTE_RELAY_API_KEY` 作为首次启动的默认值。

`backend/app/services/image_gen.py::generate_images()` 会把模板的 8 个字段拼回"【主体】…【风格】…"格式的提示词，连同你上传的产品图，一起 POST 到 `{Base URL}/images/edits`（multipart，`image[]` 字段），并按 OpenAI 规范带上：

| 参数 | 说明 | 前端控件 |
|---|---|---|
| `size` | `auto` / `1024x1024` / `1024x1536` / `1536x1024`，不传时按模板【参数】里的 `--ar` 猜一个 | 生成面板"尺寸"下拉 |
| `quality` | `auto` / `low` / `medium` / `high` | "质量"下拉 |
| `n` | 1-4，多选套图时每个套图单独设置 | "已选套图"面板每行的数量框，或"生成数量" |
| `output_format` | `png` / `jpeg` / `webp`，落盘文件名和下载时的 `Content-Type` 都按这个来 | "格式"下拉 |
| `background` | `auto` / `opaque` / `transparent` | "背景"下拉 |

- **没配置中转 Base URL / 密钥时**，会自动降级成本地用 Pillow 画的占位图（把拼好的提示词打印在图上），整个链路（上传->选模板->生成->扣额度->存档->15天过期->打包下载）在没有任何真实上游的情况下也能跑通、demo、联调前端。
- 如果那个中转服务之外你还想接别的图片模型/服务商，改 `_call_relay_image_edit` 这一个函数即可，其余业务逻辑不用动。

## API 中转层：反向代理到远程中转服务

本服务自己的 `/v1/*` 现在是一层很薄的反向代理，直接转发到管理员配置的远程中转服务，不再自己做 OpenAI<->Claude 的格式互转（那个远程服务已经做好了）：

```bash
curl http://<本服务地址>:8411/v1/chat/completions \
  -H "Authorization: Bearer rk-本服务签发给你的中转密钥" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

已实现 `POST /v1/chat/completions`（含流式 SSE 透传）、`POST /v1/images/generations`、`POST /v1/images/edits`、`GET /v1/models`，对应 `routers/relay.py` + `services/relay_client.py`。

- 鉴权分两层：终端用户用**本服务自己签发**的 `rk-` key（`User.relay_key`，`routers/relay.py::get_relay_user` 校验），本服务再用**管理员配置**的上游 `rk-` key（`GlobalConfig.remote_relay_api_key`）去请求远程中转服务 —— 两个 key 互不相同，终端用户永远看不到上游那个。
- 如果管理员还没配置中转地址/密钥，所有 `/v1/*` 请求会返回 `503`，提示去"设置·中转访问"里填。

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
