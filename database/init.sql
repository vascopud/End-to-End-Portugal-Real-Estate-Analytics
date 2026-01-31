-- Create table for storing real estate properties
-- Use TEXT for flexibility, but appropriate types for sorting/filtering (INTEGER, FLOAT)

CREATE TABLE IF NOT EXISTS properties (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    price INTEGER, -- Stored as integer (e.g., 350000)
    raw_location TEXT, -- Original location string
    distrito TEXT,
    concelho TEXT,
    freguesia TEXT,
    area_m2 FLOAT, -- Area in square meters
    room_count INTEGER, -- Number of rooms (T0=0, T1=1, etc.)
    url TEXT UNIQUE, -- To prevent duplicate entries
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Index on price and area for fast filtering
CREATE INDEX idx_properties_price ON properties(price);
CREATE INDEX idx_properties_area ON properties(area_m2);
CREATE INDEX idx_properties_distrito ON properties(distrito);
CREATE INDEX idx_properties_concelho ON properties(concelho);
CREATE INDEX idx_properties_freguesia ON properties(freguesia);

-- View for location statistics
CREATE OR REPLACE VIEW location_stats AS
SELECT 
    distrito, 
    concelho,
    freguesia,
    COUNT(*) as total_listings,
    ROUND(AVG(price)) as average_price,
    ROUND(AVG(price::float / NULLIF(area_m2, 0))::numeric, 2) as average_price_m2
FROM properties
GROUP BY distrito, concelho, freguesia;
