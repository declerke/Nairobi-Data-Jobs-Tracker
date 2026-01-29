import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
from urllib.parse import urlparse

import psycopg2
from psycopg2 import pool, sql, extras
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logger = logging.getLogger(__name__)

class DatabaseManager:
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        min_conn: int = 1,
        max_conn: int = 5
    ):
        self.host = host or os.getenv('DB_HOST', 'localhost')
        self.port = port or int(os.getenv('DB_PORT', 5432))
        self.database = database or os.getenv('DB_NAME', 'nairobi_jobs_db')
        self.user = user or os.getenv('DB_USER', 'postgres')
        self.password = password or os.getenv('DB_PASSWORD', '')
        
        self.min_conn = min_conn
        self.max_conn = max_conn
        self.connection_pool = None
        
        logger.info(f"DatabaseManager initialized for {self.host}:{self.port}/{self.database}")
    
    def initialize_pool(self):
        try:
            self.connection_pool = psycopg2.pool.SimpleConnectionPool(
                self.min_conn,
                self.max_conn,
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=10
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        if not self.connection_pool:
            self.initialize_pool()
        
        conn = self.connection_pool.getconn()
        try:
            yield conn
        finally:
            self.connection_pool.putconn(conn)
    
    def test_connection(self) -> bool:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version();")
                    version = cur.fetchone()[0]
                    logger.info(f"Database connection successful. PostgreSQL version: {version}")
                    return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def create_database_if_not_exists(self):
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database='postgres',
                user=self.user,
                password=self.password
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (self.database,)
                )
                exists = cur.fetchone()
                
                if not exists:
                    cur.execute(sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(self.database)
                    ))
                    logger.info(f"Database '{self.database}' created successfully")
                else:
                    logger.info(f"Database '{self.database}' already exists")
            
            conn.close()
        except Exception as e:
            logger.error(f"Error creating database: {e}")
            raise
    
    def create_tables(self):
        create_jobs_table = """
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            job_title VARCHAR(500) NOT NULL,
            company VARCHAR(300),
            location VARCHAR(300),
            salary_text VARCHAR(200),
            posting_url VARCHAR(1000) UNIQUE NOT NULL,
            posted_date DATE,
            description TEXT,
            full_description TEXT,
            source VARCHAR(100) NOT NULL,
            scrape_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            keywords_matched TEXT[],
            keyword_count INTEGER DEFAULT 0,
            is_remote BOOLEAN DEFAULT FALSE,
            is_hybrid BOOLEAN DEFAULT FALSE,
            experience_level VARCHAR(100),
            employment_type VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            application_deadline DATE,
            salary_min NUMERIC(12, 2),
            salary_max NUMERIC(12, 2),
            salary_currency VARCHAR(10)
        );
        
        CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);
        CREATE INDEX IF NOT EXISTS idx_jobs_posted_date ON jobs(posted_date DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_keyword_count ON jobs(keyword_count DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs(location);
        CREATE INDEX IF NOT EXISTS idx_jobs_scrape_timestamp ON jobs(scrape_timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_is_active ON jobs(is_active);
        CREATE INDEX IF NOT EXISTS idx_jobs_keywords_matched ON jobs USING GIN(keywords_matched);
        
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        
        DROP TRIGGER IF EXISTS update_jobs_updated_at ON jobs;
        CREATE TRIGGER update_jobs_updated_at
        BEFORE UPDATE ON jobs
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
        """
        
        create_scrape_runs_table = """
        CREATE TABLE IF NOT EXISTS scrape_runs (
            id SERIAL PRIMARY KEY,
            run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source VARCHAR(100) NOT NULL,
            jobs_found INTEGER DEFAULT 0,
            jobs_inserted INTEGER DEFAULT 0,
            jobs_updated INTEGER DEFAULT 0,
            jobs_duplicates INTEGER DEFAULT 0,
            status VARCHAR(50) DEFAULT 'success',
            error_message TEXT,
            duration_seconds NUMERIC(10, 2)
        );
        
        CREATE INDEX IF NOT EXISTS idx_scrape_runs_timestamp ON scrape_runs(run_timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_scrape_runs_source ON scrape_runs(source);
        """
        
        create_notifications_table = """
        CREATE TABLE IF NOT EXISTS email_notifications (
            id SERIAL PRIMARY KEY,
            job_id INTEGER REFERENCES jobs(id) ON DELETE CASCADE,
            sent_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            recipient VARCHAR(300),
            status VARCHAR(50) DEFAULT 'sent',
            error_message TEXT
        );
        
        CREATE INDEX IF NOT EXISTS idx_notifications_job_id ON email_notifications(job_id);
        CREATE INDEX IF NOT EXISTS idx_notifications_timestamp ON email_notifications(sent_timestamp DESC);
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_jobs_table)
                    cur.execute(create_scrape_runs_table)
                    cur.execute(create_notifications_table)
                    conn.commit()
                    logger.info("All database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise
    
    def insert_job(self, job_data: Dict[str, Any]) -> Optional[int]:
        insert_query = """
        INSERT INTO jobs (
            job_title, company, location, salary_text, posting_url,
            posted_date, description, full_description, source,
            keywords_matched, keyword_count, is_remote, is_hybrid
        ) VALUES (
            %(job_title)s, %(company)s, %(location)s, %(salary_text)s,
            %(posting_url)s, %(posted_date)s, %(description)s,
            %(full_description)s, %(source)s, %(keywords_matched)s,
            %(keyword_count)s, %(is_remote)s, %(is_hybrid)s
        )
        ON CONFLICT (posting_url) DO NOTHING
        RETURNING id;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(insert_query, job_data)
                    result = cur.fetchone()
                    conn.commit()
                    
                    if result:
                        job_id = result[0]
                        logger.debug(f"Inserted job ID {job_id}: {job_data.get('job_title')}")
                        return job_id
                    else:
                        logger.debug(f"Duplicate job skipped: {job_data.get('posting_url')}")
                        return None
        except Exception as e:
            logger.error(f"Error inserting job: {e}")
            logger.error(f"Job data: {job_data}")
            return None
    
    def insert_jobs_batch(self, jobs_list: List[Dict[str, Any]]) -> Tuple[int, int]:
        if not jobs_list:
            return 0, 0
        
        inserted_count = 0
        duplicate_count = 0
        
        for job_data in jobs_list:
            result = self.insert_job(job_data)
            if result:
                inserted_count += 1
            else:
                duplicate_count += 1
        
        logger.info(f"Batch insert completed: {inserted_count} inserted, {duplicate_count} duplicates")
        return inserted_count, duplicate_count
    
    def update_job_keywords(self, job_id: int, keywords: List[str]):
        update_query = """
        UPDATE jobs
        SET keywords_matched = %s,
            keyword_count = %s
        WHERE id = %s;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(update_query, (keywords, len(keywords), job_id))
                    conn.commit()
                    logger.debug(f"Updated keywords for job ID {job_id}")
        except Exception as e:
            logger.error(f"Error updating job keywords: {e}")
    
    def get_jobs_without_keywords(self, limit: int = 100) -> List[Dict[str, Any]]:
        query = """
        SELECT id, job_title, description, full_description
        FROM jobs
        WHERE keywords_matched IS NULL OR keyword_count = 0
        ORDER BY scrape_timestamp DESC
        LIMIT %s;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(query, (limit,))
                    jobs = cur.fetchall()
                    return [dict(job) for job in jobs]
        except Exception as e:
            logger.error(f"Error fetching jobs without keywords: {e}")
            return []
    
    def get_new_jobs_with_keywords(self, hours: int = 24, min_keywords: int = 1) -> List[Dict[str, Any]]:
        query = """
        SELECT 
            id, job_title, company, location, salary_text,
            posting_url, posted_date, description, source,
            keywords_matched, keyword_count, scrape_timestamp
        FROM jobs
        WHERE scrape_timestamp >= NOW() - INTERVAL '%s hours'
            AND keyword_count >= %s
            AND is_active = TRUE
        ORDER BY keyword_count DESC, scrape_timestamp DESC;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(query, (hours, min_keywords))
                    jobs = cur.fetchall()
                    logger.info(f"Found {len(jobs)} new jobs with ≥{min_keywords} keywords in last {hours}h")
                    return [dict(job) for job in jobs]
        except Exception as e:
            logger.error(f"Error fetching new jobs with keywords: {e}")
            return []
    
    def get_jobs_by_source(self, source: str, days: int = 7) -> List[Dict[str, Any]]:
        query = """
        SELECT *
        FROM jobs
        WHERE source = %s
            AND scrape_timestamp >= NOW() - INTERVAL '%s days'
        ORDER BY scrape_timestamp DESC;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(query, (source, days))
                    return [dict(job) for job in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching jobs by source: {e}")
            return []
    
    def log_scrape_run(
        self,
        source: str,
        jobs_found: int,
        jobs_inserted: int,
        jobs_updated: int = 0,
        jobs_duplicates: int = 0,
        status: str = 'success',
        error_message: str = None,
        duration_seconds: float = 0
    ) -> int:
        insert_query = """
        INSERT INTO scrape_runs (
            source, jobs_found, jobs_inserted, jobs_updated,
            jobs_duplicates, status, error_message, duration_seconds
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        insert_query,
                        (source, jobs_found, jobs_inserted, jobs_updated,
                         jobs_duplicates, status, error_message, duration_seconds)
                    )
                    run_id = cur.fetchone()[0]
                    conn.commit()
                    logger.info(f"Logged scrape run ID {run_id} for {source}")
                    return run_id
        except Exception as e:
            logger.error(f"Error logging scrape run: {e}")
            return -1
    
    def log_email_notification(
        self,
        job_id: int,
        recipient: str,
        status: str = 'sent',
        error_message: str = None
    ):
        insert_query = """
        INSERT INTO email_notifications (job_id, recipient, status, error_message)
        VALUES (%s, %s, %s, %s);
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(insert_query, (job_id, recipient, status, error_message))
                    conn.commit()
        except Exception as e:
            logger.error(f"Error logging email notification: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        stats_query = """
        SELECT 
            COUNT(*) as total_jobs,
            COUNT(DISTINCT source) as total_sources,
            COUNT(CASE WHEN keyword_count > 0 THEN 1 END) as jobs_with_keywords,
            COUNT(CASE WHEN scrape_timestamp >= NOW() - INTERVAL '24 hours' THEN 1 END) as jobs_last_24h,
            COUNT(CASE WHEN scrape_timestamp >= NOW() - INTERVAL '7 days' THEN 1 END) as jobs_last_7d,
            MAX(scrape_timestamp) as last_scrape,
            AVG(keyword_count) as avg_keyword_count
        FROM jobs
        WHERE is_active = TRUE;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(stats_query)
                    stats = dict(cur.fetchone())
                    logger.info(f"Database statistics: {stats}")
                    return stats
        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {}
    
    def cleanup_old_jobs(self, days: int = 90):
        update_query = """
        UPDATE jobs
        SET is_active = FALSE
        WHERE scrape_timestamp < NOW() - INTERVAL '%s days'
            AND is_active = TRUE
        RETURNING id;
        """
        
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(update_query, (days,))
                    archived_ids = cur.fetchall()
                    conn.commit()
                    logger.info(f"Archived {len(archived_ids)} jobs older than {days} days")
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {e}")
    
    def close_all_connections(self):
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("All database connections closed")

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'nairobi_jobs_db'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', '')
    )

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    db = DatabaseManager()
    if db.test_connection():
        print("✓ Connection test passed")
    try:
        db.create_tables()
        print("✓ Tables created/verified")
    except Exception as e:
        print(f"✗ Table creation failed: {e}")
    stats = db.get_statistics()
    print(f"✓ Database statistics: {stats}")
    db.close_all_connections()
    
_db_manager_instance = None

def get_db_manager() -> DatabaseManager:
    global _db_manager_instance
    if _db_manager_instance is None:
        _db_manager_instance = DatabaseManager()
    return _db_manager_instance

def test_connection() -> bool:
    manager = get_db_manager()
    return manager.test_connection()
