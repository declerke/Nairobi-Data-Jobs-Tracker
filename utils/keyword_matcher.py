import logging
import re
from typing import List, Dict, Optional, Any, Union, Set, Tuple
from collections import Counter

logger = logging.getLogger(__name__)

class KeywordMatcher:
    
    DEFAULT_KEYWORDS = [
        # ── Data Engineering ────────────────────────────────────────────────
        'Data Engineer', 'Python', 'SQL', 'ETL', 'ELT', 'Data Pipeline',
        'Airflow', 'Kafka', 'Spark', 'dbt', 'Pandas', 'PySpark', 'Databricks',
        'PostgreSQL', 'MySQL', 'BigQuery', 'Snowflake', 'Redshift',
        'AWS', 'Azure', 'GCP', 'Docker', 'Kubernetes', 'Terraform',
        'FastAPI', 'Flask', 'MLOps',
        # ── Data Analysis / BI ──────────────────────────────────────────────
        'Data Analyst', 'Analytics', 'Business Intelligence', 'BI Analyst',
        'Power BI', 'Tableau', 'Looker', 'Metabase', 'Excel',
        'Data Visualization', 'Reporting', 'Dashboard', 'Statistical Analysis',
        'R', 'SPSS', 'Google Analytics', 'Analyst',
        # ── Information Technology ───────────────────────────────────────────
        'IT Officer', 'IT Support', 'IT Manager', 'System Administrator',
        'Network Administrator', 'Network Engineer', 'IT Technician',
        'Help Desk', 'Service Desk', 'ITIL', 'Linux', 'Windows Server',
        'Active Directory', 'Cybersecurity', 'Cloud Computing', 'DevOps',
        'Technical Support', 'Infrastructure', 'IT Analyst',
        'Systems Analyst', 'ICT Officer',
        # ── Graduate / Entry-Level ───────────────────────────────────────────
        'Graduate', 'Trainee', 'Intern', 'Internship', 'Entry Level',
        'Fresh Graduate', 'Junior', 'Attachment', 'Industrial Attachment',
        'Management Trainee', 'Graduate Program',
        # ── Database Management ──────────────────────────────────────────────
        'DBA', 'Database Administrator', 'Database Developer', 'Oracle',
        'MongoDB', 'Redis', 'SQL Server', 'MSSQL', 'NoSQL',
        'Database Design', 'Cassandra', 'Database Engineer', 'MariaDB',
    ]

    KEYWORD_VARIATIONS = {
        # Data Engineering
        'Data Engineer':          ['data engineer', 'data engineering'],
        'Python':                 ['python', 'python3'],
        'SQL':                    ['sql', 'structured query language'],
        'ETL':                    ['etl', 'extract transform load', 'extract, transform'],
        'Airflow':                ['airflow', 'apache airflow'],
        'Spark':                  ['spark', 'apache spark', 'pyspark'],
        'Kafka':                  ['kafka', 'apache kafka'],
        'PostgreSQL':             ['postgres', 'postgresql', 'psql'],
        'MySQL':                  ['mysql', 'my sql'],
        'AWS':                    ['aws', 'amazon web services'],
        'GCP':                    ['gcp', 'google cloud platform', 'google cloud'],
        'Azure':                  ['azure', 'microsoft azure', 'ms azure'],
        'Docker':                 ['docker', 'containerization', 'containers'],
        'Kubernetes':             ['kubernetes', 'k8s'],
        'Terraform':              ['terraform', 'infrastructure as code', 'iac'],
        'FastAPI':                ['fastapi', 'fast api'],
        # Data Analysis / BI
        'Data Analyst':           ['data analyst', 'data analysis', 'analyst'],
        'Analytics':              ['analytics', 'analytical'],
        'Business Intelligence':  ['business intelligence', 'bi', 'b.i.'],
        'BI Analyst':             ['bi analyst', 'business analyst', 'business analysis'],
        'Power BI':               ['power bi', 'powerbi', 'power-bi'],
        'Tableau':                ['tableau'],
        'Data Visualization':     ['data visualization', 'data visualisation', 'dataviz'],
        'Excel':                  ['excel', 'microsoft excel', 'spreadsheet'],
        'Statistical Analysis':   ['statistical analysis', 'statistics', 'statistical'],
        # Information Technology
        'IT Officer':             ['it officer', 'ict officer', 'information technology officer'],
        'IT Support':             ['it support', 'ict support', 'tech support', 'technical support'],
        'IT Manager':             ['it manager', 'ict manager', 'technology manager'],
        'System Administrator':   ['system administrator', 'sysadmin', 'systems admin'],
        'Network Administrator':  ['network administrator', 'network admin'],
        'Network Engineer':       ['network engineer', 'networking engineer'],
        'Help Desk':              ['help desk', 'helpdesk', 'service desk', 'it helpdesk'],
        'ITIL':                   ['itil', 'it infrastructure library'],
        'Cybersecurity':          ['cybersecurity', 'cyber security', 'information security', 'infosec'],
        'Cloud Computing':        ['cloud computing', 'cloud infrastructure', 'cloud services'],
        'DevOps':                 ['devops', 'dev ops', 'site reliability', 'sre'],
        'Systems Analyst':        ['systems analyst', 'system analyst', 'it analyst'],
        'ICT Officer':            ['ict officer', 'ict', 'information communication technology'],
        # Graduate / Entry-Level
        'Graduate':               ['graduate', 'graduates', 'grad'],
        'Trainee':                ['trainee', 'traineeship'],
        'Intern':                 ['intern', 'interns'],
        'Internship':             ['internship', 'internships', 'attachment'],
        'Entry Level':            ['entry level', 'entry-level', 'entry position'],
        'Fresh Graduate':         ['fresh graduate', 'recent graduate', 'newly graduated'],
        'Junior':                 ['junior', 'jr.', 'associate'],
        'Industrial Attachment':  ['industrial attachment', 'industry attachment'],
        'Management Trainee':     ['management trainee', 'management trainee program'],
        'Graduate Program':       ['graduate program', 'graduate programme', 'graduate scheme'],
        # Database Management
        'DBA':                    ['dba', 'database administrator', 'db admin'],
        'Database Administrator': ['database administrator', 'database admin', 'dba'],
        'Database Developer':     ['database developer', 'db developer'],
        'Oracle':                 ['oracle', 'oracle database', 'oracle dba'],
        'MongoDB':                ['mongodb', 'mongo db', 'mongo'],
        'SQL Server':             ['sql server', 'mssql', 'microsoft sql server'],
        'MSSQL':                  ['mssql', 'ms sql', 'sql server'],
        'NoSQL':                  ['nosql', 'no-sql', 'non-relational'],
        'Database Design':        ['database design', 'schema design', 'data modeling', 'data modelling'],
        'Database Engineer':      ['database engineer', 'db engineer'],
    }

    KEYWORD_WEIGHTS = {
        # High-value: exact role titles Ian is targeting
        'Data Engineer':          5,
        'Data Analyst':           5,
        'Database Administrator': 5,
        'Graduate Program':       5,
        'Management Trainee':     5,
        'Internship':             4,
        'Graduate':               4,
        'Business Intelligence':  4,
        'IT Officer':             4,
        'Systems Analyst':        4,
        # Core technical skills
        'Python':                 3,
        'SQL':                    3,
        'ETL':                    3,
        'Airflow':                3,
        'PostgreSQL':             3,
        'Power BI':               3,
        'Tableau':                3,
        'AWS':                    2.5,
        'Azure':                  2.5,
        'GCP':                    2.5,
        'Docker':                 2.5,
        'Spark':                  2.5,
        'Kafka':                  2.5,
        'dbt':                    2.5,
        'Cybersecurity':          2.5,
        'DevOps':                 2.5,
        # Supporting skills
        'MySQL':                  2,
        'MongoDB':                2,
        'Excel':                  2,
        'Analytics':              2,
        'Linux':                  2,
        'Network Engineer':       2,
        'IT Support':             2,
        'Trainee':                2,
        'Intern':                 2,
        'Junior':                 1.5,
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


def get_matcher() -> 'KeywordMatcher':
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = KeywordMatcher()
    return _matcher_instance


def match_keywords(text: str) -> List[str]:
    return get_matcher().match_keywords(text)


def match_in_job(job_data: Dict[str, Any]) -> Dict[str, Any]:
    matcher = get_matcher()
    score, keywords = matcher.score_job(job_data)
    job_data['keywords_matched'] = keywords
    job_data['keyword_count'] = len(keywords)
    return job_data
