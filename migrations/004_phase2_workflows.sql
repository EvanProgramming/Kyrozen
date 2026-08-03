-- Phase 2: persist project workflow classification without changing old projects.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS project_type TEXT NOT NULL DEFAULT 'software';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS budget TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS workflow_version TEXT NOT NULL DEFAULT 'phase2.v1';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS type_source TEXT NOT NULL DEFAULT 'default';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS type_confidence TEXT NOT NULL DEFAULT 'low';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS type_confirmed BOOLEAN NOT NULL DEFAULT FALSE;
