from gnews import GNews
from curl_cffi import requests
import trafilatura
from googlenewsdecoder import gnewsdecoder
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
# from datetime import datetime
from typing import List
import asyncio
import time
import calendar
import urllib.parse

def match_date(pub_date_str: str, target_month: str, target_year: str) -> bool:
    if not pub_date_str:
        return True 
    try:
        dt = parsedate_to_datetime(pub_date_str)
        print(f"[DEBUG DATE] Artikel tanggal: {dt.strftime('%Y-%m-%d')} (Bulan: {dt.month}, Tahun: {dt.year}) | Target Filter -> Bulan: {target_month}, Tahun: {target_year}")

        if target_month != "all" and dt.month != int(target_month):
            return False
        if dt.year != int(target_year):
            return False
        return True
    except Exception as e:
        print(f"[DEBUG DATE ERROR] Gagal parse format tanggal '{pub_date_str}': {e}")
        return True

async def scrape_news(keywords: List[str], max_results: int = 10, month: str = "all", year: str = "2026") -> list[dict]:
    results = []
    # Jika max_results <= 0 (opsi Ambil Semua), set angka besar agar GNews mengambil sebanyak mungkin
    fetch_limit = max_results if max_results > 0 else 10000
    
    gn = GNews(language='id', country='ID', max_results=fetch_limit)
    loop = asyncio.get_running_loop()

    SYSTEM_KABUPATEN = "Kabupaten Sampang"

    custom_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.google.com/",
        "Upgrade-Insecure-Requests": "1"
    }

    semaphore = asyncio.Semaphore(5)

    async def process_article(art: dict, kw_clean: str) -> dict | None:
        pub_date = art.get('published date')

        if not match_date(pub_date, month, year):
            print(f"[DEBUG FILTER] Artikel dilewati karena tidak cocok dengan filter waktu.")
            return None
        
        async with semaphore:
            title = art.get('title', 'Tanpa Judul')
            gnews_url = art.get('url', '#')
            publisher = art.get('publisher', {}).get('title', 'Media Nasional')
            fallback_desc = art.get(
                'description',
                f"Informasi berita mengenai {kw_clean} di wilayah {SYSTEM_KABUPATEN} dari {publisher}."
            )

            full_article_text = ""
            real_url = gnews_url

            if gnews_url and gnews_url != '#':
                try:
                    def get_real_url(url_to_decode: str) -> str:
                        if "news.google.com" in url_to_decode:
                            time.sleep(0.3)
                            clean_gnews_url = url_to_decode.split("?")[0]
                            try:
                                decoded = gnewsdecoder(clean_gnews_url, interval=1)
                                if isinstance(decoded, dict):
                                    target = decoded.get("decoded_url") or decoded.get("unshortened_url")
                                    if target:
                                        return target
                                elif isinstance(decoded, str) and decoded.startswith("http"):
                                    return decoded
                            except Exception as dec_err:
                                print(f"[DEBUG DECODE EXCEPTION] {dec_err}")
                        return url_to_decode

                    real_url = await loop.run_in_executor(None, get_real_url, gnews_url)
                    print(f"[DEBUG URL] {publisher} -> {real_url}")

                    if "news.google.com" not in real_url:
                        fetch_url = real_url
                        if any(domain in real_url for domain in ["tribunnews.com", "kompas.com", "sindonews.com", "grid.id"]):
                            separator = "&" if "?" in real_url else "?"
                            fetch_url = f"{real_url}{separator}page=all"

                        def fetch_deep_page(target_url: str):
                            try:
                                res = requests.get(
                                    target_url,
                                    headers=custom_headers,
                                    impersonate="chrome",
                                    timeout=15,
                                    allow_redirects=True
                                )
                                if res.status_code == 200:
                                    return res.text
                            except Exception as err:
                                print(f"[DEBUG FETCH ERROR] {target_url}: {err}")
                            return None

                        html_content = await loop.run_in_executor(None, fetch_deep_page, fetch_url)

                        if html_content:
                            extracted_text = trafilatura.extract(
                                html_content,
                                include_comments=False,
                                include_tables=False,
                                include_formatting=False,
                                favor_recall=True
                            )
                            if not extracted_text or len(extracted_text) <= 80:
                                soup = BeautifulSoup(html_content, "html.parser")
                                paragraphs = [
                                    p.get_text(strip=True)
                                    for p in soup.find_all("p")
                                    if len(p.get_text(strip=True)) > 45
                                ]
                                if paragraphs:
                                    extracted_text = "\n\n".join(paragraphs)

                            if extracted_text and len(extracted_text) > 80:
                                full_article_text = extracted_text

                except Exception as e:
                    print(f"[DEBUG ERROR] {real_url}: {e}")

            final_description = (
                full_article_text
                if full_article_text
                else f"[Mode Ringkasan] {fallback_desc} (Situs sumber membatasi akses baca langsung)."
            )

            return {
                "keyword": f"{kw_clean} ({SYSTEM_KABUPATEN})",
                "title": title,
                "url": real_url,
                "snippet": final_description
            }

    for kw in keywords:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        
        search_query = f"{kw_clean} {SYSTEM_KABUPATEN}"
        
        # Tambahkan operator tanggal Google News secara dinamis
        if month != "all":
            last_day = calendar.monthrange(int(year), int(month))[1]
            search_query += f" after:{year}-{int(month):02d}-01 before:{year}-{int(month):02d}-{last_day}"
        else:
            search_query += f" after:{year}-01-01 before:{year}-12-31"

        encoded_query = urllib.parse.quote(search_query, safe=':-+')

        try:
            articles = await loop.run_in_executor(None, gn.get_news, encoded_query)            

            if articles:
                tasks = [process_article(art, kw_clean) for art in articles]
                batch_results = await asyncio.gather(*tasks)
                valid_results = [res for res in batch_results if res is not None]
                results.extend(valid_results)
        except Exception as e:
            print(f"Gagal mengambil data untuk keyword '{kw_clean}': {e}")
            
        await asyncio.sleep(0.5)

    return results