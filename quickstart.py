import os
import sys
from pathlib import Path
import subprocess

def print_header(text):
    print("\n" + "=" * 80)
    print(f"  {text}")
    print("=" * 80 + "\n")

def check_python_version():
    print("Checking Python version...")
    version = sys.version_info
    if version.major == 3 and version.minor >= 10:
        print(f"✅ Python {version.major}.{version.minor}.{version.micro} - OK")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} - Need 3.10+")
        return False

def check_env_file():
    print("Checking .env file...")
    env_file = Path('.env')
    env_example = Path('.env.example')
    
    if env_file.exists():
        print("✅ .env file found")
        return True
    elif env_example.exists():
        print("⚠️  .env file not found")
        print(f"   Please copy .env.example to .env and configure it:")
        print(f"   cp .env.example .env")
        return False
    else:
        print("❌ Neither .env nor .env.example found")
        return False

def install_dependencies():
    print("Installing dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                      check=True)
        print("✅ Dependencies installed")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install dependencies")
        return False

def test_database_connection():
    print("Testing database connection...")
    try:
        from utils import test_connection
        if test_connection():
            print("✅ Database connection successful")
            return True
        else:
            print("❌ Database connection failed")
            print("   Please check your database configuration in .env")
            return False
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def test_email_config():
    print("Testing email configuration...")
    try:
        from config import EmailConfig
        if EmailConfig.is_configured():
            print("✅ Email configured")
            print(f"   From: {EmailConfig.USER}")
            print(f"   To: {EmailConfig.RECIPIENT}")
            
            choice = input("\n   Send test email? (y/n): ").lower()
            if choice == 'y':
                from utils import send_test_email
                if send_test_email():
                    print("   ✅ Test email sent successfully")
                    return True
                else:
                    print("   ❌ Failed to send test email")
                    return False
            return True
        else:
            print("⚠️  Email not configured")
            print("   Email notifications will be disabled")
            return False
    except Exception as e:
        print(f"❌ Email configuration error: {e}")
        return False

def test_scrapers():
    print("Testing scrapers (this may take a few seconds)...")
    try:
        from scrapers import scrape_brightermonday
        print("   Testing BrighterMonday scraper...")
        jobs = scrape_brightermonday()
        print(f"   ✅ Scraped {len(jobs)} jobs from BrighterMonday")
        return True
    except Exception as e:
        print(f"   ⚠️  Scraper test error (this is OK if site structure changed): {e}")
        return False

def show_next_steps():
    print_header("NEXT STEPS")
    print("✨ Setup Complete! Here's what to do next:\n")
    print("1️⃣  Initialize Airflow:")
    print("   export AIRFLOW_HOME=$(pwd)/airflow")
    print("   airflow db init")
    print("   airflow users create --username admin --password admin --firstname Admin --lastname User --role Admin --email admin@example.com")
    print()
    print("2️⃣  Copy DAG to Airflow:")
    print("   mkdir -p $AIRFLOW_HOME/dags")
    print("   cp dags/jobs_pipeline_dag.py $AIRFLOW_HOME/dags/")
    print()
    print("3️⃣  Start Airflow:")
    print("   # Terminal 1:")
    print("   airflow webserver --port 8080")
    print()
    print("   # Terminal 2:")
    print("   airflow scheduler")
    print()
    print("4️⃣  Access Airflow UI:")
    print("   Open: http://localhost:8080")
    print("   Login: admin / admin")
    print()
    print("5️⃣  Enable and trigger DAG:")
    print("   - Find 'nairobi_data_jobs_pipeline' in the DAGs list")
    print("   - Toggle it ON")
    print("   - Click 'Trigger DAG' to run manually")
    print()
    print("6️⃣  Monitor execution:")
    print("   - Check Airflow UI for task status")
    print("   - View logs: airflow/logs/")
    print("   - Check email inbox for job alerts")
    print()
    print("📚 Documentation:")
    print("   - Full README: README.md")
    print("   - Database schema: setup_database.sql")
    print("   - Configuration: .env")
    print()
    print("🆘 Troubleshooting:")
    print("   - Check logs in logs/ndjt.log")
    print("   - Verify .env settings")
    print("   - Test individual components:")
    print("     python utils/database.py")
    print("     python utils/email_notifier.py")
    print("     python scrapers/brightermonday.py")

def main():
    print_header("NAIROBI DATA JOBS TRACKER - QUICK START")
    print("This script will help you set up the project.\n")
    checks = []
    checks.append(("Python Version", check_python_version()))
    checks.append(("Environment File", check_env_file()))
    
    if checks[1][1]:
        choice = input("\nInstall dependencies? (y/n): ").lower()
        if choice == 'y':
            checks.append(("Dependencies", install_dependencies()))
        
        if all(check[1] for check in checks):
            checks.append(("Database Connection", test_database_connection()))
            checks.append(("Email Configuration", test_email_config()))
            
            choice = input("\nTest scrapers? (takes ~10 seconds) (y/n): ").lower()
            if choice == 'y':
                checks.append(("Scrapers", test_scrapers()))
    
    print_header("SETUP SUMMARY")
    for name, status in checks:
        icon = "✅" if status else "❌"
        print(f"{icon} {name}")
    
    all_passed = all(check[1] for check in checks if check[0] != "Email Configuration")
    if all_passed:
        show_next_steps()
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above before proceeding.")
        print("   Refer to README.md for detailed setup instructions.")
    
    print("\n" + "=" * 80)
    print("Setup script complete!")
    print("=" * 80 + "\n")

if __name__ == '__main__':
    main()