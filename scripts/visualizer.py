import streamlit as st
import pandas as pd
import joblib
import os
import psycopg2
from dotenv import load_dotenv
import plotly.express as px

# Set page config
st.set_page_config(
    page_title="Portugal Real Estate Analytics",
    page_icon="🏠",
    layout="wide"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
        font-family: 'Inter', sans-serif;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
        height: 3em;
        background-color: #007bff;
        color: white;
        font-weight: bold;
    }
    .price-box {
        padding: 20px;
        border-radius: 10px;
        background-color: #ffffff;
        border: 2px solid #007bff;
        text-align: center;
        margin-top: 20px;
    }
    .price-text {
        color: #007bff;
        font-size: 32px;
        font-weight: bold;
    }
    .metric-card {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
        border-left: 5px solid #007bff;
    }
    </style>
    """, unsafe_allow_html=True)

# Load Utilities
@st.cache_resource
def load_ml_assets():
    model = joblib.load("models/price_model.joblib")
    locations = joblib.load("models/location_metadata.joblib")
    return model, locations

@st.cache_data
def load_raw_data():
    load_dotenv(".env")
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    query = "SELECT price, distrito, concelho, freguesia, area_m2, room_count FROM properties"
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Basic cleaning for exploration
    df = df[(df['price'] > 0) & (df['area_m2'] > 0)]
    df['price_per_m2'] = df['price'] / df['area_m2']
    return df

# Main Title
st.title("Portugal Real Estate Hub")

# Create Tabs
tab_predict, tab_insights = st.tabs(["Price Prediction", "Data Insights"])

# Tab 1: Prediction
with tab_predict:
    st.header("Predict Hypothetical House Price")
    
    try:
        model, locations = load_ml_assets()
        
        col1, col2 = st.columns(2)
        with col1:
            distritos = sorted(list(locations.keys()))
            distrito_p = st.selectbox("Distrito", distritos, key="dist_p")
            concelhos = sorted(list(locations[distrito_p].keys()))
            concelho_p = st.selectbox("Concelho", concelhos, key="conc_p")
            freguesias = locations[distrito_p][concelho_p]
            freguesia_p = st.selectbox("Freguesia", freguesias, key="freg_p")

        with col2:
            area_m2 = st.number_input("Area (m²)", min_value=1, max_value=5000, value=100, step=1)
            room_count = st.number_input("Typology (e.g., T2 = 2)", min_value=0, max_value=20, value=2, step=1)

        if st.button("Predict Price", key="btn_p"):
            input_df = pd.DataFrame([{
                'distrito': distrito_p,
                'concelho': concelho_p,
                'freguesia': freguesia_p,
                'area_m2': area_m2,
                'room_count': room_count
            }])
            prediction = model.predict(input_df)[0]
            final_price = max(0, prediction)
            
            st.markdown(f"""
                <div class="price-box">
                    <p style="margin-bottom: 5px; color: #555;">Estimated Market Value</p>
                    <p class="price-text">€ {final_price:,.2f}</p>
                </div>
            """, unsafe_allow_html=True)
            st.info("This is an estimate based on recent listings. External factors like finishing quality, view, and specific street location can vary the price.")

    except Exception as e:
        st.error(f"Error loading assets: {e}")

# Tab 2: Insights
with tab_insights:
    st.header("Market Exploration & Averages")
    
    df = load_raw_data()
    
    # Sidebar-like filters within the tab
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        dist_filter = st.multiselect("Filter by Distrito", options=sorted(df['distrito'].unique()), default=[])
    
    filtered_df = df.copy()
    if dist_filter:
        filtered_df = filtered_df[filtered_df['distrito'].isin(dist_filter)]
        
    with col_f2:
        conc_options = sorted(filtered_df['concelho'].unique())
        conc_filter = st.multiselect("Filter by Concelho", options=conc_options, default=[])

    if conc_filter:
        filtered_df = filtered_df[filtered_df['concelho'].isin(conc_filter)]

    # Metrics Row
    m1, m2, m3, m4 = st.columns(4)
    avg_price = filtered_df['price'].mean()
    avg_area = filtered_df['area_m2'].mean()
    avg_sqm = filtered_df['price_per_m2'].mean()
    total_listings = len(filtered_df)

    m1.metric("Avg Price", f"€{avg_price:,.0f}" if not pd.isna(avg_price) else "N/A")
    m2.metric("Avg Area", f"{avg_area:.1f} m²" if not pd.isna(avg_area) else "N/A")
    m3.metric("Avg Price / m²", f"€{avg_sqm:,.0f}" if not pd.isna(avg_sqm) else "N/A")
    m4.metric("Listings Found", f"{total_listings:,}")

    # Visualizations
    st.markdown("---")
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("Geographic Price Comparison")
        
        metric_to_plot = 'price_per_m2'
        
        if not filtered_df.empty:
            # Aggregate based on Concelho (excluding outlier Ourem/Ourém)
            mask = ~filtered_df['concelho'].str.contains('Ourem|Ourém', case=False, na=False)
            geo_avg = filtered_df[mask].groupby('concelho')[metric_to_plot].mean().sort_values(ascending=False).head(20).reset_index()
            
            fig = px.bar(geo_avg, x=metric_to_plot, y='concelho', orientation='h', 
                         title="Top 20 Concelhos by Avg Price / m²",
                         labels={metric_to_plot: 'Avg Price / m² (€)', 'concelho': 'Concelho'},
                         color=metric_to_plot, color_continuous_scale='Viridis')
            
            # Force all Y-axis labels to show
            fig.update_yaxes(dtick=1)
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No data matches the selected filters.")

    with c2:
        st.subheader("Typology Mix")
        if not filtered_df.empty:
            # Clean room_count for pie chart
            def group_typology(val):
                if pd.isna(val): return "Unknown"
                try:
                    num = int(val)
                    if num > 4: return "Other"
                    return f"T{num}"
                except:
                    return "Unknown"
            
            filtered_df['typology'] = filtered_df['room_count'].apply(group_typology)
            
            # Count and prepare for pie chart
            typology_counts = filtered_df['typology'].value_counts().reset_index()
            typology_counts.columns = ['typology', 'count']
            
            # Define specific order: T0, T1, T2, T3, T4, Other, Unknown
            custom_order = ["T0", "T1", "T2", "T3", "T4", "Other", "Unknown"]
            
            fig_pie = px.pie(typology_counts, values='count', names='typology', 
                             title="Typology Distribution",
                             hole=0.4,
                             category_orders={"typology": custom_order})
            st.plotly_chart(fig_pie, use_container_width=True)

    # Raw Data Table
    st.subheader("Raw Listings Data")
    st.dataframe(filtered_df.sort_values('price', ascending=False).head(100), use_container_width=True)

# Sidebar info
st.sidebar.header("About")
st.sidebar.info("This tool provides real estate analytics and price predictions for the Portuguese market.")
st.sidebar.markdown("---")
st.sidebar.write(f"**Total Properties in DB:** {len(df):,}")
st.sidebar.write("Powered by Scraped Imovirtual Data.")
