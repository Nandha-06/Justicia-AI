import asyncio
import json
import os
import sys
import time
import re
from bs4 import BeautifulSoup
import requests

# Ensure data directory exists
os.makedirs("data", exist_ok=True)
CACHE_FILE = "data/bns_sections.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def parse_html_content(html_content, section_id):
    """
    Parses BNS page HTML to extract chapter, section number, title, and content.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Initialize defaults
    chapter = "General"
    sec_num = str(section_id)
    sec_title = f"Section {section_id}"
    desc_html = ""
    desc_text = ""
    
    # 1. Parse Chapter
    chapter_elem = soup.find(class_="title fill")
    if chapter_elem:
        chapter = chapter_elem.get_text().strip()
    else:
        # Fallback search for header
        th_title = soup.find("th", class_="title")
        if th_title:
            chapter = th_title.get_text().strip()
            
    # 2. Parse Section Head (Number & Title)
    head_tr = soup.find(class_="mys-head")
    if head_tr:
        strong_elem = head_tr.find("strong")
        if strong_elem:
            sec_num = strong_elem.get_text().strip()
        h2_elems = head_tr.find_all("h2")
        if len(h2_elems) > 1:
            sec_title = h2_elems[1].get_text().strip()
    
    # 3. Parse Description Content
    desc_tr = soup.find(class_="mys-desc")
    if desc_tr:
        td_elem = desc_tr.find("td")
        if td_elem:
            desc_html = td_elem.decode_contents().strip()
            desc_text = td_elem.get_text(separator="\n").strip()
            # Clean up whitespace and non-breaking spaces
            desc_text = re.sub(r'\xa0', ' ', desc_text)
            desc_text = re.sub(r'\n+', '\n', desc_text)
            
    # Clean section number
    sec_num = re.sub(r'[^\w\s\.-]', '', sec_num).strip()
            
    return {
        "section_id": section_id,
        "section_number": sec_num,
        "section_title": sec_title,
        "chapter": chapter,
        "content_html": desc_html,
        "content_text": desc_text,
        "source_url": f"https://devgan.in/bns/section/{section_id}/"
    }

async def crawl_with_crawl4ai(section_id):
    """
    Crawls a single BNS page using Crawl4AI.
    """
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
    url = f"https://devgan.in/bns/section/{section_id}/"
    
    # Configure crawl run settings (disable cache to get fresh pages)
    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS
    )
    
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url, config=config)
        if result and result.success:
            return parse_html_content(result.html, section_id)
        else:
            raise Exception(f"Crawl4AI failed to fetch page: {result.error_message if result else 'Unknown'}")

def crawl_with_requests(section_id):
    """
    Fallback crawl method using standard requests and BeautifulSoup.
    """
    url = f"https://devgan.in/bns/section/{section_id}/"
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return parse_html_content(response.text, section_id)

def load_cached_data():
    """
    Loads crawled sections from local JSON cache if exists.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Map by section ID for easy lookup
                return {item["section_id"]: item for item in data}
        except Exception as e:
            print(f"Error reading cache file {CACHE_FILE}: {e}. Starting fresh.")
    return {}

def save_data(sections_dict):
    """
    Saves sections list sorted by section_id to JSON file.
    """
    sorted_sections = [sections_dict[sid] for sid in sorted(sections_dict.keys())]
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted_sections, f, indent=4, ensure_ascii=False)
    print(f"Saved {len(sorted_sections)} sections to {CACHE_FILE}")

async def scrape_bns(start=1, end=358, use_crawl4ai=True):
    """
    Main loop to scrape BNS sections sequentially.
    """
    cached_sections = load_cached_data()
    print(f"Loaded {len(cached_sections)} sections from cache.")
    
    to_scrape = [sid for sid in range(start, end + 1) if sid not in cached_sections]
    if not to_scrape:
        print("All requested sections are already cached!")
        return list(cached_sections.values())
        
    if use_crawl4ai:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
        config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS)
        
        print("Booting AsyncWebCrawler...")
        async with AsyncWebCrawler() as crawler:
            for section_id in to_scrape:
                print(f"Scraping Section {section_id}/{end}...")
                success = False
                retry_count = 0
                max_retries = 3
                
                while not success and retry_count < max_retries:
                    try:
                        url = f"https://devgan.in/bns/section/{section_id}/"
                        result = await crawler.arun(url=url, config=config)
                        if result and result.success:
                            section_data = parse_html_content(result.html, section_id)
                            success = True
                        else:
                            raise Exception(result.error_message if result else "Unknown Crawl4AI error")
                    except Exception as e:
                        print(f"Crawl4AI failed for section {section_id}: {e}. Trying fallback requests...")
                        try:
                            section_data = crawl_with_requests(section_id)
                            success = True
                        except Exception as req_err:
                            retry_count += 1
                            print(f"Fallback requests also failed for section {section_id} (Attempt {retry_count}/{max_retries}): {req_err}")
                            if retry_count < max_retries:
                                await asyncio.sleep(2)
                
                if success:
                    if not section_data["content_text"]:
                        print(f"Warning: Section {section_id} text was empty!")
                    cached_sections[section_id] = section_data
                    if len(cached_sections) % 10 == 0 or section_id == end:
                        save_data(cached_sections)
                    await asyncio.sleep(0.2)
    else:
        for section_id in to_scrape:
            print(f"Scraping Section {section_id}/{end} using requests fallback...")
            success = False
            retry_count = 0
            max_retries = 3
            
            while not success and retry_count < max_retries:
                try:
                    section_data = crawl_with_requests(section_id)
                    success = True
                except Exception as e:
                    retry_count += 1
                    print(f"Error scraping Section {section_id} (Attempt {retry_count}/{max_retries}): {e}")
                    if retry_count < max_retries:
                        await asyncio.sleep(2)
            
            if success:
                if not section_data["content_text"]:
                    print(f"Warning: Section {section_id} text was empty!")
                cached_sections[section_id] = section_data
                if len(cached_sections) % 10 == 0 or section_id == end:
                    save_data(cached_sections)
                await asyncio.sleep(0.2)
                
    save_data(cached_sections)
    print("Scraping completed!")
    return list(cached_sections.values())

if __name__ == "__main__":
    # Allow passing custom range from command line
    start_sec = 1
    end_sec = 358
    try_crawl4ai = True
    
    if len(sys.argv) > 1:
        start_sec = int(sys.argv[1])
    if len(sys.argv) > 2:
        end_sec = int(sys.argv[2])
    if len(sys.argv) > 3:
        try_crawl4ai = sys.argv[3].lower() == "true"
        
    print(f"Starting BNS scraper. Range: Section {start_sec} to {end_sec}. Use Crawl4AI: {try_crawl4ai}")
    asyncio.run(scrape_bns(start_sec, end_sec, use_crawl4ai=try_crawl4ai))
