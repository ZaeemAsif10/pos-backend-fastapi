from fastapi import APIRouter, Depends, HTTPException, status # pyrefly: ignore [missing-import]
from fastapi.security import OAuth2PasswordRequestForm # pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session # pyrefly: ignore [missing-import]
from datetime import timedelta # pyrefly: ignore [missing-import]

from app.db.database import get_db # pyrefly: ignore [missing-import]
from app.schemas.user import UserCreate, UserResponse, Token # pyrefly: ignore [missing-import]
from app.crud.crud_user import get_user_by_email, create_user # pyrefly: ignore [missing-import]
from app.core.security import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES # pyrefly: ignore [missing-import]
from app.models.user import Role # pyrefly: ignore [missing-import]

router = APIRouter()

@router.post("/signup", response_model=UserResponse)
def signup(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user (Cashier, Manager, etc.)
    """
    user = get_user_by_email(db, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="Is email se pehle hi ek account mojood hai.",
        )
    
    # Check if the requested role exists
    role = db.query(Role).filter(Role.id == user_in.role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail="Yeh role database mein mojood nahi hai.")
        
    user = create_user(db, user_in)
    return user

@router.post("/login", response_model=Token)
def login(db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Login with Email and Password to get a JWT token.
    Note: OAuth2PasswordRequestForm uses 'username', but we map it to 'email'.
    """
    user = get_user_by_email(db, email=form_data.username)
    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Galat email ya password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Yeh user block kiya ja chuka hai.")
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user.id, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

from app.api.deps import get_current_active_user
from app.models.user import User

@router.get("/me", response_model=UserResponse)
def read_user_me(current_user: User = Depends(get_current_active_user)):
    """
    Get current logged in user profile with role and business info.
    """
    return current_user
