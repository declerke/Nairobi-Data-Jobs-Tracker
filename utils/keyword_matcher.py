import logging
import re
from typing import List, Dict, Optional, Any, Union, Set, Tuple
from collections import Counter

logger = logging.getLogger(__name__)

class KeywordMatcher:
    
    DEFAULT_KEYWORDS = [
        'Python', 'SQL', 'R', 'Java', 'Scala', 'JavaScript', 'Go',
        'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Cassandra',
        'Snowflake', 'BigQuery', 'Redshift', 'DynamoDB',
        'FastAPI', 'Flask', 'Django', 'Pandas', 'NumPy', 'Scikit-learn',
        'TensorFlow', 'PyTorch', 'Spark', 'Kafka', 'Airflow', 'dbt',
        'AWS', 'Azure', 'GCP', 'Google Cloud', 'Amazon Web Services',
        'Docker', 'Kubernetes', 'Git', 'GitHub', 'GitLab', 'Jenkins',
        'Terraform', 'CI/CD',
        'Tableau', 'Power BI', 'Looker', 'Metabase', 'Superset',
        'ETL', 'ELT', 'Data Pipeline', 'Data Warehouse', 'Data Lake',
        'Stream Processing', 'Batch Processing',
        'Machine Learning', 'ML', 'Deep Learning', 'NLP', 'Computer Vision',
        'Neural Networks', 'Random Forest', 'XGBoost'
    ]
    
    KEYWORD_VARIATIONS = {
        'PostgreSQL': ['postgres', 'postgresql', 'psql'],
        'MySQL': ['mysql', 'my sql'],
        'FastAPI': ['fastapi', 'fast api'],
        'AWS': ['aws', 'amazon web services', 'amazon aws'],
        'GCP': ['gcp', 'google cloud platform', 'google cloud'],
        'Azure': ['azure', 'microsoft azure', 'ms azure'],
        'Git': ['git', 'version control'],
        'GitHub': ['github', 'git hub'],
        'Docker': ['docker', 'containerization', 'containers'],
        'Kubernetes': ['kubernetes', 'k8s'],
        'Machine Learning': ['machine learning', 'ml', 'machinelearning'],
        'Data Science': ['data science', 'datascience'],
        'Pandas': ['pandas', 'pd'],
        'NumPy': ['numpy', 'np'],
        'Scikit-learn': ['scikit-learn', 'sklearn', 'scikit learn'],
        'TensorFlow': ['tensorflow', 'tf'],
        'PyTorch': ['pytorch', 'torch'],
        'Airflow': ['airflow', 'apache airflow'],
        'Spark': ['spark', 'apache spark', 'pyspark'],
        'Kafka': ['kafka', 'apache kafka'],
        'CI/CD': ['ci/cd', 'cicd', 'continuous integration', 'continuous deployment'],
        'ETL': ['etl', 'extract transform load'],
        'Power BI': ['power bi', 'powerbi', 'power-bi'],
    }
    
    KEYWORD_WEIGHTS = {
        'FastAPI': 3,
        'PostgreSQL': 3,
        'Docker': 3,
        'Kafka': 3,
        'Airflow': 3,
        'Spark': 3,
        'AWS': 2.5,
        'Azure': 2.5,
        'GCP': 2.5,
        'Python': 2,
        'SQL': 2,
        'Pandas': 2,
        'MySQL': 2,
        'Git': 2,
        'ETL': 2,
    }

    def __init__(self, target_keywords: List[str] = None, case_sensitive: bool = False):
        self.target_keywords = target_keywords or self.DEFAULT_KEYWORDS
        self.case_sensitive = case_sensitive
        self._build_patterns()
        logger.info(f"KeywordMatcher initialized with {len(self.target_keywords)} keywords")
    
    def _build_patterns(self):
        self.patterns = {}
        for keyword in self.target_keywords:
            variations = self.KEYWORD_VARIATIONS.get(keyword, [keyword])
            if keyword.lower() not in [v.lower() for v in variations]:
                variations.append(keyword)
            
            patterns = []
            for variant in variations:
                escaped = re.escape(variant)
                pattern = r'\b' + escaped + r'\b'
                patterns.append(pattern)
            
            combined_pattern = '|'.join(patterns)
            flags = 0 if self.case_sensitive else re.IGNORECASE
            self.patterns[keyword] = re.compile(combined_pattern, flags)
    
    def match_keywords(self, text: str) -> List[str]:
        if not text:
            return []
        matched = set()
        for keyword, pattern in self.patterns.items():
            if pattern.search(text):
                matched.add(keyword)
        return sorted(list(matched))
    
    def match_with_context(self, text: str, context_chars: int = 50) -> Dict[str, List[str]]:
        if not text:
            return {}
        results = {}
        for keyword, pattern in self.patterns.items():
            matches = pattern.finditer(text)
            contexts = []
            for match in matches:
                start = max(0, match.start() - context_chars)
                end = min(len(text), match.end() + context_chars)
                context = text[start:end].strip()
                contexts.append(context)
            if contexts:
                results[keyword] = contexts
        return results
    
    def score_job(self, job_data: Dict) -> Tuple[float, List[str]]:
        title = job_data.get('job_title', '')
        description = job_data.get('description', '')
        full_desc = job_data.get('full_description', '')
        combined_text = f"{title} {description} {full_desc}"
        
        matched_keywords = self.match_keywords(combined_text)
        score = 0.0
        for keyword in matched_keywords:
            weight = self.KEYWORD_WEIGHTS.get(keyword, 1.0)
            if self.patterns[keyword].search(title):
                weight *= 1.5
            score += weight
        return score, matched_keywords
    
    def extract_skills(self, text: str) -> Dict[str, List[str]]:
        matched = self.match_keywords(text)
        categories = {
            'languages': [],
            'databases': [],
            'cloud': [],
            'frameworks': [],
            'tools': [],
            'other': []
        }
        
        language_keywords = {'Python', 'SQL', 'R', 'Java', 'Scala', 'JavaScript', 'Go'}
        database_keywords = {'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Cassandra', 
                           'Snowflake', 'BigQuery', 'Redshift', 'DynamoDB'}
        cloud_keywords = {'AWS', 'Azure', 'GCP', 'Google Cloud', 'Amazon Web Services'}
        framework_keywords = {'FastAPI', 'Flask', 'Django', 'Pandas', 'NumPy', 
                            'Scikit-learn', 'TensorFlow', 'PyTorch', 'Spark'}
        tool_keywords = {'Docker', 'Kubernetes', 'Git', 'GitHub', 'GitLab', 
                        'Jenkins', 'Terraform', 'Airflow', 'Kafka', 'dbt'}
        
        for keyword in matched:
            if keyword in language_keywords:
                categories['languages'].append(keyword)
            elif keyword in database_keywords:
                categories['databases'].append(keyword)
            elif keyword in cloud_keywords:
                categories['cloud'].append(keyword)
            elif keyword in framework_keywords:
                categories['frameworks'].append(keyword)
            elif keyword in tool_keywords:
                categories['tools'].append(keyword)
            else:
                categories['other'].append(keyword)
        
        return {k: v for k, v in categories.items() if v}
    
    def get_keyword_frequency(self, text: str) -> Counter:
        frequencies = Counter()
        for keyword, pattern in self.patterns.items():
            matches = pattern.findall(text)
            if matches:
                frequencies[keyword] = len(matches)
        return frequencies
    
    def suggest_missing_skills(self, matched_keywords: List[str]) -> List[str]:
        pairings = {
            'Python': ['Pandas', 'NumPy', 'FastAPI', 'Flask'],
            'SQL': ['PostgreSQL', 'MySQL'],
            'AWS': ['Docker', 'Kubernetes'],
            'Docker': ['Kubernetes', 'CI/CD'],
            'Pandas': ['NumPy', 'Python'],
            'FastAPI': ['Python', 'PostgreSQL'],
            'Airflow': ['Python', 'ETL'],
            'Spark': ['Python', 'Scala', 'Kafka'],
        }
        
        suggestions = set()
        for keyword in matched_keywords:
            if keyword in pairings:
                for paired in pairings[keyword]:
                    if paired not in matched_keywords:
                        suggestions.add(paired)
        return sorted(list(suggestions))
    
    def analyze_job_batch(self, jobs: List[Dict]) -> Dict[str, Any]:
        all_keywords = []
        scores = []
        for job in jobs:
            score, keywords = self.score_job(job)
            all_keywords.extend(keywords)
            scores.append(score)
        
        keyword_counts = Counter(all_keywords)
        return {
            'total_jobs': len(jobs),
            'avg_score': sum(scores) / len(scores) if scores else 0,
            'max_score': max(scores) if scores else 0,
            'min_score': min(scores) if scores else 0,
            'top_keywords': keyword_counts.most_common(10),
            'total_unique_keywords': len(keyword_counts),
            'avg_keywords_per_job': len(all_keywords) / len(jobs) if jobs else 0
        }

def process_job_for_keywords(job_data: Dict, keywords: List[str] = None) -> Dict:
    matcher = KeywordMatcher(target_keywords=keywords)
    score, matched = matcher.score_job(job_data)
    job_data['keywords_matched'] = matched
    job_data['keyword_count'] = len(matched)
    job_data['keyword_score'] = score
    return job_data

def batch_process_keywords(jobs: List[Dict], keywords: List[str] = None) -> List[Dict]:
    matcher = KeywordMatcher(target_keywords=keywords)
    processed_jobs = []
    for job in jobs:
        score, matched = matcher.score_job(job)
        job['keywords_matched'] = matched
        job['keyword_count'] = len(matched)
        job['keyword_score'] = score
        processed_jobs.append(job)
    logger.info(f"Processed {len(jobs)} jobs for keyword matching")
    return processed_jobs

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    matcher = KeywordMatcher()
    test_job = {
        'job_title': 'Senior Data Engineer',
        'description': 'We are looking for a Data Engineer with experience in Python, PostgreSQL, and AWS.',
        'full_description': """
        Requirements:
        - 3+ years experience with Python and SQL
        - Strong knowledge of PostgreSQL and MySQL
        - Experience with cloud platforms (AWS, Azure, or GCP)
        - Familiarity with Docker and Kubernetes
        - Knowledge of data pipeline tools like Airflow or Kafka
        - Experience with FastAPI or Flask
        
        Nice to have:
        - Pandas and NumPy for data processing
        - Git/GitHub for version control
        - CI/CD experience
        """
    }
    score, keywords = matcher.score_job(test_job)
    print(f"\n✓ Matched keywords ({len(keywords)}): {', '.join(keywords)}")
    print(f"✓ Job score: {score:.2f}")
    skills = matcher.extract_skills(test_job['full_description'])
    print(f"\n✓ Extracted skills by category:")
    for category, skill_list in skills.items():
        print(f"  - {category}: {', '.join(skill_list)}")
    suggestions = matcher.suggest_missing_skills(keywords)
    print(f"\n✓ Suggested missing skills: {', '.join(suggestions) if suggestions else 'None'}")
    
_matcher_instance = None

_matcher_instance = None

_matcher_instance = None

_matcher_instance = None

def get_matcher() -> 'KeywordMatcher':
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = KeywordMatcher()
    return _matcher_instance

def match_keywords(text: str) -> List[str]:
    # Changed from 'extract_keywords' to 'find_matches' to match class
    return get_matcher().find_matches(text) 

def match_in_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    # Changed from 'analyze_job' to 'process_job' to match class
    return get_matcher().process_job(job_data)
