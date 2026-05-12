```
# CLAUDE.md - 黑客松项目助手配置

> 本文件用于告诉 Claude 这个项目的关键信息、技术栈、常用命令和协作规则。  
> 在开发过程中，Claude 会自动参考此文件内容来给出更准确的代码建议和操作。

## 🎯 项目简介
- **项目名称**：Pachong - 分布式电商爬虫系统
- **一句话目标**：从 URL 提交到结构化数据提取的全自动流水线，支持自适应反检测与弹性调度。
- **目标用户**：数据采集工程师、商业分析师、需要竞品价格监控的电商团队。
- **核心功能**：
  1. 批量提交 URL（支持 txt/CSV/直接粘贴），自动去重与优先级排序。
  2. 四引擎自适应抓取（HTTP/2 → Playwright → Nodriver），应对 JS 挑战和反爬。
  3. 五层提取管道（Schema.org → CSS/XPath → 自适应 IE → LLM 修复 → 多模态视觉），字段召回率 > 92%。
  4. 实时 Web 控制台（Apple 风格 UI），展示任务状态、结果预览与反爬警告。
  5. 分布式调度（Kafka + Redis 令牌桶 + PostgreSQL），支持水平扩展。

## 🧰 技术栈
- **前端**：原生 HTML/CSS/JS（Apple 设计系统，无框架依赖）+ TailwindCSS（可选）
- **后端**：FastAPI (Python 3.11+) + Uvicorn
- **异步 HTTP**：aiohttp（连接池、HTTP/2）、httpx（备用）
- **浏览器自动化**：Playwright（Chromium 池）、Nodriver（实验性）
- **数据库**：PostgreSQL + SQLAlchemy 2.0 (async) / 可选 MongoDB（结果存储）
- **消息队列**：Kafka（或 Redis Streams）
- **缓存/限流**：Redis（令牌桶、熔断状态、LLM 缓存）
- **对象存储**：MinIO / S3（原始 HTML、截图）
- **可观测性**：Prometheus + Grafana + OpenTelemetry
- **部署**：Docker Compose（本地生产模拟） / Kubernetes (HPA) / AWS Lambda (Serverless)
- **测试**：pytest + pytest-asyncio（覆盖率 > 85%）

## 📁 项目结构（说明）
```



pachong/
├── api/ # FastAPI 路由层
│ ├── routes/ # 具体端点（tasks, stats, batch）
│ └── _task_service.py # 任务 CRUD 服务
├── core/ # 核心实体与配置
│ ├── config.py # YAML 配置 + 热加载
│ ├── entities.py # Pydantic 模型（Task, Result）
│ └── exceptions.py # 自定义异常层级
├── scheduler/ # 调度器
│ ├── queue.py # 优先级队列 + URL 去重
│ ├── rate_limiter.py # 域名级令牌桶 + 自适应信号量
│ └── dispatcher.py # Kafka / Redis 分发
├── network/ # 网络与反检测
│ ├── http_client.py # aiohttp 连接池（按域名 Session）
│ ├── dns_cache.py # DNS 缓存 + 预热 + 持久化
│ ├── browser_pool.py # Playwright 实例池
│ └── anti_detect/ # 指纹、代理调度
├── extractor/ # 提取管道
│ ├── pipeline.py # 五层管道（并行执行）
│ ├── llm_fix.py # LLM 修复 + Redlock 缓存
│ └── adaptive_ie.py # spaCy NER 自适应
├── storage/ # 存储适配器
│ ├── repository.py # 批量写入 + 断点续扫
│ └── models.py # SQLAlchemy / Motor 模型
├── resilience/ # 韧性与监控
│ ├── circuit_breaker.py # 操作级熔断器（LLM/Playwright）
│ ├── ban_detector.py # 反爬反馈 + PID 调速
│ └── metrics.py # Prometheus 指标埋点
├── cli/ # Typer CLI 命令
├── tests/ # 单元测试与集成测试
├── scripts/ # 辅助脚本（数据迁移、预热）
├── docker-compose.yml # 全服务编排
├── start.bat # Windows 一键启动
└── CLAUDE.md # 本文件

text

```
## 🧪 常用命令
### 开发环境
```bash
# 安装依赖（推荐使用 conda 或 venv）
pip install -r requirements.txt
playwright install chromium

# 启动 API 服务（开发模式，自动重载）
uvicorn api.main:app --reload --port 8000

# 启动前端（如果使用 Vite 单独开发）
npm run dev

# 运行所有测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_extractor.py -v

# 代码格式化与 lint
black .
ruff check .

# 启动完整 Docker 环境（PostgreSQL+Redis+Kafka+MinIO）
docker-compose up -d
```



### 生产环境

bash

```
# 构建镜像
docker build -t pachong:latest .

# 运行容器（使用环境变量覆盖配置）
docker run -e REDIS_URL=redis://prod:6379 -p 8000:8000 pachong:latest

# 或使用 docker-compose 一键启动所有服务
docker-compose -f docker-compose.prod.yml up -d

# Kubernetes 部署（需要先配置 kubeconfig）
kubectl apply -f k8s/
```



### 数据管理

bash

```
# 手动提交单个 URL
python cli/main.py submit https://example.com --priority 80

# 批量提交文件（每行一个 URL）
python cli/main.py submit-batch urls.txt

# 导出所有结果到 CSV
python cli/main.py export --format csv --output results.csv

# 清理 30 天前的原始 HTML
python scripts/cleanup_old_html.py --days 30
```



## 🧠 协作规则（Claude 必须遵守）

1. **代码风格**：
   - 使用 `async/await` 处理所有 I/O（禁止同步阻塞）。
   - 类型注解必须完整（`from __future__ import annotations`）。
   - 日志使用 `structlog`，并始终附带 `task_id` 或 `request_id`。
2. **修改代码前的检查**：
   - 先读取相关文件的完整内容（`read_file`）。
   - 若需要修改超过 15 行，先向用户确认。
   - 运行 `pytest tests/` 确保已有测试通过。
3. **安全与隐私**：
   - 绝对不要在代码或日志中硬编码代理密码、API Key。
   - 所有密钥通过环境变量或 Kubernetes Secret 注入。
   - 爬取的原始 HTML 不得包含用户个人信息（如邮箱、手机号），存储前需脱敏。
4. **性能考量**：
   - 避免在热路径中使用 `asyncio.gather(*many_tasks)` 无限制并发，必须结合信号量。
   - 批量数据库写入使用 `bulk_insert`，单条事务提交仅用于关键状态更新。
   - LLM 调用必须经过缓存（Redis + 结构化签名），严禁无缓存重复调用。
5. **测试要求**：
   - 新增功能需同步添加单元测试（至少覆盖正常路径和异常路径）。
   - 网络请求相关代码使用 `respx` 或 `aioresponses` 模拟外部依赖。

## 🚨 已知问题与解决方案（常见陷阱）

| 问题                                     | 症状                                | 解决办法                                                     |
| :--------------------------------------- | :---------------------------------- | :----------------------------------------------------------- |
| `[WinError 1225] 远程计算机拒绝网络连接` | 所有任务 fallback 到 demo           | 检查防火墙是否放行 Python / 关闭代理 / 使用 `curl` 测试外网连通性 |
| Playwright 浏览器启动失败                | `playwright._impl._api_types.Error` | 运行 `playwright install chromium` / 设置 `PLAYWRIGHT_BROWSERS_PATH` 环境变量 |
| LLM 缓存命中率极低                       | 大量重复调用 OpenAI API             | 检查缓存 key 生成逻辑（是否基于完整 HTML？改为前 10KB + 结构签名） |
| Redis 连接池耗尽                         | `redis.exceptions.ConnectionError`  | 增加 `max_connections` 参数（默认 10 → 50），或改用 `redis.asyncio.ConnectionPool` |
| PostgreSQL 死锁                          | `could not serialize access`        | 确保使用 `asyncpg` 驱动，并设置 `isolation_level="read_committed"` |

## 📌 使用的设计系统

- **UI 风格**：Apple 风格（参考 `docs/apple-design-system.yaml`）
  - 主色调：`#0066cc`（唯一强调色）
  - 字体：SF Pro Display / SF Pro Text（后备系统字体）
  - 圆角胶囊（`border-radius: 9999px`）用于所有主要按钮
  - 无边框无阴影（除产品图外）
- **主题切换**：默认浅色模式，后期可增加深色变量

## 🔗 外部依赖 API

| 服务                                                         | 用途         | 限流策略                                 |
| :----------------------------------------------------------- | :----------- | :--------------------------------------- |
| OpenAI API (GPT-4o)                                          | LLM 修复字段 | 10 RPM（可调整），使用本地缓存 + Redlock |
| [ipapi.co](https://ipapi.co/) / [ipinfo.io](https://ipinfo.io/) | GeoIP 查询   | 1000 次/天（免费版）                     |
| ScraperAPI / BrightData                                      | 备用代理池   | 付费套餐，按请求计费                     |

## 👥 团队分工（示例）

| 角色       | 职责                               |
| :--------- | :--------------------------------- |
| 后端开发   | FastAPI、网络引擎、提取管道        |
| 前端开发   | React 控制台（或原生 JS）、UI 升级 |
| SRE/DevOps | Docker、K8s、监控告警              |
| 测试工程师 | 编写爬虫对抗测试用例、质量验收     |

## 📈 后续优化方向（Roadmap）

- 支持 WebSocket 实时推送任务进度（替代轮询）。
- 增加浏览器指纹轮换商店（自动下载指纹库）。
- 实现自适应重试策略（根据错误类型动态调整退避时间）。
- 前端增加“一键导出结果”到 Excel/PDF。
- 集成 Slack/钉钉机器人，发送封锁警报。

------

**最后更新**：2026-05-11
**维护者**：Pachong Team
**反馈渠道**：请在项目 Issue 中提出修改建议，不要直接修改本文件（除非你是 owner）。