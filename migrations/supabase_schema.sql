-- Kyrozen Beta — Supabase PostgreSQL Schema
-- Run this in your Supabase SQL Editor after creating the project.

-- User profiles mirror Supabase Auth users
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    beta_invite_code TEXT,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger to auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (user_id, email, name, role)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'name', split_part(NEW.email, '@', 1)),
        COALESCE(NEW.raw_user_meta_data->>'role', 'user')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Projects
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    current_stage TEXT NOT NULL DEFAULT 'problem_discovery',
    next_steps TEXT,
    blocked_reason TEXT,
    progress INTEGER DEFAULT 0,
    risks JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own projects" ON projects;
CREATE POLICY "Users can only access their own projects"
    ON projects FOR ALL
    USING (user_id = auth.uid());

-- Tasks
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    steps JSONB DEFAULT '[]',
    result JSONB,
    errors JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own tasks" ON tasks;
CREATE POLICY "Users can only access their own tasks"
    ON tasks FOR ALL
    USING (user_id = auth.uid());

-- Decisions
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    reason TEXT,
    alternatives JSONB DEFAULT '[]',
    rejected_reasons JSONB DEFAULT '{}',
    source TEXT DEFAULT 'agent',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own decisions" ON decisions;
CREATE POLICY "Users can only access their own decisions"
    ON decisions FOR ALL
    USING (user_id = auth.uid());

-- Artifacts
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    change_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own artifacts" ON artifacts;
CREATE POLICY "Users can only access their own artifacts"
    ON artifacts FOR ALL
    USING (user_id = auth.uid());

-- Learning records (Phase 9)
CREATE TABLE IF NOT EXISTS learning_records (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    memory TEXT NOT NULL,
    memory_type TEXT NOT NULL,
    source TEXT,
    confidence TEXT NOT NULL DEFAULT 'low',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    scope TEXT NOT NULL DEFAULT 'private',
    tags JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE learning_records ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own learning records" ON learning_records;
CREATE POLICY "Users can only access their own learning records"
    ON learning_records FOR ALL
    USING (user_id = auth.uid());

-- Failure knowledge
CREATE TABLE IF NOT EXISTS failure_knowledge (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    problem TEXT NOT NULL,
    cause TEXT,
    solution TEXT,
    affected_scope TEXT,
    verification TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE failure_knowledge ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own failure knowledge" ON failure_knowledge;
CREATE POLICY "Users can only access their own failure knowledge"
    ON failure_knowledge FOR ALL
    USING (user_id = auth.uid());

-- Success knowledge
CREATE TABLE IF NOT EXISTS success_knowledge (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    goal TEXT,
    solution TEXT NOT NULL,
    conditions TEXT,
    result TEXT,
    confidence TEXT NOT NULL DEFAULT 'medium',
    verification_status TEXT NOT NULL DEFAULT 'unverified',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE success_knowledge ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own success knowledge" ON success_knowledge;
CREATE POLICY "Users can only access their own success knowledge"
    ON success_knowledge FOR ALL
    USING (user_id = auth.uid());

-- Suggestions
CREATE TABLE IF NOT EXISTS suggestions (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    suggestion TEXT NOT NULL,
    reason TEXT,
    evidence JSONB DEFAULT '[]',
    impact TEXT,
    priority TEXT NOT NULL DEFAULT 'medium',
    status TEXT NOT NULL DEFAULT 'new',
    category TEXT,
    related_learning_ids JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE suggestions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own suggestions" ON suggestions;
CREATE POLICY "Users can only access their own suggestions"
    ON suggestions FOR ALL
    USING (user_id = auth.uid());

-- User feedback (Phase 10)
CREATE TABLE IF NOT EXISTS user_feedback (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    type TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT DEFAULT 'medium',
    status TEXT DEFAULT 'open',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own feedback" ON user_feedback;
CREATE POLICY "Users can only access their own feedback"
    ON user_feedback FOR ALL
    USING (user_id = auth.uid());

-- Events / Analytics (Phase 10)
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    payload JSONB DEFAULT '{}',
    session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own events" ON events;
CREATE POLICY "Users can only access their own events"
    ON events FOR ALL
    USING (user_id = auth.uid());

-- Error logs (Phase 10)
CREATE TABLE IF NOT EXISTS error_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    endpoint TEXT,
    method TEXT,
    error_type TEXT,
    message TEXT,
    stack TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE error_logs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own error logs" ON error_logs;
CREATE POLICY "Users can only access their own error logs"
    ON error_logs FOR ALL
    USING (user_id = auth.uid());

-- Indexes
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_decisions_user_id ON decisions(user_id);
CREATE INDEX IF NOT EXISTS idx_decisions_project_id ON decisions(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_user_id ON artifacts(user_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_project_id ON artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(type);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_project_id ON events(project_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_error_logs_user_id ON error_logs(user_id);
