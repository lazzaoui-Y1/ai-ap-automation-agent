"""
backend/app/utils/regex_safe.py
حماية من ReDoS (Regular Expression Denial of Service)
"""

import re
import signal
from typing import Pattern, Optional, Match, List
from contextlib import contextmanager
from functools import lru_cache

from .exceptions import FileProcessingError
from .logging import app_logger


# ═══════════════════════════════════════════════════
# Timeout Handler
# ═══════════════════════════════════════════════════

class TimeoutException(Exception):
    """استثناء Timeout"""
    pass


def timeout_handler(signum, frame):
    """معالج إشارة Timeout"""
    raise TimeoutException("Regex operation timed out")


@contextmanager
def time_limit(seconds: int):
    """
    Context manager لتحديد وقت التنفيذ
    
    Usage:
        with time_limit(1):
            result = re.search(pattern, text)
    """
    # تعيين signal alarm
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        # إلغاء alarm
        signal.alarm(0)


# ═══════════════════════════════════════════════════
# Safe Regex Functions
# ═══════════════════════════════════════════════════

def safe_re_search(
    pattern: Pattern,
    text: str,
    timeout: int = 1,
    flags: int = 0
) -> Optional[Match]:
    """
    Regex search آمن مع timeout
    
    Args:
        pattern: النمط (يمكن أن يكون string أو compiled pattern)
        text: النص المراد البحث فيه
        timeout: الحد الأقصى بالثواني
        flags: Regex flags
    
    Returns:
        Match object أو None
    
    Raises:
        FileProcessingError: إذا انتهت المهلة
    """
    try:
        with time_limit(timeout):
            if isinstance(pattern, str):
                return re.search(pattern, text, flags)
            else:
                return pattern.search(text)
    
    except TimeoutException:
        app_logger.error(
            f"Regex search timed out after {timeout}s. "
            f"Possible ReDoS attack or inefficient pattern."
        )
        raise FileProcessingError(
            f"Text processing timed out (possible complex content)"
        )
    
    except Exception as e:
        app_logger.error(f"Regex search failed: {str(e)}")
        return None


def safe_re_match(
    pattern: Pattern,
    text: str,
    timeout: int = 1,
    flags: int = 0
) -> Optional[Match]:
    """Regex match آمن مع timeout"""
    try:
        with time_limit(timeout):
            if isinstance(pattern, str):
                return re.match(pattern, text, flags)
            else:
                return pattern.match(text)
    
    except TimeoutException:
        app_logger.error(f"Regex match timed out after {timeout}s")
        raise FileProcessingError(
            f"Text processing timed out (possible complex content)"
        )
    
    except Exception as e:
        app_logger.error(f"Regex match failed: {str(e)}")
        return None


def safe_re_findall(
    pattern: Pattern,
    text: str,
    timeout: int = 2,
    flags: int = 0,
    max_results: int = 1000
) -> List[str]:
    """
    Regex findall آمن مع timeout وحد أقصى للنتائج
    """
    try:
        with time_limit(timeout):
            if isinstance(pattern, str):
                results = re.findall(pattern, text, flags)
            else:
                results = pattern.findall(text)
            
            # تحديد عدد النتائج لمنع استنزاف الذاكرة
            if len(results) > max_results:
                app_logger.warning(
                    f"Regex findall returned {len(results)} results, "
                    f"truncating to {max_results}"
                )
                return results[:max_results]
            
            return results
    
    except TimeoutException:
        app_logger.error(f"Regex findall timed out after {timeout}s")
        return []
    
    except Exception as e:
        app_logger.error(f"Regex findall failed: {str(e)}")
        return []


def safe_re_sub(
    pattern: Pattern,
    repl: str,
    text: str,
    timeout: int = 2,
    count: int = 0,
    flags: int = 0
) -> str:
    """Regex substitution آمن"""
    try:
        with time_limit(timeout):
            if isinstance(pattern, str):
                return re.sub(pattern, repl, text, count=count, flags=flags)
            else:
                return pattern.sub(repl, text, count=count)
    
    except TimeoutException:
        app_logger.error(f"Regex substitution timed out after {timeout}s")
        # إرجاع النص الأصلي في حالة الفشل
        return text
    
    except Exception as e:
        app_logger.error(f"Regex substitution failed: {str(e)}")
        return text


# ═══════════════════════════════════════════════════
# Safe Compiled Patterns (مع Cache)
# ═══════════════════════════════════════════════════

@lru_cache(maxsize=128)
def get_safe_pattern(pattern_str: str, flags: int = 0) -> Pattern:
    """
    Compile regex pattern مع caching
    
    Args:
        pattern_str: نمط Regex
        flags: Regex flags
    
    Returns:
        Compiled pattern
    """
    try:
        return re.compile(pattern_str, flags)
    except re.error as e:
        app_logger.error(f"Invalid regex pattern: {pattern_str} - {str(e)}")
        raise ValueError(f"Invalid regex pattern: {str(e)}")


# ═══════════════════════════════════════════════════
# Pre-defined Safe Patterns
# ═══════════════════════════════════════════════════

class SafePatterns:
    """
    أنماط Regex آمنة ومختبرة
    """
    
    # Email validation (safe pattern)
    EMAIL = get_safe_pattern(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    # Phone number (international format)
    PHONE = get_safe_pattern(
        r'^\+?[1-9]\d{1,14}$'
    )
    
    # UUID v4
    UUID = get_safe_pattern(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        re.IGNORECASE
    )
    
    # Saudi VAT number (15 digits, starts and ends with 3)
    SAUDI_VAT = get_safe_pattern(
        r'^3\d{13}3$'
    )
    
    # Date (YYYY-MM-DD)
    DATE_ISO = get_safe_pattern(
        r'^\d{4}-\d{2}-\d{2}$'
    )
    
    # JSON object (simple, non-greedy)
    # ⚠️ الكود القديم الخطير: r'\{.*\}'
    # ✅ الكود الجديد الآمن:
    JSON_SIMPLE = get_safe_pattern(
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    )
    
    # Arabic text
    ARABIC = get_safe_pattern(
        r'[\u0600-\u06FF]+'
    )
    
    # Numbers (including decimals)
    NUMBER = get_safe_pattern(
        r'^-?\d+(?:\.\d+)?$'
    )
    
    # Alphanumeric with underscores
    ALPHANUM_UNDERSCORE = get_safe_pattern(
        r'^[a-zA-Z0-9_]+$'
    )
    
    # Invoice number patterns
    INVOICE_NUMBER = get_safe_pattern(
        r'^[A-Z]{2,4}-?\d{4,10}$',
        re.IGNORECASE
    )


# ═══════════════════════════════════════════════════
# JSON Extraction (Safe Version)
# ═══════════════════════════════════════════════════

def extract_json_safe(text: str, timeout: int = 2) -> Optional[str]:
    """
    استخراج JSON من نص بشكل آمن
    بديل آمن للكود الخطير: re.search(r'\{.*\}', text, re.DOTALL)
    
    Args:
        text: النص المحتوي على JSON
        timeout: الحد الأقصى بالثواني
    
    Returns:
        JSON string أو None
    """
    try:
        # طريقة آمنة: البحث عن { و } المتطابقة
        stack = []
        start_idx = None
        
        with time_limit(timeout):
            for i, char in enumerate(text):
                if char == '{':
                    if not stack:
                        start_idx = i
                    stack.append(char)
                
                elif char == '}':
                    if stack:
                        stack.pop()
                        
                        # إذا أصبح stack فارغاً، وجدنا JSON كامل
                        if not stack and start_idx is not None:
                            json_str = text[start_idx:i+1]
                            return json_str
        
        return None
    
    except TimeoutException:
        app_logger.error("JSON extraction timed out")
        return None
    
    except Exception as e:
        app_logger.error(f"JSON extraction failed: {str(e)}")
        return None


# ═══════════════════════════════════════════════════
# Pattern Validation (للتحقق من أمان Patterns)
# ═══════════════════════════════════════════════════

def is_safe_pattern(pattern: str) -> bool:
    """
    التحقق من أن Pattern آمن (لا يحتوي على أنماط خطرة)
    
    Args:
        pattern: النمط المراد فحصه
    
    Returns:
        True إذا كان آمناً
    """
    # أنماط خطرة معروفة
    dangerous_patterns = [
        r'.*.*',           # Nested quantifiers
        r'.+.+',           # Nested quantifiers
        r'(.*)+',          # Nested quantifiers with groups
        r'(.+)+',          # Nested quantifiers with groups
        r'(a|a)+',         # Overlapping alternatives
        r'(a*)*',          # Nested star quantifiers
        r'(a+)+',          # Nested plus quantifiers
    ]
    
    # فحص الأنماط الخطرة
    for dangerous in dangerous_patterns:
        if dangerous in pattern:
            app_logger.warning(f"Potentially dangerous regex pattern detected: {pattern}")
            return False
    
    # فحص عدد الـ quantifiers
    quantifier_count = pattern.count('*') + pattern.count('+') + pattern.count('{')
    
    if quantifier_count > 10:
        app_logger.warning(f"Pattern has too many quantifiers: {quantifier_count}")
        return False
    
    return True


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'safe_re_search',
    'safe_re_match',
    'safe_re_findall',
    'safe_re_sub',
    'get_safe_pattern',
    'SafePatterns',
    'extract_json_safe',
    'is_safe_pattern',
]