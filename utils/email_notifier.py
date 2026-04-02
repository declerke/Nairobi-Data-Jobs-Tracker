import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Any, List, Dict, Optional
from time import sleep

logger = logging.getLogger(__name__)

class EmailNotifier:
    
    def __init__(
        self,
        sender_email: str = None,
        sender_password: str = None,
        smtp_host: str = None,
        smtp_port: int = None,
        recipient_email: str = None
    ):
        self.sender_email = sender_email or os.getenv('EMAIL_SENDER')
        self.sender_password = sender_password or os.getenv('EMAIL_PASSWORD')
        self.smtp_server = os.getenv('SMTP_SERVER', '')
        self.smtp_host = smtp_host or os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', 587))
        self.recipient_email = recipient_email or os.getenv('EMAIL_RECIPIENT')
        
        if not self.sender_email or not self.sender_password:
            logger.warning("Email credentials not configured. Notifications will be disabled.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"EmailNotifier initialized for {self.sender_email} -> {self.recipient_email}")
    
    def test_connection(self) -> bool:
        if not self.enabled:
            logger.warning("Email not configured, skipping connection test")
            return False
        
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                logger.info("Email connection test successful")
                return True
        except Exception as e:
            logger.error(f"Email connection test failed: {e}")
            return False
    
    def _create_job_html(self, job: Dict) -> str:
        keywords = job.get('keywords_matched', [])
        if isinstance(keywords, str):
            keywords = keywords.split(',') if keywords else []
        
        keyword_badges = ' '.join([
            f'<span style="background-color: #e3f2fd; color: #1976d2; padding: 2px 8px; '
            f'border-radius: 3px; font-size: 12px; margin-right: 4px;">{k}</span>'
            for k in keywords
        ])
        
        job_html = f"""
        <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; margin-bottom: 16px; background-color: #ffffff;">
            <h3 style="margin: 0 0 8px 0; color: #1976d2;">
                <a href="{job.get('posting_url', '#')}" style="text-decoration: none; color: #1976d2;">
                    {job.get('job_title', 'N/A')}
                </a>
            </h3>
            
            <div style="margin-bottom: 12px;">
                <p style="margin: 4px 0; color: #666;">
                    <strong>Company:</strong> {job.get('company', 'N/A')}
                </p>
                <p style="margin: 4px 0; color: #666;">
                    <strong>Location:</strong> {job.get('location', 'N/A')}
                </p>
                {f'<p style="margin: 4px 0; color: #666;"><strong>Salary:</strong> {job.get("salary_text")}</p>' if job.get('salary_text') else ''}
                <p style="margin: 4px 0; color: #666;">
                    <strong>Source:</strong> {job.get('source', 'N/A')}
                </p>
                {f'<p style="margin: 4px 0; color: #666;"><strong>Posted:</strong> {job.get("posted_date")}</p>' if job.get('posted_date') else ''}
            </div>
            
            <div style="margin-bottom: 12px;">
                <strong style="color: #333;">Matched Keywords ({len(keywords)}):</strong><br>
                {keyword_badges if keyword_badges else '<em style="color: #999;">None</em>'}
            </div>
            
            {f'<div style="margin-top: 12px; padding: 12px; background-color: #f5f5f5; border-radius: 4px;"><p style="margin: 0; color: #666; font-size: 14px;">{job.get("description", "")[:300]}...</p></div>' if job.get('description') else ''}
            
            <div style="margin-top: 12px;">
                <a href="{job.get('posting_url', '#')}" style="display: inline-block; background-color: #1976d2; color: white; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-size: 14px;">
                    View Full Job Posting →
                </a>
            </div>
        </div>
        """
        return job_html
    
    def _create_job_plaintext(self, job: Dict) -> str:
        keywords = job.get('keywords_matched', [])
        if isinstance(keywords, str):
            keywords = keywords.split(',') if keywords else []
        
        text = f"""
{'=' * 80}
{job.get('job_title', 'N/A')}
{'=' * 80}

Company: {job.get('company', 'N/A')}
Location: {job.get('location', 'N/A')}
{f"Salary: {job.get('salary_text')}" if job.get('salary_text') else ''}
Source: {job.get('source', 'N/A')}
{f"Posted: {job.get('posted_date')}" if job.get('posted_date') else ''}

Matched Keywords ({len(keywords)}):
{', '.join(keywords) if keywords else 'None'}

{f"Description: {job.get('description', '')[:300]}..." if job.get('description') else ''}

Link: {job.get('posting_url', 'N/A')}
"""
        return text
    
    def send_job_alert(self, job: Dict) -> bool:
        if not self.enabled:
            logger.warning("Email not configured, skipping notification")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"New Job Match: {job.get('job_title', 'Unknown')} at {job.get('company', 'Unknown')}"
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            
            plain_text = self._create_job_plaintext(job)
            html_text = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
                <div style="background-color: #1976d2; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
                    <h2 style="margin: 0;">🎯 New Job Match Found!</h2>
                </div>
                <div style="padding: 20px; background-color: #f9f9f9;">
                    {self._create_job_html(job)}
                </div>
                <div style="padding: 16px; background-color: #e0e0e0; border-radius: 0 0 8px 8px; text-align: center; font-size: 12px; color: #666;">
                    <p style="margin: 0;">Sent by Nairobi Data Jobs Tracker</p>
                    <p style="margin: 4px 0 0 0;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(plain_text, 'plain'))
            msg.attach(MIMEText(html_text, 'html'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            logger.info(f"Email sent for job: {job.get('job_title')} at {job.get('company')}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def send_daily_digest(self, jobs: List[Dict], date: str = None) -> bool:
        if not self.enabled:
            logger.warning("Email not configured, skipping digest")
            return False
        if not jobs:
            logger.info("No jobs to include in digest")
            return True
        
        date_str = date or datetime.now().strftime('%Y-%m-%d')
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Daily Job Digest: {len(jobs)} New Matches - {date_str}"
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            
            plain_text = f"NAIROBI DATA JOBS TRACKER - DAILY DIGEST\n{date_str}\n{'=' * 80}\n\nFound {len(jobs)} new job matches today!\n"
            for idx, job in enumerate(jobs, 1):
                plain_text += f"\n{idx}. {self._create_job_plaintext(job)}"
            
            jobs_html = '\n'.join([self._create_job_html(job) for job in jobs])
            total_keywords = sum(len(job.get('keywords_matched', [])) for job in jobs)
            unique_companies = len(set(job.get('company', 'N/A') for job in jobs))
            unique_sources = len(set(job.get('source', 'N/A') for job in jobs))
            
            html_text = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 700px; margin: 0 auto; background-color: #f5f5f5;">
                <div style="background-color: #1976d2; color: white; padding: 24px; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 28px;">📊 Daily Job Digest</h1>
                    <p style="margin: 8px 0 0 0; font-size: 16px; opacity: 0.9;">{date_str}</p>
                </div>
                <div style="padding: 20px; background-color: white; border-left: 3px solid #1976d2; border-right: 3px solid #1976d2;">
                    <div style="background-color: #e3f2fd; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
                        <h2 style="margin: 0 0 12px 0; color: #1976d2; font-size: 20px;">Summary</h2>
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px;">
                            <div><strong style="color: #666;">Total Jobs:</strong> {len(jobs)}</div>
                            <div><strong style="color: #666;">Total Keywords:</strong> {total_keywords}</div>
                            <div><strong style="color: #666;">Companies:</strong> {unique_companies}</div>
                            <div><strong style="color: #666;">Sources:</strong> {unique_sources}</div>
                        </div>
                    </div>
                    <h2 style="color: #1976d2; border-bottom: 2px solid #1976d2; padding-bottom: 8px;">Job Matches ({len(jobs)})</h2>
                    {jobs_html}
                </div>
                <div style="padding: 20px; background-color: #e0e0e0; border-radius: 0 0 8px 8px; text-align: center;">
                    <p style="margin: 0; color: #666; font-size: 14px;"><strong>Tip:</strong> Apply early!</p>
                    <hr style="border: none; border-top: 1px solid #ccc; margin: 16px 0;">
                    <p style="margin: 0; font-size: 12px; color: #999;">Sent by Nairobi Data Jobs Tracker<br>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(plain_text, 'plain'))
            msg.attach(MIMEText(html_text, 'html'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            logger.info(f"Daily digest sent with {len(jobs)} jobs")
            return True
        except Exception as e:
            logger.error(f"Failed to send daily digest: {e}")
            return False
    
    def send_weekly_summary(self, stats: Dict) -> bool:
        if not self.enabled:
            logger.warning("Email not configured, skipping weekly summary")
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"Weekly Jobs Summary - {stats.get('week_ending', 'N/A')}"
            msg['From'] = self.sender_email
            msg['To'] = self.recipient_email
            
            plain_text = f"NAIROBI DATA JOBS TRACKER - WEEKLY SUMMARY\nWeek Ending: {stats.get('week_ending', 'N/A')}\n{'=' * 80}\n"
            msg.attach(MIMEText(plain_text, 'plain'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            logger.info("Weekly summary sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send weekly summary: {e}")
            return False
    
    def send_test_email(self) -> bool:
        test_job = {
            'job_title': 'Test Job - Senior Data Engineer',
            'company': 'Test Company Inc.',
            'location': 'Nairobi, Kenya',
            'salary_text': 'KSh 150,000 - 200,000',
            'posting_url': 'https://example.com/jobs/test',
            'source': 'Test Source',
            'posted_date': datetime.now().strftime('%Y-%m-%d'),
            'keywords_matched': ['Python', 'PostgreSQL', 'AWS', 'Docker'],
            'description': 'Test job posting.'
        }
        return self.send_job_alert(test_job)

def send_notification(jobs: List[Dict], notification_type: str = 'digest') -> bool:
    notifier = EmailNotifier()
    if not notifier.enabled:
        return False
    if notification_type == 'single' and jobs:
        return notifier.send_job_alert(jobs[0])
    elif notification_type == 'digest':
        return notifier.send_daily_digest(jobs)
    elif notification_type == 'weekly':
        return notifier.send_weekly_summary({'week_ending': datetime.now().strftime('%Y-%m-%d')})
    return False

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    notifier = EmailNotifier()
    if notifier.enabled:
        if notifier.test_connection():
            print("✓ Email connection test passed")

_notifier_instance = None


def get_notifier():
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = EmailNotifier()
    return _notifier_instance


def send_job_alerts(jobs: List[Dict[str, Any]]):
    return get_notifier().send_daily_digest(jobs)


def send_test_email():
    return get_notifier().send_test_email()