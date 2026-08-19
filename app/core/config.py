import os # pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings # pyrefly: ignore [missing-import]
from dotenv import load_dotenv # pyrefly: ignore [missing-import]

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Shahenshah POS"
    VERSION: str = "1.0"
    API_V1_STR: str = "/api/v1"
    
    # DB
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mysql+pymysql://root:@localhost:3306/shahenshah_pos")

settings = Settings()
