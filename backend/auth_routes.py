
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from backend.auth_schemas import RegisterRequest, LoginRequest, UserResponse
from backend.auth_service import register_student, authenticate_student, student_email_exists
from backend.auth_security import create_access_token, decode_access_token
from backend.auth_token_store import revoke_token, is_token_revoked
from backend.production.security import is_demo


router = APIRouter(prefix="/auth", tags=["Authentication"])

bearer_scheme = HTTPBearer(auto_error=False)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(request: RegisterRequest):
    try:
        student = register_student(
            name=request.name,
            email=str(request.email),
            password=request.password,
        )
        return student

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )


@router.post("/login")
def login(request: LoginRequest):
    if not student_email_exists(str(request.email)):
        raise HTTPException(status_code=404, detail="No account exists for this email. Please sign up.")
    student = authenticate_student(
        email=str(request.email),
        password=request.password,
    )

    if student is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(student["student_id"])

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": student,
    }


def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme), request: Request = None,
):
    if request is not None and getattr(request.state,"production_student",None) is not None:
        return request.state.production_student
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_access_token(token)
        student_id = int(payload["sub"])

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from backend.auth_db import get_auth_connection

    connection = get_auth_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT student_id, name, email
                FROM students
                WHERE student_id = %s
                """,
                (student_id,),
            )
            row = cursor.fetchone()

        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Student account not found.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return {
            "student_id": row[0],
            "name": row[1],
            "email": row[2],
            "is_demo": is_demo(row[0]),
        }

    finally:
        connection.close()


@router.get("/me", response_model=UserResponse)
def get_me(student: dict = Depends(get_current_student)):
    return student


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    if is_token_revoked(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has already been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        decode_access_token(token)

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    revoke_token(token)

    return {"message": "Logout successful."}

