# 小 Q 邮 · 北邮校园 AI 助理

基于 RAG（检索增强生成）的北京邮电大学智能校园助理。后端 FastAPI + SQLite + FAISS/BM25 混合检索；前端 React (Vite)，支持 **SSE 流式输出**逐字显示答案。

- 意图路由：关键词快速分流（KNOWLEDGE / CHITCHAT / TASK_EXECUTION / CLARIFICATION）
- 记忆分层：短期会话 + 长期用户画像，SQLite 持久化
- 检索：BM25 稀疏 + bge-small-zh-v1.5 稠密，RRF 融合
- 爬虫：内置教务处、图书馆、研究生院、门户等数据源，可手动或定时抓取
- 隐私：学号、手机号、身份证等 PII 自动脱敏

---

## 目录

- [一、环境准备](#一环境准备)
- [二、配置 .env](#二配置-env)
- [三、灌数据（二选一或都做）](#三灌数据二选一或都做)
- [四、构建索引](#四构建索引)
- [五、启动](#五启动)
- [六、API 速查](#六api-速查)
- [七、项目结构](#七项目结构)
- [八、测试](#八测试)
- [常见问题](#常见问题)

---

## 一、环境准备

需要 **Python ≥ 3.10** 和 **Node.js ≥ 18**。

```bash
# 后端
pip install -e .
pip install -e ".[dev]"   # 可选，带 pytest/ruff

# 前端
cd frontend
npm install
cd ..
```

---

## 二、配置 `.env`

```bash
cp .env.example .env
```

打开 `.env` 至少填这几个：

```bash
# LLM —— 推荐硅基流动或官方 DeepSeek
BUPT_LLM__API_KEY=sk-...your_key...
BUPT_LLM__BASE_URL=https://api.siliconflow.cn/
BUPT_LLM__MODEL_NAME=deepseek-ai/DeepSeek-V3   # V3 更快；R1 是推理模型慢但更强
BUPT_LLM__TEMPERATURE=0.7
BUPT_LLM__MAX_TOKENS=2048

# Embedding（默认已指向 bge-small-zh-v1.5，首次启动会自动下载 ~90MB）
BUPT_EMBEDDING__MODEL_NAME=BAAI/bge-small-zh-v1.5
BUPT_EMBEDDING__DEVICE=cpu

# App
BUPT_APP__DEBUG=true
BUPT_APP__HOST=0.0.0.0
BUPT_APP__PORT=8000

# Admin（调用 /api/admin/* 需要）
ADMIN_API_KEY=change-me-to-a-secure-random-string

# CORS，前端 dev 默认 5173；填 "*" 允许任意来源
CORS_ORIGINS=*
```

---

## 三、灌数据（二选一或都做）

助理要能回答校园问题，知识库里得有东西。否则会走 demo fallback 或只剩低置信度答案。

### 方法 A：灌示例数据（最快，用于调试）

```bash
python scripts/seed_test_data.py
```

会在 `data/raw/` 生成若干条假的图书馆、教务、食堂文档。

### 方法 B：抓真实校园站点（生产用）

```bash
# 列出所有可用数据源
python -m scripts.run_crawler --list

# 抓全部公开源（不含需要登录的门户）
python -m scripts.run_crawler

# 只抓某一个源
python -m scripts.run_crawler --source 教务通知

# 自定义输出目录
python -m scripts.run_crawler --output data/raw
```

`信息门户` (`my.bupt.edu.cn`) 需要统一认证登录，通过 `POST /api/portal/login` 登录后调 `POST /api/portal/crawl` 抓取；见 [六、API 速查](#六api-速查)。

服务端启动后还会按每个源配置的间隔（10min ~ 1day）后台定时增量抓取。

---

## 四、构建索引

抓完原始数据后把它们切片、向量化、写入 FAISS：

```bash
python scripts/build_knowledge_base.py --source file
```

结果写到 `data/indices/school.index`。之后问答时 `HybridRetriever` 会同时查 BM25 和 FAISS，用 RRF 合并排序。

> 换了 embedding 模型或维度后**必须重建索引**，否则向量维度不匹配会启动失败。

---

## 五、启动

两个进程分别起：

```bash
# 终端 1：后端
python app.py
# API → http://localhost:8000
# OpenAPI docs → http://localhost:8000/docs

# 终端 2：前端
cd frontend
npm run dev
# UI → http://localhost:5173（端口以 vite 输出为准）
```

在浏览器打开前端，随便输一句问题，答案会**逐字出现**（SSE 流式）。如果仍然卡 90 秒或只显示假数据，见下方 [常见问题](#常见问题)。

---

## 六、API 速查

### 聊天（两种）

```bash
# 普通 —— 等完整答案再返回
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "query": "北邮图书馆几点开门？", "session_id": "sess_001"}'

# 流式 —— Server-Sent Events
curl -N -X POST http://localhost:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "query": "北邮图书馆几点开门？", "session_id": "sess_001"}'
# 返回事件：meta → token*N → done ；出错发 error
```

### 记忆

```bash
# 按语义搜一个用户的历史记忆
curl -X POST http://localhost:8000/api/memory/user_001/search \
  -H "Content-Type: application/json" \
  -d '{"query": "图书馆", "top_k": 5}'

# 最近对话
curl "http://localhost:8000/api/memory/user_001/history?limit=10"

# 删一条记忆（需确认 token）
curl -X DELETE "http://localhost:8000/api/memory/user_001/<mem_id>?confirmation_token=confirm-delete-<mem_id>"
```

### 北邮门户（需登录的内部源）

```bash
# 用统一认证账号密码登录，cookie 缓存在内存 2 小时
curl -X POST http://localhost:8000/api/portal/login \
  -H "Content-Type: application/json" \
  -d '{"username": "your_bupt_id", "password": "xxx"}'

# 用已登录 session 抓需要认证的源
curl -X POST "http://localhost:8000/api/portal/crawl?username=your_bupt_id"
```

### 管理端（需 `X-Admin-Key` header）

```bash
# 全量重建索引
curl -X POST http://localhost:8000/api/admin/reindex \
  -H "X-Admin-Key: <ADMIN_API_KEY>"

# 手动触发单源爬虫入队
curl -X POST http://localhost:8000/api/admin/crawl/news \
  -H "X-Admin-Key: <ADMIN_API_KEY>"

# 系统统计
curl http://localhost:8000/api/admin/stats \
  -H "X-Admin-Key: <ADMIN_API_KEY>"
```

---

## 七、项目结构

```
bupt-ai-assistant/
├── app.py                      # FastAPI 入口（含 lifespan、CORS、embedding 预热）
├── config/
│   └── settings.py             # pydantic-settings 配置
├── src/
│   ├── models.py               # 共享 Pydantic 模型（ChatRequest/ChatResponse/Intent...）
│   ├── api/
│   │   ├── routes.py           # /api/chat、/api/chat/stream、记忆、门户、管理端
│   │   └── dependencies.py     # FastAPI DI 容器
│   ├── crawler/
│   │   ├── base.py             # BUPT_DATA_SOURCES 数据源定义
│   │   ├── spider.py           # 异步爬虫
│   │   ├── processor.py        # 清洗 + 分块
│   │   └── auth.py             # 北邮统一认证登录
│   ├── embedding/service.py    # bge-small-zh-v1.5 封装，lazy load + 预热
│   ├── retriever/
│   │   ├── faiss_store.py      # FAISS 向量索引
│   │   ├── hybrid_retriever.py # BM25 + FAISS RRF 融合
│   │   └── reranker.py
│   ├── memory/
│   │   ├── store.py            # SQLite 持久化 + 用户粒度 FAISS 子索引
│   │   ├── manager.py          # 分层记忆生命周期
│   │   └── compressor.py       # LLM 压缩长记忆
│   ├── dialogue/
│   │   ├── router.py           # 关键词意图路由（无 LLM 调用）
│   │   ├── prompt_builder.py   # RAG prompt 拼装
│   │   └── manager.py          # 对话编排（handle_message / handle_message_stream）
│   ├── llm/client.py           # OpenAI 兼容客户端（generate / stream_with_messages）
│   ├── scheduler/background.py # APScheduler 后台任务
│   └── utils/
│       ├── privacy.py          # PII 检测/脱敏
│       └── text_processing.py  # 分块、HTML 清洗
├── scripts/
│   ├── build_knowledge_base.py # 离线索引构建
│   ├── seed_test_data.py       # 示例数据
│   └── run_crawler.py          # 手动触发爬虫
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # 主界面 + SSE 流式消费
│   │   ├── api/client.js       # chat / chatStream / 记忆 / 门户
│   │   └── components/         # MessageBubble 等
│   └── package.json
├── tests/
│   ├── unit/                   # 模块级单测
│   └── integration/            # 端到端对话流
├── data/
│   ├── raw/                    # 爬虫原始输出
│   ├── processed/              # 清洗分块后
│   └── indices/                # FAISS 索引文件
└── docs/
    └── ARCHITECTURE.md
```

---

## 八、测试

```bash
# 全量（除了 text_processing 依赖 jieba 可能缺失）
pytest --ignore=tests/unit/test_text_processing.py -v

# 只跑对话端到端
pytest tests/integration/test_dialogue_flow.py -v
```

---

## 常见问题

### Q1. 问一句得到的都是"图书馆开放时间..."或"选课时间..."等固定答案，看起来是编好的
**那是前端 demo fallback**。回答右下角参考来源会显示 `[1] 演示数据`。触发条件是 `/api/chat/stream` 请求失败 —— 打开浏览器 DevTools → Network，发一条消息看 `chat/stream` 状态码：

- `404` → 后端是旧代码，重启 `python app.py`，确认 `/docs` 里有 `POST /api/chat/stream`
- `CORS error` → `.env` 里的 `CORS_ORIGINS` 没包含前端 origin
- `5xx` → 看后端日志，多半是 LLM API key 不对或网络不通

### Q2. 首次启动很慢
首次会从 HuggingFace 下载 bge-small-zh-v1.5（~90MB）。后续启动直接读本地缓存。出现 `Warning: You are sending unauthenticated requests to the HF Hub` 是正常的，不影响功能。

### Q3. 回答很慢、一直"发送中..."
- 如果用的是 `deepseek-ai/DeepSeek-R1`（推理模型），本身就慢，5~30s 很正常 —— 流式输出能让你看到逐字生成。换成 `DeepSeek-V3` 或 `Qwen/Qwen2.5-7B-Instruct` 会明显更快。
- 前端兜底 90s 没收到任何 token 就会中断并报错。

### Q4. 索引维度不匹配
```
AssertionError: index dim=1024 but vectors are 512-d
```
说明 `data/indices/` 下是旧模型（bge-m3）产的索引。删掉 `data/indices/` 整个目录重新跑 `scripts/build_knowledge_base.py`。

### Q5. Admin 接口 401
检查 `ADMIN_API_KEY` 是否和 `.env` 一致，调用时带 header：`-H "X-Admin-Key: <value>"`。

---

## License

MIT
