#!/usr/bin/env python3
"""
Nairobi Data Jobs Tracker — standalone pipeline runner.
No Airflow or Docker required.

Usage:
    python run.py               # full run
    python run.py --dry-run     # scrape + match, skip DB insert and email
    python run.py --source myjobmag   # run a single scraper only
"""

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    FeatureFlags,
    KeywordConfig,
    LoggingConfig,
    validate_config,
)
from scrapers import scrape_brightermonday, scrape_myjobmag, scrape_fuzu
from utils import get_db_manager, get_matcher, get_notifier, setup_logging
from utils.keyword_matcher import batch_process_keywords

SOURCES = {
    'brightermonday': (scrape_brightermonday, lambda: FeatureFlags.ENABLE_BRIGHTERMONDAY),
    'myjobmag':       (scrape_myjobmag,       lambda: FeatureFlags.ENABLE_MYJOBMAG),
    'fuzu':           (scrape_fuzu,            lambda: FeatureFlags.ENABLE_FUZU),
}


def run_pipeline(dry_run: bool = False, only_source: str = None):
    setup_logging(log_level=LoggingConfig.LEVEL, log_file=LoggingConfig.FILE)
    logger = logging.getLogger('run')

    logger.info("=" * 60)
    logger.info("Nairobi Data Jobs Tracker — Pipeline Start")
    logger.info(f"Timestamp : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Dry run   : {dry_run}")
    logger.info("=" * 60)

    is_valid, config_errors = validate_config()
    if not is_valid:
        for err in config_errors:
            logger.warning(f"Config: {err}")

    # Initialise database
    db = get_db_manager()
    try:
        db.create_database_if_not_exists()
        db.create_tables()
        logger.info("Database schema ready")
    except Exception as exc:
        logger.error(f"Database init failed: {exc}")
        sys.exit(1)

    # ── Scrape ──────────────────────────────────────────────────────────────
    all_jobs = []

    for name, (scrape_fn, enabled_fn) in SOURCES.items():
        if only_source and name != only_source:
            continue
        if not enabled_fn():
            logger.info(f"{name}: disabled in config, skipping")
            continue

        start = time.time()
        log_id = db.log_scrape_start(name)

        try:
            logger.info(f"{name}: starting scrape …")
            jobs = scrape_fn()
            duration = round(time.time() - start, 2)
            all_jobs.extend(jobs)

            db.log_scrape_end(
                log_id=log_id,
                jobs_found=len(jobs),
                jobs_new=len(jobs),
                jobs_updated=0,
                jobs_failed=0,
                status='success',
                duration_seconds=duration,
            )
            logger.info(f"{name}: {len(jobs)} jobs in {duration}s")

        except Exception as exc:
            duration = round(time.time() - start, 2)
            db.log_scrape_end(
                log_id=log_id,
                jobs_found=0,
                jobs_new=0,
                jobs_updated=0,
                jobs_failed=0,
                status='failed',
                error_message=str(exc),
                duration_seconds=duration,
            )
            logger.error(f"{name}: FAILED after {duration}s — {exc}")

    if not all_jobs:
        logger.warning("No jobs scraped from any source. Exiting.")
        return

    logger.info(f"Total raw jobs collected: {len(all_jobs)}")

    # ── Keyword matching ────────────────────────────────────────────────────
    processed = batch_process_keywords(
        all_jobs, keywords=KeywordConfig.get_all_keywords()
    )
    matched_count = sum(1 for j in processed if j.get('keyword_count', 0) > 0)
    logger.info(f"Keyword matching: {matched_count}/{len(processed)} jobs matched")

    if dry_run:
        logger.info("DRY RUN — top 5 results:")
        for job in sorted(processed, key=lambda j: j.get('keyword_count', 0), reverse=True)[:5]:
            kws = ', '.join(job.get('keywords_matched', [])[:4])
            logger.info(f"  [{job['source']}] {job['job_title']} @ {job['company']} | {kws}")
        logger.info("DRY RUN complete — no DB writes, no emails.")
        return

    # ── Insert to database ──────────────────────────────────────────────────
    inserted = 0
    duplicates = 0

    for job in processed:
        job_data = {
            'job_title':           job.get('job_title'),
            'company':             job.get('company'),
            'location':            job.get('location'),
            'salary_text':         job.get('salary_text'),
            'posting_url':         job.get('posting_url'),
            'posted_date':         job.get('posted_date'),
            'description_snippet': job.get('description_snippet'),
            'full_description':    job.get('full_description'),
            'source':              job.get('source'),
            'keywords_matched':    job.get('keywords_matched', []),
            'keyword_match_count': job.get('keyword_count', 0),
            'metadata':            job.get('metadata'),
        }
        result = db.insert_job(job_data)
        if result:
            inserted += 1
        else:
            duplicates += 1

    logger.info(f"DB insert: {inserted} new, {duplicates} duplicates")

    # ── Email notifications ─────────────────────────────────────────────────
    if FeatureFlags.ENABLE_EMAIL_NOTIFICATIONS:
        notifier = get_notifier()
        if notifier.enabled:
            new_jobs = db.get_unnotified_jobs(
                min_keywords=KeywordConfig.MIN_MATCHES_FOR_ALERT
            )
            if new_jobs:
                logger.info(f"Sending digest for {len(new_jobs)} matched jobs …")
                if notifier.send_daily_digest(new_jobs):
                    for job in new_jobs:
                        db.mark_job_notified(job['id'], recipient=notifier.recipient_email)
                    logger.info("Email digest sent")
                else:
                    logger.error("Email digest failed to send")
            else:
                logger.info("No new keyword-matched jobs to notify")
        else:
            logger.info("Email not configured — skipping notifications")

    # ── Summary ─────────────────────────────────────────────────────────────
    stats = db.get_statistics()
    logger.info("=" * 60)
    logger.info("Pipeline complete")
    logger.info(f"  This run : {inserted} inserted, {duplicates} duplicates")
    logger.info(f"  DB total : {stats.get('total_jobs', 'N/A')} active jobs")
    logger.info(f"  Last 24h : {stats.get('jobs_last_24h', 'N/A')} jobs")
    logger.info(f"  Matched  : {stats.get('jobs_with_keywords', 'N/A')} with keywords")
    logger.info("=" * 60)

    db.close_all_connections()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Nairobi Data Jobs Tracker pipeline')
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Scrape and match keywords but skip DB inserts and email'
    )
    parser.add_argument(
        '--source', choices=list(SOURCES.keys()),
        help='Run a single scraper instead of all three'
    )
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run, only_source=args.source)
