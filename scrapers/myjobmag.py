import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup, NavigableString
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
            'DNT': '1',
        }

    def build_search_url(self, location: str = 'nairobi', page: int = 1) -> str:
        if page > 1:
            return f"{self.BASE_URL}/jobs-location/{location}/{page}"
        return f"{self.BASE_URL}/jobs-location/{location}"

    def parse_job_listings(self, html: str, page_url: str) -> List[Dict]:
        soup = BeautifulSoup(html, 'lxml')
        jobs = []

        job_cards = soup.select('li.job-list-li')

        if not job_cards:
            if 'captcha' in html.lower() or 'forbidden' in html.lower():
                logger.error("Access denied or CAPTCHA on MyJobMag.")
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
            # Title: li.mag-b > h2 > a
            title_elem = card.select_one('li.mag-b h2 a') or card.select_one('h2 a')
            if not title_elem or not title_elem.get('href'):
                return None

            full_title = clean_text(title_elem.get_text(strip=True))
            posting_url = make_absolute_url(self.BASE_URL, title_elem['href'])

            # Separate job title from company (format: "Job Title at Company Name")
            if ' at ' in full_title:
                parts = full_title.rsplit(' at ', 1)
                job_title = parts[0].strip()
                company_from_title = parts[1].strip()
            else:
                job_title = full_title
                company_from_title = None

            # Company: prefer logo img alt text over title parsing
            company = 'N/A'
            logo_img = card.select_one('li.job-logo a img')
            if logo_img and logo_img.get('alt'):
                alt = logo_img['alt'].strip()
                company = alt.replace(' logo', '').replace(' Logo', '').strip()
            elif company_from_title:
                company = company_from_title

            # Description snippet: li.job-desc
            desc_elem = card.select_one('li.job-desc')
            description_snippet = (
                truncate_text(clean_text(desc_elem.get_text(strip=True)), 500)
                if desc_elem else None
            )

            # Date and location: li[id="job-date"]
            posted_date = datetime.now()
            location = 'Nairobi'
            date_elem = card.find('li', id='job-date')
            if date_elem:
                # Date is the direct text content before the span
                date_text = ''.join(
                    str(c).strip() for c in date_elem.contents
                    if isinstance(c, NavigableString)
                ).strip()
                if date_text:
                    parsed = parse_date(date_text)
                    if parsed:
                        posted_date = parsed

                loc_link = date_elem.select_one('a[href*="/jobs-location/"]')
                if loc_link:
                    location = normalize_location(clean_text(loc_link.get_text(strip=True)))

            salary_text = extract_salary(card.get_text())

            return {
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
                'metadata': {'scraper_version': '2.0', 'page_url': page_url}
            }
        except Exception:
            return None

    def scrape(self) -> List[Dict]:
        if not FeatureFlags.ENABLE_MYJOBMAG:
            return []

        all_jobs = []

        for page in range(1, 6):
            url = self.build_search_url(location='nairobi', page=page)
            response = self.request_helper.get_with_retry(url, headers=self.headers)
            if not response or response.status_code != 200:
                break
            jobs = self.parse_job_listings(response.text, url)
            if not jobs:
                break
            all_jobs.extend(jobs)
            self.request_helper.random_delay(2, 4)

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
    for j in jobs[:3]:
        print(f"  {j['job_title']} @ {j['company']} — {j['location']}")
