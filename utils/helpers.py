import time
import random
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urljoin
import requests
from fake_useragent import UserAgent

from config.settings import ScrapingConfig

logger = logging.getLogger(__name__)

class RequestHelper:
    
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
    
    def get_headers(self, custom_user_agent: Optional[str] = None) -> Dict[str, str]:
        user_agent = custom_user_agent or ScrapingConfig.USER_AGENT
        
        if not custom_user_agent:
            try:
                user_agent = self.ua.random
            except Exception:
                pass
        
        return {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def random_delay(self, min_seconds: Optional[float] = None, max_seconds: Optional[float] = None):
        min_delay = min_seconds or ScrapingConfig.DELAY_MIN
        max_delay = max_seconds or ScrapingConfig.DELAY_MAX
        
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)
    
    def get_with_retry(
        self,
        url: str,
        max_retries: Optional[int] = None,
        timeout: Optional[int] = None,
        **kwargs
    ) -> Optional[requests.Response]:
        max_retries = max_retries or ScrapingConfig.MAX_RETRIES
        timeout = timeout or ScrapingConfig.TIMEOUT
        
        for attempt in range(max_retries):
            try:
                headers = kwargs.pop('headers', self.get_headers())
                
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=timeout,
                    **kwargs
                )
                
                response.raise_for_status()
                return response
            
            except requests.exceptions.RequestException:
                if attempt < max_retries - 1:
                    backoff_time = 2 ** attempt
                    time.sleep(backoff_time)
                else:
                    return None
        
        return None

def clean_text(text: Optional[str]) -> str:
    if not text:
        return ''
    
    text = ' '.join(text.split())
    text = re.sub(r'[^\w\s.,!?;:()\-\'\"\/]', '', text)
    text = text.replace('‘', "'").replace('’', "'")
    text = text.replace('“', '"').replace('”', '"')
    
    return text.strip()

def truncate_text(text: str, max_length: int = 500, suffix: str = '...') -> str:
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix

def extract_salary(text: str) -> Optional[str]:
    if not text:
        return None
    
    patterns = [
        r'KES\s*[\d,]+(?:\s*-\s*KES\s*[\d,]+)?',
        r'[\d,]+\s*-\s*[\d,]+\s*KES',
        r'Ksh\.?\s*[\d,]+(?:\s*-\s*Ksh\.?\s*[\d,]+)?',
        r'[\d,]+\s*-\s*[\d,]+\s*per\s+month',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_text(match.group())
    
    return None

def normalize_location(location: Optional[str]) -> str:
    if not location:
        return 'Kenya'
    
    location = clean_text(location)
    
    replacements = {
        'Nairobi, Kenya': 'Nairobi',
        'Nairobi County': 'Nairobi',
        'Nairobi CBD': 'Nairobi',
        'Remote - Kenya': 'Remote (Kenya)',
        'Anywhere in Kenya': 'Remote (Kenya)',
    }
    
    for old, new in replacements.items():
        if old.lower() in location.lower():
            return new
    
    return location

def parse_relative_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    
    date_str = date_str.lower().strip()
    now = datetime.now()
    
    if 'today' in date_str or 'just now' in date_str:
        return now
    elif 'yesterday' in date_str:
        return now - timedelta(days=1)
    
    patterns = [
        (r'(\d+)\s*day', 'days'),
        (r'(\d+)\s*week', 'weeks'),
        (r'(\d+)\s*month', 'months'),
        (r'(\d+)\s*hour', 'hours'),
    ]
    
    for pattern, unit in patterns:
        match = re.search(pattern, date_str)
        if match:
            value = int(match.group(1))
            
            if unit == 'days':
                return now - timedelta(days=value)
            elif unit == 'weeks':
                return now - timedelta(weeks=value)
            elif unit == 'months':
                return now - timedelta(days=value * 30)
            elif unit == 'hours':
                return now - timedelta(hours=value)
    
    return None

def parse_absolute_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    
    date_str = clean_text(date_str)
    
    formats = [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%B %d, %Y',
        '%d %B %Y',
        '%b %d, %Y',
        '%d %b %Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None

def parse_date(date_str: str) -> Optional[datetime]:
    date = parse_relative_date(date_str)
    if date:
        return date
    
    return parse_absolute_date(date_str)

def is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def make_absolute_url(base_url: str, relative_url: str) -> str:
    return urljoin(base_url, relative_url)

def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return ''

def validate_job_data(job_data: Dict[str, Any]) -> tuple[bool, list[str]]:
    required_fields = ['job_title', 'posting_url', 'source']
    errors = []
    
    for field in required_fields:
        if not job_data.get(field):
            errors.append(f"Missing required field: {field}")
    
    if job_data.get('posting_url') and not is_valid_url(job_data['posting_url']):
        errors.append("Invalid posting URL")
    
    valid_sources = ['BrighterMonday', 'MyJobMag', 'Fuzu', 'Other']
    if job_data.get('source') not in valid_sources:
        errors.append(f"Invalid source: {job_data.get('source')}")
    
    return (len(errors) == 0, errors)

def setup_logging(log_level: str = 'INFO', log_file: Optional[str] = None):
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    handlers = [logging.StreamHandler()]
    
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=handlers
    )

_request_helper = None

def get_request_helper() -> RequestHelper:
    global _request_helper
    if _request_helper is None:
        _request_helper = RequestHelper()
    return _request_helper

if __name__ == '__main__':
    setup_logging(log_level='INFO')
    
    dirty_text = "  This   is  some\n\nmessy    text!!!  "
    print(f"Cleaned:  '{clean_text(dirty_text)}'")
    
    test_texts = [
        "Salary: KES 80,000 - KES 120,000 per month",
        "Offering Ksh 50,000 to Ksh 75,000",
    ]
    for text in test_texts:
        print(f"'{text}' → {extract_salary(text)}")
