-- Kyrozen membership entitlements and persistent dual usage ledger.
-- Apply this migration before enabling membership endpoints on Supabase.
CREATE TABLE IF NOT EXISTS public.memberships (
    user_id TEXT PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active',
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,
    price_rmb NUMERIC(12, 4) NOT NULL DEFAULT 0,
    monthly_cost_limit_rmb NUMERIC(12, 4) NOT NULL DEFAULT 0,
    free_subsidy_limit_rmb NUMERIC(12, 4) NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.membership_seats (
    owner_user_id TEXT NOT NULL,
    member_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (owner_user_id, member_user_id)
);
CREATE TABLE IF NOT EXISTS public.project_creation_events (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_project_creation_owner ON public.project_creation_events(owner_user_id, created_at);
CREATE TABLE IF NOT EXISTS public.usage_events (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT,
    task_id TEXT,
    kind TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cache_hit_tokens INTEGER NOT NULL DEFAULT 0,
    tool_calls INTEGER NOT NULL DEFAULT 0,
    credits INTEGER NOT NULL DEFAULT 0,
    cost_rmb NUMERIC(12, 6) NOT NULL DEFAULT 0,
    formula_version TEXT NOT NULL DEFAULT 'v1',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_usage_owner_time ON public.usage_events(owner_user_id, created_at);
CREATE TABLE IF NOT EXISTS public.task_budget_states (
    task_id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'running',
    reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.afdian_accounts (
    user_id TEXT PRIMARY KEY,
    afdian_user_id TEXT UNIQUE NOT NULL,
    afdian_user_private_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.afdian_oauth_states (
    state TEXT PRIMARY KEY, user_id TEXT NOT NULL, redirect_uri TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL, consumed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS public.afdian_checkout_sessions (
    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, plan TEXT NOT NULL, plan_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', checkout_url TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), expires_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS public.afdian_orders (
    out_trade_no TEXT PRIMARY KEY, user_id TEXT, afdian_user_id TEXT,
    afdian_user_private_id TEXT, plan TEXT, plan_id TEXT, month INTEGER NOT NULL DEFAULT 1,
    total_amount NUMERIC(12,4), status INTEGER, raw_payload JSONB,
    verification_status TEXT NOT NULL DEFAULT 'pending', review_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.membership_grants (
    id TEXT PRIMARY KEY, out_trade_no TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL,
    plan TEXT NOT NULL, starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.membership_payment_reviews (
    id TEXT PRIMARY KEY, out_trade_no TEXT, reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolved_at TIMESTAMPTZ, resolved_by TEXT
);
