import os # pyrefly: ignore [missing-import]
from sqlalchemy import create_engine # pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker # pyrefly: ignore [missing-import]
from dotenv import load_dotenv # pyrefly: ignore [missing-import]

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:@localhost:3306/shahenshah_pos")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
