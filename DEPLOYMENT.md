# Kyrozen Beta Deployment Guide

This guide covers how to deploy Kyrozen Beta for local development and production.

## Architecture Overview

```
Users
  │
  ▼
Reverse Proxy (Nginx / Traefik) with HTTPS
  │
  ├──► Kyrozen Frontend (Vite + React + Nginx, port 80)
  │      └── static SPA, proxies /api to backend
  │
  └──► Kyrozen Backend (FastAPI + Uvicorn, port 8000)
         └── SQLite files or Supabase PostgreSQL
              └── Supabase Auth (JWT validation)
```

## Prerequisites

- Docker Engine 24+
- Docker Compose v2+
- A Supabase project (for production auth + database)
- A domain name and reverse proxy (for production HTTPS)
- At least one AI model API key (DeepSeek, OpenAI, Anthropic, Google, or Ollama)

## Quick Start — Local SQLite

```bash
# 1. Clone or enter the project
cd /path/to/Kyrozen

# 2. Copy environment template
cp .env.example .env

# 3. Edit .env for local SQLite
# KYROZEN_DB_BACKEND=sqlite
# KYROZEN_DB_PATH=./workspace/kyrozen.db
# Add your AI model API key

# 4. Build and run
docker compose up -d --build

# 5. Open http://localhost
```

## Production Deployment with Supabase

### 1. Configure Supabase

- Create or open your Supabase project.
- Go to **Project Settings > API** and copy:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `SUPABASE_SERVICE_ROLE_KEY`
  - `JWT Secret` (used as `SUPABASE_JWT_SECRET`)
- Apply the Kyrozen schema to your Supabase database:
  - Use the SQL Editor to run [`migrations/supabase_schema.sql`](./migrations/supabase_schema.sql).
  - Or connect with `psql` and run the same file.

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
SUPABASE_JWT_SECRET=<jwt-secret>

KYROZEN_DB_BACKEND=supabase
KYROZEN_WORKSPACE_ROOT=./workspace
KYROZEN_PERMISSION_MODE=strict
KYROZEN_SECRET_KEY=<generate-with-openssl-rand-hex-32>

DEEPSEEK_API_KEY=<your-key>
# or OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, OLLAMA_BASE_URL

KYROZEN_BETA_INVITE_ONLY=false
KYROZEN_CORS_ORIGINS=https://your-domain.com
```

### 3. Build and Run

```bash
docker compose up -d --build
```

### 4. Configure Reverse Proxy

Point your domain to the server running Docker Compose, then proxy to the frontend container on port 80.

Example Nginx virtual host:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 5. Verify

```bash
# Health check
curl https://your-domain.com/api/health

# View logs
docker compose logs -f kyrozen-backend
```

## Database Migrations

### SQLite

SQLite schema is applied automatically on first run. Back up the `workspace/kyrozen.db` file regularly.

### Supabase

When schema changes are released:

1. Review new migration files in `migrations/`.
2. Run them against your Supabase project via SQL Editor or `psql`.
3. Keep versioned migration backups.

## Security Checklist

- [ ] `.env` is not committed to Git.
- [ ] `SUPABASE_SERVICE_ROLE_KEY` and `KYROZEN_SECRET_KEY` are strong and unique.
- [ ] HTTPS is enabled in production.
- [ ] `KYROZEN_CORS_ORIGINS` is restricted to your real domain(s).
- [ ] Rate limiting is enabled (`KYROZEN_RATE_LIMIT_PER_MINUTE > 0`).
- [ ] Workspace volume backups are scheduled.
- [ ] Supabase RLS policies are enabled (handled by `supabase_schema.sql`).

## Updating to a New Release

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose down
docker compose up -d --build

# Apply any new Supabase migrations if using supabase backend
```

## Troubleshooting

### Backend fails to start

```bash
docker compose logs kyrozen-backend
```

Common causes:
- Missing required environment variables.
- Invalid Supabase service role key or JWT secret.
- Missing AI provider API key.

### Frontend cannot reach backend

- Verify `VITE_API_BASE_URL=/api` in `frontend/.env`.
- Verify the Nginx proxy passes `/api` to `http://kyrozen-backend:8000`.
- Verify CORS origins include your frontend domain.

### Database foreign key errors

- Ensure Supabase schema was applied.
- For SQLite, ensure `KYROZEN_DB_PATH` is writable inside the container.

### Auth errors

- Verify `SUPABASE_JWT_SECRET` matches your Supabase project.
- Verify frontend uses the correct `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- Verify user tokens are not expired.

## Files Reference

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Production Compose stack |
| `Dockerfile.backend` | Backend image build |
| `frontend/Dockerfile` | Frontend image build |
| `frontend/nginx.conf` | SPA + API proxy rules |
| `.env.example` | Required environment variables |
| `migrations/supabase_schema.sql` | Supabase PostgreSQL schema |
| `migrations/001_add_user_id.sql` | SQLite migration for user isolation |
