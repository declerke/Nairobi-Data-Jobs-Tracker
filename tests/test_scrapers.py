import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scrapers import (
    BrighterMondayScraper,
    MyJobMagScraper,
    FuzuScraper
)
from utils import (
    clean_text,
    extract_salary,
    parse_date,
    is_valid_url,
    validate_job_data
)

class TestBrighterMondayScraper:
    
    def test_scraper_initialization(self):
        scraper = BrighterMondayScraper()
        assert scraper.SOURCE_NAME == 'BrighterMonday'
        assert scraper.BASE_URL == 'https://www.brightermonday.co.ke'
    
    def test_build_search_url(self):
        scraper = BrighterMondayScraper()
        url = scraper.build_search_url(query='data engineer', location='nairobi', page=1)
        assert 'data engineer' in url.lower() or 'data+engineer' in url.lower()
        assert 'nairobi' in url.lower()
    
    @patch('scrapers.brightermonday.get_request_helper')
    def test_scrape_with_mock(self, mock_helper):
        mock_response = Mock()
        mock_response.text = '<html><body><div class="job-card"><h2>Data Engineer</h2></div></body></html>'
        
        mock_helper_instance = Mock()
        mock_helper_instance.get_with_retry.return_value = mock_response
        mock_helper.return_value = mock_helper_instance
        
        scraper = BrighterMondayScraper()
        assert scraper.SOURCE_NAME is not None

class TestMyJobMagScraper:
    
    def test_scraper_initialization(self):
        scraper = MyJobMagScraper()
        assert scraper.SOURCE_NAME == 'MyJobMag'
        assert scraper.BASE_URL == 'https://www.myjobmag.co.ke'
    
    def test_build_search_url(self):
        scraper = MyJobMagScraper()
        url = scraper.build_search_url(query='data', location='nairobi')
        assert 'data' in url.lower()

class TestFuzuScraper:
    
    def test_scraper_initialization(self):
        scraper = FuzuScraper()
        assert scraper.SOURCE_NAME == 'Fuzu'
        assert scraper.BASE_URL == 'https://www.fuzu.com'

class TestHelperFunctions:
    
    def test_clean_text(self):
        dirty = "  This   has    extra   spaces  "
        clean = clean_text(dirty)
        assert clean == "This has extra spaces"
    
    def test_extract_salary(self):
        text1 = "Salary: KES 80,000 - KES 120,000"
        salary1 = extract_salary(text1)
        assert salary1 is not None
        assert 'KES' in salary1 or 'Ksh' in salary1 or '80' in salary1
        
        text2 = "Competitive salary package"
        salary2 = extract_salary(text2)
        assert salary2 is None or 'competitive' not in salary2.lower()
    
    def test_parse_date(self):
        date1 = parse_date("2 days ago")
        assert date1 is not None
        
        date2 = parse_date("2024-01-15")
        assert date2 is not None
        assert date2.year == 2024
    
    def test_is_valid_url(self):
        assert is_valid_url("https://www.example.com/job/123") == True
        assert is_valid_url("http://example.com") == True
        assert is_valid_url("not-a-url") == False
        assert is_valid_url("") == False
    
    def test_validate_job_data(self):
        valid_job = {
            'job_title': 'Data Engineer',
            'posting_url': 'https://example.com/job/1',
            'source': 'BrighterMonday'
        }
        is_valid, errors = validate_job_data(valid_job)
        assert is_valid == True
        assert len(errors) == 0
        
        invalid_job = {
            'job_title': 'Data Engineer',
        }
        is_valid, errors = validate_job_data(invalid_job)
        assert is_valid == False
        assert len(errors) > 0

class TestKeywordMatching:
    
    def test_keyword_import(self):
        from utils import get_matcher
        matcher = get_matcher()
        assert matcher is not None
    
    def test_basic_keyword_match(self):
        from utils import match_keywords
        
        text = "Looking for a Data Engineer with Python, PostgreSQL, and AWS experience"
        keywords = match_keywords(text)
        
        assert len(keywords) > 0
        assert any(kw in ['Python', 'PostgreSQL', 'AWS'] for kw in keywords)

class TestDatabaseOperations:
    
    @pytest.mark.skipif(not Path(__file__).parent.parent.joinpath('.env').exists(),
                        reason="No .env file - skipping DB tests")
    def test_db_connection(self):
        from utils import test_connection
        result = test_connection()
        assert isinstance(result, bool)

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])