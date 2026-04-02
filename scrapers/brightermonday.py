import logging
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup

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


class BrighterMondayScraper:

    BASE_URL = 'https://www.brightermonday.co.ke'
    SOURCE_NAME = 'BrighterMonday'

    def __init__(self):
        self.jobs_scraped = []

    def build_search_url(self, query: str = 'data') -> str:
        return f"{self.BASE_URL}/jobs?q={query}"

    def _parse_api_json(self, data) -> List[Dict]:
        """Parse job data from an intercepted JSON API response."""
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

            title = (item.get('title') or item.get('name') or
                     item.get('job_title') or item.get('position'))
            url = (item.get('url') or item.get('link') or
                   item.get('posting_url') or item.get('job_url'))

            if not title or not url:
                continue
            if not url.startswith('http'):
                url = f"{self.BASE_URL}{url}"

            raw_company = (item.get('company') or item.get('employer') or
                           item.get('affiliation') or item.get('organisation') or 'N/A')
            raw_location = (item.get('location') or item.get('city') or
                            item.get('location_name') or 'Nairobi')
            raw_desc = (item.get('description') or item.get('snippet') or
                        item.get('summary') or '')
            raw_date = (item.get('posted_date') or item.get('date') or
                        item.get('created_at') or item.get('published_at') or '')
            raw_salary = (item.get('salary') or item.get('salary_text') or
                          item.get('salary_range') or '')

            job = {
                'job_title': clean_text(str(title)),
                'company': clean_text(str(raw_company)),
                'location': normalize_location(str(raw_location)),
                'posting_url': url,
                'source': self.SOURCE_NAME,
                'salary_text': clean_text(str(raw_salary)) or extract_salary(str(raw_desc)),
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
        """Parse Playwright-rendered HTML using the known /listings/ URL pattern."""
        soup = BeautifulSoup(html, 'lxml')
        jobs = []
        seen_urls = set()

        listing_links = soup.select('a[href*="/listings/"]')
        if not listing_links:
            logger.warning("BrighterMonday: no /listings/ links found in rendered HTML")
            return []

        for link in listing_links:
            href = link.get('href', '')
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)

            posting_url = make_absolute_url(self.BASE_URL, href)
            job_title = clean_text(link.get_text(strip=True))
            if not job_title:
                continue

            # Walk up the DOM to find the nearest container with meaningful content
            card = link.parent
            for _ in range(6):
                if card is None:
                    break
                if card.name in ('article', 'div', 'li', 'section'):
                    card_text = card.get_text(separator=' ', strip=True)
                    if len(card_text) > len(job_title) + 10:
                        break
                card = card.parent

            card_text = card.get_text(separator='|', strip=True) if card else ''

            # Company: look for a /company/ link within the card
            company = 'N/A'
            if card:
                co_elem = card.select_one('a[href*="/company/"]')
                if co_elem:
                    company = clean_text(co_elem.get_text(strip=True))

            # Location: scan card text for known Kenyan cities
            location = 'Nairobi'
            for loc in ['Nairobi', 'Mombasa', 'Kisumu', 'Eldoret', 'Nakuru', 'Remote']:
                if loc.lower() in card_text.lower():
                    location = loc
                    break

            job = {
                'job_title': job_title,
                'company': company,
                'location': location,
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
            browser = p.chromium.launch(headless=True)

            for query in queries:
                url = self.build_search_url(query)
                captured_api_data: List = []
                html_content: Optional[str] = None

                context = browser.new_context(
                    user_agent=(
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
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
                        if any(t in resp_url for t in ['/jobs', '/listings', '/search', '/api', '/v1', '/v2']):
                            data = response.json()
                            captured_api_data.append(data)
                    except Exception:
                        pass

                page.on('response', handle_response)

                try:
                    page.goto(url, wait_until='networkidle', timeout=35000)
                    page.wait_for_timeout(2000)
                    html_content = page.content()
                    logger.info(f"BrighterMonday: loaded page for '{query}', "
                                f"captured {len(captured_api_data)} API responses")
                except PWTimeout:
                    logger.warning(f"BrighterMonday: timeout loading '{query}'")
                    try:
                        html_content = page.content()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"BrighterMonday: page load error for '{query}': {e}")
                finally:
                    context.close()

                # Primary: parse intercepted API JSON
                api_jobs = []
                for data in captured_api_data:
                    api_jobs.extend(self._parse_api_json(data))

                if api_jobs:
                    logger.info(f"BrighterMonday API intercept: {len(api_jobs)} jobs for '{query}'")
                    all_jobs.extend(api_jobs)
                elif html_content:
                    html_jobs = self._parse_html(html_content, url)
                    logger.info(f"BrighterMonday HTML parse: {len(html_jobs)} jobs for '{query}'")
                    all_jobs.extend(html_jobs)
                else:
                    logger.warning(f"BrighterMonday: no data obtained for '{query}'")

            browser.close()

        return all_jobs

    def scrape(self) -> List[Dict]:
        if not FeatureFlags.ENABLE_BRIGHTERMONDAY:
            return []

        queries = [
            # Data Engineering
            'data+engineer', 'data+analyst', 'data+scientist',
            # Information Technology
            'IT+officer', 'systems+analyst', 'network+engineer',
            # Database Management
            'database+administrator', 'SQL+developer',
            # Graduate / Entry-level
            'graduate+trainee', 'IT+graduate',
            # Business Intelligence
            'business+intelligence', 'BI+analyst',
        ]
        all_jobs = self._scrape_with_playwright(queries)
        unique_jobs = list({j['posting_url']: j for j in all_jobs}.values())
        self.jobs_scraped = unique_jobs
        logger.info(f"BrighterMonday total unique jobs: {len(unique_jobs)}")
        return unique_jobs


def scrape_brightermonday() -> List[Dict]:
    scraper = BrighterMondayScraper()
    return scraper.scrape()


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    jobs = scrape_brightermonday()
    print(f"Scraped {len(jobs)} jobs from BrighterMonday")
    for j in jobs[:3]:
        print(f"  {j['job_title']} @ {j['company']} — {j['location']}")
