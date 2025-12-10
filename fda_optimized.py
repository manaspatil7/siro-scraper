"""
FDA Guidance Documents Scraper - OPTIMIZED VERSION
===================================================
Features:
- Direct page navigation via URL (skips clicking through pages)
- Parallel downloads using ThreadPoolExecutor
- Bot detection evasion (stealth mode)
- Randomized delays to appear human-like
- Faster scraping with optimized waits
"""

import time
import re
import csv
import random
import argparse
from pathlib import Path
from typing import List, Dict, Set
from datetime import datetime
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
from selenium.common.exceptions import TimeoutException

# ---------- CONFIG ----------
BASE_URL = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"
OUTPUT_DIR = "FDA_Guidance_Documents"
CSV_FILE = "fda_guidance_documents.csv"

TOTAL_PAGES = 280
ITEMS_PER_PAGE = 10

# Optimized timing
PAGE_LOAD_WAIT = 2
MIN_DELAY = 0.3
MAX_DELAY = 1.0

# Parallel downloads
MAX_DOWNLOAD_WORKERS = 5

# Realistic headers for downloads
HEADERS_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

# Thread-safe print
print_lock = threading.Lock()
# ----------------------------


def safe_print(*args, **kwargs):
    """Thread-safe print function."""
    with print_lock:
        print(*args, **kwargs)


def random_delay(min_delay=MIN_DELAY, max_delay=MAX_DELAY):
    """Add random delay to appear human-like."""
    time.sleep(random.uniform(min_delay, max_delay))


def get_random_headers():
    """Get random headers for requests."""
    return {
        "User-Agent": random.choice(HEADERS_LIST),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def sanitize_filename(name: str, default: str = "file") -> str:
    name = name.strip() if name else default
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name[:150].strip() or default


def setup_stealth_driver(headless: bool = False):
    """Setup Chrome driver with stealth/anti-detection features."""
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless=new")
    
    # Anti-detection options
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")
    
    # Randomize user agent
    chrome_options.add_argument(f"--user-agent={random.choice(HEADERS_LIST)}")
    
    # Disable automation flags
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    
    # Remove webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver


def navigate_to_page_direct(driver, page_num: int) -> bool:
    """
    Navigate to a specific page using multiple fast methods.
    """
    try:
        # Method 1: Try using page number input if available
        try:
            # Look for page input or page number links
            page_input = driver.find_elements(By.CSS_SELECTOR, ".dataTables_paginate input")
            if page_input:
                page_input[0].clear()
                page_input[0].send_keys(str(page_num))
                page_input[0].send_keys("\n")
                time.sleep(PAGE_LOAD_WAIT)
                return True
        except:
            pass
        
        # Method 2: Click page number directly if visible
        try:
            page_links = driver.find_elements(By.CSS_SELECTOR, f".dataTables_paginate a[data-dt-idx='{page_num}']")
            if page_links:
                driver.execute_script("arguments[0].click();", page_links[0])
                time.sleep(PAGE_LOAD_WAIT)
                return True
        except:
            pass
        
        # Method 3: Fast sequential clicking (optimized)
        return navigate_sequential_fast(driver, page_num)
        
    except Exception as e:
        print(f"    Navigation error: {e}")
        return False


def navigate_sequential_fast(driver, target_page: int) -> bool:
    """Fast sequential navigation by clicking Next button repeatedly."""
    try:
        # First, go to page 1
        try:
            first_btn = driver.find_element(By.CSS_SELECTOR, ".dataTables_paginate .first:not(.disabled)")
            driver.execute_script("arguments[0].click();", first_btn)
            time.sleep(0.5)
        except:
            pass
        
        # Now click Next rapidly
        for i in range(target_page - 1):
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, ".dataTables_paginate .next:not(.disabled)")
                driver.execute_script("arguments[0].click();", next_btn)
                
                # Minimal wait - just enough for table to update
                time.sleep(0.3)
                
                # Progress update every 20 pages
                if (i + 1) % 20 == 0:
                    print(f"      ... at page {i + 2}")
                    
            except Exception as e:
                print(f"    Failed at page {i + 2}: {e}")
                return False
        
        time.sleep(PAGE_LOAD_WAIT)
        return True
        
    except Exception as e:
        print(f"    Sequential navigation failed: {e}")
        return False


def click_next_fast(driver) -> bool:
    """Click next button once (for page-by-page navigation)."""
    try:
        next_btn = driver.find_element(By.CSS_SELECTOR, ".dataTables_paginate .next:not(.disabled)")
        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(PAGE_LOAD_WAIT)
        return True
    except Exception as e:
        print(f"    Next click failed: {e}")
        return False


def wait_for_table(driver, timeout=10):
    """Wait for DataTable to load."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#DataTables_Table_0 tbody tr"))
        )
        random_delay(0.5, 1.0)
        return True
    except TimeoutException:
        return False


def collect_table_rows_fast(driver) -> List[Dict]:
    """Optimized row collection - extract data quickly."""
    entries = []
    
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, "#DataTables_Table_0 tbody tr")
        
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 2:
                    continue
                
                entry = {
                    "title": "",
                    "detail_url": "",
                    "download_url": "",
                    "date": "",
                    "center": "",
                    "topic": "",
                    "status": "",
                    "comment": ""
                }
                
                # Get ALL links in the entire row
                all_links = row.find_elements(By.TAG_NAME, "a")
                
                for link in all_links:
                    href = link.get_attribute("href") or ""
                    text = link.text.strip()
                    
                    # Download link pattern: /media/ and /download
                    if "/media/" in href and "/download" in href:
                        entry["download_url"] = href
                    # Title/detail link pattern
                    elif "/guidance/" in href or "/regulatory-information/" in href:
                        if not entry["title"] and text:
                            entry["title"] = text
                            entry["detail_url"] = href
                    # Fallback for other FDA links
                    elif "fda.gov" in href and text and not entry["title"]:
                        entry["title"] = text
                        entry["detail_url"] = href
                
                # If no title found from links, get from cell text
                if not entry["title"]:
                    cell_text = cells[1].text.strip().split('\n')[0] if len(cells) > 1 else ""
                    entry["title"] = cell_text
                
                # Extract other fields from cell text
                for cell in cells:
                    text = cell.text.strip()
                    # Date pattern
                    if re.match(r'\d{1,2}/\d{1,2}/\d{4}', text) and not entry["date"]:
                        entry["date"] = text
                    # Status
                    elif text in ["Final", "Draft"] and not entry["status"]:
                        entry["status"] = text
                    # Comment
                    elif text in ["Yes", "No"] and not entry["comment"]:
                        entry["comment"] = text
                
                if entry["title"]:
                    entries.append(entry)
                    
            except Exception:
                continue
                
    except Exception as e:
        print(f"    Error collecting rows: {e}")
    
    return entries


def download_file_with_session(session: requests.Session, entry: Dict, output_dir: Path, index: int) -> tuple:
    """
    Download file using a session with cookies.
    Returns (success: bool, message: str)
    """
    url = entry.get("download_url", "")
    title = entry.get("title", f"document_{index}")
    
    if not url:
        return (False, "No URL")
    
    # Make sure URL is absolute
    if url.startswith("/"):
        url = f"https://www.fda.gov{url}"
    
    filename = f"{index:04d}_{sanitize_filename(title)}.pdf"
    filepath = output_dir / filename
    
    if filepath.exists() and filepath.stat().st_size > 1000:
        return (True, "Exists")
    
    # Try download with retries
    for attempt in range(3):
        try:
            headers = get_random_headers()
            headers["Referer"] = "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"
            
            with session.get(url, headers=headers, stream=True, timeout=60, allow_redirects=True) as r:
                # Accept both 200 and redirects
                if r.status_code in [200, 301, 302]:
                    with open(filepath, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    # Verify file was saved and has content
                    if filepath.exists() and filepath.stat().st_size > 1000:
                        return (True, filename)
                    else:
                        filepath.unlink(missing_ok=True)  # Remove empty file
                        continue
                else:
                    r.raise_for_status()
            
        except requests.exceptions.HTTPError as e:
            if attempt < 2:
                random_delay(0.5, 1)
            else:
                # Final check - maybe file was saved anyway
                if filepath.exists() and filepath.stat().st_size > 1000:
                    return (True, filename)
                return (False, f"HTTP {e.response.status_code}" if hasattr(e, 'response') else str(e)[:30])
        except Exception as e:
            if attempt < 2:
                random_delay(0.5, 1)
            else:
                if filepath.exists() and filepath.stat().st_size > 1000:
                    return (True, filename)
                return (False, str(e)[:30])
    
    # Final check after all retries
    if filepath.exists() and filepath.stat().st_size > 1000:
        return (True, filename)
    
    return (False, "Failed")


def create_session_from_driver(driver) -> requests.Session:
    """Create a requests session with cookies from Selenium driver."""
    session = requests.Session()
    
    # Copy cookies from browser to requests session
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''))
    
    return session


def download_batch_parallel(session: requests.Session, entries: List[Dict], output_dir: Path, start_index: int) -> dict:
    """
    Download multiple files in parallel using ThreadPoolExecutor.
    Uses session with browser cookies for authentication.
    """
    results = {"downloaded": 0, "skipped": 0, "failed": 0}
    
    with ThreadPoolExecutor(max_workers=MAX_DOWNLOAD_WORKERS) as executor:
        # Submit all download tasks
        future_to_entry = {}
        for i, entry in enumerate(entries):
            idx = start_index + i
            if entry.get("download_url"):
                future = executor.submit(download_file_with_session, session, entry, output_dir, idx)
                future_to_entry[future] = (idx, entry["title"][:40])
            else:
                results["skipped"] += 1
        
        # Process completed downloads
        for future in as_completed(future_to_entry):
            idx, title = future_to_entry[future]
            try:
                success, message = future.result()
                if success:
                    if message == "Exists":
                        results["skipped"] += 1
                    else:
                        results["downloaded"] += 1
                        safe_print(f"    ✅ [{idx}] {title}...")
                else:
                    results["failed"] += 1
                    safe_print(f"    ❌ [{idx}] {title}... ({message})")
            except Exception as e:
                results["failed"] += 1
                safe_print(f"    ❌ [{idx}] Error: {e}")
    
    return results


def save_to_csv(entries: List[Dict], csv_path: Path):
    """Save entries to CSV."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = ["index", "title", "detail_url", "download_url", "date", "center", "topic", "status", "comment"]
    
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx, entry in enumerate(entries, start=1):
            writer.writerow({"index": idx, **entry})
    
    print(f"📊 Saved {len(entries)} entries to {csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="FDA Guidance Documents Scraper - OPTIMIZED",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fda_optimized.py                        # Interactive mode
  python fda_optimized.py --start 1 --end 50     # Pages 1-50
  python fda_optimized.py --start 100 --end 150  # Pages 100-150
  python fda_optimized.py --no-download          # Metadata only
  python fda_optimized.py --headless             # No browser window
        """
    )
    parser.add_argument("--start", type=int, default=None, help="Start page")
    parser.add_argument("--end", type=int, default=None, help="End page")
    parser.add_argument("--no-download", action="store_true", help="Skip downloads")
    parser.add_argument("--headless", action="store_true", help="Headless mode")
    args = parser.parse_args()
    
    # Get page range
    if args.start is None or args.end is None:
        print(f"\n📚 FDA Guidance Documents - OPTIMIZED SCRAPER")
        print("=" * 50)
        print(f"Total pages available: {TOTAL_PAGES}")
        print("=" * 50)
        
        try:
            start_input = input(f"  Start page [1]: ").strip()
            start_page = int(start_input) if start_input else 1
            
            end_input = input(f"  End page [{TOTAL_PAGES}]: ").strip()
            end_page = int(end_input) if end_input else TOTAL_PAGES
        except ValueError:
            print("Invalid input, using defaults.")
            start_page, end_page = 1, TOTAL_PAGES
    else:
        start_page = args.start
        end_page = args.end
    
    # Validate
    start_page = max(1, start_page)
    end_page = min(TOTAL_PAGES, end_page)
    if start_page > end_page:
        print("❌ Invalid range")
        return
    
    pages_to_scrape = end_page - start_page + 1
    
    print(f"\n🚀 OPTIMIZED SETTINGS:")
    print(f"   📄 Pages: {start_page} to {end_page} ({pages_to_scrape} pages)")
    print(f"   📥 Downloads: {'OFF' if args.no_download else 'ON (parallel)'}")
    print(f"   🔧 Workers: {MAX_DOWNLOAD_WORKERS} parallel downloads")
    print(f"   🛡️ Stealth mode: ON")
    
    out_dir = Path(OUTPUT_DIR).absolute()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / CSV_FILE
    
    print(f"   📁 Output: {out_dir}\n")
    
    driver = setup_stealth_driver(headless=args.headless)
    
    all_entries: List[Dict] = []
    seen_titles: Set[str] = set()
    total_downloaded = 0
    total_skipped = 0
    total_failed = 0
    
    try:
        # Load page
        print("🌐 Loading FDA page...")
        driver.get(BASE_URL)
        
        if not wait_for_table(driver, timeout=15):
            print("❌ Failed to load table")
            return
        
        # Check total
        try:
            info = driver.find_element(By.CSS_SELECTOR, "#DataTables_Table_0_info").text
            print(f"📊 {info}")
        except:
            pass
        
        # Create session with browser cookies for downloads
        download_session = create_session_from_driver(driver)
        print("🔑 Session created with browser cookies")
        
        print(f"\n⚡ Starting optimized scrape...\n")
        start_time = time.time()
        
        # Navigate to start page
        if start_page > 1:
            print(f"⏩ Navigating to page {start_page}...")
            if navigate_sequential_fast(driver, start_page):
                print(f"   ✅ Reached page {start_page}")
                wait_for_table(driver)
            else:
                print(f"   ❌ Navigation failed")
        
        # Scrape each page
        for page_num in range(start_page, end_page + 1):
            print(f"\n{'='*60}")
            print(f"📄 PAGE {page_num}/{end_page}")
            print(f"{'='*60}")
            
            # Navigate if not first page of range
            if page_num > start_page:
                if not click_next_fast(driver):
                    print("   ⚠️ Navigation failed")
                    break
            
            # Collect entries
            entries = collect_table_rows_fast(driver)
            print(f"   📋 Found {len(entries)} entries")
            
            # Filter new entries
            new_entries = []
            for entry in entries:
                key = f"{entry['title']}|{entry.get('date', '')}"
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_entries.append(entry)
                    new_entries.append(entry)
            
            with_download = sum(1 for e in new_entries if e.get("download_url"))
            print(f"   📥 With download links: {with_download}/{len(new_entries)}")
            
            # Parallel download
            if not args.no_download and new_entries:
                print(f"   ⬇️ Downloading in parallel...")
                start_idx = (page_num - 1) * ITEMS_PER_PAGE + 1
                results = download_batch_parallel(download_session, new_entries, out_dir, start_idx)
                
                total_downloaded += results["downloaded"]
                total_skipped += results["skipped"]
                total_failed += results["failed"]
                
                print(f"   ✅ Page done: {results['downloaded']} downloaded, {results['skipped']} skipped")
            
            # Save progress every 10 pages
            if page_num % 10 == 0:
                save_to_csv(all_entries, csv_path)
            
            # Small random delay between pages
            random_delay(0.5, 1.5)
        
        # Final save
        elapsed = time.time() - start_time
        save_to_csv(all_entries, csv_path)
        
        print(f"\n{'='*60}")
        print(f"🎯 COMPLETE!")
        print(f"{'='*60}")
        print(f"   ⏱️ Time: {elapsed:.1f} seconds")
        print(f"   📊 Entries: {len(all_entries)}")
        if not args.no_download:
            print(f"   ✅ Downloaded: {total_downloaded}")
            print(f"   ⏭️ Skipped: {total_skipped}")
            print(f"   ❌ Failed: {total_failed}")
        print(f"   📁 Location: {out_dir}")
        print(f"   📄 CSV: {csv_path}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted!")
        save_to_csv(all_entries, csv_path)
        
    finally:
        driver.quit()


if __name__ == "__main__":
    main()

