import time
import re
from pathlib import Path
from typing import List, Tuple, Set

import requests
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

# ---------- CONFIG ----------
BASE_URL = "https://www.who.int/publications/i?publishingoffices=c09761c0-ab8e-4cfa-9744-99509c4d306b"
OUTPUT_DIR = "WHO_Documents_AllPages_PDFs"

PAGE_LOAD_WAIT = 4
SCROLL_PAUSE = 1
DOWNLOAD_SLEEP = 0.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
# ----------------------------


def sanitize_filename(name: str, default: str = "file") -> str:
    name = name.strip() if name else default
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name[:150].strip() or default


def setup_driver(headless: bool = False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )
    return driver


def wait_for_page_load(driver):
    """Wait for page content to load."""
    time.sleep(PAGE_LOAD_WAIT)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
    time.sleep(SCROLL_PAUSE)
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(SCROLL_PAUSE)


def get_total_pages(driver) -> int:
    """Get total number of pages."""
    try:
        page_source = driver.page_source
        
        # Look for "Page X of Y" pattern
        match = re.search(r'Page\s+\d+\s+of\s+(\d+)', page_source, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Fallback: Calculate from "X-Y of Z items"
        match = re.search(r'(\d+)-(\d+)\s+of\s+(\d+)\s+items', page_source, re.IGNORECASE)
        if match:
            per_page = int(match.group(2)) - int(match.group(1)) + 1
            total_items = int(match.group(3))
            return (total_items + per_page - 1) // per_page
            
    except Exception as e:
        print(f"⚠️ Could not detect total pages: {e}")
    
    return 9


def get_first_card_identifier(driver) -> str:
    """Get a unique identifier for the first card to detect page changes."""
    try:
        cards = driver.find_elements(By.CSS_SELECTOR, ".sf-publications-item__container")
        if cards:
            # Get all links from first card to create a unique identifier
            links = cards[0].find_elements(By.TAG_NAME, "a")
            for link in links:
                href = link.get_attribute("href") or ""
                if "/publications/i/item/" in href:
                    return href
            # Fallback to title
            header = cards[0].find_element(By.CSS_SELECTOR, ".sf-publications-item__header")
            return header.text.strip()[:50]
    except:
        pass
    return ""


def click_next_page_kendo(driver) -> bool:
    """
    Click the 'Next' page button using Kendo UI selectors.
    Based on HTML: <a aria-label="Go to the next page" class="k-link k-pager-nav">
    """
    try:
        # Scroll to bottom where pagination is
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        # Get current first card to detect if page changes
        old_identifier = get_first_card_identifier(driver)
        
        # Find the "Next" button using Kendo UI selectors
        next_button = None
        
        # Method 1: Exact aria-label match (from screenshot)
        selectors = [
            "a[aria-label='Go to the next page']",
            "a[title='Go to the next page']",
            ".k-pager-nav[aria-label='Go to the next page']",
            "#ppager a[aria-label='Go to the next page']",
            ".k-pager-wrap a[aria-label='Go to the next page']",
        ]
        
        for selector in selectors:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    next_button = btn
                    print(f"    Found next button with selector: {selector}")
                    break
            except:
                continue
        
        # Method 2: XPath with aria-label
        if not next_button:
            xpaths = [
                "//a[@aria-label='Go to the next page']",
                "//a[contains(@aria-label, 'next page')]",
                "//a[contains(@title, 'next page')]",
            ]
            for xpath in xpaths:
                try:
                    btn = driver.find_element(By.XPATH, xpath)
                    if btn.is_displayed():
                        next_button = btn
                        print(f"    Found next button with xpath: {xpath}")
                        break
                except:
                    continue
        
        # Method 3: Look for k-i-arrow-60-right icon
        if not next_button:
            try:
                arrow_icon = driver.find_element(By.CSS_SELECTOR, ".k-i-arrow-60-right")
                next_button = arrow_icon.find_element(By.XPATH, "./..")  # Get parent <a>
                print("    Found next button via arrow icon")
            except:
                pass
        
        if not next_button:
            print("    ❌ Could not find next button")
            return False
        
        # Scroll button into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
        time.sleep(0.5)
        
        # Click the button
        try:
            next_button.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", next_button)
        
        print("    Clicked next button, waiting for page to load...")
        time.sleep(PAGE_LOAD_WAIT)
        
        # Verify page changed
        new_identifier = get_first_card_identifier(driver)
        if new_identifier != old_identifier:
            print("    ✅ Page content changed")
            return True
        else:
            print("    ⚠️ Page content might not have changed")
            return True  # Continue anyway, might be checking wrong
        
    except Exception as e:
        print(f"    ❌ Error clicking next: {e}")
        return False


def use_page_input_kendo(driver, target_page: int) -> bool:
    """
    Navigate using the Kendo UI page input field.
    Based on HTML: <span class="k-pager-input k-label">
    """
    try:
        # Scroll to pagination
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        
        old_identifier = get_first_card_identifier(driver)
        
        # Find the input field inside .k-pager-input
        input_field = None
        
        selectors = [
            ".k-pager-input input",
            "#ppager input",
            ".k-pager-wrap input",
            "input.k-textbox",
            ".k-pager-input input[type='text']",
            ".k-pager-input input[type='number']",
        ]
        
        for selector in selectors:
            try:
                inp = driver.find_element(By.CSS_SELECTOR, selector)
                if inp.is_displayed():
                    input_field = inp
                    print(f"    Found page input with selector: {selector}")
                    break
            except:
                continue
        
        if not input_field:
            print("    ❌ Could not find page input field")
            return False
        
        # Scroll into view
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", input_field)
        time.sleep(0.3)
        
        # Clear and type new page number
        input_field.click()
        time.sleep(0.2)
        
        # Select all and replace
        input_field.send_keys(Keys.CONTROL + "a")
        time.sleep(0.1)
        input_field.send_keys(str(target_page))
        time.sleep(0.2)
        input_field.send_keys(Keys.ENTER)
        
        print(f"    Entered page {target_page}, waiting for load...")
        time.sleep(PAGE_LOAD_WAIT)
        
        # Verify page changed
        new_identifier = get_first_card_identifier(driver)
        if new_identifier != old_identifier:
            print("    ✅ Page content changed")
            return True
        else:
            print("    ⚠️ Content might not have changed")
            return True
        
    except Exception as e:
        print(f"    ❌ Error using page input: {e}")
        return False


def collect_publication_cards(driver) -> List[Tuple[str, str]]:
    """Collect all publication cards from the current page."""
    publications: List[Tuple[str, str]] = []

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".sf-publications-item__container"))
        )
    except TimeoutException:
        print("    [WARN] Timeout waiting for cards")
        return []

    cards = driver.find_elements(By.CSS_SELECTOR, ".sf-publications-item__container")

    for idx, card in enumerate(cards, start=1):
        title = None
        detail_url = None

        # Get title
        try:
            header = card.find_element(By.CSS_SELECTOR, ".sf-publications-item__header")
            title = header.text.strip()
        except:
            pass

        # Get detail URL - try multiple methods
        try:
            link = card.find_element(By.XPATH, ".//a[contains(text(), 'Read') or contains(text(), 'More')]")
            detail_url = link.get_attribute("href")
        except:
            pass
        
        if not detail_url:
            try:
                links = card.find_elements(By.TAG_NAME, "a")
                for link in links:
                    href = link.get_attribute("href") or ""
                    if "/publications/i/item/" in href:
                        detail_url = href
                        break
            except:
                pass

        if detail_url and "/publications/i/item/" in detail_url:
            if not title:
                title = f"who_publication_{idx}"
            publications.append((title, detail_url))

    return publications


def extract_pdf_from_detail(detail_url: str) -> str | None:
    """Extract the PDF download link from a detail page."""
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"    [ERR] Failed to load detail: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1) <a class="download-url"> with iris.who.int
    for a in soup.find_all("a", class_="download-url"):
        href = a.get("href")
        if href and "iris.who.int" in href:
            return href

    # 2) Any 'Download' link with iris.who.int
    for a in soup.find_all("a"):
        text = (a.get_text() or "").strip()
        href = a.get("href")
        if "Download" in text and href and "iris.who.int" in href:
            return href

    # 3) Any iris.who.int link with /content
    for a in soup.find_all("a"):
        href = a.get("href")
        if href and "iris.who.int" in href and "/content" in href:
            return href

    return None


def download_file(title: str, url: str, output_dir: Path, index: int) -> bool:
    output_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"{index:03d}_{sanitize_filename(title)}.pdf"
    filepath = output_dir / filename

    if filepath.exists():
        print(f"    Already exists")
        return True

    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=120) as r:
            r.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        print(f"    ✅ Saved: {filename}")
        return True
    except Exception as e:
        print(f"    ❌ Failed: {e}")
        return False


def main():
    out_dir = Path(OUTPUT_DIR)
    driver = setup_driver(headless=False)

    all_pub_entries: List[Tuple[str, str]] = []
    seen_detail_urls: Set[str] = set()

    try:
        # 1️⃣ Load first page
        print("🌐 Loading first page...")
        driver.get(BASE_URL)
        wait_for_page_load(driver)
        
        total_pages = get_total_pages(driver)
        print(f"📚 Total pages detected: {total_pages}")
        print(f"📄 Will scrape all {total_pages} pages\n")

        # 2️⃣ Scrape each page
        for page_num in range(1, total_pages + 1):
            print(f"\n{'='*60}")
            print(f"📄 PAGE {page_num}/{total_pages}")
            print(f"{'='*60}")
            
            # Navigate to page (except for page 1)
            if page_num > 1:
                print(f"  ➡️ Navigating to page {page_num}...")
                
                # Try clicking next button (more reliable for sequential navigation)
                if not click_next_page_kendo(driver):
                    # Fallback: try page input
                    if not use_page_input_kendo(driver, page_num):
                        print(f"  ⚠️ Could not navigate to page {page_num}, stopping")
                        break
                
                # Additional wait for content to fully load
                wait_for_page_load(driver)
            
            # Collect publications
            pubs = collect_publication_cards(driver)
            print(f"  📋 Found {len(pubs)} publications on this page")
            
            new_count = 0
            for title, detail_url in pubs:
                if detail_url not in seen_detail_urls:
                    seen_detail_urls.add(detail_url)
                    all_pub_entries.append((title, detail_url))
                    new_count += 1
            
            print(f"  ✅ Added {new_count} NEW (total: {len(all_pub_entries)})")
            
            if page_num > 1 and new_count == 0:
                print(f"  ⚠️ WARNING: 0 new publications - pagination might have failed!")

        print(f"\n{'='*60}")
        print(f"✅ COLLECTION COMPLETE: {len(all_pub_entries)} unique publications")
        print(f"{'='*60}\n")

        # 3️⃣ Download PDFs
        success_count = 0
        fail_count = 0
        
        for idx, (title, detail_url) in enumerate(all_pub_entries, start=1):
            short_title = title.replace('\n', ' ')[:55]
            print(f"\n[{idx}/{len(all_pub_entries)}] {short_title}...")

            pdf_url = extract_pdf_from_detail(detail_url)
            if not pdf_url:
                print(f"    [WARN] No PDF found")
                fail_count += 1
                continue

            if download_file(title, pdf_url, out_dir, idx):
                success_count += 1
            else:
                fail_count += 1
                
            time.sleep(DOWNLOAD_SLEEP)

        print(f"\n{'='*60}")
        print(f"🎯 ALL DONE!")
        print(f"   ✅ Downloaded: {success_count}")
        print(f"   ❌ Failed: {fail_count}")
        print(f"   📁 Location: {out_dir.absolute()}")
        print(f"{'='*60}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted! Saving links...")
        with open("collected_links.txt", "w", encoding="utf-8") as f:
            for title, url in all_pub_entries:
                f.write(f"{title}\t{url}\n")
        print(f"   Saved {len(all_pub_entries)} links")
        
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
