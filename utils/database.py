import json
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
                if not cur.fetchone():
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
        # Schema aligned with setup_database.sql
        create_jobs_table = """
        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            job_title VARCHAR(500) NOT NULL,
            company VARCHAR(300),
            location VARCHAR(200),
            salary_text VARCHAR(200),
            description_snippet TEXT,
            full_description TEXT,
            posting_url VARCHAR(1000) UNIQUE NOT NULL,
            source VARCHAR(50) NOT NULL,
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
        CREATE INDEX IF NOT EXISTS idx_jobs_keyword_count ON jobs(keyword_match_count DESC)
            WHERE keyword_match_count > 0;
        CREATE INDEX IF NOT EXISTS idx_jobs_active ON jobs(is_active, scrape_timestamp DESC);

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
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """

        create_scrape_logs_table = """
        CREATE TABLE IF NOT EXISTS scrape_logs (
            id SERIAL PRIMARY KEY,
            source VARCHAR(50) NOT NULL,
            scrape_start TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            scrape_end TIMESTAMP,
            jobs_found INTEGER DEFAULT 0,
            jobs_new INTEGER DEFAULT 0,
            jobs_updated INTEGER DEFAULT 0,
            jobs_failed INTEGER DEFAULT 0,
            status VARCHAR(20),
            error_message TEXT,
            duration_seconds NUMERIC(10, 2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_scrape_logs_source
            ON scrape_logs(source, scrape_start DESC);
        """

        create_email_logs_table = """
        CREATE TABLE IF NOT EXISTS email_logs (
            id SERIAL PRIMARY KEY,
            recipient VARCHAR(255) NOT NULL,
            subject VARCHAR(500),
            jobs_count INTEGER DEFAULT 0,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(20),
            error_message TEXT,
            job_ids INTEGER[]
        );

        CREATE INDEX IF NOT EXISTS idx_email_logs_sent ON email_logs(sent_at DESC);
        """

        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_jobs_table)
                    cur.execute(create_scrape_logs_table)
                    cur.execute(create_email_logs_table)
                    conn.commit()
                    logger.info("All database tables created/verified successfully")
        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise

    def insert_job(self, job_data: Dict[str, Any]) -> Optional[int]:
        insert_query = """
        INSERT INTO jobs (
            job_title, company, location, salary_text, description_snippet,
            full_description, posting_url, source, posted_date,
            keywords_matched, keyword_match_count, metadata
        ) VALUES (
            %(job_title)s, %(company)s, %(location)s, %(salary_text)s,
            %(description_snippet)s, %(full_description)s, %(posting_url)s,
            %(source)s, %(posted_date)s, %(keywords_matched)s,
            %(keyword_match_count)s, %(metadata)s
        )
        ON CONFLICT (posting_url) DO NOTHING
        RETURNING id;
        """
        try:
            # psycopg2 cannot auto-serialize dict → JSONB; convert explicitly
            row = dict(job_data)
            if isinstance(row.get('metadata'), dict):
                row['metadata'] = json.dumps(row['metadata'])
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(insert_query, row)
                    result = cur.fetchone()
                    conn.commit()
                    if result:
                        logger.debug(f"Inserted job ID {result[0]}: {job_data.get('job_title')}")
                        return result[0]
                    else:
                        logger.debug(f"Duplicate skipped: {job_data.get('posting_url')}")
                        return None
        except Exception as e:
            logger.error(f"Error inserting job: {e}")
            return None

    def insert_jobs_batch(self, jobs_list: List[Dict[str, Any]]) -> Tuple[int, int]:
        inserted = 0
        duplicates = 0
        for job_data in jobs_list:
            result = self.insert_job(job_data)
            if result:
                inserted += 1
            else:
                duplicates += 1
        logger.info(f"Batch insert: {inserted} inserted, {duplicates} duplicates")
        return inserted, duplicates

    def update_job_keywords(self, job_id: int, keywords: List[str]):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE jobs SET keywords_matched = %s, keyword_match_count = %s WHERE id = %s;",
                        (keywords, len(keywords), job_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error updating keywords for job {job_id}: {e}")

    def get_jobs_without_keywords(self, limit: int = 100) -> List[Dict[str, Any]]:
        query = """
        SELECT id, job_title, description_snippet, full_description
        FROM jobs
        WHERE keywords_matched IS NULL OR keyword_match_count = 0
        ORDER BY scrape_timestamp DESC
        LIMIT %s;
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(query, (limit,))
                    return [dict(job) for job in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching jobs without keywords: {e}")
            return []

    def get_new_jobs_with_keywords(self, hours: int = 24, min_keywords: int = 1) -> List[Dict[str, Any]]:
        query = """
        SELECT id, job_title, company, location, salary_text,
               posting_url, posted_date, description_snippet, source,
               keywords_matched, keyword_match_count, scrape_timestamp
        FROM jobs
        WHERE scrape_timestamp >= NOW() - INTERVAL '1 hour' * %s
          AND keyword_match_count >= %s
          AND is_active = TRUE
        ORDER BY keyword_match_count DESC, scrape_timestamp DESC;
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
        cutoff = datetime.now() - timedelta(days=days)
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(
                        "SELECT * FROM jobs WHERE source = %s AND scrape_timestamp >= %s ORDER BY scrape_timestamp DESC;",
                        (source, cutoff)
                    )
                    return [dict(job) for job in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching jobs by source: {e}")
            return []

    # ── Scrape logging ───────────────────────────────────────────────────────

    def log_scrape_start(self, source: str) -> int:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO scrape_logs (source, scrape_start, status) VALUES (%s, NOW(), 'partial') RETURNING id;",
                        (source,)
                    )
                    run_id = cur.fetchone()[0]
                    conn.commit()
                    return run_id
        except Exception as e:
            logger.error(f"Error starting scrape log: {e}")
            return -1

    def log_scrape_end(
        self,
        log_id: int,
        jobs_found: int,
        jobs_new: int,
        jobs_updated: int,
        jobs_failed: int,
        status: str,
        error_message: str = None,
        duration_seconds: float = 0
    ):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE scrape_logs
                        SET scrape_end = NOW(),
                            jobs_found = %s,
                            jobs_new = %s,
                            jobs_updated = %s,
                            jobs_failed = %s,
                            status = %s,
                            error_message = %s,
                            duration_seconds = %s
                        WHERE id = %s;
                        """,
                        (jobs_found, jobs_new, jobs_updated, jobs_failed,
                         status, error_message, duration_seconds, log_id)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error ending scrape log: {e}")

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
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO scrape_logs
                            (source, scrape_start, scrape_end, jobs_found, jobs_new,
                             jobs_updated, jobs_failed, status, error_message, duration_seconds)
                        VALUES (%s, NOW(), NOW(), %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id;
                        """,
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

    # ── Notification helpers ─────────────────────────────────────────────────

    def get_unnotified_jobs(self, min_keywords: int = 1) -> List[Dict[str, Any]]:
        query = """
        SELECT id, job_title, company, location, salary_text,
               posting_url, posted_date, description_snippet, source,
               keywords_matched, keyword_match_count, scrape_timestamp
        FROM jobs
        WHERE is_active = TRUE
          AND keyword_match_count >= %s
          AND is_notified = FALSE
        ORDER BY keyword_match_count DESC, scrape_timestamp DESC;
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(query, (min_keywords,))
                    return [dict(job) for job in cur.fetchall()]
        except Exception as e:
            logger.error(f"Error fetching unnotified jobs: {e}")
            return []

    def mark_job_notified(self, job_id: int, recipient: str = ''):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE jobs SET is_notified = TRUE, notification_sent_at = NOW() WHERE id = %s;",
                        (job_id,)
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error marking job {job_id} as notified: {e}")

    def log_email_notification(
        self,
        job_id: int,
        recipient: str,
        status: str = 'sent',
        error_message: str = None
    ):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO email_logs (recipient, subject, jobs_count, status, error_message, job_ids)
                        VALUES (%s, %s, 1, %s, %s, %s);
                        """,
                        (recipient, f'Job alert: job {job_id}', status, error_message, [job_id])
                    )
                    conn.commit()
        except Exception as e:
            logger.error(f"Error logging email notification: {e}")

    def log_email_sent(
        self,
        recipient: str,
        subject: str,
        jobs_count: int,
        job_ids: List[int],
        status: str,
        error_message: str = None
    ):
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO email_logs (recipient, subject, jobs_count, status, error_message, job_ids)
                        VALUES (%s, %s, %s, %s, %s, %s);
                        """,
                        (recipient, subject, jobs_count, status, error_message, job_ids)
                    )
                    conn.commit()
                    logger.info(f"Logged email to {recipient}: {jobs_count} jobs, status={status}")
        except Exception as e:
            logger.error(f"Error logging email sent: {e}")

    # ── Maintenance ──────────────────────────────────────────────────────────

    def get_statistics(self) -> Dict[str, Any]:
        stats_query = """
        SELECT
            COUNT(*)                                                            AS total_jobs,
            COUNT(DISTINCT source)                                              AS total_sources,
            COUNT(CASE WHEN keyword_match_count > 0 THEN 1 END)                AS jobs_with_keywords,
            COUNT(CASE WHEN scrape_timestamp >= NOW() - INTERVAL '24 hours'
                       THEN 1 END)                                             AS jobs_last_24h,
            COUNT(CASE WHEN scrape_timestamp >= NOW() - INTERVAL '7 days'
                       THEN 1 END)                                             AS jobs_last_7d,
            MAX(scrape_timestamp)                                               AS last_scrape,
            AVG(keyword_match_count)                                            AS avg_keyword_count
        FROM jobs
        WHERE is_active = TRUE;
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                    cur.execute(stats_query)
                    return dict(cur.fetchone())
        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {}

    def cleanup_old_jobs(self, days: int = 90):
        cutoff = datetime.now() - timedelta(days=days)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE jobs SET is_active = FALSE WHERE scrape_timestamp < %s AND is_active = TRUE RETURNING id;",
                        (cutoff,)
                    )
                    archived = cur.fetchall()
                    conn.commit()
                    logger.info(f"Archived {len(archived)} jobs older than {days} days")
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {e}")

    def archive_old_jobs(self, days: int = 180) -> int:
        cutoff = datetime.now() - timedelta(days=days)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE jobs SET is_active = FALSE WHERE scrape_timestamp < %s AND is_active = TRUE RETURNING id;",
                        (cutoff,)
                    )
                    archived = cur.fetchall()
                    conn.commit()
                    logger.info(f"Archived {len(archived)} jobs older than {days} days")
                    return len(archived)
        except Exception as e:
            logger.error(f"Error archiving old jobs: {e}")
            return 0

    def cleanup_old_logs(self, days: int = 90):
        cutoff = datetime.now() - timedelta(days=days)
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM scrape_logs WHERE scrape_start < %s;", (cutoff,))
                    cur.execute("DELETE FROM email_logs WHERE sent_at < %s;", (cutoff,))
                    conn.commit()
                    logger.info(f"Cleaned up logs older than {days} days")
        except Exception as e:
            logger.error(f"Error cleaning up logs: {e}")

    def close_all_connections(self):
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("All database connections closed")


# ── Convenience singletons ───────────────────────────────────────────────────

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'nairobi_jobs_db'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', '')
    )


_db_manager_instance = None


def get_db_manager() -> DatabaseManager:
    global _db_manager_instance
    if _db_manager_instance is None:
        _db_manager_instance = DatabaseManager()
    return _db_manager_instance


def test_connection() -> bool:
    return get_db_manager().test_connection()


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
    print(f"✓ Statistics: {stats}")
    db.close_all_connections()
