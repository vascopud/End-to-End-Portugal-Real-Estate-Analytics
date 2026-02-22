# Portugal Real Estate Analytics Hub

An end-to-end data platform to scrape, analyze, and predict real estate prices in the Portuguese market. This project transitions from raw web scraping to sophisticated machine learning and an interactive visualization dashboard.

## Key Features

- **Hierarchical Scraper**: Robustly extracts data from Imovirtual using a geographic hierarchy (Distrito -> Concelho -> Freguesia).
- **Advanced EDA**: Automated cleaning and outlier detection using the Interquartile Range (IQR) method.
- **Machine Learning**: 
    - Predictive model for property prices using **XGBoost**.
    - Exhaustive **GridSearchCV** optimization (972 fits) resulting in a **0.71 R² score**.
    - Target encoding for handling high-cardinality geographic data.
- **Interactive Dashboard**: 
    - **Price Predictor**: Estimate hypothetical house prices based on location and specs.
    - **Market Insights**: Comparative analysis of "Price per m²" across municipalities.
    - **Typology Mix**: Distribution of housing stock from T0 to T4+.

## Project Structure

```
real-estate-watchdog/
├── database/
│   └── init.sql # PostgreSQL schema (Distrito, Concelho, Freguesia)
├── scraper/
│   └── main.py # Hierarchical BeautifulSoup scraper
├── notebooks/
│   ├── eda_analysis.ipynb
│   └── price_prediction_modeling.ipynb
├── scripts/
│   ├── train_final_model.py # Exhaustive GridSearchCV training script
│   └── visualizer.py # Streamlit Dashboard (Prediction + Analytics)
├── models/
│   ├── price_model.joblib # Trained XGBoost Pipeline
│   └── location_metadata.joblib # UI Location Hierarchy
├── docker-compose.yml # PostgreSQL container setup
└── .env # Database credentials
```

## Setup & Usage

### Database Setup
```bash
docker-compose up -d
```
The database will be initialized using `database/init.sql`.

### Scraping Data
```bash
pip install -r scraper/requirements.txt
python scraper/main.py
```

### Model Training
If you wish to retrain the model with fresh data:
```bash
python scripts/train_final_model.py
```

### Launch visualizer
```bash
streamlit run scripts/visualizer.py
```

## Technologies Used
- **Backend**: Python, BeautifulSoup4, PostgreSQL, Docker.
- **Data Science**: Pandas, NumPy, Scikit-Learn, XGBoost, Category Encoders.
- **Frontend**: Streamlit, Plotly Express.