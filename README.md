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
│       ├── models.py            # User / Template / RemixTemplate / GenerationJob / RelayProvider / UserProductAccess / GlobalConfig
│       ├── schemas.py           # Pydantic 请求/响应模型
│       ├── auth.py              # JWT 登录鉴权
│       ├── crud.py              # 额度/权限/产品权限/用量统计相关的查询辅助函数
│       ├── seed.py              # 启动时把 seed_data 灌入系统模板
│       ├── migrate.py           # 启动时轻量 SQLite 自动迁移（补列 + 老数据搬迁）
│       ├── routers/
│       │   ├── auth.py          # 注册（含审核）/登录/me/中转密钥
│       │   ├── templates.py     # 套图模板的增删改查 + 级联筛选 + 产品权限过滤
│       │   ├── remix_templates.py # 二创套图模板的增删改查 + 图1背景图上传/读取
│       │   ├── generate.py      # 生成套图（含二创批量生成）+ 历史记录 + 按批次打包下载
│       │   ├── admin.py         # 用户/供应商/模板筛选统计/产品权限/全局配置/统计
│       │   └── relay.py         # /v1/chat/completions 等 OpenAI 兼容接口，反代到当前激活供应商
│       └── services/
│           ├── image_gen.py     # 拼装提示词 + 按供应商类型分流调用图片生成
│           ├── storage.py       # 文件落盘 / 15天过期清理 / 按批次zip打包 / 二创背景图存取
│           └── relay_client.py  # 反代到当前激活供应商的通用请求/流式转发
└── frontend/                    # 原生 HTML/CSS/JS，无需构建
    ├── index.html                主应用：筛选模板 -> 生成 -> 按批次的历史记录
    ├── remix.html                二创套图：模板管理 + 批量放置产品
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
| API 配置改为调用远程中转服务，并可随时切换供应商（不再直接存 OpenAI/Anthropic 密钥） | `models.RelayProvider` 表（可加多个，`is_active` 标记当前用哪个），管理后台"API 供应商"卡片管理，支持 `sync_edit`（自建中转等同步 `/images/edits`）和 `toapis_async`（ToAPIs 异步任务制）两种类型，`services/image_gen.py` 按类型分流调用，`services/relay_client.py` + `routers/relay.py` 反向代理 `/v1/chat/completions`、`/v1/images/generations`、`/v1/images/edits`、`/v1/models` |
| 每个用户专属 `rk-` 中转密钥，可随时重置（旧密钥立即失效） | `User.relay_key` + `POST /api/auth/relay-key/regenerate`（这是本服务自己签发给终端用户的密钥，和管理员配置的上游中转密钥是两回事） |
| 打包下载按"批次"（一次点生成）分文件夹，而不是一图一文件夹 | `GenerationJob.batch_id`，`storage.py::build_zip_by_batch`，历史记录按批次分组 + 每批"下载本批次"按钮 |
| 图片模型可选，默认 `gpt-image-2` | `RelayProvider.image_model`，管理后台每个供应商一行可改 + "刷新"拉取该供应商真实模型列表 |
| 管理后台套图模板按季节/产品/所属人筛选，可编辑，统计7天/30天用量 | `GET /api/admin/templates`（筛选+用量统计），`crud.template_usage_counts`，后台"编辑"按钮 |
| 按产品分配使用权限 | `UserProductAccess` 表 + `crud.get_allowed_products`，管理后台"产品使用权限"卡片 |
| 二创套图模板（预设背景图 + 批量放置产品） | `models.RemixTemplate`，`routers/remix_templates.py`，`POST /api/generate/remix`，独立页面 `/remix.html` |

## 套图模板种子数据

你上传的《圣诞灯串提示词库.xlsx》已经被 `backend/seed_data/templates.json` 承载（24 条：室内 8 场景 + 室内细节 4 条 + 室外 9 场景 + 室外特写 3 条特写），服务启动时自动作为**系统模板**导入（`is_system=True`，普通用户不可编辑/删除，管理员可以）。

要继续录入其它品类（比如别的节日、别的产品）的模板表格，最简单的方式是复用同一张表结构（场景/细节、季节、产品、区域、主体描述四个提示词模块），再跑一遍：

```bash
python3 convert_seed.py   # 已附在交付包里，改一下 SRC/OUT 路径即可复用
```

也可以直接用管理员账号在前端"生成套图"面板里手填 8 个字段，保存为系统模板（需要在 `POST /api/templates?as_system=true` 上做，目前前端 UI 里管理员创建系统模板的入口还没做按钮，可以在 `admin.html` 里加一个"新建系统模板"表单，或者直接调 API）。

## 图片生成：可切换的多供应商中转

管理后台有一个"API 供应商"列表（可以加多个，随时一键切换"当前使用"哪一个），本服务本身不保存任何真实的 OpenAI/Anthropic 密钥，只保存每个供应商的 `Base URL` + 密钥。目前支持两种调用方式（`kind` 字段区分，新增供应商时选）：

| kind | 适用场景 | 调用方式 |
|---|---|---|
| `sync_edit` | 你自己那个 ai-relay 项目（端口 8511），或任何 OpenAI 官方 `/images/edits` 兼容接口 | 同步：`POST {base_url}/images/edits`（multipart，`image[]` 字段），直接拿到图片 |
| `toapis_async` | [ToAPIs](https://toapis.com)（`gpt-image-2` 等模型） | 异步任务制：先 `POST {base_url}/uploads/images` 把产品图传上去拿 URL，再 `POST {base_url}/images/generations`（JSON，`reference_images` 传 URL 列表）拿任务 id，然后轮询 `GET {base_url}/images/generations/{task_id}` 直到 `completed`/`failed` |

新增/切换在管理后台"API 供应商"卡片里操作：填名称、选类型、填 Base URL 和密钥、点添加；已有的供应商点"设为当前使用"就能切换，立即生效，不用重启容器。旧版本里配置过的单个"中转访问"会在升级后自动迁移成第一个供应商（`backend/app/migrate.py::migrate_legacy_relay_provider`）。

`backend/app/services/image_gen.py::generate_images()` 会先把模板的 8 个字段拼回"【主体】…【风格】…"格式的提示词，然后按 provider.kind 分流：

- `sync_edit`：和之前一样，把 `size`(`auto`/`1024x1024`/`1024x1536`/`1536x1024`) / `quality` / `n` / `output_format` / `background` 直接透传。
- `toapis_async`：`size` 改传模板【参数】里 `--ar` 后面的比例字符串（比如 `4:5`、`16:9`，正好和 ToAPIs 的 `size` 字段格式一致，见 `aspect_ratio_from_parameters()`），`quality` 粗略映射成 ToAPIs 的 `resolution`（`high`→`2k`，其余→`1k`），`background` 只有等于 `transparent` 时才传（ToAPIs 要求普通生图不要带这个字段）。轮询按官方建议：先等 5 秒，之后每次间隔 ≥5 秒并加了随机抖动，最长等 110 秒，超时或 `failed` 都会抛错走到下面的占位图兜底。

不管哪种供应商：
- **没有任何供应商 / 当前供应商没配好时**，自动降级成本地用 Pillow 画的占位图（把拼好的提示词打印在图上），整个链路（上传->选模板->生成->扣额度->存档->15天过期->打包下载）在没有真实上游的情况下也能跑通、demo、联调前端。
- 调用失败（超时、上游报错等）同样会兜底成占位图，不会让整个请求 500，`GenerationJob.status` 会标成 `failed` 并带上 `error_message`。
- 如果以后要接第三个供应商类型，在 `services/image_gen.py` 里加一个 `_call_xxx()` 函数、在 `generate_images()` 里加一个 `elif provider.kind == "xxx"` 分支、在 `models.RelayProvider.kind` 注释和 `routers/admin.py` 的合法值列表、`admin.html` 的下拉框里都加上新值就行。

## API 中转层：反向代理到当前使用的供应商

本服务自己的 `/v1/*` 是一层很薄的反向代理，直接转发到管理后台"当前使用"的那个供应商：

```bash
curl http://<本服务地址>:8411/v1/chat/completions \
  -H "Authorization: Bearer rk-本服务签发给你的中转密钥" \
  -H "Content-Type: application/json" \
  -d '{"model":"claude-sonnet-4-6","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

已实现 `POST /v1/chat/completions`（含流式 SSE 透传）、`POST /v1/images/generations`、`POST /v1/images/edits`、`GET /v1/models`，对应 `routers/relay.py` + `services/relay_client.py`。

- 鉴权分两层：终端用户用**本服务自己签发**的 `rk-` key（`User.relay_key`，`routers/relay.py::get_relay_user` 校验），本服务再用**当前激活供应商**的密钥（`crud.get_active_provider(db)`）去请求上游 —— 两个 key 互不相同，终端用户永远看不到上游那个。
- 如果还没添加/激活任何供应商，所有 `/v1/*` 请求会返回 `503`，提示去"API 供应商"里配一个。
- **注意**：`/v1/images/generations` 和 `/v1/images/edits` 这两个透传接口只是把请求原样转发给当前供应商，不做参数转换。如果当前激活的是 `toapis_async` 类型（异步任务制、没有 `/images/edits` 这个接口），直接拿 OpenAI SDK 打这两个透传接口可能对不上；这层的参数归一化只在本服务自己的"套图生成"业务逻辑（`image_gen.py`）里做了，纯透传层暂时没做。

## 批次下载、模型选择、模板管理、产品权限、二创套图

这几块是同一批加的，放一起说：

**打包下载按"批次"分文件夹**：以前是一个生成记录一个文件夹；现在改成"点一次生成套图"算一批（即使这次点击因为多选了几个模板而拆成好几个后端请求，也共享同一个 `batch_id`），历史记录里按批次分组展示，每批一个"下载本批次"按钮，多批一起勾选也可以合并打包——zip 里是 `<时间>_<批次号前8位>/01.png, 02.png...` 这样一批一个文件夹，不再是一张图一个文件夹。`GenerationJob.batch_id` + `storage.py::build_zip_by_batch()`。

**图片模型可选**：模型现在是"供应商"的属性（`RelayProvider.image_model`，默认 `gpt-image-2`），不是写死的全局常量。管理后台每个供应商一行可以直接改模型 ID，也有个"刷新"按钮去掉那个供应商真实的 `/models` 接口拉列表（`GET /api/admin/providers/{id}/models`）供参考。生成套图时用的是"当前激活供应商"的 `image_model`。

**管理后台的套图模板表**：加了季节/产品/所属人三个筛选下拉（所属人可选"系统"或具体某个用户名），每行多了 7 天/30 天用量统计（`crud.template_usage_counts`，按 `GenerationJob.template_id` + 时间范围聚合），点"编辑"可以直接在后台改任意模板的全部字段（包括系统模板——admin 本来就有编辑系统模板的权限，只是以前前端没做这个入口）。

**按产品分配使用权限**：新表 `UserProductAccess(user_id, product)`。默认所有人能看到/用全部产品（没有配置=不限制），管理后台"产品使用权限"卡片选一个用户、勾选允许的产品、保存，之后这个用户浏览套图模板/二创模板时就只能看到这些产品下的了。管理员自己永远不受限。`crud.get_allowed_products()` 返回 `None`=不限制 或者一个具体的产品集合，套图模板和二创模板的可见性查询里都接了这个过滤。

**二创套图模板（新的一整套功能，独立页面 `/remix.html`）**：跟常规套图模板的区别是——每个模板自带一张预设背景图（图1，上传时存到 `data/remix_backgrounds/`），只有一个简单提示词框（默认"把上传的产品（图2）放到图1中"），不是 8 个结构化字段。命名建议是"产品-描述"这种（比如"沙发-低角度-白底"），不强制校验，只是 UI 占位提示。使用时选一个模板，一次性批量上传最多 20 张产品图，系统会挨个把"图1（模板背景）+ 这张产品图"一起送给图片模型，一张产品图对应生成一张结果，全部算一批（沿用上面的批次下载）。权限、可见性、按产品筛选跟常规模板走的是同一套逻辑（`crud.remix_visible_to`/`remix_editable_by`/`get_allowed_products`）。管理后台有张只读总览表，实际的新建/编辑/删除都在 `/remix.html` 页面里做（管理员在那边新建时会多一个"设为系统模板"勾选框）。



- `GenerationJob.prompt_snapshot_json` 存的是**生成那一刻**实际用的8个字段快照 —— 就算之后模板被改了/删了，历史记录里看到的还是当时真实生成用的提示词。
- 额度判断用的是"今日（UTC）已产生的成功生成成本之和 + 本次预计花费 <= daily_quota"，在 `routers/generate.py` 里下单前校验。
- 过期清理是"软删除友好"的：只删过期的 `GenerationJob` 行和它对应的图片文件，不影响模板、用户、统计里的历史成本汇总（`admin/stats` 里的累计成本是所有历史成功记录之和，不受清理影响，因为清理只删 `GenerationJob` 行本身——如果你想要"过期后也不再计入累计成本"，那清理时得改成只删文件不删行，这个可以按你实际需要再调）。
- `RelayProvider` 表存所有配置过的供应商，`is_active` 标记当前用哪个（`routers/admin.py::activate_provider` 切换时会把其它行的 `is_active` 全部置为 `False`，保证同一时间只有一个生效）。

## 数据库自动迁移

项目没有接 Alembic，`backend/app/migrate.py` 里是一个很轻量的启动时自检：`run_sqlite_migrations()` 检查已存在的表缺哪些列就自动 `ALTER TABLE ADD COLUMN` 补上（老账号会被标记为已审核，不会被新加的审核功能卡住；老的生成记录会按 `legacy-<id>` 各自变成自己的单条批次，保证批次下载对老数据也能用），`migrate_legacy_relay_provider()` 把老版本里配置过的单个中转地址/密钥自动搬进新的 `RelayProvider` 表。这几个新表（`relay_providers`、`remix_templates`、`user_product_access`）本身是全新的表，`create_all()` 会直接建好，不需要额外迁移逻辑，只有"已存在的表新增列"才需要在 `REQUIRED_COLUMNS` 里登记。两个函数都是幂等的、只在 SQLite 上生效，且只在检测到"确实缺东西"时才动手，正常升级不需要手动碰数据库或删 `./data`。如果之后你自己改了模型字段，记得照着这个文件的模式在 `REQUIRED_COLUMNS` 里加一行，不然新装的人没事，老装的人会 500。

## 已知限制 / 后续可以加的

- 密码/JWT 目前用的是最基础的 `passlib[bcrypt]` + `python-jose`，生产环境务必换掉 `.env` 里的 `SECRET_KEY`。
- 存储是本地磁盘（挂载到 `./data`），没有做 S3/OSS 之类的对象存储，单机够用，多副本部署需要改成对象存储。
- 没有做邮箱验证、找回密码、频率限制（rate limit）。
- 管理员在后台可以编辑任意已有套图模板，但"新建一个系统模板"目前还是只能调 API（`POST /api/templates?as_system=true`），后台没有对应的新建表单；二创模板倒是有完整的新建表单，在 `/remix.html`。
- `/v1` 中转层没有做按 token 计费/限流，只有套图生成走了配额系统；如果也想让中转 API 调用计入额度，需要在 `routers/relay.py` 里接入 `crud.used_today` 之类的逻辑。
- `toapis_async` 的轮询是同步阻塞在请求线程里的（单张最长 110 秒）。二创套图的批量生成（`POST /api/generate/remix`）是在同一个 HTTP 请求里顺序处理每张产品图的，如果当前供应商是 `toapis_async` 且一次传了接近 20 张，最坏情况可能要等将近一小时，很容易被反向代理或浏览器的请求超时打断——批量上传建议先从几张试起，真要上量应该把整个生成流程改成后台任务队列 + 前端轮询/WebSocket 通知，而不是让一个 HTTP 请求死等。
