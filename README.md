# email-notify

> 基于 Docker 的轻量邮件发送微服务。对外提供 HTTP 接口，调用方传入收件人、主题、正文即可触发邮件发送，底层 SMTP 凭据通过环境变量注入，避免泄露。

---

## 特性

- **低内存**：gunicorn 单 worker + 4 线程，运行时 RSS 约 30-40 MB，`mem_limit: 64m` 兜底
- **轻镜像**：基于 `python:3.12-alpine`，最终镜像约 60-70 MB
- **安全**：非 root 用户运行、文件系统 `read_only`、Bearer Token 鉴权（常量时间比较）
- **生产可用**：`restart: unless-stopped`、日志轮转（10MB × 3 份）、内置 healthcheck
- **零外部状态**：无数据库、无缓存，SMTP 配置全部走环境变量

---

## 目录结构

```
email-notify/
├── sendmail.py              # 原始脚本（保留，向后兼容，可独立运行）
├── app/
│   ├── __init__.py
│   ├── server.py            # Flask 路由 + 参数校验 + 错误映射
│   ├── mailer.py            # SMTP 发送逻辑（env 驱动）
│   └── auth.py              # Bearer Token 鉴权
├── requirements.txt         # flask + gunicorn（版本钉死）
├── Dockerfile               # python:3.12-alpine，非 root
├── docker-compose.yml       # 资源限制 + 健康检查 + 日志轮转
├── .env.example             # 环境变量模板
├── .gitignore
└── README.md
```

---

## 快速开始

### 1. 准备配置

```bash
cp .env.example .env
```

编辑 `.env`，填入真实 SMTP 配置，并把 `API_KEY` 改成一个足够长的随机串：

```bash
# 生成一个 32 字节的随机 API_KEY
openssl rand -hex 32
```

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

# 发送一封测试邮件
curl -X POST http://localhost:8000/api/send \
  -H "Authorization: Bearer <你的 API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": ["dev@example.com"],
    "subject": "测试邮件",
    "message_body": "<h1>Hello</h1><p>from email-notify</p>"
  }'
# {"recipients":["dev@example.com"],"status":"sent"}
```

---

## 接口文档

### `POST /api/send` — 发送邮件

**请求头**

| 名称            | 必填 | 说明               |
| --------------- | ---- | ------------------ |
| `Authorization` | 是   | `Bearer <API_KEY>` |
| `Content-Type`  | 是   | `application/json` |

**请求体**

| 字段           | 类型       | 必填 | 说明                           |
| -------------- | ---------- | ---- | ------------------------------ |
| `recipients`   | `string[]` | 是   | 收件人数组，元素需含 `@`，非空 |
| `subject`      | `string`   | 是   | 主题，非空                     |
| `message_body` | `string`   | 是   | HTML 正文，非空                |

**响应**

| 状态码 | 响应体                                            | 含义                        |
| ------ | ------------------------------------------------- | --------------------------- |
| `200`  | `{"status":"sent","recipients":[...]}`            | 发送成功                    |
| `400`  | `{"error":"<原因>"}`                              | 参数校验失败 / 非 JSON 体   |
| `401`  | `{"error":"unauthorized"}`                        | Token 缺失或错误            |
| `500`  | `{"error":"server_misconfigured","detail":"..."}` | SMTP 环境变量未配置         |
| `502`  | `{"error":"smtp_failed","detail":"..."}`          | SMTP 连接 / 认证 / 投递失败 |

### `GET /healthz` — 健康检查

无需鉴权。返回 `{"status":"ok"}`，**不会**发起 SMTP 连接，避免健康探针污染发件统计。供 docker healthcheck 使用。

---

## 客户端调用示例

### cURL

```bash
curl -X POST http://localhost:8000/api/send \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "recipients": ["ops@example.com","dev@example.com"],
    "subject": "线上告警",
    "message_body": "<h2>Disk &gt; 95%</h2><pre>host-12 /dev/sda1 ...</pre>"
  }'
```

### Python (requests)

```python
import requests

requests.post(
    "http://localhost:8000/api/send",
    headers={
        "Authorization": "Bearer <API_KEY>",
        "Content-Type": "application/json",
    },
    json={
        "recipients": ["dev@example.com"],
        "subject": "告警通知",
        "message_body": "<h1>CPU 超过 90%</h1>",
    },
    timeout=35,
).raise_for_status()
```

### Go

```go
body, _ := json.Marshal(map[string]any{
    "recipients":    []string{"dev@example.com"},
    "subject":       "告警通知",
    "message_body":  "<h1>CPU 超过 90%</h1>",
})
req, _ := http.NewRequest("POST", "http://localhost:8000/api/send", bytes.NewReader(body))
req.Header.Set("Authorization", "Bearer "+apiKey)
req.Header.Set("Content-Type", "application/json")
resp, err := http.DefaultClient.Do(req)
```

---

## 环境变量

| 变量          | 说明                                       | 示例                            |
| ------------- | ------------------------------------------ | ------------------------------- |
| `SMTP_SERVER` | SMTP 服务器地址                            | `smtp.163.com`                  |
| `SMTP_PORT`   | SMTP 端口                                  | `25`（STARTTLS）/ `587` / `465` |
| `SENDER_MAIL` | 发件人邮箱                                 | `foo@163.com`                   |
| `SENDER_PW`   | 发件人密码 / 授权码（163/QQ 等需用授权码） | `ABCDXXXXXXXXXXXX`              |
| `API_KEY`     | 调用方鉴权 Token，建议 ≥ 32 字节随机串     | `openssl rand -hex 32`          |

> **注意**：当前实现固定使用 `STARTTLS`（先明文连接再升级）。若你的服务只支持 SSL 直连（如 465），需在 `app/mailer.py` 中把 `smtplib.SMTP` 换成 `smtplib.SMTP_SSL`。

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

| 指标             | 典型值   | 上限             |
| ---------------- | -------- | ---------------- |
| 运行时内存 (RSS) | 30-40 MB | `mem_limit: 64m` |
| 镜像大小         | 60-70 MB | -                |
| 启动时间         | < 2s     | -                |

### 日志

- `json-file` 驱动，轮转 `10m × 3 份`（最多 30MB 落盘）
- gunicorn access log + error log 全部打到 stdout，由 docker 收集
- 业务日志格式：`%(asctime)s %(levelname)s [email-notify] %(message)s`

---

## 调参与扩展

### 提升并发

默认 `1 worker × 4 threads`。若 QPS 上升，修改 `Dockerfile` 的 CMD：

```dockerfile
CMD ["gunicorn", "-w", "2", "--threads", "8", \
     "-b", "0.0.0.0:8000", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "app.server:app"]
```

**务必**同步把 `docker-compose.yml` 的 `mem_limit` 调至 `128m` 以上（每个 worker 约增 25-35 MB）。

### 进一步降低内存

加 `--preload` 让多个 worker 共享一份解释器代码（仅多 worker 时有意义），或切换到 `bottle + waitress`（约省 10 MB）。

---

## 安全说明

1. **`.env` 已在 `.gitignore` 中**，切勿提交真实凭据
2. **API Token 鉴权**：未带正确 Token 的请求会被拒绝，防止开放中继
3. **非 root 容器**：使用 `appuser` 运行，即使容器被攻破也无法提权到 root
4. **只读文件系统**：`read_only: true` + `tmpfs: /tmp`，限制写入范围
5. **建议**：生产环境在前面加一层反向代理（nginx / traefik）做 TLS 终结和限流

---

## 常见问题

<details>
<summary><b>返回 <code>502 smtp_failed: [SSL] WRONG_VERSION_NUMBER</code></b></summary>

你的 SMTP 端口可能需要 SSL 直连而非 STARTTLS。修改 `app/mailer.py`：

```python
with smtplib.SMTP_SSL(cfg["smtp_server"], cfg["smtp_port"], context=context, timeout=30) as server:
    server.login(...)
    server.sendmail(...)
```

</details>

<details>
<summary><b>返回 <code>502 smtp_failed: ... Authentication required</code> 或 <code>535</code></b></summary>

`SENDER_PW` 应填邮箱服务商的**授权码**，不是登录密码。163/126/QQ/Gmail 等均需在邮箱后台单独生成。

</details>

<details>
<summary><b>容器启动后立刻 OOM Killed</b></summary>

`mem_limit: 64m` 过低。检查 `docker compose logs`，若为 OOM，临时调到 `96m` 或 `128m` 排查。

</details>

<details>
<summary><b>健康检查一直不健康</b></summary>

alpine 镜像默认带 `wget`，healthcheck 用它访问 `/healthz`。如果你换了基础镜像（如 `slim`），需安装 `wget` 或改用 `curl`，并相应调整 `healthcheck.test`。

</details>

<details>
<summary><b>原始脚本 <code>sendmail.py</code> 还能用吗？</b></summary>

可以。`sendmail.py` 保留未动，可独立 `python sendmail.py` 运行（仍读自身硬编码值）。新服务能力全部在 `app/` 包内，互不干扰。

</details>

---

## 设计取舍

| 决策      | 选择             | 理由                                                   |
| --------- | ---------------- | ------------------------------------------------------ |
| Web 框架  | Flask + gunicorn | SMTP 是阻塞 I/O，sync + 多线程足够；生态成熟，内存可控 |
| Worker 数 | 1                | 通知类服务低 QPS，单 worker 把内存压到最低             |
| 鉴权      | 单一 API Key     | 内部服务调用场景，避免引入数据库做账号体系             |
| 健康检查  | 不连 SMTP        | 防止探针触发外部连接污染发件人统计                     |
| 邮件连接  | 每次新建         | 低内存优先，避免常驻连接池；后续按需引入               |

---

## License

MIT
