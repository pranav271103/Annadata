"""
Crop Yield Data Loader
"""

import pandas as pd
import numpy as np
import logging
from pathlib import Path
from typing import Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CropYieldLoader:
    """
    Load and validate crop yield dataset
    
    Features:
    - Crop, Crop_Year, Season, State, Area, Production, 
      Annual_Rainfall, Fertilizer, Pesticide, Yield
    """
    
    def __init__(self):
        """Initialize crop data loader"""
        self.data = None
        logger.info("CropYieldLoader initialized")
    
    def load_data(self, csv_path: str = 'C://Users//prana//Downloads//Annadata//data//raw//crop_yield//crop_yield.csv') -> pd.DataFrame:
        """
        Load crop yield CSV file
        
        Args:
            csv_path: Path to crop data CSV
            
        Returns:
            DataFrame with crop data
        """
        try:
            if not Path(csv_path).exists():
                raise FileNotFoundError(f"Crop data not found: {csv_path}")
            
            df = pd.read_csv(csv_path)
            self.data = df
            
            logger.info(f"Loaded crop data: {df.shape[0]} rows × {df.shape[1]} columns")
            logger.info(f"   Columns: {list(df.columns)}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading crop data: {e}")
            raise
    
    def validate_data(self) -> bool:
        """Validate data quality"""
        if self.data is None:
            logger.error("No data loaded")
            return False
        
        try:
            logger.info("\nDATA VALIDATION")
            logger.info("-" * 80)
            
            # Check shape
            logger.info(f"Shape: {self.data.shape}")
            
            # Check columns
            expected_cols = ['Crop', 'Crop_Year', 'Season', 'State', 'Area', 
                            'Production', 'Annual_Rainfall', 'Fertilizer', 'Pesticide', 'Yield']
            missing_cols = [col for col in expected_cols if col not in self.data.columns]
            
            if missing_cols:
                logger.warning(f"Missing columns: {missing_cols}")
            else:
                logger.info(f"All expected columns present")
            
            # Check missing values
            missing = self.data.isnull().sum()
            if missing.sum() > 0:
                logger.warning(f"\nMissing values:")
                for col, count in missing[missing > 0].items():
                    logger.warning(f"   {col}: {count} ({count/len(self.data)*100:.2f}%)")
            else:
                logger.info(f"No missing values")
            
            # Check data types
            logger.info(f"\nData types:")
            for col, dtype in self.data.dtypes.items():
                logger.info(f"   {col}: {dtype}")
            
            # Check for duplicates
            duplicates = self.data.duplicated().sum()
            if duplicates > 0:
                logger.warning(f"Found {duplicates} duplicate rows")
            else:
                logger.info(f"No duplicate rows")
            
            return True
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False
    
    def explore_data(self) -> None:
        """Explore dataset characteristics"""
        if self.data is None:
            logger.error("No data to explore")
            return
        
        try:
            logger.info("\n" + "=" * 80)
            logger.info("CROP DATA EXPLORATION")
            logger.info("=" * 80)
            
            # Unique values
            logger.info(f"\nUNIQUE VALUES:")
            logger.info(f"   Crops: {self.data['Crop'].nunique()}")
            logger.info(f"   Years: {self.data['Crop_Year'].nunique()} ({self.data['Crop_Year'].min()}-{self.data['Crop_Year'].max()})")
            logger.info(f"   Seasons: {self.data['Season'].nunique()} - {list(self.data['Season'].unique())}")
            logger.info(f"   States: {self.data['State'].nunique()}")
            
            # Crops
            logger.info(f"\nTOP CROPS:")
            for crop, count in self.data['Crop'].value_counts().head(10).items():
                logger.info(f"   {crop}: {count} records")
            
            # States
            logger.info(f"\nTOP STATES:")
            for state, count in self.data['State'].value_counts().head(10).items():
                logger.info(f"   {state}: {count} records")
            
            # Statistics
            logger.info(f"\nNUMERIC STATISTICS:")
            stats = self.data.describe()
            logger.info(f"\n{stats.to_string()}")
            
            # Yield analysis (TARGET VARIABLE)
            logger.info(f"\nYIELD ANALYSIS (TARGET):")
            logger.info(f"   Min: {self.data['Yield'].min()}")
            logger.info(f"   Max: {self.data['Yield'].max()}")
            logger.info(f"   Mean: {self.data['Yield'].mean():.2f}")
            logger.info(f"   Median: {self.data['Yield'].median():.2f}")
            logger.info(f"   Std: {self.data['Yield'].std():.2f}")
            logger.info(f"   Zero yields: {(self.data['Yield'] == 0).sum()}")
            
            # Production analysis
            logger.info(f"\nPRODUCTION ANALYSIS:")
            logger.info(f"   Min: {self.data['Production'].min()}")
            logger.info(f"   Max: {self.data['Production'].max()}")
            logger.info(f"   Mean: {self.data['Production'].mean():.2e}")
            logger.info(f"   Median: {self.data['Production'].median():.2e}")
            
            # Fertilizer & Pesticide
            logger.info(f"\nFERTILIZER & PESTICIDE:")
            logger.info(f"   Fertilizer range: {self.data['Fertilizer'].min():.2e} - {self.data['Fertilizer'].max():.2e}")
            logger.info(f"   Pesticide range: {self.data['Pesticide'].min():.2e} - {self.data['Pesticide'].max():.2e}")
            
            # Rainfall
            logger.info(f"\nRAINFALL ANALYSIS:")
            logger.info(f"   Min: {self.data['Annual_Rainfall'].min():.2f} mm")
            logger.info(f"   Max: {self.data['Annual_Rainfall'].max():.2f} mm")
            logger.info(f"   Mean: {self.data['Annual_Rainfall'].mean():.2f} mm")
            
        except Exception as e:
            logger.error(f"Exploration error: {e}")
    
    def identify_outliers(self) -> None:
        """Identify potential outliers"""
        if self.data is None:
            return
        
        try:
            logger.info(f"\nOUTLIER DETECTION:")
            logger.info("-" * 80)
            
            # Yield outliers (using IQR method)
            Q1 = self.data['Yield'].quantile(0.25)
            Q3 = self.data['Yield'].quantile(0.75)
            IQR = Q3 - Q1
            outlier_mask = (self.data['Yield'] < Q1 - 1.5*IQR) | (self.data['Yield'] > Q3 + 1.5*IQR)
            
            logger.info(f"   Yield outliers: {outlier_mask.sum()} ({outlier_mask.sum()/len(self.data)*100:.2f}%)")
            
            # Production outliers
            Q1_prod = self.data['Production'].quantile(0.25)
            Q3_prod = self.data['Production'].quantile(0.75)
            IQR_prod = Q3_prod - Q1_prod
            outlier_prod = (self.data['Production'] < Q1_prod - 1.5*IQR_prod) | (self.data['Production'] > Q3_prod + 1.5*IQR_prod)
            
            logger.info(f"   Production outliers: {outlier_prod.sum()} ({outlier_prod.sum()/len(self.data)*100:.2f}%)")
            
            # Fertilizer outliers
            Q1_fert = self.data['Fertilizer'].quantile(0.25)
            Q3_fert = self.data['Fertilizer'].quantile(0.75)
            IQR_fert = Q3_fert - Q1_fert
            outlier_fert = (self.data['Fertilizer'] < Q1_fert - 1.5*IQR_fert) | (self.data['Fertilizer'] > Q3_fert + 1.5*IQR_fert)
            
            logger.info(f"   Fertilizer outliers: {outlier_fert.sum()} ({outlier_fert.sum()/len(self.data)*100:.2f}%)")
            
        except Exception as e:
            logger.error(f"Outlier detection error: {e}")
    
    def save_data(self, output_path: str = 'data/processed/crop_raw_data.csv') -> None:
        """Save loaded data to processed folder"""
        if self.data is None:
            logger.error("No data to save")
            return
        
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            self.data.to_csv(output_path, index=False)
            logger.info(f"Data saved: {output_path}")
        except Exception as e:
            logger.error(f"Error saving data: {e}")
    
    def get_summary(self) -> dict:
        """Get dataset summary"""
        if self.data is None:
            return {}
        
        return {
            'records': len(self.data),
            'features': self.data.shape[1],
            'missing_values': self.data.isnull().sum().sum(),
            'unique_crops': self.data['Crop'].nunique(),
            'unique_states': self.data['State'].nunique(),
            'year_range': f"{self.data['Crop_Year'].min()}-{self.data['Crop_Year'].max()}",
            'yield_range': f"{self.data['Yield'].min():.2f}-{self.data['Yield'].max():.2f}"
        }


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    
    print("\n" + "=" * 80)
    print("CROP YIELD DATA LOADER")
    print("=" * 80)
    
    try:
        # Initialize loader
        loader = CropYieldLoader()
        
        # Load data
        logger.info("\nLoading crop yield data...")
        df = loader.load_data('C://Users//prana//Downloads//Annadata//data//raw//crop_yield//crop_yield.csv')
        
        # Validate
        logger.info("\nValidating data...")
        loader.validate_data()
        
        # Explore
        logger.info("\nExploring data...")
        loader.explore_data()
        
        # Outliers
        logger.info("\nDetecting outliers...")
        loader.identify_outliers()
        
        # Save
        logger.info("\nSaving data...")
        loader.save_data('data/processed/crop_raw_data.csv')
        
        # Summary
        summary = loader.get_summary()
        logger.info(f"\nSUMMARY:")
        for key, value in summary.items():
            logger.info(f"   {key}: {value}")
        
        print("\n" + "=" * 80)
        print("CROP DATA LOADED SUCCESSFULLY!")
        print("=" * 80)
        
    except Exception as e:
        logger.error(f"\nPipeline failed: {e}")
        raise
