# src/news_scraper/main.py
import io
import json
import pandas as pd
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
from news_scraper.scraper import scrape_news

app = FastAPI(title="Web Scraper Berita")

BASE_DIR = Path(__file__).resolve().parent

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Buat daftar tahun secara dinamis (misal dari 2020 sampai tahun berjalan)
def get_dynamic_years():
    current_year = datetime.now().year
    # Rentang dari tahun saat ini sampai 5 tahun lalu
    return list(range(current_year, current_year - 6, -1))

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    current_year = str(datetime.now().year)
    return templates.TemplateResponse(
        request, 
        "index.html", 
        {
            "results": [], 
            "results_json": "[]",
            "keywords": "", 
            "max_results": 10,
            "selected_month": "all",
            "selected_year": current_year,
            "dynamic_years": get_dynamic_years(),
            "searched": False
        }
    )

@app.post("/scrape", response_class=HTMLResponse)
async def handle_scrape(
    request: Request, 
    keywords: str = Form(...),
    max_results: int = Form(10),
    month: str = Form("all"),
    year: str = Form(str(datetime.now().year))
):
    # Jika max_results bernilai 0 atau negatif, set ke angka sangat besar (dianggap ambil semua)
    safe_max_results = max_results if max_results > 0 else 10000

    raw_keywords = keywords.replace(",", "\n").split("\n")
    clean_keywords = [k.strip() for k in raw_keywords if k.strip()]
    
    news_results = await scrape_news(
        clean_keywords,
        max_results=safe_max_results,
        month=month,
        year=year
    )
    
    return templates.TemplateResponse(
        request, 
        "index.html", 
        {
            "results": news_results, 
            "results_json": json.dumps(news_results), # Simpan data JSON untuk dikirim ke form export
            "keywords": keywords,
            "max_results": safe_max_results,
            "selected_month": month,
            "selected_year": year,
            "dynamic_years": get_dynamic_years(),
            "searched": True
        }
    )

@app.post("/export")
async def export_data(data_json: str = Form(...), format: str = Form(...)):
    # Ubah kembali string JSON dari form menjadi list of dict
    records = json.loads(data_json)
    
    # Susun DataFrame dengan nama kolom yang rapi
    df = pd.DataFrame(records)
    if not df.empty:
        df = df[["keyword", "title", "snippet", "url"]]
        df.columns = ["Kata Kunci", "Judul", "Deskripsi", "Link Berita"]
    else:
        df = pd.DataFrame(columns=["Kata Kunci", "Judul", "Deskripsi", "Link Berita"])

    if format == "csv":
        stream = io.StringIO()
        df.to_csv(stream, index=False, encoding="utf-8-sig")
        response = StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv"
        )
        response.headers["Content-Disposition"] = "attachment; filename=hasil_scraping_berita_sampang.csv"
        return response

    elif format == "excel":
        stream = io.BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Berita")
        stream.seek(0)
        response = StreamingResponse(
            stream,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response.headers["Content-Disposition"] = "attachment; filename=hasil_scraping_berita.xlsx"
        return response