"""
backend/app/utils/rate_limit.py
نظام Rate Limiting باستخدام SlowAPI و Redis
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request, Response
from typing import Optional, Callable
import redis
import os
from functools import wraps

from .logging import app_logger


# ═══════════════════════════════════════════════════
# Redis Configuration
# ═══════════════════════════════════════════════════

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").lower() == "true"


def get_redis_client() -> Optional[redis.Redis]:
    """الحصول على Redis client"""
    if not REDIS_ENABLED:
        app_logger.warning("Redis is disabled. Rate limiting will use in-memory storage.")
        return None
    
    try:
        client = redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5
        )
        # اختبار الاتصال
        client.ping()
        app_logger.info("Redis connection established for rate limiting")
        return client
    
    except Exception as e:
        app_logger.error(f"Failed to connect to Redis: {str(e)}")
        app_logger.warning("Falling back to in-memory rate limiting")
        return None


# ═══════════════════════════════════════════════════
# Custom Key Functions
# ═══════════════════════════════════════════════════

def get_user_key(request: Request) -> str:
    """
    مفتاح Rate Limiting حسب المستخدم
    يستخدم user_id من Token إذا كان موجود
    """
    # محاولة الحصول على user من Token
    if hasattr(request.state, 'user') and request.state.user:
        user_id = getattr(request.state.user, 'user_id', None)
        if user_id:
            return f"user:{user_id}"
    
    # استخدام IP كبديل
    return f"ip:{get_remote_address(request)}"


def get_customer_key(request: Request) -> str:
    """
    مفتاح Rate Limiting حسب العميل
    """
    # محاولة الحصول على customer_id من path
    customer_id = request.path_params.get('customer_id')
    
    if customer_id:
        return f"customer:{customer_id}"
    
    # استخدام user_key كبديل
    return get_user_key(request)


def get_endpoint_key(request: Request) -> str:
    """
    مفتاح Rate Limiting حسب Endpoint
    """
    path = request.url.path
    user_key = get_user_key(request)
    return f"{user_key}:endpoint:{path}"


# ═══════════════════════════════════════════════════
# Limiter Setup
# ═══════════════════════════════════════════════════

# إنشاء Limiter
limiter = Limiter(
    key_func=get_remote_address,  # Default key function
    storage_uri=REDIS_URL if REDIS_ENABLED else "memory://",
    strategy="fixed-window",  # or "moving-window"
    headers_enabled=True,  # إضافة headers للـ response
)


# ═══════════════════════════════════════════════════
# Custom Rate Limit Decorators
# ═══════════════════════════════════════════════════

def rate_limit_by_user(limit_string: str):
    """
    Rate limit حسب المستخدم
    
    Usage:
        @app.get("/api/data")
        @rate_limit_by_user("10/minute")
        async def get_data():
            ...
    """
    def decorator(func):
        @wraps(func)
        @limiter.limit(limit_string, key_func=get_user_key)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def rate_limit_by_customer(limit_string: str):
    """
    Rate limit حسب العميل
    
    Usage:
        @app.post("/api/invoices/{customer_id}")
        @rate_limit_by_customer("50/hour")
        async def process_invoice(customer_id: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        @limiter.limit(limit_string, key_func=get_customer_key)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def rate_limit_by_endpoint(limit_string: str):
    """
    Rate limit حسب المستخدم والـ Endpoint
    
    Usage:
        @app.post("/api/expensive-operation")
        @rate_limit_by_endpoint("5/minute")
        async def expensive_operation():
            ...
    """
    def decorator(func):
        @wraps(func)
        @limiter.limit(limit_string, key_func=get_endpoint_key)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════
# Rate Limit Configurations
# ═══════════════════════════════════════════════════

class RateLimitConfig:
    """إعدادات Rate Limiting للـ Endpoints المختلفة"""
    
    # Global limits (by IP)
    GLOBAL_LIMIT = "100/minute"
    
    # Authentication endpoints
    AUTH_LOGIN = "5/minute"          # منع Brute Force
    AUTH_REGISTER = "3/hour"         # منع Spam
    AUTH_REFRESH = "10/hour"
    
    # Invoice processing (expensive operations)
    INVOICE_PROCESS = "20/minute"    # LLM calls are expensive
    INVOICE_BATCH = "5/hour"         # Batch operations
    
    # Read operations
    INVOICE_READ = "100/minute"
    CUSTOMER_READ = "100/minute"
    
    # Stats and monitoring
    STATS_READ = "30/minute"
    
    # Admin operations
    ADMIN_OPERATIONS = "50/minute"


# ═══════════════════════════════════════════════════
# Custom Error Response
# ═══════════════════════════════════════════════════

def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    معالج مخصص لتجاوز Rate Limit
    """
    app_logger.warning(
        f"Rate limit exceeded: {get_remote_address(request)} "
        f"on {request.url.path}"
    )
    
    # استخراج معلومات من الاستثناء
    retry_after = getattr(exc, 'retry_after', None)
    
    response = Response(
        content={
            "error": "RATE_LIMIT_EXCEEDED",
            "message": "Too many requests. Please slow down.",
            "detail": str(exc),
            "retry_after": retry_after
        },
        status_code=429,
        headers={
            "Retry-After": str(retry_after) if retry_after else "60"
        }
    )
    
    return response


# ═══════════════════════════════════════════════════
# Middleware for Rate Limit Headers
# ═══════════════════════════════════════════════════

class RateLimitHeadersMiddleware:
    """
    إضافة Headers معلوماتية عن Rate Limiting
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # يمكن إضافة Headers هنا
            pass
        
        await self.app(scope, receive, send)


# ═══════════════════════════════════════════════════
# Rate Limit Checker (للاستخدام البرمجي)
# ═══════════════════════════════════════════════════

class RateLimitChecker:
    """
    فحص Rate Limit برمجياً
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or get_redis_client()
    
    def check_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> bool:
        """
        التحقق من عدم تجاوز الحد
        
        Args:
            key: المفتاح الفريد
            limit: العدد الأقصى المسموح
            window_seconds: النافذة الزمنية بالثواني
        
        Returns:
            True إذا كان ضمن الحد، False إذا تجاوز
        """
        if not self.redis:
            # بدون Redis، نسمح بكل شيء (fallback)
            return True
        
        try:
            current = self.redis.incr(key)
            
            if current == 1:
                # أول طلب، نضع expiry
                self.redis.expire(key, window_seconds)
            
            return current <= limit
        
        except Exception as e:
            app_logger.error(f"Rate limit check failed: {str(e)}")
            # في حالة الفشل، نسمح بالطلب
            return True
    
    def get_remaining(
        self,
        key: str,
        limit: int
    ) -> int:
        """الحصول على العدد المتبقي من الطلبات"""
        if not self.redis:
            return limit
        
        try:
            current = int(self.redis.get(key) or 0)
            return max(0, limit - current)
        except:
            return limit
    
    def reset_limit(self, key: str) -> None:
        """إعادة تعيين الحد لمفتاح معين"""
        if self.redis:
            try:
                self.redis.delete(key)
            except:
                pass


# ═══════════════════════════════════════════════════
# Cost-Based Rate Limiting (للعمليات المكلفة)
# ═══════════════════════════════════════════════════

class CostBasedRateLimiter:
    """
    Rate Limiting بناءً على التكلفة
    مفيد لـ LLM calls حيث كل عملية لها تكلفة مختلفة
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or get_redis_client()
    
    def consume_credits(
        self,
        user_id: str,
        cost: int,
        max_credits: int = 1000,
        window_seconds: int = 3600  # 1 hour
    ) -> bool:
        """
        استهلاك Credits
        
        Args:
            user_id: معرف المستخدم
            cost: تكلفة العملية
            max_credits: الحد الأقصى من Credits
            window_seconds: النافذة الزمنية
        
        Returns:
            True إذا تم الاستهلاك بنجاح
        """
        if not self.redis:
            return True
        
        key = f"credits:{user_id}"
        
        try:
            current = int(self.redis.get(key) or 0)
            
            if current + cost > max_credits:
                app_logger.warning(
                    f"Credit limit exceeded for user {user_id}: "
                    f"{current + cost}/{max_credits}"
                )
                return False
            
            new_value = self.redis.incrby(key, cost)
            
            if current == 0:
                self.redis.expire(key, window_seconds)
            
            app_logger.debug(
                f"Credits consumed for {user_id}: {cost} "
                f"(total: {new_value}/{max_credits})"
            )
            
            return True
        
        except Exception as e:
            app_logger.error(f"Credit consumption failed: {str(e)}")
            return True  # Fallback


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'limiter',
    'get_redis_client',
    'get_user_key',
    'get_customer_key',
    'get_endpoint_key',
    'rate_limit_by_user',
    'rate_limit_by_customer',
    'rate_limit_by_endpoint',
    'RateLimitConfig',
    'custom_rate_limit_exceeded_handler',
    'RateLimitChecker',
    'CostBasedRateLimiter',
]