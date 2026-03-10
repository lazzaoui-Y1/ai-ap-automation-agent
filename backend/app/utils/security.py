"""
backend/app/utils/security.py
نظام أمان متكامل: JWT, Password Hashing, RBAC
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
import os
from enum import Enum

from .exceptions import AuthenticationError, AuthorizationError
from .logging import app_logger


# ═══════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════

SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer security scheme
security_scheme = HTTPBearer()


# ═══════════════════════════════════════════════════
# User Roles & Permissions
# ═══════════════════════════════════════════════════

class UserRole(str, Enum):
    """أدوار المستخدمين"""
    SUPER_ADMIN = "super_admin"      # إدارة كاملة
    ADMIN = "admin"                  # إدارة العملاء
    USER = "user"                    # مستخدم عادي
    API_CLIENT = "api_client"        # عميل API فقط


class Permission(str, Enum):
    """الصلاحيات"""
    # Invoice permissions
    INVOICE_READ = "invoice:read"
    INVOICE_CREATE = "invoice:create"
    INVOICE_UPDATE = "invoice:update"
    INVOICE_DELETE = "invoice:delete"
    
    # Customer permissions
    CUSTOMER_READ = "customer:read"
    CUSTOMER_CREATE = "customer:create"
    CUSTOMER_UPDATE = "customer:update"
    CUSTOMER_DELETE = "customer:delete"
    
    # Admin permissions
    USER_MANAGE = "user:manage"
    SYSTEM_CONFIG = "system:config"


# Role -> Permissions mapping
ROLE_PERMISSIONS: Dict[UserRole, List[Permission]] = {
    UserRole.SUPER_ADMIN: list(Permission),  # All permissions
    UserRole.ADMIN: [
        Permission.INVOICE_READ,
        Permission.INVOICE_CREATE,
        Permission.INVOICE_UPDATE,
        Permission.CUSTOMER_READ,
        Permission.CUSTOMER_UPDATE,
    ],
    UserRole.USER: [
        Permission.INVOICE_READ,
        Permission.INVOICE_CREATE,
    ],
    UserRole.API_CLIENT: [
        Permission.INVOICE_CREATE,
        Permission.INVOICE_READ,
    ]
}


# ═══════════════════════════════════════════════════
# Password Utilities
# ═══════════════════════════════════════════════════

def hash_password(password: str) -> str:
    """تشفير كلمة المرور"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """التحقق من كلمة المرور"""
    return pwd_context.verify(plain_password, hashed_password)


# ═══════════════════════════════════════════════════
# JWT Token Functions
# ═══════════════════════════════════════════════════

def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    إنشاء Access Token
    
    Args:
        data: البيانات المراد تضمينها في Token
        expires_delta: مدة صلاحية Token
    
    Returns:
        JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    إنشاء Refresh Token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    فك تشفير Token والتحقق من صلاحيته
    
    Args:
        token: JWT token
    
    Returns:
        البيانات المستخرجة من Token
    
    Raises:
        AuthenticationError: إذا كان Token غير صالح
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    
    except JWTError as e:
        app_logger.warning(f"Invalid token: {str(e)}")
        raise AuthenticationError("Invalid or expired token")


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """
    التحقق من Token ونوعه
    """
    payload = decode_token(token)
    
    if payload.get("type") != token_type:
        raise AuthenticationError(f"Invalid token type. Expected: {token_type}")
    
    return payload


# ═══════════════════════════════════════════════════
# User Authentication
# ═══════════════════════════════════════════════════

class TokenData:
    """بيانات Token"""
    def __init__(
        self,
        user_id: str,
        username: str,
        email: str,
        role: UserRole,
        customer_id: Optional[str] = None,
        permissions: Optional[List[Permission]] = None
    ):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.role = role
        self.customer_id = customer_id
        self.permissions = permissions or ROLE_PERMISSIONS.get(role, [])


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme)
) -> TokenData:
    """
    الحصول على المستخدم الحالي من Token
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: TokenData = Depends(get_current_user)):
            ...
    """
    token = credentials.credentials
    
    try:
        payload = verify_token(token, token_type="access")
        
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        email: str = payload.get("email")
        role_str: str = payload.get("role")
        customer_id: Optional[str] = payload.get("customer_id")
        
        if not user_id or not username:
            raise AuthenticationError("Invalid token payload")
        
        role = UserRole(role_str)
        
        user_data = TokenData(
            user_id=user_id,
            username=username,
            email=email,
            role=role,
            customer_id=customer_id
        )
        
        app_logger.debug(f"User authenticated: {username} (role: {role.value})")
        
        return user_data
    
    except ValueError as e:
        app_logger.warning(f"Invalid role in token: {str(e)}")
        raise AuthenticationError("Invalid user role")
    
    except Exception as e:
        app_logger.error(f"Authentication failed: {str(e)}")
        raise AuthenticationError("Authentication failed")


# ═══════════════════════════════════════════════════
# Permission Checking
# ═══════════════════════════════════════════════════

class PermissionChecker:
    """
    التحقق من الصلاحيات
    
    Usage:
        require_permission = PermissionChecker([Permission.INVOICE_CREATE])
        
        @app.post("/invoices")
        async def create_invoice(user: TokenData = Depends(require_permission)):
            ...
    """
    
    def __init__(self, required_permissions: List[Permission]):
        self.required_permissions = required_permissions
    
    async def __call__(
        self,
        user: TokenData = Depends(get_current_user)
    ) -> TokenData:
        """
        التحقق من أن المستخدم لديه الصلاحيات المطلوبة
        """
        for permission in self.required_permissions:
            if permission not in user.permissions:
                app_logger.warning(
                    f"Permission denied: {user.username} lacks {permission.value}"
                )
                raise AuthorizationError(
                    f"Permission denied. Required: {permission.value}",
                    required_permission=permission.value
                )
        
        return user


def require_role(allowed_roles: List[UserRole]):
    """
    Decorator للتحقق من دور المستخدم
    
    Usage:
        @app.get("/admin")
        async def admin_route(
            user: TokenData = Depends(require_role([UserRole.ADMIN, UserRole.SUPER_ADMIN]))
        ):
            ...
    """
    async def role_checker(
        user: TokenData = Depends(get_current_user)
    ) -> TokenData:
        if user.role not in allowed_roles:
            app_logger.warning(
                f"Role check failed: {user.username} has role {user.role.value}, "
                f"required one of: {[r.value for r in allowed_roles]}"
            )
            raise AuthorizationError(
                f"Insufficient permissions. Required role: {[r.value for r in allowed_roles]}"
            )
        
        return user
    
    return role_checker


# ═══════════════════════════════════════════════════
# Customer Isolation
# ═══════════════════════════════════════════════════

async def verify_customer_access(
    customer_id: str,
    user: TokenData = Depends(get_current_user)
) -> TokenData:
    """
    التحقق من أن المستخدم لديه وصول إلى العميل المحدد
    
    Usage:
        @app.get("/customers/{customer_id}/invoices")
        async def get_invoices(
            customer_id: str,
            user: TokenData = Depends(verify_customer_access)
        ):
            ...
    """
    # Super Admin لديه وصول لكل العملاء
    if user.role == UserRole.SUPER_ADMIN:
        return user
    
    # المستخدمون الآخرون يمكنهم فقط الوصول لعميلهم
    if user.customer_id != customer_id:
        app_logger.warning(
            f"Customer access denied: {user.username} tried to access "
            f"customer {customer_id} but belongs to {user.customer_id}"
        )
        raise AuthorizationError(
            "You don't have access to this customer's data"
        )
    
    return user


# ═══════════════════════════════════════════════════
# API Key Authentication (for external integrations)
# ═══════════════════════════════════════════════════

def generate_api_key() -> str:
    """إنشاء API Key عشوائي"""
    return f"sk_{secrets.token_urlsafe(32)}"


def verify_api_key(api_key: str) -> bool:
    """
    التحقق من API Key
    TODO: ربط بقاعدة بيانات للـ API Keys
    """
    # للآن mock - يجب ربطه بقاعدة بيانات
    valid_keys = os.getenv("VALID_API_KEYS", "").split(",")
    return api_key in valid_keys


async def get_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security_scheme)
) -> str:
    """
    التحقق من API Key
    
    Usage:
        @app.post("/api/external")
        async def external_api(api_key: str = Depends(get_api_key)):
            ...
    """
    api_key = credentials.credentials
    
    if not verify_api_key(api_key):
        app_logger.warning(f"Invalid API key used")
        raise AuthenticationError("Invalid API key")
    
    return api_key


# ═══════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════

def create_user_tokens(user_data: Dict[str, Any]) -> Dict[str, str]:
    """
    إنشاء Access & Refresh Tokens للمستخدم
    
    Args:
        user_data: بيانات المستخدم (user_id, username, email, role, customer_id)
    
    Returns:
        {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}
    """
    access_token = create_access_token(data={
        "sub": user_data["user_id"],
        "username": user_data["username"],
        "email": user_data["email"],
        "role": user_data["role"],
        "customer_id": user_data.get("customer_id")
    })
    
    refresh_token = create_refresh_token(data={
        "sub": user_data["user_id"],
        "username": user_data["username"]
    })
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    # Password
    'hash_password',
    'verify_password',
    
    # Tokens
    'create_access_token',
    'create_refresh_token',
    'decode_token',
    'verify_token',
    'create_user_tokens',
    
    # Authentication
    'get_current_user',
    'get_api_key',
    'TokenData',
    
    # Authorization
    'PermissionChecker',
    'require_role',
    'verify_customer_access',
    
    # Enums
    'UserRole',
    'Permission',
    
    # API Keys
    'generate_api_key',
    'verify_api_key',
]