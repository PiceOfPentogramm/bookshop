import uuid
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from prometheus_fastapi_instrumentator import Instrumentator

from database import get_db
from schemas import UserCreate, UserLogin, UserResponse, TokenResponse
from crud import get_user_by_email, get_user_by_id, create_user
from auth import verify_password, create_access_token, verify_token

app = FastAPI(title="Bookshop User Service", version="1.0.0")

security = HTTPBearer()

Instrumentator().instrument(app).expose(app)

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    try:
        user = create_user(db, user_data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    return user


@app.post("/login", response_model=TokenResponse)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = get_user_by_email(db, credentials.email)
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    token = create_access_token(
        user_id=str(user.id),
        email=user.email,
        role=user.role.value,
    )
    return TokenResponse(access_token=token)


def _get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    payload = verify_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
        )
    user = get_user_by_id(db, uuid.UUID(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


# /users/me must be declared before /users/{user_id} to avoid route shadowing
@app.get("/users/me", response_model=UserResponse)
def get_me(current_user=Depends(_get_current_user)):
    return current_user


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user
