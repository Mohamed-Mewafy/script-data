name: Run Media Scraper

on:
  schedule:
    - cron: '0 */6 * * *' # تشغيل تلقائي كل 6 ساعات (مثلاً)
  workflow_dispatch:      # لتمكين التشغيل اليدوي

jobs:
  scrape-job:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      # ---> أضف هذه الخطوة لتثبيت المكتبات المطلوبة <---
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests beautifulsoup4 supabase

      - name: Run Scraper Script
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
        run: |
          python -u series.py
          
