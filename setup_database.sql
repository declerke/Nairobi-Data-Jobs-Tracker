CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    job_title VARCHAR(500) NOT NULL,
    company VARCHAR(300),
    location VARCHAR(200),
    salary_text VARCHAR(200),
    description_snippet TEXT,
    full_description TEXT,
    posting_url VARCHAR(1000) UNIQUE NOT NULL,
    source VARCHAR(50) NOT NULL CHECK (source IN ('BrighterMonday', 'MyJobMag', 'Fuzu', 'Other')),
    posted_date DATE,
    scrape_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    keywords_matched TEXT[],
    keyword_match_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    is_notified BOOLEAN DEFAULT FALSE,
    notification_sent_at TIMESTAMP,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_scrape_timestamp ON jobs(scrape_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_keywords ON jobs USING GIN(keywords_matched);
CREATE INDEX IF NOT EXISTS idx_jobs_keyword_count ON jobs(keyword_match_count DESC) WHERE keyword_match_count > 0;
CREATE INDEX IF NOT EXISTS idx_jobs_notification ON jobs(is_notified, keyword_match_count) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active, scrape_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_active_recent ON jobs(is_active, scrape_timestamp DESC, keyword_match_count DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_fulltext ON jobs USING GIN(
    to_tsvector('english', COALESCE(job_title, '') || ' ' || COALESCE(full_description, ''))
);

CREATE TABLE IF NOT EXISTS scrape_logs (
    id SERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    scrape_start TIMESTAMP NOT NULL,
    scrape_end TIMESTAMP,
    jobs_found INTEGER DEFAULT 0,
    jobs_new INTEGER DEFAULT 0,
    jobs_updated INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,
    status VARCHAR(20) CHECK (status IN ('success', 'partial', 'failed')),
    error_message TEXT,
    duration_seconds NUMERIC(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scrape_logs_source ON scrape_logs(source, scrape_start DESC);
CREATE INDEX IF NOT EXISTS idx_scrape_logs_status ON scrape_logs(status, scrape_start DESC);

CREATE TABLE IF NOT EXISTS email_logs (
    id SERIAL PRIMARY KEY,
    recipient VARCHAR(255) NOT NULL,
    subject VARCHAR(500),
    jobs_count INTEGER DEFAULT 0,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) CHECK (status IN ('sent', 'failed')),
    error_message TEXT,
    job_ids INTEGER[]
);

CREATE INDEX IF NOT EXISTS idx_email_logs_sent ON email_logs(sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_logs_status ON email_logs(status, sent_at DESC);

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_jobs_updated_at
BEFORE UPDATE ON jobs
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE FUNCTION update_keyword_match_count()
RETURNS TRIGGER AS $$
BEGIN
    NEW.keyword_match_count = COALESCE(array_length(NEW.keywords_matched, 1), 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_jobs_keyword_count
BEFORE INSERT OR UPDATE OF keywords_matched ON jobs
FOR EACH ROW
EXECUTE FUNCTION update_keyword_match_count();

CREATE OR REPLACE VIEW recent_matched_jobs AS
SELECT 
    id,
    job_title,
    company,
    location,
    salary_text,
    posting_url,
    source,
    posted_date,
    keywords_matched,
    keyword_match_count,
    scrape_timestamp,
    is_notified
FROM jobs
WHERE 
    is_active = TRUE
    AND keyword_match_count > 0
    AND scrape_timestamp > CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY keyword_match_count DESC, scrape_timestamp DESC;

CREATE OR REPLACE VIEW daily_job_stats AS
SELECT 
    DATE(scrape_timestamp) as scrape_date,
    source,
    COUNT(*) as total_jobs,
    COUNT(CASE WHEN keyword_match_count > 0 THEN 1 END) as matched_jobs,
    AVG(keyword_match_count) as avg_keywords,
    COUNT(CASE WHEN is_notified THEN 1 END) as notified_jobs
FROM jobs
WHERE scrape_timestamp > CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY scrape_date, source
ORDER BY scrape_date DESC, source;

CREATE OR REPLACE VIEW trending_keywords AS
SELECT 
    unnest(keywords_matched) as keyword,
    COUNT(*) as frequency,
    COUNT(DISTINCT source) as sources_count,
    MAX(scrape_timestamp) as last_seen
FROM jobs
WHERE scrape_timestamp > CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY keyword
ORDER BY frequency DESC;

CREATE OR REPLACE VIEW company_hiring_stats AS
SELECT 
    company,
    COUNT(*) as total_postings,
    COUNT(CASE WHEN keyword_match_count > 0 THEN 1 END) as relevant_postings,
    MIN(scrape_timestamp) as first_seen,
    MAX(scrape_timestamp) as last_seen,
    array_agg(DISTINCT source) as job_boards
FROM jobs
WHERE 
    company IS NOT NULL 
    AND scrape_timestamp > CURRENT_TIMESTAMP - INTERVAL '60 days'
GROUP BY company
HAVING COUNT(*) >= 2
ORDER BY total_postings DESC;

CREATE OR REPLACE FUNCTION get_jobs_by_keywords(keyword_list TEXT[])
RETURNS TABLE (
    job_id INTEGER,
    job_title VARCHAR,
    company VARCHAR,
    keywords_matched TEXT[],
    posting_url VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        j.id,
        j.job_title,
        j.company,
        j.keywords_matched,
        j.posting_url
    FROM jobs j
    WHERE j.keywords_matched && keyword_list
    AND j.is_active = TRUE
    ORDER BY j.keyword_match_count DESC, j.scrape_timestamp DESC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION archive_old_jobs(days_old INTEGER DEFAULT 180)
RETURNS INTEGER AS $$
DECLARE
    archived_count INTEGER;
BEGIN
    UPDATE jobs
    SET is_active = FALSE
    WHERE scrape_timestamp < CURRENT_TIMESTAMP - (days_old || ' days')::INTERVAL
    AND is_active = TRUE;
    
    GET DIAGNOSTICS archived_count = ROW_COUNT;
    RETURN archived_count;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_unnotified_jobs()
RETURNS TABLE (
    job_id INTEGER,
    job_title VARCHAR,
    company VARCHAR,
    location VARCHAR,
    keywords_matched TEXT[],
    keyword_match_count INTEGER,
    posting_url VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        j.id,
        j.job_title,
        j.company,
        j.location,
        j.keywords_matched,
        j.keyword_match_count,
        j.posting_url
    FROM jobs j
    WHERE 
        j.is_active = TRUE
        AND j.is_notified = FALSE
        AND j.keyword_match_count > 0
    ORDER BY j.keyword_match_count DESC, j.scrape_timestamp DESC;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE PROCEDURE cleanup_old_logs(days_to_keep INTEGER DEFAULT 90)
LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM scrape_logs 
    WHERE scrape_start < CURRENT_TIMESTAMP - (days_to_keep || ' days')::INTERVAL;
    
    DELETE FROM email_logs 
    WHERE sent_at < CURRENT_TIMESTAMP - (days_to_keep || ' days')::INTERVAL;
END;
$$;

CREATE TABLE IF NOT EXISTS keyword_priorities (
    keyword VARCHAR(100) PRIMARY KEY,
    priority INTEGER DEFAULT 1 CHECK (priority BETWEEN 1 AND 5),
    category VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO keyword_priorities (keyword, priority, category) VALUES
    ('FastAPI', 5, 'Framework'),
    ('PostgreSQL', 5, 'Database'),
    ('MySQL', 4, 'Database'),
    ('Flask', 4, 'Framework'),
    ('Pandas', 5, 'Data Processing'),
    ('NumPy', 4, 'Data Processing'),
    ('Azure', 5, 'Cloud'),
    ('AWS', 5, 'Cloud'),
    ('GCP', 5, 'Cloud'),
    ('Docker', 4, 'DevOps'),
    ('Kafka', 4, 'Data Streaming'),
    ('Git', 3, 'Version Control'),
    ('GitHub', 3, 'Version Control'),
    ('Python', 5, 'Programming'),
    ('SQL', 5, 'Database'),
    ('ETL', 5, 'Data Engineering'),
    ('Airflow', 5, 'Orchestration'),
    ('Spark', 4, 'Big Data'),
    ('Tableau', 3, 'Visualization'),
    ('Power BI', 3, 'Visualization')
ON CONFLICT (keyword) DO NOTHING;

DO $$
BEGIN
    RAISE NOTICE 'Nairobi Data Jobs Tracker - Database Schema Created Successfully!';
END $$;