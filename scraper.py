import requests
from bs4 import BeautifulSoup
import urllib.parse
import time
import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def fetch_html(url):
    try:
        user_agent = get_random_user_agent()
        headers = {"User-Agent": user_agent}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

def scrape_saramin(keyword):
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://www.saramin.co.kr/zf_user/search/recruit?searchword={encoded_keyword}&loc_mcd=101000,102000,108000&exp_cd=1,2"
    
    html = fetch_html(url)
    if not html: return []
    
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    for element in soup.select(".item_recruit"):
        if len(results) >= 10: break
        
        title_el = element.select_one(".area_job .job_tit a")
        company_el = element.select_one(".area_corp .corp_name a")
        deadline_el = element.select_one(".job_date .date")
        
        if not (title_el and company_el and deadline_el): continue
        
        title = title_el.get('title') or title_el.get_text(strip=True)
        company_name = company_el.get('title') or company_el.get_text(strip=True)
        link_path = title_el.get('href', '')
        deadline = deadline_el.get_text(strip=True)
        
        if title and company_name and link_path:
            results.append({
                "title": title,
                "companyName": company_name,
                "link": link_path if link_path.startswith("http") else f"https://www.saramin.co.kr{link_path}",
                "deadline": deadline
            })
            
    return results

def scrape_jobkorea(keyword):
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://www.jobkorea.co.kr/Search/?stext={encoded_keyword}"
    
    html = fetch_html(url)
    if not html: return []
    
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    for element in soup.select(".list-post article"):
        if len(results) >= 10: break
        
        title_el = element.select_one(".post-list-info .title")
        company_el = element.select_one(".post-list-corp .name")
        deadline_el = element.select_one(".post-list-info .option .exp")
        
        if not (title_el and company_el and deadline_el): continue
        
        title = title_el.get('title') or title_el.get_text(strip=True)
        company_name = company_el.get('title') or company_el.get_text(strip=True)
        link_path = title_el.get('href', '')
        deadline = deadline_el.get_text(strip=True)
        
        if title and company_name and link_path:
            results.append({
                "title": title,
                "companyName": company_name,
                "link": link_path if link_path.startswith("http") else f"https://www.jobkorea.co.kr{link_path}",
                "deadline": deadline
            })
            
    return results

def scrape_catch(keyword):
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://www.catch.co.kr/Search/SearchList?Keyword={encoded_keyword}"
    
    html = fetch_html(url)
    if not html: return []
    
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    for element in soup.select(".table2 tbody tr"):
        if len(results) >= 10: break
        
        title_el = element.select_one(".t2 .name")
        company_el = element.select_one(".t1")
        deadline_el = element.select_one(".num_dday span")
        link_el = element.select_one("a.tdlink.al")
        
        if not (title_el and company_el and deadline_el and link_el): continue
        
        title = title_el.get_text(strip=True)
        company_name = company_el.get_text(strip=True)
        link_path = link_el.get('href', '')
        deadline = deadline_el.get_text(strip=True)
        
        if title and company_name and link_path:
            results.append({
                "title": title,
                "companyName": company_name,
                "link": link_path if link_path.startswith("http") else f"https://www.catch.co.kr{link_path}",
                "deadline": deadline
            })
            
    return results

def run_full_scraping():
    keywords = ["항체", "진단키트"]
    all_results = []
    
    for keyword in keywords:
        print(f"Scraping for keyword: {keyword}")
        
        saramin_results = scrape_saramin(keyword)
        all_results.extend(saramin_results)
        time.sleep(1)
        
        jobkorea_results = scrape_jobkorea(keyword)
        all_results.extend(jobkorea_results)
        time.sleep(1)
        
        catch_results = scrape_catch(keyword)
        all_results.extend(catch_results)
        time.sleep(1)
        
    unique_links = set()
    must_include_keywords = ["항체", "진단키트"]
    excluded_keywords = [
        "상무", "임상", "인턴", "UI/UX", "해외 사업", "해외영업",
        "터널", "건축", "토목", "회계", "재무", "디자인", "마케팅", "물류운송"
    ]
    
    filtered_results = []
    for item in all_results:
        is_must_include = any(mk in item["title"] for mk in must_include_keywords)
        
        if not is_must_include:
            has_excluded_keyword = any(ex in item["title"] or ex in item["companyName"] for ex in excluded_keywords)
            if has_excluded_keyword: continue
            
        if item["link"] in unique_links: continue
        
        unique_links.add(item["link"])
        filtered_results.append(item)
        
    return filtered_results
