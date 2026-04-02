import logging
import time
import random
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup

import requests

from utils.helpers import (
    clean_text,
    truncate_text,
    extract_salary,
    normalize_location,
    parse_date,
    make_absolute_url,
    validate_job_data
)
from config.settings import FeatureFlags

logger = logging.getLogger(__name__)


class FuzuScraper:

    BASE_URL = 'https://fuzu.com'
    SOURCE_NAME = 'Fuzu'

    HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.google.com/',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
    }

    def __init__(self):
        self.jobs_scraped = []

    def build_search_url(self, query: str = 'data', page: int = 1) -> str:
        return f"{self.BASE_URL}/kenya/jobs?q={query}&page={page}"

    def _try_requests(self, url: str) -> Optional[str]:
        """Attempt plain HTTP request with full browser headers and cookie priming."""
        session = requests.Session()
        try:
            session.get(self.BASE_URL, headers=self.HEADERS, timeout=15)
        except Exception:
            pass
        time.sleep(random.uniform(1.5, 3.0))
        try:
            response = session.get(url, headers=self.HEADERS, timeout=30)
            if response.status_code == 200 and len(response.text) > 2000:
                logger.info(f"Fuzu requests: HTTP 200 for {url}")
                return response.text
            logger.debug(f"Fuzu requests: HTTP {response.status_code} for {url}")
        except Exception as e:
            logger.debug(f"Fuzu requests exception: {e}")
        return None

    def _parse_api_json(self, data) -> List[Dict]:
        """Parse Fuzu job data from an intercepted JSON response."""
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get('jobs') or data.get('results') or
                data.get('data') or data.get('listings') or
                data.get('items') or []
            )
        else:
            return []

        jobs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = (item.get('title') or item.get('name') or item.get('job_title'))
            url = (item.get('url') or item.get('link') or item.get('posting_url'))
            if not title or not url:
                continue
            if not url.startswith('http'):
                url = f"{self.BASE_URL}{url}"

            raw_desc = item.get('description') or item.get('snippet') or ''
            raw_date = (item.get('posted_date') or item.get('date') or
                        item.get('created_at') or item.get('deadline') or '')

            job = {
                'job_title': clean_text(str(title)),
                'company': clean_text(str(item.get('company') or item.get('employer') or 'N/A')),
                'location': normalize_location(str(item.get('location') or 'Kenya')),
                'posting_url': url,
                'source': self.SOURCE_NAME,
                'salary_text': None,
                'description_snippet': truncate_text(clean_text(str(raw_desc)), 500) or None,
                'full_description': None,
                'posted_date': parse_date(str(raw_date)),
                'scrape_timestamp': datetime.now(),
                'keywords_matched': [],
                'metadata': {'source': 'api_intercept'}
            }
            is_valid, _ = validate_job_data(job)
            if is_valid:
                jobs.append(job)

        return jobs

    def _parse_html(self, html: str, page_url: str) -> List[Dict]:
        """Parse Fuzu HTML (structure varies; uses broad link-based extraction)."""
        soup = BeautifulSoup(html, 'lxml')
        jobs = []
        seen_urls = set()

        job_links = (
            soup.select('a[href*="/kenya/job/"]') or
            soup.select('a[href*="/job/"]') or
            soup.select('a[href*="/jobs/"]')
        )

        for link in job_links:
            href = link.get('href', '')
            if not href or href in seen_urls or href == page_url:
                continue
            seen_urls.add(href)

            posting_url = make_absolute_url(self.BASE_URL, href)
            job_title = clean_text(link.get_text(strip=True))
            if not job_title or len(job_title) < 4:
                continue

            # Walk up to find the card container
            card = link.parent
            for _ in range(5):
                if card is None:
                    break
                if card.name in ('article', 'div', 'li', 'section'):
                    if len(card.get_text(separator=' ', strip=True)) > len(job_title) + 10:
                        break
                card = card.parent

            card_text = card.get_text(separator='|', strip=True) if card else ''

            job = {
                'job_title': job_title,
                'company': 'N/A',
                'location': 'Kenya',
                'posting_url': posting_url,
                'source': self.SOURCE_NAME,
                'salary_text': extract_salary(card_text),
                'description_snippet': None,
                'full_description': None,
                'posted_date': datetime.now(),
                'scrape_timestamp': datetime.now(),
                'keywords_matched': [],
                'metadata': {'source': 'html_parse', 'page_url': page_url}
            }
            is_valid, _ = validate_job_data(job)
            if is_valid:
                jobs.append(job)

        return jobs

    def _scrape_with_playwright(self, queries: List[str]) -> List[Dict]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
            return []

        all_jobs = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])

            for query in queries:
                url = self.build_search_url(query)
                captured_api_data: List = []
                html_content: Optional[str] = None

                context = browser.new_context(
                    user_agent=self.HEADERS['User-Agent'],
                    viewport={'width': 1280, 'height': 800},
                )
                page = context.new_page()

                def handle_response(response):
                    try:
                        if response.status != 200:
                            return
                        content_type = response.headers.get('content-type', '')
                        if 'json' not in content_type:
                            return
                        resp_url = response.url
                        if any(t in resp_url for t in ['/jobs', '/api', '/search', '/v1', '/v2']):
                            data = response.json()
                            captured_api_data.append(data)
                    except Exception:
                        pass

                page.on('response', handle_response)

                try:
                    page.goto(url, wait_until='networkidle', timeout=35000)
                    page.wait_for_timeout(2000)
                    html_content = page.content()
                    logger.info(f"Fuzu Playwright: loaded '{query}', "
                                f"captured {len(captured_api_data)} API responses")
                except PWTimeout:
                    logger.warning(f"Fuzu: timeout for '{query}'")
                    try:
                        html_content = page.content()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"Fuzu: Playwright error for '{query}': {e}")
                finally:
                    context.close()

                api_jobs = []
                for data in captured_api_data:
                    api_jobs.extend(self._parse_api_json(data))

                if api_jobs:
                    logger.info(f"Fuzu API intercept: {len(api_jobs)} jobs for '{query}'")
                    all_jobs.extend(api_jobs)
                elif html_content:
                    html_jobs = self._parse_html(html_content, url)
                    logger.info(f"Fuzu HTML parse: {len(html_jobs)} jobs for '{query}'")
                    all_jobs.extend(html_jobs)

            browser.close()

        return all_jobs

    def scrape(self) -> List[Dict]:
        if not FeatureFlags.ENABLE_FUZU:
            return []

        queries = [
            # Data Engineering
            'data+engineer', 'data+analyst', 'data+scientist',
            # Information Technology
            'IT+officer', 'systems+analyst', 'network+engineer',
            # Database Management
            'database+administrator',
            # Graduate / Entry-level
            'graduate+trainee',
            # Business Intelligence
            'business+intelligence',
        ]
        all_jobs = []

        # Try requests first (fast, no browser overhead)
        for query in queries:
            url = self.build_search_url(query)
            html = self._try_requests(url)
            if html:
                try:
                    jobs = self._parse_html(html, url)
                    all_jobs.extend(jobs)
                    logger.info(f"Fuzu requests: {len(jobs)} jobs for '{query}'")
                except Exception as e:
                    logger.debug(f"Fuzu requests parse error for '{query}': {e}")
            time.sleep(random.uniform(2, 4))

        # Fall back to Playwright if requests yielded nothing
        if not all_jobs:
            logger.info("Fuzu requests returned 0 jobs — switching to Playwright")
            all_jobs = self._scrape_with_playwright(queries)

        unique_jobs = list({j['posting_url']: j for j in all_jobs}.values())
        self.jobs_scraped = unique_jobs
        logger.info(f"Fuzu total unique jobs: {len(unique_jobs)}")
        return unique_jobs


def scrape_fuzu() -> List[Dict]:
    scraper = FuzuScraper()
    return scraper.scrape()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    jobs = scrape_fuzu()
    print(f"Scraped {len(jobs)} jobs from Fuzu")
    for j in jobs[:3]:
        print(f"  {j['job_title']} @ {j['company']} — {j['location']}")
