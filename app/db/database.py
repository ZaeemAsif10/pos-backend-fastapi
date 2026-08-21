import os # pyrefly: ignore [missing-import]
from sqlalchemy import create_engine # pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker # pyrefly: ignore [missing-import]
from dotenv import load_dotenv # pyrefly: ignore [missing-import]

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:@localhost:3306/shahenshah_pos")

connect_args = {}
if "aivencloud.com" in DATABASE_URL or "ssl" in DATABASE_URL.lower():
    if "?" in DATABASE_URL:
        base_url, _ = DATABASE_URL.split("?", 1)
        DATABASE_URL = base_url
    connect_args = {"ssl": {"ssl_mode": "REQUIRED"}}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
