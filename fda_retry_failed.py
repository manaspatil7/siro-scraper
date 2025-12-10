"""
FDA Smart Retry - Scans folder & downloads only missing files
==============================================================
- Scans your existing PDF folder
- Scrapes FDA website to get all entries
- Compares and downloads ONLY what's missing
- No CSV dependency - works directly with files on disk
"""

import time
import re
import random
from pathlib import Path
from typing import List, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ---------- CONFIG ----------
BASE_URL = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"
OUTPUT_DIR = "FDA_Guidance_Document"

PAGE_LOAD_WAIT = 2
MAX_WORKERS = 5
# ----------------------------

print_lock = threading.Lock()

HEADERS_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def safe_print(*args, **kwargs):
    with print_lock:
        print(*args, **kwargs)


def sanitize_filename(name: str, default: str = "file") -> str:
    name = name.strip() if name else default
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name[:150].strip() or default


def get_random_headers():
    return {
        "User-Agent": random.choice(HEADERS_LIST),
        "Referer": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents",
    }


def setup_driver(headless: bool = True):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(f"--user-agent={random.choice(HEADERS_LIST)}")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    return driver


def scan_existing_files(folder: Path) -> Set[str]:
    """Scan folder and return set of sanitized titles (from filenames)."""
    existing = set()
    
    if not folder.exists():
        return existing
    
    for pdf in folder.glob("*.pdf"):
        # Extract title from filename: "0001_Title Here.pdf" -> "Title Here"
        name = pdf.stem  # Remove .pdf
        # Remove index prefix if present
        if re.match(r'^\d{4}_', name):
            name = name[5:]  # Remove "0001_"
        existing.add(name.lower().strip())
    
    return existing


def title_exists(title: str, existing_titles: Set[str]) -> bool:
    """Check if a title already exists in downloaded files."""
    sanitized = sanitize_filename(title).lower().strip()
    
    # Direct match
    if sanitized in existing_titles:
        return True
    
    # Partial match (first 50 chars) - handles truncation
    sanitized_short = sanitized[:50]
    for existing in existing_titles:
        if existing.startswith(sanitized_short) or sanitized_short.startswith(existing[:50]):
            return True
    
    return False


def collect_table_rows(driver) -> List[Dict]:
    """Collect entries from current page."""
    entries = []
    
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "#DataTables_Table_0 tbody tr")
        
        for row in rows:
            try:
                entry = {"title": "", "download_url": ""}
                
                all_links = row.find_elements(By.TAG_NAME, "a")
                for link in all_links:
                    href = link.get_attribute("href") or ""
                    text = link.text.strip()
                    
                    if "/media/" in href and "/download" in href:
                        entry["download_url"] = href
                    elif text and not entry["title"]:
                        entry["title"] = text
                
                if entry["title"] and entry["download_url"]:
                    entries.append(entry)
                    
            except:
                continue
                
    except Exception as e:
        print(f"    Error: {e}")
    
    return entries


def click_next(driver) -> bool:
    """Click next page button."""
    try:
        next_btn = driver.find_element(By.CSS_SELECTOR, ".dataTables_paginate .next:not(.disabled)")
        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(PAGE_LOAD_WAIT)
        return True
    except:
        return False


def download_file(entry: dict, output_dir: Path, index: int, session: requests.Session) -> tuple:
    """Download a single file."""
    url = entry.get("download_url", "")
    title = entry.get("title", f"document_{index}")
    
    if not url:
        return (False, "No URL")
    
    if url.startswith("/"):
        url = f"https://www.fda.gov{url}"
    
    filename = f"{index:04d}_{sanitize_filename(title)}.pdf"
    filepath = output_dir / filename
    
    if filepath.exists() and filepath.stat().st_size > 1000:
        return (True, "Exists")
    
    # Try download with retries
    for attempt in range(2):
        try:
            headers = {
                "User-Agent": random.choice(HEADERS_LIST),
                "Accept": "application/pdf,*/*",
                "Referer": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents",
            }
            
            with session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) as r:
                if r.status_code == 200:
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    if filepath.exists() and filepath.stat().st_size > 1000:
                        return (True, filename)
                    else:
                        filepath.unlink(missing_ok=True)
                elif r.status_code == 404:
                    # This URL genuinely doesn't exist on FDA
                    return (False, f"404 - PDF removed from FDA")
                else:
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    return (False, f"HTTP {r.status_code}")
                    
        except Exception as e:
            if attempt == 0:
                time.sleep(1)
                continue
            return (False, str(e)[:25])
    
    return (False, "Failed")


def main():
    out_dir = Path(OUTPUT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Scan existing files
    print("📁 Scanning existing files...")
    existing_titles = scan_existing_files(out_dir)
    print(f"   Found {len(existing_titles)} existing PDFs\n")
    
    # Step 2: Setup browser
    print("🌐 Loading FDA website...")
    driver = setup_driver(headless=False)
    session = requests.Session()
    
    try:
        driver.get(BASE_URL)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#DataTables_Table_0 tbody tr"))
        )
        time.sleep(PAGE_LOAD_WAIT)
        
        # Copy cookies
        for cookie in driver.get_cookies():
            session.cookies.set(cookie['name'], cookie['value'])
        
        # Get total pages
        try:
            info = driver.find_element(By.CSS_SELECTOR, "#DataTables_Table_0_info").text
            print(f"📊 {info}")
        except:
            pass
        
        # Step 3: Scan all pages and find missing
        print("\n🔍 Scanning FDA pages for missing files...\n")
        
        missing_entries = []
        page_num = 0
        total_checked = 0
        
        while True:
            page_num += 1
            entries = collect_table_rows(driver)
            
            page_missing = []
            for entry in entries:
                total_checked += 1
                if not title_exists(entry["title"], existing_titles):
                    page_missing.append(entry)
            
            if page_missing:
                missing_entries.extend(page_missing)
                print(f"   Page {page_num}: {len(page_missing)} missing (total missing: {len(missing_entries)})")
            else:
                print(f"   Page {page_num}: ✓ all exist")
            
            # Next page
            if not click_next(driver):
                break
            
            # Safety limit
            if page_num >= 280:
                break
        
        print(f"\n📊 Scan complete!")
        print(f"   Total entries checked: {total_checked}")
        print(f"   Already downloaded: {total_checked - len(missing_entries)}")
        print(f"   Missing: {len(missing_entries)}")
        
        if not missing_entries:
            print("\n✅ All files already downloaded! Nothing to do.")
            return
        
        # Step 4: Download missing files using BROWSER (more reliable)
        print(f"\n📥 Downloading {len(missing_entries)} missing files...")
        print("   Using browser download method (more reliable)\n")
        
        downloaded = 0
        failed = 0
        start_index = len(existing_titles) + 1
        
        for i, entry in enumerate(missing_entries):
            idx = start_index + i
            title = entry["title"][:45]
            url = entry.get("download_url", "")
            
            if not url:
                failed += 1
                continue
            
            # Make URL absolute
            if url.startswith("/"):
                url = f"https://www.fda.gov{url}"
            
            filename = f"{idx:04d}_{sanitize_filename(entry['title'])}.pdf"
            filepath = out_dir / filename
            
            if filepath.exists() and filepath.stat().st_size > 1000:
                print(f"  ⏭️ [{idx}] Already exists")
                continue
            
            # Refresh session cookies every 50 downloads
            if i % 50 == 0 and i > 0:
                print(f"\n   🔄 Refreshing session (at {i}/{len(missing_entries)})...")
                driver.get(BASE_URL)
                time.sleep(2)
                session = requests.Session()
                for cookie in driver.get_cookies():
                    session.cookies.set(cookie['name'], cookie['value'])
            
            # Download with fresh headers
            try:
                headers = {
                    "User-Agent": driver.execute_script("return navigator.userAgent"),
                    "Accept": "application/pdf,application/octet-stream,*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": BASE_URL,
                    "Connection": "keep-alive",
                }
                
                resp = session.get(url, headers=headers, timeout=60, allow_redirects=True)
                
                if resp.status_code == 200 and len(resp.content) > 1000:
                    with open(filepath, "wb") as f:
                        f.write(resp.content)
                    downloaded += 1
                    print(f"  ✅ [{idx}] {title}...")
                else:
                    failed += 1
                    print(f"  ❌ [{idx}] {title}... (HTTP {resp.status_code})")
                    
            except Exception as e:
                failed += 1
                print(f"  ❌ [{idx}] {title}... ({str(e)[:25]})")
            
            # Small delay
            time.sleep(random.uniform(0.3, 0.8))
        
        print(f"\n{'='*50}")
        print(f"🎯 COMPLETE!")
        print(f"   ✅ Downloaded: {downloaded}")
        print(f"   ❌ Failed (don't exist on FDA): {failed}")
        print(f"   📁 Total files now: {len(existing_titles) + downloaded}")
        print(f"{'='*50}")
        
    except KeyboardInterrupt:
        print("\n⚠️ Interrupted!")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
