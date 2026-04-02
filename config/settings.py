import os
from pathlib import Path
from typing import List
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / '.env'

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    print(f"Warning: .env file not found at {ENV_FILE}")
    print("Using environment variables or defaults.")

class DatabaseConfig:
    HOST = os.getenv('DB_HOST', 'localhost')
    PORT = int(os.getenv('DB_PORT', '5432'))
    NAME = os.getenv('DB_NAME', 'nairobi_jobs')
    USER = os.getenv('DB_USER', 'jobs_user')
    PASSWORD = os.getenv('DB_PASSWORD', '')
    POOL_SIZE = int(os.getenv('DB_POOL_SIZE', '5'))
    
    @classmethod
    def get_connection_string(cls) -> str:
        return f"postgresql://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.NAME}"
    
    @classmethod
    def get_connection_dict(cls) -> dict:
        return {
            'host': cls.HOST,
            'port': cls.PORT,
            'database': cls.NAME,
            'user': cls.USER,
            'password': cls.PASSWORD
        }

class EmailConfig:
    HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
    PORT = int(os.getenv('EMAIL_PORT', '587'))
    USE_TLS = os.getenv('EMAIL_USE_TLS', 'True').lower() == 'true'
    USER = os.getenv('EMAIL_USER', '')
    PASSWORD = os.getenv('EMAIL_PASSWORD', '')
    RECIPIENT = os.getenv('EMAIL_RECIPIENT', os.getenv('EMAIL_USER', ''))
    SUBJECT_PREFIX = os.getenv('EMAIL_SUBJECT_PREFIX', '[Nairobi Jobs]')
    
    @classmethod
    def is_configured(cls) -> bool:
        return bool(cls.USER and cls.PASSWORD and cls.RECIPIENT)

class ScrapingConfig:
    USER_AGENT = os.getenv(
        'USER_AGENT',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    DELAY_MIN = float(os.getenv('REQUEST_DELAY_MIN', '3'))
    DELAY_MAX = float(os.getenv('REQUEST_DELAY_MAX', '8'))
    TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', '3'))
    MAX_JOBS_PER_SITE = int(os.getenv('MAX_JOBS_PER_SITE', '100'))

class JobBoardURLs:
    BRIGHTERMONDAY = os.getenv(
        'BRIGHTERMONDAY_URL',
        'https://www.brightermonday.co.ke/jobs/search'
    )
    MYJOBMAG = os.getenv(
        'MYJOBMAG_URL',
        'https://www.myjobmag.co.ke/jobs-by-function'
    )
    FUZU = os.getenv(
        'FUZU_URL',
        'https://www.fuzu.com/kenya/jobs'
    )

class KeywordConfig:
    # ── Data Engineering ────────────────────────────────────────────────────
    _DE = (
        'Data Engineer,Python,SQL,ETL,ELT,Data Pipeline,Airflow,Kafka,Spark,'
        'dbt,Pandas,PySpark,Databricks,BigQuery,Snowflake,Redshift,PostgreSQL,'
        'MySQL,AWS,Azure,GCP,Docker,Kubernetes,Terraform,FastAPI,Flask,MLOps'
    )
    # ── Data Analysis / BI ──────────────────────────────────────────────────
    _DA = (
        'Data Analyst,Analytics,Business Intelligence,BI Analyst,Power BI,'
        'Tableau,Looker,Metabase,Excel,Data Visualization,Reporting,Dashboard,'
        'Statistical Analysis,R,SPSS,Google Analytics,Insight,Analyst'
    )
    # ── Information Technology ──────────────────────────────────────────────
    _IT = (
        'IT Officer,IT Support,IT Manager,System Administrator,Network Administrator,'
        'Network Engineer,IT Technician,Help Desk,Service Desk,ITIL,Linux,'
        'Windows Server,Active Directory,Cybersecurity,Cloud Computing,DevOps,'
        'Technical Support,Infrastructure,IT Analyst,Systems Analyst,ICT Officer'
    )
    # ── Graduate / Entry-Level ──────────────────────────────────────────────
    _GRAD = (
        'Graduate,Trainee,Intern,Internship,Entry Level,Fresh Graduate,Junior,'
        'Attachment,Industrial Attachment,Management Trainee,Apprentice,Graduate Program'
    )
    # ── Database Management ─────────────────────────────────────────────────
    _DB = (
        'DBA,Database Administrator,Database Developer,Oracle,MongoDB,Redis,'
        'SQL Server,MSSQL,NoSQL,Database Design,Cassandra,Database Engineer,MariaDB'
    )

    _default_keywords = ','.join([_DE, _DA, _IT, _GRAD, _DB])

    _target_keywords_str = os.getenv('TARGET_KEYWORDS', _default_keywords)
    TARGET_KEYWORDS: List[str] = [k.strip() for k in _target_keywords_str.split(',') if k.strip()]
    _bonus_keywords_str = os.getenv('BONUS_KEYWORDS', '')
    BONUS_KEYWORDS: List[str] = [k.strip() for k in _bonus_keywords_str.split(',') if k.strip()]
    MIN_MATCHES_FOR_ALERT = int(os.getenv('MIN_KEYWORDS_FOR_ALERT', '1'))
    
    @classmethod
    def get_all_keywords(cls) -> List[str]:
        return cls.TARGET_KEYWORDS + cls.BONUS_KEYWORDS

class FeatureFlags:
    ENABLE_BRIGHTERMONDAY = os.getenv('ENABLE_BRIGHTERMONDAY', 'True').lower() == 'true'
    ENABLE_MYJOBMAG = os.getenv('ENABLE_MYJOBMAG', 'True').lower() == 'true'
    ENABLE_FUZU = os.getenv('ENABLE_FUZU', 'True').lower() == 'true'
    ENABLE_EMAIL_NOTIFICATIONS = os.getenv('ENABLE_EMAIL_NOTIFICATIONS', 'True').lower() == 'true'
    ENABLE_DEDUPLICATION = os.getenv('ENABLE_DEDUPLICATION', 'True').lower() == 'true'
    DRY_RUN = os.getenv('DRY_RUN', 'False').lower() == 'true'
    TEST_MODE = os.getenv('TEST_MODE', 'False').lower() == 'true'
    VERBOSE = os.getenv('VERBOSE', 'False').lower() == 'true'

class LoggingConfig:
    LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
    FILE = os.getenv('LOG_FILE', str(BASE_DIR / 'logs' / 'ndjt.log'))
    LOG_DIR = Path(FILE).parent
    LOG_DIR.mkdir(parents=True, exist_ok=True)

class TimezoneConfig:
    TIMEZONE = os.getenv('TIMEZONE', 'Africa/Nairobi')

class RetentionConfig:
    RETENTION_DAYS = int(os.getenv('RETENTION_DAYS', '180'))

class AirflowConfig:
    DAG_SCHEDULE = os.getenv('DAG_SCHEDULE', '0 8 * * *')
    DAG_CATCHUP = os.getenv('DAG_CATCHUP', 'False').lower() == 'true'
    TASK_RETRIES = int(os.getenv('TASK_RETRIES', '2'))
    TASK_RETRY_DELAY_MINUTES = int(os.getenv('TASK_RETRY_DELAY_MINUTES', '5'))

def validate_config() -> tuple[bool, List[str]]:
    errors = []
    if not DatabaseConfig.PASSWORD:
        errors.append("Database password not set (DB_PASSWORD)")
    if FeatureFlags.ENABLE_EMAIL_NOTIFICATIONS and not EmailConfig.is_configured():
        errors.append("Email notifications enabled but credentials not set (EMAIL_USER, EMAIL_PASSWORD)")
    if not KeywordConfig.TARGET_KEYWORDS:
        errors.append("No target keywords configured (TARGET_KEYWORDS)")
    if not any([
        FeatureFlags.ENABLE_BRIGHTERMONDAY,
        FeatureFlags.ENABLE_MYJOBMAG,
        FeatureFlags.ENABLE_FUZU
    ]):
        errors.append("All scrapers are disabled - enable at least one")
    return (len(errors) == 0, errors)

def print_config_summary():
    print("=" * 80)
    print("NAIROBI DATA JOBS TRACKER - CONFIGURATION SUMMARY")
    print("=" * 80)
    print(f"\n📊 DATABASE:")
    print(f"  Host: {DatabaseConfig.HOST}")
    print(f"  Port: {DatabaseConfig.PORT}")
    print(f"  Database: {DatabaseConfig.NAME}")
    print(f"  User: {DatabaseConfig.USER}")
    print(f"  Password: {'*' * len(DatabaseConfig.PASSWORD) if DatabaseConfig.PASSWORD else '[NOT SET]'}")
    print(f"\n📧 EMAIL:")
    print(f"  Enabled: {FeatureFlags.ENABLE_EMAIL_NOTIFICATIONS}")
    if EmailConfig.is_configured():
        print(f"  From: {EmailConfig.USER}")
        print(f"  To: {EmailConfig.RECIPIENT}")
        print(f"  SMTP: {EmailConfig.HOST}:{EmailConfig.PORT}")
    else:
        print(f"  Status: NOT CONFIGURED")
    print(f"\n🔍 SCRAPERS:")
    print(f"  BrighterMonday: {'✓' if FeatureFlags.ENABLE_BRIGHTERMONDAY else '✗'}")
    print(f"  MyJobMag: {'✓' if FeatureFlags.ENABLE_MYJOBMAG else '✗'}")
    print(f"  Fuzu: {'✓' if FeatureFlags.ENABLE_FUZU else '✗'}")
    print(f"\n🎯 KEYWORDS:")
    print(f"  Target Keywords ({len(KeywordConfig.TARGET_KEYWORDS)}): {', '.join(KeywordConfig.TARGET_KEYWORDS[:5])}...")
    print(f"  Min Matches for Alert: {KeywordConfig.MIN_MATCHES_FOR_ALERT}")
    print(f"\n⚙️  FEATURES:")
    print(f"  Dry Run: {FeatureFlags.DRY_RUN}")
    print(f"  Test Mode: {FeatureFlags.TEST_MODE}")
    print(f"  Deduplication: {FeatureFlags.ENABLE_DEDUPLICATION}")
    print(f"\n📝 LOGGING:")
    print(f"  Level: {LoggingConfig.LEVEL}")
    print(f"  File: {LoggingConfig.FILE}")
    print(f"\n⏰ SCHEDULE:")
    print(f"  Timezone: {TimezoneConfig.TIMEZONE}")
    print(f"  Airflow Schedule: {AirflowConfig.DAG_SCHEDULE}")
    is_valid, errors = validate_config()
    print(f"\n✅ VALIDATION:")
    if is_valid:
        print(f"  Status: PASSED - Configuration is valid")
    else:
        print(f"  Status: FAILED - {len(errors)} error(s)")
        for error in errors:
            print(f"    ❌ {error}")
    print("=" * 80)
    print()

if __name__ == '__main__':
    print_config_summary()
