# 📰 FastAPI News Scraper (Kabupaten Sampang)
Aplikasi web FastAPI untuk *scraping* berita regional Kabupaten Sampang menggunakan Google News RSS dan `trafilatura`.

## clone project
git clone https://github.com/syamsinur/news-scraper.git
\ncd news-scraper

## create virtual environment using pip
python -m venv .venv
### Windows:
.venv\Scripts\activate
### Mac/Linux:
source .venv/bin/activate
### install dependencies
pip install -r requirements.txt 
### run
uvicorn src.news_scraper.main:app --reload

## create virtual environment using uv
uv sync
### run
uv run uvicorn news_scraper.main:app --reload