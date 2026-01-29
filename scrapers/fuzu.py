import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from datetime import datetime

from utils.helpers import (
    get_request_helper,
    clean_text,
    truncate_text,
    extract_salary,
    normalize_location,
    parse_date,
    make_absolute_url,
    validate_job_data
)
from config.settings import ScrapingConfig, FeatureFlags

logger = logging.getLogger(__name__)

class FuzuScraper:
    
    BASE_URL = 'https://www.fuzu.com'
    SOURCE_NAME = 'Fuzu'
    
    def __init__(self):
        self.request_helper = get_request_helper()
        self.jobs_scraped = []
    
    def build_search_url(self, query: str = 'data', location: str = 'kenya', page: int = 1) -> str:
        return f"{self.BASE_URL}/kenya/jobs?q={query}&location={location}&page={page}"
    
    def scrape_search_page(self, query: str = 'data', location: str = 'kenya', max_pages: int = 3) -> List[Dict]:
        all_jobs = []
        
        for page in range(1, max_pages + 1):
            url = self.build_search_url(query, location, page)
            response = self.request_helper.get_with_retry(url)
            
            if not response:
                continue
            
            jobs = self.parse_job_listings(response.text, url)
            all_jobs.extend(jobs)
            
            if len(all_jobs) >= ScrapingConfig.MAX_JOBS_PER_SITE:
                break
            
            if page < max_pages:
                self.request_helper.random_delay()
        
        return all_jobs
    
    def parse_job_listings(self, html: str, page_url: str) -> List[Dict]:
        soup = BeautifulSoup(html, 'lxml')
        jobs = []
        
        job_cards = soup.find_all('div', class_='job-listing') or \
                   soup.find_all('article', class_='job') or \
                   soup.select('div[class*="job"]')
        
        for card in job_cards:
            try:
                job = self.parse_job_card(card, page_url)
                if job:
                    is_valid, errors = validate_job_data(job)
                    if is_valid:
                        jobs.append(job)
            except Exception:
                continue
        
        return jobs
    
    def parse_job_card(self, card: BeautifulSoup, page_url: str) -> Optional[Dict]:
        try:
            title_elem = card.find('h2') or card.find('h3') or card.find('a', class_='job-title')
            if not title_elem:
                return None
            
            job_title = clean_text(title_elem.get_text())
            
            link_elem = title_elem if title_elem.name == 'a' else title_elem.find('a')
            if not link_elem:
                link_elem = card.find('a', href=True)
            
            if not link_elem or not link_elem.get('href'):
                return None
            
            posting_url = make_absolute_url(page_url, link_elem['href'])
            
            company_elem = card.find(['div', 'span'], {'class': lambda x: x and 'company' in x.lower()})
            company = clean_text(company_elem.get_text()) if company_elem else None
            
            location_elem = card.find(['div', 'span'], {'class': lambda x: x and 'location' in x.lower()})
            location = normalize_location(location_elem.get_text()) if location_elem else 'Nairobi'
            
            desc_elem = card.find('div', class_='description') or card.find('p', class_='snippet')
            description_snippet = truncate_text(clean_text(desc_elem.get_text())) if desc_elem else None
            
            salary_elem = card.find(['div', 'span'], {'class': lambda x: x and 'salary' in x.lower()})
            salary_text = extract_salary(salary_elem.get_text()) if salary_elem else None
            
            date_elem = card.find('time') or card.find(['div', 'span'], {'class': lambda x: x and 'date' in x.lower()})
            posted_date = None
            if date_elem:
                date_str = date_elem.get('datetime') or date_elem.get_text()
                posted_date = parse_date(clean_text(date_str))
            
            job = {
                'job_title': job_title,
                'company': company,
                'location': location,
                'posting_url': posting_url,
                'source': self.SOURCE_NAME,
                'salary_text': salary_text,
                'description_snippet': description_snippet,
                'full_description': None,
                'posted_date': posted_date,
                'scrape_timestamp': datetime.now(),
                'keywords_matched': [],
                'metadata': {'scraper_version': '1.0', 'page_url': page_url}
            }
            
            return job
        except Exception:
            return None
    
    def scrape(self) -> List[Dict]:
        if not FeatureFlags.ENABLE_FUZU:
            return []
        
        all_jobs = []
        queries = ['data engineer', 'data scientist', 'data analyst', 'data']
        
        for query in queries:
            jobs = self.scrape_search_page(query=query.replace(' ', '%20'), location='kenya', max_pages=2)
            all_jobs.extend(jobs)
            if len(all_jobs) >= ScrapingConfig.MAX_JOBS_PER_SITE:
                break
            self.request_helper.random_delay(5, 10)
        
        unique_jobs = {job['posting_url']: job for job in all_jobs}.values()
        unique_jobs = list(unique_jobs)
        self.jobs_scraped = unique_jobs
        return unique_jobs

def scrape_fuzu() -> List[Dict]:
    scraper = FuzuScraper()
    return scraper.scrape()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    jobs = scrape_fuzu()
    print(f"Scraped {len(jobs)} jobs from Fuzu")