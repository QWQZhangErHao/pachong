<div align="center">
  <br/>
  <h1>🕷️ Pachong · 分布式电商爬虫系统</h1>

  <p><strong>World-class distributed e-commerce scraping system · 世界级分布式电商数据采集系统</strong></p>

  <p>From URL submission to structured data extraction — a fully automated pipeline with adaptive anti-detection and elastic scheduling.</p>
  <p>从 URL 提交到结构化数据提取的全自动流水线,支持自适应反检测与弹性调度。</p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python" alt="Python">
    <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi" alt="FastAPI">
    <img src="https://img.shields.io/badge/Kafka-3.x-231F20?logo=apachekafka" alt="Kafka">
    <img src="https://img.shields.io/badge/Redis-7-FF4438?logo=redis" alt="Redis">
    <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql" alt="PostgreSQL">
    <img src="https://img.shields.io/badge/Playwright-1.48+-2EAD33?logo=playwright" alt="Playwright">
    <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  </p>
</div>

---

## ✨ Features · 核心功能

| Feature 功能 | Description 说明 |
|-------------|-----------------|
| 📥 **Batch Submission** 批量提交 | Bulk URL submission via txt/CSV/paste, auto deduplication & priority ranking / 批量提交 URL(支持 txt/CSV/直接粘贴),自动去重与优先级排序 |
| 🧭 **4-Engine Adaptive Crawling** 四引擎自适应抓取 | HTTP/2 → Playwright → Nodriver fallback chain for JS challenges & anti-bot / HTTP/2 → Playwright → Nodriver 四级引擎应对 JS 挑战和反爬 |
| 🔬 **5-Layer Extraction Pipeline** 五层提取管道 | Schema.org → CSS/XPath → Adaptive IE → LLM repair → Multimodal vision, field recall > 92% / Schema.org → CSS/XPath → 自适应信息抽取 → LLM 修复 → 多模态视觉,字段召回率 > 92% |
| 🛡️ **Anti-Detection Suite** 反检测套件 | Browser fingerprinting, behavioral simulation, proxy rotation, TLS fingerprint consistency / 浏览器指纹、行为模拟、代理轮换、TLS 指纹一致性 |
| 📊 **Real-time Web Console** 实时控制台 | Apple-style dashboard for task status, result preview & anti-bot warnings / Apple 风格 Web 控制台,展示任务状态、结果预览与反爬警告 |
| ⚡ **Elastic Distributed Scheduling** 弹性分布式调度 | Kafka + Redis token bucket + PostgreSQL, horizontal scaling / Kafka + Redis 令牌桶 + PostgreSQL,支持水平扩展 |
| 🩺 **Resilience & Observability** 韧性与可观测性 | Circuit breakers, adaptive throttling, Prometheus + Grafana + OpenTelemetry / 熔断器、自适应限速、Prometheus + Grafana + OpenTelemetry 全链路观测 |

---

## 🏗️ Architecture · 系统架构

```
┌──────────────┐    ┌──────────────────────────────────────────────────┐
│   Web UI     │    │                    Scheduler                     │
│  FastAPI     │───▶│  Priority Queue · Dedup · Rate Limiter · Frontier │
└──────────────┘    └───────────────────────┬──────────────────────────┘
                                            │ Kafka / Redis Streams
                     ┌──────────────────────▼──────────────────────────┐
                     │                     Workers                      │
                     │  ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
                     │  │ HTTP/2     │ │ Playwright │ │  Nodriver    │  │
                     │  │ aiohttp    │ │  Pool      │ │  (exper.)    │  │
                     │  └────────────┘ └────────────┘ └──────────────┘  │
                     │        │              │              │           │
                     │  ┌─────────────────────────────────────────┐    │
                     │  │      5-Layer Extraction Pipeline        │    │
                     │  │ Schema.org → CSS/XPath → IE → LLM → Vis │    │
                     │  └─────────────────────────────────────────┘    │
                     └───────────────────────┬──────────────────────────┘
                                             │
             ┌───────────────────────────────┼───────────────────────────────┐
             │                               │                               │
     ┌───────▼───────┐              ┌────────▼────────┐            ┌─────────▼─────────┐
     │  PostgreSQL   │              │  Redis (cache)  │            │  MinIO / S3       │
     │  tasks/results│              │  rate-limit/lock│            │  raw HTML/screens │
     └───────────────┘              └─────────────────┘            └───────────────────┘
```

---

## 📁 Project Structure · 项目结构

```
pachong/
├── api/               # FastAPI 路由层 (routes: tasks, stats, results, batch)
├── scheduler/         # 调度器: 优先级队列、URL 去重、令牌桶限速、站点地图
├── network/           # 网络层: aiohttp 连接池、DNS 缓存、浏览器池
├── anti_detect/       # 反检测: 浏览器指纹、行为模拟、代理池、身份生成
├── extractor/         # 提取管道: 五层提取、LLM 修复、自适应信息抽取
├── queue/             # 消息队列: Kafka 生产/消费、背压控制
├── storage/           # 存储: PostgreSQL (SQLAlchemy async)、MongoDB、S3/MinIO
├── resilience/        # 韧性: 熔断器、封禁检测、自适应限速、Prometheus 指标
├── tracing/           # 可观测性: OpenTelemetry 追踪
├── serverless/        # Serverless 适配: AWS Lambda / GCP Function
├── cli/               # Typer CLI 命令
├── tests/             # 单元测试与集成测试
├── deploy/            # Docker Compose / Kubernetes / 监控 (Prometheus+Grafana)
├── scripts/           # 辅助脚本 (数据迁移、代理种子、一键启动)
├── config/            # YAML 配置 (default / development / production)
└── pyproject.toml     # 项目元数据与依赖
```

---

## 🚀 Quick Start · 快速开始

### Requirements 环境要求

- **Python 3.12+**
- [uv](https://docs.astral.sh/uv/) (推荐) 或 pip
- PostgreSQL / Redis / Kafka(完整运行需要;纯本地模式可跳过)

### Installation 安装

```bash
# 1. Clone & install
git clone https://github.com/QWQZhangErHao/pachong.git
cd pachong

# 2. Install dependencies (uv recommended)
make dev-install        # or: uv pip install -e ".[dev]"

# 3. Install browser for Playwright engine
playwright install chromium

# 4. Configure environment
cp .env.example .env    # edit credentials as needed
```

### Running 运行

```bash
# Start a worker process
make worker

# Start the API server
uvicorn pachong.api.app:app --reload

# Windows one-click start
scripts/start.bat

# Run a demo
python demo.py
```

### Docker 部署

```bash
cd deploy/docker
docker compose up -d
```

Kubernetes 部署见 `deploy/k8s/`,Serverless 部署见 `deploy/serverless/`。

---

## 🧪 Development · 开发

```bash
make test        # pytest -v (tests/ 目录)
make lint        # ruff check pachong/ tests/
make fmt         # ruff format pachong/ tests/
make migrate     # alembic upgrade head
```

---

## 🛠️ CLI 使用

```bash
pachong --help              # 查看所有命令
# 示例: 批量提交 URL
pachong submit urls.txt
```

---

## 📄 License · 许可

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">
  <sub>Built with Python, FastAPI, Kafka, Redis & Playwright · 用 ❤️ 构建</sub>
</div>
