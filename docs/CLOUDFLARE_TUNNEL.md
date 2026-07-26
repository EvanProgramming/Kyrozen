# Cloudflare Tunnel 部署指南

使用 Cloudflare Tunnel 可以在没有海外服务器、不备案的情况下，让 `kyrozen.chat` 正常访问。

## 原理

- 用户访问 `https://kyrozen.chat`
- 请求到达 Cloudflare 边缘节点（自动提供 HTTPS 证书）
- Cloudflare 通过加密隧道把请求转发到国内服务器上的 `cloudflared`
- `cloudflared` 把请求转发给 Kyrozen 后端容器

源站不需要开放 80/443 端口给公网，也不需要自己管理 HTTPS 证书。

## 前提

1. 一个 Cloudflare 账号：https://dash.cloudflare.com
2. 域名 `kyrozen.chat` 已经添加到 Cloudflare
3. 域名 DNS 服务器已经改成 Cloudflare 提供的 nameserver

## 步骤

### 1. 在 Cloudflare 添加站点

登录 https://dash.cloudflare.com，点击 **Add a Site**，输入 `kyrozen.chat`，选择 **Free** 套餐。

Cloudflare 会扫描现有 DNS 记录。如果没有，手动添加一条 A 记录：

- **Type**: A
- **Name**: `@`
- **IPv4 address**: `119.91.132.155`
- **Proxy status**: 灰色（关闭）
- **TTL**: Auto

> 注意：先不要开启橙色云代理，等 Tunnel 配好后再改。

### 2. 修改域名 DNS 服务器

Cloudflare 会提供两个 nameserver，例如：

```
lara.ns.cloudflare.com
greg.ns.cloudflare.com
```

到你购买 `kyrozen.chat` 的域名注册商后台，把 DNS 服务器改成这两个。等待生效（通常几分钟到几小时）。

### 3. 创建 Tunnel

访问 Cloudflare Zero Trust：https://one.dash.cloudflare.com

1. 左侧菜单选择 **Networks** → **Tunnels**
2. 点击 **Create a tunnel**
3. 选择 **Cloudflared**
4. **Tunnel name**: `kyrozen-server`（随便填）
5. 点击 **Save tunnel**
6. 在 **Choose your environment** 选择 **Docker**
7. 复制那一长串 **token**（形如 `eyJhIjoi...`）

把这个 token 告诉我，或者写入服务器上的 `/opt/kyrozen/.env`：

```bash
TUNNEL_TOKEN=eyJhIjoi...
```

### 4. 配置 Public Hostname

在同一页继续配置：

- **Subdomain**: 留空
- **Domain**: `kyrozen.chat`
- **Path**: 留空
- **Type**: `HTTP`
- **URL**: `kyrozen-backend:8000`

点击 **Save hostname**。

### 5. 在服务器上启动 cloudflared

SSH 到服务器后执行：

```bash
cd /opt/kyrozen
# 确保 .env 里有 TUNNEL_TOKEN
docker compose -f docker-compose.selfhosted.yml up -d --build --remove-orphans
```

### 6. 验证

```bash
curl -I https://kyrozen.chat/api/health
```

应该返回 200。

### 7. 可选：开启 Cloudflare 代理缓存

回到 Cloudflare DNS 设置，把 `kyrozen.chat` 的 A 记录旁边灰色云点成橙色（开启代理）。这样可以通过 Cloudflare CDN 缓存静态资源。

> 如果开启代理后 Tunnel 还能正常工作，说明配置成功。

## 后续维护

- `cloudflared` 会自动更新
- 如果需要重启：`docker compose -f docker-compose.selfhosted.yml restart cloudflared`
- 查看日志：`docker compose -f docker-compose.selfhosted.yml logs -f cloudflared`

## 与桌面客户端的关系

桌面客户端默认连接 `https://kyrozen.chat`。Cloudflare Tunnel 支持 WebSocket，所以客户端的 WebSocket 连接也能正常工作。
