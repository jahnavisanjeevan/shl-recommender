"""
SHL Catalog Scraper
Scrapes Individual Test Solutions from https://www.shl.com/solutions/products/product-catalog/
Run this once to build catalog/shl_catalog.json before starting the API.
"""

import json
import time
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.shl.com"
CATALOG_URL = f"{BASE_URL}/solutions/products/product-catalog/"
OUTPUT_PATH = Path("catalog/shl_catalog.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Test type legend from SHL catalog
TEST_TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgment",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "M": "Motivation",
    "P": "Personality & Behavior",
    "S": "Situational Judgment",
}


def get_page(url: str, retries: int = 3) -> BeautifulSoup | None:
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as e:
            print(f"  Attempt {attempt+1} failed for {url}: {e}")
            time.sleep(2 ** attempt)
    return None


def parse_test_types(cell_text: str) -> list[str]:
    """Extract test type codes from a cell (e.g. 'A K' -> ['A','K'])."""
    return [ch for ch in cell_text.strip().split() if ch in TEST_TYPE_LABELS]


def scrape_catalog_page(url: str) -> list[dict]:
    """Scrape one page of the catalog table."""
    soup = get_page(url)
    if not soup:
        return []

    products = []
    # The catalog renders as a table with rows for each product
    table = soup.find("table")
    if not table:
        # Try alternative structure — div-based listing
        rows = soup.select("div.product-catalogue-training-calendar__row")
        for row in rows:
            name_el = row.select_one("a")
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            href = name_el.get("href", "")
            url_full = href if href.startswith("http") else BASE_URL + href

            # Grab test type dots/icons
            type_cells = row.select("span[class*='catalogue__circle']")
            test_types = []
            for span in type_cells:
                classes = " ".join(span.get("class", []))
                for code, _ in TEST_TYPE_LABELS.items():
                    if f"-{code.lower()}" in classes or f"_{code.lower()}" in classes:
                        test_types.append(code)

            products.append({
                "name": name,
                "url": url_full,
                "test_types": test_types,
                "test_type_labels": [TEST_TYPE_LABELS[t] for t in test_types],
                "description": "",
                "remote_testing": None,
                "adaptive_irt": None,
                "duration": "",
            })
        return products

    # Table-based layout
    rows = table.find_all("tr")[1:]  # skip header
    for row in rows:
        cols = row.find_all("td")
        if not cols:
            continue

        name_el = cols[0].find("a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        href = name_el.get("href", "")
        prod_url = href if href.startswith("http") else BASE_URL + href

        # Columns vary; try to extract test types from remaining cols
        test_types = []
        remote_testing = None
        adaptive_irt = None

        for idx, col in enumerate(cols[1:], start=1):
            txt = col.get_text(strip=True)
            # Check for checkmark symbols
            has_check = bool(col.find(class_=re.compile(r"check|tick|yes", re.I))) or txt in ("✓", "•", "Yes", "yes")
            if idx == 1 and has_check:
                remote_testing = True
            elif idx == 1:
                remote_testing = False
            elif idx == 2 and has_check:
                adaptive_irt = True
            elif idx == 2:
                adaptive_irt = False
            else:
                parsed = parse_test_types(txt)
                test_types.extend(parsed)

        products.append({
            "name": name,
            "url": prod_url,
            "test_types": list(set(test_types)),
            "test_type_labels": [TEST_TYPE_LABELS[t] for t in set(test_types)],
            "description": "",
            "remote_testing": remote_testing,
            "adaptive_irt": adaptive_irt,
            "duration": "",
        })

    return products


def get_product_detail(product: dict) -> dict:
    """Enrich a product with description from its detail page."""
    soup = get_page(product["url"])
    if not soup:
        return product

    # Try several selectors for description
    for sel in [
        "div.product-hero__description",
        "div.product-description",
        "section.product-overview p",
        "div[class*='description'] p",
        "main p",
    ]:
        el = soup.select_one(sel)
        if el:
            product["description"] = el.get_text(strip=True)[:600]
            break

    # Duration
    for sel in ["span[class*='duration']", "div[class*='duration']", "td[class*='duration']"]:
        el = soup.select_one(sel)
        if el:
            product["duration"] = el.get_text(strip=True)
            break

    return product


def get_all_catalog_pages() -> list[str]:
    """Find all paginated catalog URLs for Individual Test Solutions."""
    urls = []
    # Start page
    base = CATALOG_URL
    soup = get_page(base)
    if not soup:
        return [base]

    urls.append(base)

    # Look for pagination
    pagination = soup.select("a[class*='pagination'], a[class*='next'], li.next a")
    seen = {base}

    # Also check for page param links
    page_links = soup.select("a[href*='product-catalog']")
    for link in page_links:
        href = link.get("href", "")
        full = href if href.startswith("http") else BASE_URL + href
        if full not in seen and "product-catalog" in full:
            seen.add(full)
            urls.append(full)

    # Try standard pagination patterns
    for page_num in range(2, 20):
        candidate_urls = [
            f"{CATALOG_URL}?start={(page_num-1)*12}",
            f"{CATALOG_URL}?page={page_num}",
            f"{CATALOG_URL}page/{page_num}/",
        ]
        for cu in candidate_urls:
            if cu not in seen:
                seen.add(cu)
                test_soup = get_page(cu)
                if test_soup:
                    # Check if page has products
                    has_products = (
                        test_soup.find("table") or
                        test_soup.select("div.product-catalogue-training-calendar__row") or
                        test_soup.select("a[href*='/en/']")
                    )
                    if has_products:
                        urls.append(cu)
                        break

    return urls


def main():
    OUTPUT_PATH.parent.mkdir(exist_ok=True)

    print("=== SHL Catalog Scraper ===")
    print(f"Target: {CATALOG_URL}")
    print()

    # Get all paginated pages
    print("Finding catalog pages...")
    pages = get_all_catalog_pages()
    print(f"Found {len(pages)} page(s).")

    all_products = []
    seen_urls = set()

    for page_url in pages:
        print(f"\nScraping: {page_url}")
        products = scrape_catalog_page(page_url)
        print(f"  Found {len(products)} products")
        for p in products:
            if p["url"] not in seen_urls:
                seen_urls.add(p["url"])
                all_products.append(p)

    print(f"\nTotal unique products: {len(all_products)}")

    # Optionally enrich with detail pages (slow but thorough)
    if "--no-detail" not in sys.argv:
        print("\nFetching product detail pages (for descriptions)...")
        for i, p in enumerate(all_products):
            print(f"  [{i+1}/{len(all_products)}] {p['name'][:50]}")
            all_products[i] = get_product_detail(p)
            time.sleep(0.5)  # Be polite

    # Save
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(all_products)} products to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
