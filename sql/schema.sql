CREATE TABLE IF NOT EXISTS sessions (
  id SERIAL PRIMARY KEY,
  session_id TEXT UNIQUE NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('claude_ai', 'claude_code')),
  project TEXT NOT NULL DEFAULT 'default',
  summary TEXT,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  metadata JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS artifacts (
  id SERIAL PRIMARY KEY,
  project TEXT NOT NULL DEFAULT 'default',
  type TEXT NOT NULL CHECK (type IN ('decision', 'context', 'note', 'code_change')),
  title TEXT,
  content TEXT NOT NULL,
  tags JSONB DEFAULT '[]',
  source_session TEXT REFERENCES sessions(session_id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('english', content), 'B')
  ) STORED
);

CREATE INDEX IF NOT EXISTS idx_artifacts_search ON artifacts USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project);
CREATE INDEX IF NOT EXISTS idx_artifacts_type ON artifacts(project, type);
CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
