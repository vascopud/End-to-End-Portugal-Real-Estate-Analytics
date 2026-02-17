import os
import pandas as pd
import numpy as np
import psycopg2
import joblib
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer
import category_encoders as ce
from xgboost import XGBRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import GridSearchCV

def train_and_export():
    load_dotenv(".env")
    
    # DB Connection
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    
    print("Loading data")
    query = "SELECT price, distrito, concelho, freguesia, area_m2, room_count FROM properties"
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Cleaning
    df = df[(df['price'] > 0) & (df['area_m2'] > 0)]
    
    def remove_outliers(df, column):
        Q1 = df[column].quantile(0.25)
        Q3 = df[column].quantile(0.75)
        IQR = Q3 - Q1
        return df[(df[column] >= Q1 - 1.5*IQR) & (df[column] <= Q3 + 1.5*IQR)]
    
    df_clean = remove_outliers(df, 'price')
    df_clean = remove_outliers(df_clean, 'area_m2')
    
    # Export location metadata for UI
    # We need a dictionary of Distrito -> Concelho -> Freguesia
    locations = {}
    for distrito in df_clean['distrito'].unique():
        dist_df = df_clean[df_clean['distrito'] == distrito]
        locations[distrito] = {}
        for concelho in dist_df['concelho'].unique():
            conc_df = dist_df[dist_df['concelho'] == concelho]
            locations[distrito][concelho] = sorted(conc_df['freguesia'].unique().tolist())
            
    os.makedirs("models", exist_ok=True)
    joblib.dump(locations, "models/location_metadata.joblib")
    print("Exported location metadata.")

    X = df_clean.drop('price', axis=1)
    y = df_clean['price']
    
    # Split for final verification to show a "real" R2 score to the user
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.15, random_state=42)
    
    numeric_features = ['area_m2', 'room_count']
    target_encoded_features = ['freguesia', 'concelho']
    onehot_features = ['distrito']
    
    numeric_transformer = Pipeline(steps=[
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, numeric_features),
            ('target', ce.TargetEncoder(), target_encoded_features),
            ('onehot', OneHotEncoder(handle_unknown='ignore'), onehot_features)
        ]
    )
    
    # Using XGBoost with an exhaustive Grid Search
    xgb_model = XGBRegressor(random_state=42, objective='reg:squarederror')
    
    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('regressor', xgb_model)
    ])
    
    # Define a comprehensive grid
    param_grid = {
        'regressor__n_estimators': [100, 500],
        'regressor__max_depth': [6, 8, 10],
        'regressor__learning_rate': [0.05, 0.1],
        'regressor__subsample': [0.8, 0.9],
        'regressor__colsample_bytree': [0.8, 0.9]
    }
    
    print("Starting Grid Search on training set (85% of data)")
    from sklearn.model_selection import GridSearchCV, KFold
    
    # Use Shuffled KFold for better stability with sparse categories
    cv_strategy = KFold(n_splits=3, shuffle=True, random_state=42)
    
    grid_search = GridSearchCV(
        pipeline, 
        param_grid, 
        cv=cv_strategy, 
        scoring='r2', 
        n_jobs=-1, 
        verbose=1
    )
    
    grid_search.fit(X_train, y_train)
    
    print(f"Best parameters: {grid_search.best_params_}")
    
    # Final verification on holdout
    best_model = grid_search.best_estimator_
    y_test_pred = best_model.predict(X_test)
    test_r2 = r2_score(y_test, y_test_pred)
    
    print(f"\n--- Model Performance Results ---")
    print(f"Cross-Validation Mean R2: {grid_search.best_score_:.4f}")
    print(f"Final Holdout Test R2:    {test_r2:.4f}")
    
    # Refit on ALL data for the deployment model
    print("\nRefitting best model on 100% of data")
    best_pipe = grid_search.best_estimator_
    best_pipe.fit(X, y)
    
    # Export best model
    joblib.dump(best_pipe, "models/price_model.joblib")
    print("Final model exported successfully to models/price_model.joblib")

if __name__ == "__main__":
    train_and_export()
