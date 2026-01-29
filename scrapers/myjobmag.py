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

class MyJobMagScraper:
    
    BASE_URL = 'https://www.myjobmag.co.ke'
    SOURCE_NAME = 'MyJobMag'
    
    def __init__(self):
        self.request_helper = get_request_helper()
        self.jobs_scraped = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.google.com/',
            'DNT': '1'
        }
    
    def build_search_url(self, query: str = 'data', location: str = 'nairobi', page: int = 1) -> str:
        if page > 1:
            return f"{self.BASE_URL}/jobs-location/{location}/{page}?q={query}"
        return f"{self.BASE_URL}/jobs-location/{location}?q={query}"
    
    def parse_job_listings(self, html: str, page_url: str) -> List[Dict]:
        soup = BeautifulSoup(html, 'lxml')
        jobs = []

        job_cards = soup.select('li.job-list-li') or \
                    soup.select('.job-info') or \
                    soup.find_all('div', class_=lambda c: c and 'media' in c.lower() and 'job' in c.lower()) or \
                    soup.find_all('li', class_=lambda c: c and 'job' in c.lower())

        if not job_cards:
            if "captcha" in html.lower() or "forbidden" in html.lower():
                logger.error("Access denied or CAPTCHA triggered on MyJobMag.")
            return []

        for card in job_cards:
            try:
                job = self.parse_job_card(card, page_url)
                if job:
                    is_valid, _ = validate_job_data(job)
                    if is_valid:
                        jobs.append(job)
            except Exception:
                continue

        return jobs

    def parse_job_card(self, card: BeautifulSoup, page_url: str) -> Optional[Dict]:
        try:
            title_link = (
                card.find('a', href=lambda x: x and '/job/' in x) or
                card.select_one('h2 a') or
                card.select_one('.job-title a')
            )

            if not title_link or not title_link.get('href'):
                return None

            job_title = clean_text(title_link.get_text(strip=True))
            posting_url = make_absolute_url(self.BASE_URL, title_link['href'])

            company = "N/A"
            company_elem = card.select_one('a[href*="/jobs-at/"]') or \
                          card.find('li', class_='job-list-details')
            if company_elem:
                company = clean_text(company_elem.get_text(strip=True))

            location = "Nairobi"
            loc_elem = card.select_one('.job-location') or \
                       card.find(string=lambda t: 'Nairobi' in str(t))
            if loc_elem:
                location = normalize_location(clean_text(str(loc_elem)))

            salary_text = extract_salary(card.get_text())

            posted_date = datetime.now()
            date_elem = card.find('li', id='job-date') or \
                       card.find(string=lambda t: any(w in str(t).lower() for w in ['ago', 'today', 'yesterday']))
            if date_elem:
                parsed = parse_date(clean_text(str(date_elem)))
                if parsed:
                    posted_date = parsed

            return {
                'job_title': job_title,
                'company': company,
                'location': location,
                'posting_url': posting_url,
                'source': self.SOURCE_NAME,
                'salary_text': salary_text,
                'description_snippet': None,
                'full_description': None,
                'posted_date': posted_date,
                'scrape_timestamp': datetime.now(),
                'keywords_matched': [],
                'metadata': {'scraper_version': '1.3', 'page_url': page_url}
            }
        except Exception:
            return None

    def scrape_search_page(self, query: str = 'data', location: str = 'nairobi', max_pages: int = 2) -> List[Dict]:
        all_jobs = []
        for page in range(1, max_pages + 1):
            url = self.build_search_url(query, location, page)
            response = self.request_helper.get_with_retry(url, headers=self.headers)
            if not response or response.status_code != 200:
                continue
            jobs = self.parse_job_listings(response.text, url)
            all_jobs.extend(jobs)
            self.request_helper.random_delay(2, 4)
        return all_jobs

    def scrape(self) -> List[Dict]:
        if not FeatureFlags.ENABLE_MYJOBMAG:
            return []
        all_jobs = []
        queries = ['data-analyst', 'data-scientist', 'data-engineer']
        for query in queries:
            jobs = self.scrape_search_page(query=query, location='nairobi', max_pages=1)
            all_jobs.extend(jobs)
        unique_jobs = list({job['posting_url']: job for job in all_jobs}.values())
        self.jobs_scraped = unique_jobs
        return unique_jobs

def scrape_myjobmag() -> List[Dict]:
    scraper = MyJobMagScraper()
    return scraper.scrape()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    jobs = scrape_myjobmag()
    print(f"Scraped {len(jobs)} jobs from MyJobMag")