-- Afdian OAuth bindings, checkout sessions, orders, grants and review queue.
-- Safe to apply after 002_memberships.sql on existing deployments.
CREATE TABLE IF NOT EXISTS public.afdian_accounts (
    user_id TEXT PRIMARY KEY, afdian_user_id TEXT UNIQUE NOT NULL,
    afdian_user_private_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.afdian_oauth_states (
    state TEXT PRIMARY KEY, user_id TEXT NOT NULL, redirect_uri TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL, consumed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS public.afdian_checkout_sessions (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, plan TEXT NOT NULL, plan_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', checkout_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS public.afdian_orders (
    out_trade_no TEXT PRIMARY KEY, user_id TEXT, afdian_user_id TEXT, afdian_user_private_id TEXT,
    plan TEXT, plan_id TEXT, month INTEGER NOT NULL DEFAULT 1, total_amount NUMERIC(12,4), status INTEGER,
    raw_payload JSONB, verification_status TEXT NOT NULL DEFAULT 'pending', review_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.membership_grants (
    id TEXT PRIMARY KEY, out_trade_no TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL, plan TEXT NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.membership_payment_reviews (
    id TEXT PRIMARY KEY, out_trade_no TEXT, reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ, resolved_by TEXT
);
