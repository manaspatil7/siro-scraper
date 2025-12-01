import os
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import time
import re

URL = "https://www.who.int/publications/i?publishingoffices=c09761c0-ab8e-4cfa-9744-99509c4d306b"
OUTPUT_FOLDER = "WHO_Documents"

headers = {
    "User-Agent": "Mozilla/5.0"
}

def clean_filename(text):
    text = re.sub(r'[<>:"/\\|?*]', '', text)
    return text.strip()[:150]

def main():
    Path(OUTPUT_FOLDER).mkdir(exist_ok=True)

    page = requests.get(URL, headers=headers).text
    soup = BeautifulSoup(page, "html.parser")

    links = []

    for a in soup.find_all("a", string=lambda s: s and "Download" in s):
        href = a.get("href")
        if href and "iris.who.int" in href:
            full = href if href.startswith("http") else "https:" + href
            parent = a.find_previous("a")
            title = clean_filename(parent.text if parent else "WHO_Document")
            links.append((title, full))

    print(f"✅ Total documents found: {len(links)}\n")

    for i, (title, link) in enumerate(links, 1):
        filename = f"{OUTPUT_FOLDER}/{title}.pdf"
        if os.path.exists(filename):
            continue

        print(f"[{i}] Downloading: {title}")

        r = requests.get(link, stream=True)
        with open(filename, "wb") as f:
            for chunk in r.iter_content(10240):
                f.write(chunk)

        time.sleep(1)

    print("\n🎯 Download Complete")

if __name__ == "__main__":
    main()
