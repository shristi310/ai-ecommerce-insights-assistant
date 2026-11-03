from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "database" / "ecommerce.db"

APP_TITLE = "E-commerce Business Insights"
CACHE_TTL_SECONDS = 300