# 自托管 Kyrozen 后端部署指南

本指南介绍如何把 Kyrozen 后端部署到你自己的服务器，同时保留 Supabase 作为账户认证服务。

## 架构

- **Supabase**：只负责用户注册/登录/JWT 签发/GitHub token metadata。
- **你的服务器**：运行 Kyrozen API + PostgreSQL，处理业务数据、AI 调用、任务调度、桌面客户端 WebSocket。
- **桌面客户端**：连接你的服务器地址（https://your-server.com）。

## 前提条件

- 一台有公网 IP 的服务器（建议 2C4G 以上）。
- 服务器已安装 Docker + Docker Compose。
- 一个 Supabase 项目（URL、anon key、service role key、JWT secret）。
- 一个 AI provider API key（DeepSeek / OpenAI / Anthropic 等）。
- 一个域名（推荐，用于 HTTPS；没有域名也可以用 IP + 自签名证书）。

## 快速部署

### 1.  clone 代码到服务器

```bash
git clone <你的仓库地址> /opt/kyrozen
cd /opt/kyrozen
```

### 2.  配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少填写以下字段：

```bash
# Supabase 认证（保留）
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_JWT_SECRET=your-jwt-secret

# AI 模型
DEEPSEEK_API_KEY=your-key

# 数据库：使用自托管 PostgreSQL
KYROZEN_DB_BACKEND=postgres

# PostgreSQL 密码（docker-compose.selfhosted.yml 会用这个密码创建数据库）
POSTGRES_DB=kyrozen
POSTGRES_USER=kyrozen
POSTGRES_PASSWORD=your-strong-password

# CORS：必须包含桌面客户端的 origin
# - http://localhost:5173 用于开发模式
# - null 用于打包后的 Electron 桌面客户端（file:// origin）
# - https://your-domain.com 如果你还要用浏览器访问
KYROZEN_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,null

# 可选：GitHub OAuth（用于客户端一键提交/推送）
GITHUB_OAUTH_CLIENT_ID=your-github-app-id
GITHUB_OAUTH_CLIENT_SECRET=your-github-app-secret
GITHUB_OAUTH_REDIRECT_URI=https://your-domain.com/api/auth/github/callback
```

### 3.  配置 Caddy（反向代理 + HTTPS）

编辑仓库根目录的 `Caddyfile`：

**有域名的情况（推荐）：**

```caddyfile
your-domain.com {
    encode gzip

    @websockets {
        header Connection *Upgrade*
        header Upgrade websocket
    }
    reverse_proxy @websockets kyrozen-backend:8000

    reverse_proxy kyrozen-backend:8000 {
        header_up Host {host}
        header_up X-Real-IP {remote}
        header_up X-Forwarded-For {remote}
        header_up X-Forwarded-Proto {scheme}
    }
}
```

**只有 IP 的情况（测试用）：**

```caddyfile
:80 {
    encode gzip

    @websockets {
        header Connection *Upgrade*
        header Upgrade websocket
    }
    reverse_proxy @websockets kyrozen-backend:8000

    reverse_proxy kyrozen-backend:8000
}
```

> 没有域名时 Caddy 只能提供 HTTP 或自签名 HTTPS。桌面客户端在非 localhost 下会强制使用 HTTPS，所以生产环境务必配置域名 + 证书。

### 4.  启动服务

```bash
docker compose -f docker-compose.selfhosted.yml up -d --build
```

等待所有服务 healthy：

```bash
docker compose -f docker-compose.selfhosted.yml ps
```

### 5.  验证后端

```bash
curl https://your-domain.com/api/health
```

应该返回健康状态。

### 6.  桌面客户端连接

打开桌面客户端，在登录页面或「设置 → 服务器地址」中输入：

```
https://your-domain.com
```

然后使用 Supabase 账号登录。

## 常用命令

```bash
# 查看日志
docker compose -f docker-compose.selfhosted.yml logs -f kyrozen-backend

# 重启后端
docker compose -f docker-compose.selfhosted.yml restart kyrozen-backend

# 更新代码后重新构建
docker compose -f docker-compose.selfhosted.yml up -d --build

# 进入 PostgreSQL 容器
docker compose -f docker-compose.selfhosted.yml exec kyrozen-postgres psql -U kyrozen -d kyrozen

# 停止整个服务
docker compose -f docker-compose.selfhosted.yml down

# 停止并删除数据卷（危险）
docker compose -f docker-compose.selfhosted.yml down -v
```

## 数据库备份

PostgreSQL 数据卷默认挂载在 Docker 命名卷中。建议设置定时备份：

```bash
# 手动备份
docker compose -f docker-compose.selfhosted.yml exec kyrozen-postgres pg_dump -U kyrozen kyrozen > kyrozen_backup_$(date +%F).sql

# 恢复备份
cat kyrozen_backup_2025-01-01.sql | docker compose -f docker-compose.selfhosted.yml exec -T kyrozen-postgres psql -U kyrozen -d kyrozen
```

## 故障排查

### 桌面客户端提示 "CORS error"

检查 `.env` 中的 `KYROZEN_CORS_ORIGINS` 是否包含：

- `null`（打包后的 Electron 客户端 origin 是 null）
- `http://localhost:5173`（开发模式）

修改后重启后端：

```bash
docker compose -f docker-compose.selfhosted.yml restart kyrozen-backend
```

### 桌面客户端无法连接 WebSocket

检查 Caddyfile 是否正确配置了 `@websockets` 反向代理。浏览器控制台会显示 WebSocket 连接失败。

### 后端日志提示 "Failed to connect to PostgreSQL"

检查：

1. `POSTGRES_PASSWORD` 是否设置。
2. `kyrozen-postgres` 是否 healthy。
3. `KYROZEN_POSTGRES_DSN` 是否正确（通常不需要手动设置，docker-compose 会自动构造）。

### HTTPS 证书问题

确保域名已正确解析到服务器 IP，并且服务器的 80/443 端口对外开放。Caddy 会自动申请 Let's Encrypt 证书。

## 安全建议

1. 修改默认的 `POSTGRES_PASSWORD`。
2. 修改 `.env` 中的 `KYROZEN_SECRET_KEY`：
   ```bash
   openssl rand -hex 32
   ```
3. 不要把 `.env` 提交到 Git。
4. 定期更新服务器和 Docker 镜像。
5. 使用防火墙限制不必要的端口暴露（只需要 80/443）。
