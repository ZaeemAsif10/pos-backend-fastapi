from datetime import datetime, timedelta, timezone # pyrefly: ignore [missing-import]
from typing import Any, Union # pyrefly: ignore [missing-import]
from jose import jwt # pyrefly: ignore [missing-import]
from passlib.context import CryptContext # pyrefly: ignore [missing-import]
from app.core.config import settings # pyrefly: ignore [missing-import]
import os # pyrefly: ignore [missing-import]

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# You should generate a strong random secret key for production and put it in .env
SECRET_KEY = os.getenv("SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 days for POS

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
