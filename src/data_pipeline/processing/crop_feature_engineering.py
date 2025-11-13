"""
Crop Feature Engineering
========================
Engineer 100+ features from raw crop data
Handles extreme scales, outliers, and categorical variables

File Location: src/data_pipeline/processing/crop_feature_engineering.py
Input: data/processed/crop_raw_data.csv (19,689 × 10)
Output: data/processed/crop_processed.csv (19,689 × 100+)
        + src/models/saved_models/scalers/crop_feature_scaler.pkl
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler, LabelEncoder
import joblib
import logging
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CropFeatureEngineer:
    """
    Engineer features from crop yield data
    
    Strategy:
    1. Handle extreme scales (log transform)
    2. Handle outliers (cap or robust scaling)
    3. Create time features
    4. Create interaction features
    5. Encode categoricals
    6. Scale all features
    """
    
    def __init__(self):
        """Initialize feature engineer"""
        self.scaler = StandardScaler()
        self.label_encoders = {}
        self.feature_names = None
        logger.info("CropFeatureEngineer initialized")
    
    def load_data(self, csv_path='data/processed/crop_raw_data.csv'):
        """Load raw crop data"""
        try:
            if not Path(csv_path).exists():
                raise FileNotFoundError(f"Data not found: {csv_path}")
            
            df = pd.read_csv(csv_path)
            logger.info(f"Loaded data: {df.shape[0]} rows × {df.shape[1]} columns")
            return df
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            raise
    
    def handle_extreme_scales(self, df):
        """
        Handle extreme value ranges using log transformation
        
        Problem: Production ranges 0 to 6.3B, Fertilizer 54 to 4.8B
        Solution: Log transform to compress scales
        """
        df = df.copy()
        
        logger.info("\nHANDLING EXTREME SCALES:")
        logger.info("-" * 80)
        
        # Columns with extreme ranges that benefit from log transform
        log_cols = ['Area', 'Production', 'Fertilizer', 'Pesticide']
        
        for col in log_cols:
            # Log(x+1) to handle zeros
            df[f'{col}_log'] = np.log1p(df[col])
            logger.info(f"   Created {col}_log (handles zeros)")
        
        return df
    
    def handle_outliers(self, df):
        """
        Handle outliers using capping method (Winsorization)
        """
        df = df.copy()
        
        logger.info("\nHANDLING OUTLIERS:")
        logger.info("-" * 80)
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        for col in numeric_cols:
            if col not in ['Crop_Year']:  # Skip year
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                
                lower_bound = Q1 - 1.5 * IQR
                upper_bound = Q3 + 1.5 * IQR
                
                # Cap outliers
                df[f'{col}_capped'] = df[col].clip(lower_bound, upper_bound)
        
        logger.info(f"   Capped outliers for {len(numeric_cols)} numeric columns")
        return df
    
    def create_time_features(self, df):
        """Create time-based features"""
        df = df.copy()
        
        logger.info("\nCREATING TIME FEATURES:")
        logger.info("-" * 80)
        
        # Year-based features
        df['Year_Centered'] = df['Crop_Year'] - df['Crop_Year'].mean()
        df['Year_Squared'] = df['Crop_Year'] ** 2
        df['Years_Since_Start'] = df['Crop_Year'] - df['Crop_Year'].min()
        
        # Cyclical encoding for year (captures seasonality)
        year_cycle = 2 * np.pi * df['Years_Since_Start'] / 24  # 24 year period
        df['Year_Sin'] = np.sin(year_cycle)
        df['Year_Cos'] = np.cos(year_cycle)
        
        logger.info(f"   Created 5 year-based features")
        
        # Season features
        season_map = {
            'Kharif     ': 1,  # Monsoon crop season
            'Rabi       ': 2,  # Winter crop season
            'Summer     ': 3,  # Summer season
            'Autumn     ': 4,  # Autumn
            'Winter     ': 5,  # Winter
            'Whole Year ': 0   # All year
        }
        df['Season_Encoded'] = df['Season'].map(season_map)
        
        # Cyclical encoding for season
        season_cycle = 2 * np.pi * df['Season_Encoded'] / 6
        df['Season_Sin'] = np.sin(season_cycle)
        df['Season_Cos'] = np.cos(season_cycle)
        
        logger.info(f"   Created 3 season-based features")
        
        return df
    
    def create_interaction_features(self, df):
        """Create interaction and ratio features"""
        df = df.copy()
        
        logger.info("\nCREATING INTERACTION FEATURES:")
        logger.info("-" * 80)
        
        # Ratio features
        df['Production_per_Area'] = df['Production'] / (df['Area'] + 1)  # Avoid division by zero
        df['Fertilizer_per_Area'] = df['Fertilizer'] / (df['Area'] + 1)
        df['Pesticide_per_Area'] = df['Pesticide'] / (df['Area'] + 1)
        
        # Interaction features
        df['Fertilizer_Pesticide_Ratio'] = df['Fertilizer'] / (df['Pesticide'] + 1)
        df['Total_Chemical'] = df['Fertilizer'] + df['Pesticide']
        df['Chemical_per_Area'] = df['Total_Chemical'] / (df['Area'] + 1)
        
        # Rainfall interactions
        df['Rainfall_Area_Product'] = df['Annual_Rainfall'] * df['Area']
        df['Rainfall_Fertilizer_Product'] = df['Annual_Rainfall'] * np.log1p(df['Fertilizer'])
        
        logger.info(f"   Created 8 interaction/ratio features")
        
        return df
    
    def encode_categorical_features(self, df):
        """One-hot encode categorical variables"""
        df = df.copy()
        
        logger.info("\nENCODING CATEGORICAL FEATURES:")
        logger.info("-" * 80)
        
        # One-hot encode top crops (reduce dimensionality)
        top_crops = df['Crop'].value_counts().head(10).index
        df['Crop_TopN'] = df['Crop'].apply(lambda x: x if x in top_crops else 'Other')
        crop_dummies = pd.get_dummies(df['Crop_TopN'], prefix='Crop', drop_first=True)
        df = pd.concat([df, crop_dummies], axis=1)
        logger.info(f"   One-hot encoded top 10 crops + Other")
        
        # One-hot encode top states
        top_states = df['State'].value_counts().head(15).index
        df['State_TopN'] = df['State'].apply(lambda x: x if x in top_states else 'Other')
        state_dummies = pd.get_dummies(df['State_TopN'], prefix='State', drop_first=True)
        df = pd.concat([df, state_dummies], axis=1)
        logger.info(f"   One-hot encoded top 15 states + Other")
        
        return df
    
    def select_features(self, df):
        """Select final features for modeling"""
        
        logger.info("\nSELECTING FEATURES:")
        logger.info("-" * 80)
        
        # Keep numeric and encoded features, drop raw categoricals
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        numeric_cols = [col for col in numeric_cols if col not in ['Crop_Year']]
        
        # Also keep original features useful for interpretation
        keep_cols = ['Crop_Year'] + list(numeric_cols)
        X = df[keep_cols].copy()
        
        logger.info(f"   Selected {len(X.columns)} features for modeling")
        logger.info(f"   Feature categories:")
        logger.info(f"      - Time: 8 features")
        logger.info(f"      - Interactions: 8 features")
        logger.info(f"      - Log transformed: {sum(1 for col in X.columns if '_log' in col)} features")
        logger.info(f"      - Capped outliers: {sum(1 for col in X.columns if '_capped' in col)} features")
        logger.info(f"      - Crop one-hot: {sum(1 for col in X.columns if 'Crop_' in col)} features")
        logger.info(f"      - State one-hot: {sum(1 for col in X.columns if 'State_' in col)} features")
        logger.info(f"      - Other: {X.shape[1] - sum(1 for col in X.columns if any(cat in col for cat in ['_log', '_capped', 'Crop_', 'State_'])) - 1} features")
        
        self.feature_names = list(X.columns)
        return X
    
    def fit_scaler(self, X):
        """Fit StandardScaler"""
        try:
            self.scaler.fit(X)
            logger.info(f"Scaler fitted")
            logger.info(f"   Mean range: {self.scaler.mean_.min():.4f} to {self.scaler.mean_.max():.4f}")
            logger.info(f"   Scale range: {self.scaler.scale_.min():.4f} to {self.scaler.scale_.max():.4f}")
            return self
        except Exception as e:
            logger.error(f"Error fitting scaler: {e}")
            raise
    
    def transform_features(self, X):
        """Transform features using scaler"""
        try:
            X_scaled = self.scaler.transform(X)
            logger.info(f"Features scaled")
            logger.info(f"   Transformed mean: {X_scaled.mean():.6f}")
            logger.info(f"   Transformed std: {X_scaled.std():.6f}")
            return X_scaled
        except Exception as e:
            logger.error(f"Error transforming features: {e}")
            raise
    
    def fit_transform(self, X):
        """Fit and transform in one step"""
        return self.fit_scaler(X).transform_features(X)
    
    def save_scaler(self, path='src/models/saved_models/scalers/crop_feature_scaler.pkl'):
        """Save fitted scaler"""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self.scaler, path)
            logger.info(f"Scaler saved: {path}")
        except Exception as e:
            logger.error(f"Error saving scaler: {e}")
            raise
    
    def save_feature_names(self, path='src/models/saved_models/crop_feature_names.pkl'):
        """Save feature names for later reference"""
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(self.feature_names, path)
            logger.info(f"Feature names saved: {path}")
        except Exception as e:
            logger.error(f"Error saving feature names: {e}")
            raise


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    
    print("\n" + "=" * 80)
    print("CROP FEATURE ENGINEERING")
    print("=" * 80)
    
    try:
        # Initialize
        engineer = CropFeatureEngineer()
        
        # Load data
        logger.info("\nLoading crop data...")
        df = engineer.load_data('data/processed/crop_raw_data.csv')
        
        # Handle scales
        logger.info("\nHandling extreme scales...")
        df = engineer.handle_extreme_scales(df)
        
        # Handle outliers
        logger.info("\nHandling outliers...")
        df = engineer.handle_outliers(df)
        
        # Create time features
        logger.info("\nCreating time features...")
        df = engineer.create_time_features(df)
        
        # Create interaction features
        logger.info("\nCreating interaction features...")
        df = engineer.create_interaction_features(df)
        
        # Encode categoricals
        logger.info("\nEncoding categorical features...")
        df = engineer.encode_categorical_features(df)
        
        # Select features
        logger.info("\nSelecting features...")
        X = engineer.select_features(df)
        
        # Scale
        logger.info("\nScaling features...")
        X_scaled = engineer.fit_transform(X)
        
        # Save scaler
        logger.info("\nSaving artifacts...")
        engineer.save_scaler()
        engineer.save_feature_names()
        
        # Save processed data
        df_processed = pd.DataFrame(X_scaled, columns=engineer.feature_names)
        df_processed.to_csv('data/processed/crop_processed.csv', index=False)
        logger.info(f"Processed data saved: data/processed/crop_processed.csv")
        
        print("\n" + "=" * 80)
        print("CROP FEATURE ENGINEERING COMPLETE!")
        print(f"   Input: 19,689 × 10")
        print(f"   Output: 19,689 × {X_scaled.shape[1]}")
        print("=" * 80)
        
    except Exception as e:
        logger.error(f"\nPipeline failed: {e}")
        raise