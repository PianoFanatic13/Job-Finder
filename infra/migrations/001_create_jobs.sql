CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  url TEXT UNIQUE NOT NULL,
  url_hash CHAR(64) NOT NULL,
  company_name TEXT NOT NULL,
  title TEXT NOT NULL,
  location TEXT[] DEFAULT '{}',
  is_remote BOOLEAN,
  required_grad_year INT,
  grad_year_flexible BOOLEAN DEFAULT FALSE,
  estimated_pay_hourly INT,
  tech_stack TEXT[] DEFAULT '{}',
  sponsors_visa BOOLEAN,
  raw_description TEXT,
  ai_extraction_status TEXT NOT NULL DEFAULT 'partial' CHECK (ai_extraction_status IN ('success', 'partial', 'failed')),
  ai_confidence_score FLOAT,
  source TEXT,
  date_posted TIMESTAMPTZ,
  date_ingested TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  date_processed TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS jobs_url_hash_key ON jobs(url_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_required_grad_year ON jobs(required_grad_year);
CREATE INDEX IF NOT EXISTS idx_jobs_estimated_pay_hourly ON jobs(estimated_pay_hourly);
CREATE INDEX IF NOT EXISTS idx_jobs_is_remote ON jobs(is_remote);
CREATE INDEX IF NOT EXISTS idx_jobs_tech_stack_gin ON jobs USING GIN(tech_stack);
CREATE INDEX IF NOT EXISTS idx_jobs_date_ingested_desc ON jobs(date_ingested DESC);
