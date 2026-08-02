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
