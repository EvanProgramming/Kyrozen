-- Add desktop client support to Kyrozen Supabase schema

-- Tasks need to know whether they require a local desktop client and which client is handling them.
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS mode TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS requires_local_client BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assigned_client_id TEXT;

-- Desktop clients connected on behalf of a user.
CREATE TABLE IF NOT EXISTS desktop_clients (
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    device_name TEXT NOT NULL DEFAULT 'Unknown Device',
    client_version TEXT,
    platform TEXT,
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    online BOOLEAN NOT NULL DEFAULT TRUE,
    current_project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE desktop_clients ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Users can only access their own desktop clients" ON desktop_clients;
CREATE POLICY "Users can only access their own desktop clients"
    ON desktop_clients FOR ALL
    USING (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS idx_desktop_clients_user ON desktop_clients(user_id);
CREATE INDEX IF NOT EXISTS idx_desktop_clients_online ON desktop_clients(user_id, online, last_active_at);
