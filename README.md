# Real-Estate Watchdog 🇵🇹

A Python-based tool to scrape, store, and analyze real estate listings from Imovirtual (Portugal).

## Project Structure

```
real-estate-watchdog/
├── data/               # Local CSV backups
├── database/
│   ├── init.sql        # PostgreSQL table schema
├── scraper/
│   ├── main.py         # The BeautifulSoup script
│   └── requirements.txt
├── model/              # (Future) ML models
├── api/                # (Future) FastAPI backend
└── README.md
```

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r scraper/requirements.txt
    ```

2.  **Run Scraper**:
    ```bash
    python scraper/main.py
    ```

3.  **Database**:
    - The project uses a PostgreSQL database running in Docker.
    - Use `docker-compose up -d` to start the database.
    - Schema is defined in `database/init.sql`.

## Features
- **Advanced Scraper**: Extracts Title, Price, Location, Area, and Rooms (T-typology) from Imovirtual.
- **Robust Pagination**: Handles thousands of pages with `limit=72`, automatic retry, and cooldowns.
- **Hierarchy Extraction**: Automatically parses Distrito, Concelho, and Freguesia from URLs.
- **Database Integration**: Direct upsert into PostgreSQL with duplicate prevention.
- **Resumable Progress**: Saves state after every page; can be stopped and resumed at any time.

## Next Steps
- Build the ML model for price prediction.
- Create a data visualization dashboard.
- Implement automated daily scraping tasks.
