# email-notify

> 基于 Docker 的轻量邮件发送微服务。**同时对外提供两种调用方式**：
> 1. **REST HTTP 接口**（给传统应用）
> 2. **MCP（Model Context Protocol）服务**（给 AI 智能体，外部 AI 远端连 Streamable HTTP / 本地 AI 用 stdio）
>
> 底层 SMTP 凭据通过环境变量注入，两种接口共用同一份发送逻辑。

---

## 特性

- **双接口单进程**：一个 Starlette + uvicorn 进程同时承载 REST 与 MCP，复用 `mailer.py`
- **低内存**：MCP 用 `stateless_http=True`，会话内存随连接数零增长；`mem_limit: 96m` 兜底
- **轻镜像**：基于 `python:3.12-alpine`，非 root 用户运行、文件系统 `read_only`
- **双传输**：MCP 同时支持 Streamable HTTP（远端 AI）和 stdio（本地 AI，如 Claude Desktop）
- **统一鉴权**：单一 `API_KEY` 同时保护 `/api/send` 与 `/mcp`，`/healthz` 放行
- **生产可用**：`restart: unless-stopped`、日志轮转、内置 healthcheck

---

## 目录结构

```
email-notify/
├── sendmail.py              # 原始脚本（保留，向后兼容，可独立运行）
├── app/
│   ├── __init__.py
│   ├── server.py            # Starlette: REST 路由 + MCP 挂载 + Bearer 中间件
│   ├── mcp_tools.py         # FastMCP 服务 + send_email 工具定义
│   ├── mcp_stdio.py         # stdio 传输入口（本地 AI 用）
│   ├── mailer.py            # SMTP 发送逻辑（REST 与 MCP 共用，env 驱动）
│   └── auth.py              # Bearer Token 校验
├── requirements.txt         # mcp[cli] + uvicorn（版本钉死）
├── Dockerfile               # python:3.12-alpine，uvicorn 启动
├── docker-compose.yml       # 资源限制 + 健康检查 + 日志轮转
├── .env.example
└── README.md
```

---

## 快速开始

### 1. 准备配置

```bash
cp .env.example .env
# 生成一个 32 字节随机 API_KEY
openssl rand -hex 32
```

编辑 `.env`，填入真实 SMTP 配置和生成的 `API_KEY`：

```dotenv
SMTP_SERVER=smtp.163.com
SMTP_PORT=25
SENDER_MAIL=xxx@163.com
SENDER_PW=xxx
API_KEY=<上面 openssl 生成的串>
```

### 2. 构建并启动

```bash
docker compose up -d --build
```

### 3. 验证

```bash
# 健康检查（无需鉴权）
curl http://localhost:8000/healthz
# {"status":"ok"}
```

---

## 接口 1：REST HTTP

### `POST /api/send` — 发送邮件

**请求头**

| 名称 | 必填 | 说明 |
|---|---|---|
| `Authorization` | 是 | `Bearer <API_KEY>` |
| `Content-Type` | 是 | `application/json` |

**请求体**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `recipients` | `string[]` | 是 | 收件人数组，元素需含 `@`，非空 |
| `subject` | `string` | 是 | 主题，非空 |
| `message_body` | `string` | 是 | HTML 正文，非空 |

**响应**

| 状态码 | 响应体 | 含义 |
|---|---|---|
| `200` | `{"status":"sent","recipients":[...]}` | 发送成功 |
| `400` | `{"error":"<原因>"}` | 参数校验失败 / 非 JSON 体 |
| `401` | `{"error":"unauthorized"}` | Token 缺失或错误 |
| `500` | `{"error":"server_misconfigured",...}` | SMTP 环境变量未配置 |
| `502` | `{"error":"smtp_failed",...}` | SMTP 连接 / 认证 / 投递失败 |

**示例**

```bash
curl -X POST http://localhost:8000/api/send \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": ["dev@example.com"],
    "subject": "测试邮件",
    "message_body": "<h1>Hello</h1><p>from email-notify</p>"
  }'
```

### `GET /healthz` — 健康检查

无需鉴权，返回 `{"status":"ok"}`，**不**发起 SMTP 连接。

---

## 接口 2：MCP（给 AI 智能体）

服务对外暴露一个 MCP 工具：

| 工具 | 入参 | 返回 |
|---|---|---|
| `send_email` | `recipients: string[]`, `subject: string`, `message_body: string` | `{"status":"sent","recipients":[...]}` |

AI 客户端有两种连法。

### 方式 A：Streamable HTTP（远端 AI 推荐）

MCP 端点：`http://<host>:8000/mcp`

调用时在 HTTP 头里带上 `Authorization: Bearer <API_KEY>`（与 REST 接口共用同一个 token）。

> ⚠️ **远程访问必须配置 Host 白名单**：SDK 默认只允许本机（`127.0.0.1`/`localhost`）连接。外部 AI 远程连入时，需在 `.env` 里设置 `MCP_ALLOWED_HOSTS`，否则会得到 `421 Invalid Host header`。两种取值：
> - **指定主机**：`MCP_ALLOWED_HOSTS=notify.example.com:*,10.0.0.5:*`（推荐，支持 `host:*` 通配端口）
> - **全放开**：`MCP_ALLOWED_HOSTS=*`（关闭 Host 校验，仅靠 Bearer Token 鉴权，适合 Docker / 反代 / 内网）
>
> 详见下方[环境变量](#环境变量)；遇到 421 可参考"常见问题"一节。

在支持自定义 HTTP Header 的 MCP 客户端里，把 `authentication` 配成 Bearer Token 即可。例如用官方 SDK 写客户端：

```python
import asyncio
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async def main():
    async with streamablehttp_client(
        "http://localhost:8000/mcp",
        headers={"Authorization": "Bearer <API_KEY>"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("send_email", {
                "recipients": ["dev@example.com"],
                "subject": "线上告警",
                "message_body": "<h1>CPU 超过 90%</h1>",
            })
            print(result.structuredContent)

asyncio.run(main())
```

> 用 MCP Inspector 快速调试：`npx -y @modelcontextprotocol/inspector`，填入 URL `http://localhost:8000/mcp` 与 Bearer Token。

### 方式 B：stdio（本地 AI，如 Claude Desktop）

stdio 模式把服务作为子进程拉起，**无需鉴权**（靠进程隔离），所有 SMTP 配置从环境变量传入。

入口：`python -m app.mcp_stdio`

Claude Desktop 配置示例（`claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "email-notify": {
      "command": "python",
      "args": ["-m", "app.mcp_stdio"],
      "env": {
        "SMTP_SERVER": "smtp.163.com",
        "SMTP_PORT": "25",
        "SENDER_MAIL": "xxx@163.com",
        "SENDER_PW": "xxx"
      }
    }
  }
}
```

> 也可直接用镜像跑：`command` 换成 `docker`，`args` 换成 `["run","-i","--rm","-e","SMTP_SERVER=...","<image>","python","-m","app.mcp_stdio"]`。

---

## 环境变量

| 变量 | 说明 | 示例 |
|---|---|---|
| `SMTP_SERVER` | SMTP 服务器地址 | `smtp.163.com` |
| `SMTP_PORT` | SMTP 端口 | `25`（STARTTLS）/ `587` / `465` |
| `SENDER_MAIL` | 发件人邮箱 | `foo@163.com` |
| `SENDER_PW` | 发件人密码 / 授权码（163/QQ 等需用授权码） | `ABCDXXXXXXXXXXXX` |
| `API_KEY` | REST 与 MCP 共用的 Bearer Token，建议 ≥ 32 字节 | `openssl rand -hex 32` |
| `MCP_ALLOWED_HOSTS` | MCP 允许的 Host 头白名单（逗号分隔，支持 `host:*`）。默认仅本机；外部访问需设置。设为 `*` 表示全放开（关闭 Host 校验，仅靠 Bearer Token 鉴权） | `notify.example.com:*,10.0.0.5:*` 或 `*` |

> **注意**：当前实现固定使用 `STARTTLS`。若服务只支持 SSL 直连（如 465），需在 `app/mailer.py` 中把 `smtplib.SMTP` 换成 `smtplib.SMTP_SSL`。

---

## 运维

### 常用命令

```bash
docker compose up -d --build      # 构建并后台启动
docker compose logs -f            # 跟踪日志
docker compose restart            # 重启
docker compose down               # 停止并删除容器
docker compose ps                 # 查看健康状态
```

### 资源占用

| 指标 | 典型值 | 上限 |
|---|---|---|
| 运行时内存 (RSS) | 50-70 MB | `mem_limit: 96m` |
| 镜像大小 | ~80 MB | - |
| 启动时间 | < 2s | - |
| MCP 会话内存增长 | 无 | 无（`stateless_http=True`） |

### 日志

- `json-file` 驱动，轮转 `10m × 3 份`（最多 30MB 落盘）
- uvicorn access log + 应用业务日志全部打到 stdout，由 docker 收集

---

## 调参与扩展

### 提升 REST 并发

uvicorn 默认单 worker。SMTP 是阻塞 I/O，已在 Starlette 里通过 `anyio.to_thread.run_sync` 丢到线程池，单进程即可并发处理多个发送。如需更高吞吐，把 Dockerfile CMD 的 `--workers` 改为 2（需同步调大 `mem_limit` 到 `160m`）。

### 新增 MCP 工具

在 `app/mcp_tools.py` 加一个 `@mcp.tool()` 函数即可，MCP 的 HTTP 与 stdio 两条链路自动获得新工具，无需改动 `server.py`。

---

## 安全说明

1. **`.env` 已在 `.gitignore` 中**，切勿提交真实凭据
2. **单一 Bearer Token**：`/api/send` 和 `/mcp` 都要校验；stdio 模式免鉴权（本地子进程）
3. **非 root 容器** + **只读文件系统**（`read_only: true` + `tmpfs: /tmp`）
4. **建议**：生产环境在前面加反向代理（nginx / traefik）做 TLS 终结和限流
5. **MCP HTTP 安全**：建议绑定内网或经反代暴露，不要直接公网无防护开放

---

## 常见问题

<details>
<summary><b>返回 <code>502 smtp_failed: [SSL] WRONG_VERSION_NUMBER</code></b></summary>

你的 SMTP 端口可能需要 SSL 直连而非 STARTTLS。修改 `app/mailer.py`：

```python
with smtplib.SMTP_SSL(cfg["smtp_server"], cfg["smtp_port"], context=context, timeout=30) as server:
```
</details>

<details>
<summary><b>返回 <code>502 smtp_failed: ... 535</code> 或 <code>Authentication required</code></b></summary>

`SENDER_PW` 应填邮箱服务商的**授权码**，不是登录密码。163/126/QQ/Gmail 等均需在邮箱后台单独生成。
</details>

<details>
<summary><b>MCP 客户端连 <code>/mcp</code> 报 401</b></summary>

MCP 端点与 REST 共用 `API_KEY`。确认客户端的 `Authorization: Bearer <API_KEY>` 头与 `.env` 里的值完全一致。
</details>

<details>
<summary><b>MCP 客户端连 <code>/mcp</code> 报 <code>421 Invalid Host header</code></b></summary>

SDK 默认开启 DNS rebinding 防护，只允许本机（`127.0.0.1`/`localhost`）连接。两种解决方式，在 `.env` 里设置 `MCP_ALLOWED_HOSTS`：

```dotenv
# 方式1：指定主机白名单（推荐，精确控制，支持 host:* 通配端口）
MCP_ALLOWED_HOSTS=notify.example.com:*
MCP_ALLOWED_HOSTS=notify.example.com:*,10.0.0.5:*

# 方式2：全放开（关闭 Host 校验，仅靠 Bearer Token 鉴权，适合 Docker / 反代 / 内网）
MCP_ALLOWED_HOSTS=*
```

改完 `docker compose up -d` 重启即可。注意方式1里的 Host 是客户端发来的 `Host:` 头值（通常是 `域名:端口`），不是 URL 路径。
</details>

<details>
<summary><b>容器启动后 OOM Killed</b></summary>

`mem_limit: 96m` 过低。检查 `docker compose logs`，临时调到 `128m` 排查。
</details>

<details>
<summary><b>原始脚本 <code>sendmail.py</code> 还能用吗？</b></summary>

可以。`sendmail.py` 保留未动，可独立 `python sendmail.py` 运行。新服务能力在 `app/` 包内，互不干扰。
</details>

---

## 设计取舍

| 决策 | 选择 | 理由 |
|---|---|---|
| Web 框架 | Starlette + uvicorn | 单一 ASGI 进程，能同时挂 MCP（async）与 REST；轻量 |
| MCP 传输 | Streamable HTTP + stdio | 远端 AI 用 HTTP，本地 AI 用 stdio；共用同一份 tool 定义 |
| MCP 模式 | `stateless_http=True` | 会话内存零增长，契合低内存诉求 |
| Worker 数 | 1 | 阻塞 SMTP 用线程池并发，单 worker 把内存压到最低 |
| 鉴权 | 单一 `API_KEY` | REST 与 MCP 共用，少一个 env 变量 |
| 健康检查 | 不连 SMTP | 防止探针触发外部连接 |
| 邮件连接 | 每次新建 | 低内存优先，避免常驻连接池 |

---

## License

MIT
