from typing import Generator # pyrefly: ignore [missing-import]
from fastapi import Depends, HTTPException, status # pyrefly: ignore [missing-import]
from fastapi.security import OAuth2PasswordBearer # pyrefly: ignore [missing-import]
from jose import jwt, JWTError # pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session # pyrefly: ignore [missing-import]
from app.core.config import settings # pyrefly: ignore [missing-import]
from app.core.security import ALGORITHM, SECRET_KEY # pyrefly: ignore [missing-import]
from app.db.database import get_db # pyrefly: ignore [missing-import]
from app.models.user import User # pyrefly: ignore [missing-import]

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login")

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User:
    """
    Validates the JWT token and returns the current user.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    return user

def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensures the user is active.
    """
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
