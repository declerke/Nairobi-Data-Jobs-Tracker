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
from config.settings import JobBoardURLs, ScrapingConfig, FeatureFlags

logger = logging.getLogger(__name__)

class BrighterMondayScraper:
    BASE_URL = 'https://www.brightermonday.co.ke'
    SOURCE_NAME = 'BrighterMonday'
    
    def __init__(self):
        self.request_helper = get_request_helper()
        self.jobs_scraped = []
    
    def build_search_url(self, query: str = 'data', page: int = 1) -> str:
        return f"{self.BASE_URL}/jobs?q={query}&page={page}"

    def parse_job_listings(self, html: str, page_url: str) -> List[Dict]:
        soup = BeautifulSoup(html, 'lxml')
        jobs = []

        job_links = soup.select('a[href*="/listings/"]') or \
                    soup.select('a[href*="/job/"]') or \
                    soup.find_all('a', class_=lambda x: x and 'title' in x.lower())

        unique_cards = []
        seen_parents = set()
        for link in job_links:
            parent = link.find_parent(['div', 'article'])
            if parent and parent not in seen_parents:
                unique_cards.append(parent)
                seen_parents.add(parent)

        if not unique_cards:
            return []

        for card in unique_cards:
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
            link_elem = card.select_one('a[href*="/listings/"]') or \
                        card.select_one('a[href*="/job/"]')
            
            if not link_elem:
                return None

            job_title = clean_text(link_elem.get_text())
            posting_url = make_absolute_url(self.BASE_URL, link_elem['href'])

            company_elem = card.select_one('a[href*="/company/"]') or \
                          card.find(['p', 'span'], class_=lambda x: x and 'text-sm' in x)
            company = clean_text(company_elem.get_text()) if company_elem else "N/A"

            meta_text = card.get_text(separator='|', strip=True)
            location = "Nairobi"
            for loc in ['Nairobi', 'Mombasa', 'Kisumu', 'Remote']:
                if loc.lower() in meta_text.lower():
                    location = loc
                    break

            salary_text = extract_salary(meta_text)

            date_text = None
            for text_node in card.find_all(string=True):
                if any(x in text_node.lower() for x in ['ago', 'today', 'yesterday']):
                    date_text = text_node
                    break
            
            posted_date = parse_date(clean_text(str(date_text))) if date_text else datetime.now()

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

    def scrape(self) -> List[Dict]:
        if not FeatureFlags.ENABLE_BRIGHTERMONDAY:
            return []
        
        all_jobs = []
        queries = ['data+analyst', 'data+scientist', 'data+engineer']
        
        for query in queries:
            url = self.build_search_url(query=query)
            response = self.request_helper.get_with_retry(url)
            if response:
                page_jobs = self.parse_job_listings(response.text, url)
                all_jobs.extend(page_jobs)
            
            self.request_helper.random_delay(2, 5)
        
        unique_jobs = list({j['posting_url']: j for j in all_jobs}.values())
        return unique_jobs

def scrape_brightermonday() -> List[Dict]:
    scraper = BrighterMondayScraper()
    return scraper.scrape()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    scraper = BrighterMondayScraper()
    jobs = scraper.scrape()
    print(f"Scraped {len(jobs)} jobs")
