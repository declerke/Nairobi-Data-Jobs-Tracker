from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scrapers import scrape_brightermonday, scrape_myjobmag, scrape_fuzu
from utils import (
    get_db_manager,
    get_notifier,
    setup_logging,
    match_in_job,
)
from config import (
    AirflowConfig,
    TimezoneConfig,
    KeywordConfig,
    FeatureFlags,
    LoggingConfig
)

setup_logging(log_level=LoggingConfig.LEVEL, log_file=LoggingConfig.FILE)
logger = logging.getLogger(__name__)

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': AirflowConfig.TASK_RETRIES,
    'retry_delay': timedelta(minutes=AirflowConfig.TASK_RETRY_DELAY_MINUTES),
    'start_date': days_ago(1),
}

def scrape_brightermonday_task(**context):
    db = get_db_manager()
    log_id = db.log_scrape_start('BrighterMonday')
    
    try:
        jobs = scrape_brightermonday()
        context['task_instance'].xcom_push(key='brightermonday_jobs', value=jobs)
        
        db.log_scrape_end(
            log_id=log_id,
            jobs_found=len(jobs),
            jobs_new=len(jobs),
            jobs_updated=0,
            jobs_failed=0,
            status='success'
        )
        return len(jobs)
    
    except Exception as e:
        db.log_scrape_end(
            log_id=log_id,
            jobs_found=0,
            jobs_new=0,
            jobs_updated=0,
            jobs_failed=0,
            status='failed',
            error_message=str(e)
        )
        raise

def scrape_myjobmag_task(**context):
    db = get_db_manager()
    log_id = db.log_scrape_start('MyJobMag')
    
    try:
        jobs = scrape_myjobmag()
        context['task_instance'].xcom_push(key='myjobmag_jobs', value=jobs)
        
        db.log_scrape_end(
            log_id=log_id,
            jobs_found=len(jobs),
            jobs_new=len(jobs),
            jobs_updated=0,
            jobs_failed=0,
            status='success'
        )
        return len(jobs)
    
    except Exception as e:
        db.log_scrape_end(
            log_id=log_id,
            jobs_found=0,
            jobs_new=0,
            jobs_updated=0,
            jobs_failed=0,
            status='failed',
            error_message=str(e)
        )
        raise

def scrape_fuzu_task(**context):
    db = get_db_manager()
    log_id = db.log_scrape_start('Fuzu')
    
    try:
        jobs = scrape_fuzu()
        context['task_instance'].xcom_push(key='fuzu_jobs', value=jobs)
        
        db.log_scrape_end(
            log_id=log_id,
            jobs_found=len(jobs),
            jobs_new=len(jobs),
            jobs_updated=0,
            jobs_failed=0,
            status='success'
        )
        return len(jobs)
    
    except Exception as e:
        db.log_scrape_end(
            log_id=log_id,
            jobs_found=0,
            jobs_new=0,
            jobs_updated=0,
            jobs_failed=0,
            status='failed',
            error_message=str(e)
        )
        raise

def process_and_store_jobs_task(**context):
    ti = context['task_instance']
    db = get_db_manager()

    all_jobs = []

    for task_id, xcom_key in [
        ('scrape_brightermonday', 'brightermonday_jobs'),
        ('scrape_myjobmag',       'myjobmag_jobs'),
        ('scrape_fuzu',           'fuzu_jobs'),
    ]:
        try:
            jobs = ti.xcom_pull(key=xcom_key, task_ids=task_id)
            if jobs:
                all_jobs.extend(jobs)
        except Exception:
            pass

    if not all_jobs:
        return 0

    inserted_count = 0

    for job in all_jobs:
        try:
            job = match_in_job(job)

            job_data = {
                'job_title':           job['job_title'],
                'company':             job.get('company'),
                'location':            job.get('location'),
                'salary_text':         job.get('salary_text'),
                'posting_url':         job['posting_url'],
                'posted_date':         job.get('posted_date'),
                'description_snippet': job.get('description_snippet'),
                'full_description':    job.get('full_description'),
                'source':              job['source'],
                'keywords_matched':    job.get('keywords_matched', []),
                'keyword_match_count': job.get('keyword_count', 0),
                'metadata':            job.get('metadata'),
            }

            if db.insert_job(job_data):
                inserted_count += 1

        except Exception:
            continue

    ti.xcom_push(key='inserted_count', value=inserted_count)
    return inserted_count

def send_email_notifications_task(**context):
    if not FeatureFlags.ENABLE_EMAIL_NOTIFICATIONS:
        return 0
    
    ti = context['task_instance']
    db = get_db_manager()
    notifier = get_notifier()
    
    jobs = db.get_unnotified_jobs(min_keywords=KeywordConfig.MIN_MATCHES_FOR_ALERT)
    
    if not jobs:
        return 0
    
    try:
        success = notifier.send_daily_digest(jobs)

        if success:
            job_ids = [job['id'] for job in jobs]
            for job_id in job_ids:
                db.mark_job_notified(job_id)

            db.log_email_sent(
                recipient=notifier.recipient_email,
                subject=f"{len(jobs)} New Job Matches",
                jobs_count=len(jobs),
                job_ids=job_ids,
                status='sent'
            )
            return len(jobs)
        else:
            db.log_email_sent(
                recipient=notifier.config.RECIPIENT,
                subject=f"{len(jobs)} New Job Matches",
                jobs_count=len(jobs),
                job_ids=[job['id'] for job in jobs],
                status='failed',
                error_message='Email send failed'
            )
            return 0
    
    except Exception:
        return 0

def cleanup_old_data_task(**context):
    db = get_db_manager()
    try:
        archived = db.archive_old_jobs(days=180)
        db.cleanup_old_logs(days=90)
        return archived
    except Exception:
        return 0

with DAG(
    'nairobi_data_jobs_pipeline',
    default_args=default_args,
    schedule_interval=AirflowConfig.DAG_SCHEDULE,
    start_date=days_ago(1),
    catchup=AirflowConfig.DAG_CATCHUP,
    tags=['jobs', 'scraping', 'nairobi', 'data'],
) as dag:
    
    scrape_brightermonday = PythonOperator(
        task_id='scrape_brightermonday',
        python_callable=scrape_brightermonday_task,
        provide_context=True,
    )
    
    scrape_myjobmag = PythonOperator(
        task_id='scrape_myjobmag',
        python_callable=scrape_myjobmag_task,
        provide_context=True,
    )
    
    scrape_fuzu = PythonOperator(
        task_id='scrape_fuzu',
        python_callable=scrape_fuzu_task,
        provide_context=True,
    )
    
    process_and_store = PythonOperator(
        task_id='process_and_store_jobs',
        python_callable=process_and_store_jobs_task,
        provide_context=True,
    )
    
    send_notifications = PythonOperator(
        task_id='send_email_notifications',
        python_callable=send_email_notifications_task,
        provide_context=True,
    )
    
    cleanup = PythonOperator(
        task_id='cleanup_old_data',
        python_callable=cleanup_old_data_task,
        provide_context=True,
    )
    
    [scrape_brightermonday, scrape_myjobmag, scrape_fuzu] >> process_and_store >> send_notifications >> cleanup
