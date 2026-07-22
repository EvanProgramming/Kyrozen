-- Migration: Add user ownership to existing Kyrozen SQLite schema.
-- Run this if you are upgrading from a pre-Phase 10 version.

ALTER TABLE projects ADD COLUMN user_id TEXT;
ALTER TABLE tasks ADD COLUMN user_id TEXT;
ALTER TABLE decisions ADD COLUMN user_id TEXT;
ALTER TABLE artifacts ADD COLUMN user_id TEXT;

CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions(user_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_user ON artifacts(user_id);
