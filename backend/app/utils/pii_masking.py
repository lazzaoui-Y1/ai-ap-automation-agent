"""
backend/app/utils/pii_masking.py
حماية البيانات الشخصية (PII) في اللوجات - GDPR Compliant
"""

import re
import hashlib
from typing import Any, Dict, List, Optional
from decimal import Decimal
from datetime import date, datetime

from .regex_safe import SafePatterns, safe_re_sub
from .logging import app_logger


# ═══════════════════════════════════════════════════
# PII Categories
# ═══════════════════════════════════════════════════

class PIICategory:
    """فئات البيانات الشخصية"""
    EMAIL = "email"
    PHONE = "phone"
    TAX_ID = "tax_id"
    CREDIT_CARD = "credit_card"
    IBAN = "iban"
    NAME = "name"
    ADDRESS = "address"
    INVOICE_NUMBER = "invoice_number"
    CUSTOMER_ID = "customer_id"


# ═══════════════════════════════════════════════════
# Masking Strategies
# ═══════════════════════════════════════════════════

def mask_email(email: str) -> str:
    """
    إخفاء البريد الإلكتروني
    
    Example:
        user@example.com -> u***@e***.com
    """
    if '@' not in email:
        return "***@***.***"
    
    local, domain = email.split('@', 1)
    
    # إخفاء local part
    if len(local) <= 2:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***' + local[-1]
    
    # إخفاء domain
    if '.' in domain:
        domain_parts = domain.split('.')
        masked_domain = domain_parts[0][0] + '***.' + domain_parts[-1]
    else:
        masked_domain = domain[0] + '***'
    
    return f"{masked_local}@{masked_domain}"


def mask_phone(phone: str) -> str:
    """
    إخفاء رقم الهاتف
    
    Example:
        +966501234567 -> +966******567
        0501234567 -> 050****567
    """
    # إزالة المسافات والشرطات
    clean_phone = re.sub(r'[\s\-()]', '', phone)
    
    if len(clean_phone) < 6:
        return "***"
    
    # الاحتفاظ بأول 3 وآخر 3 أرقام
    prefix = clean_phone[:3]
    suffix = clean_phone[-3:]
    
    return f"{prefix}{'*' * (len(clean_phone) - 6)}{suffix}"


def mask_tax_id(tax_id: str) -> str:
    """
    إخفاء الرقم الضريبي
    
    Example:
        300123456789003 -> 300***********003
    """
    if len(tax_id) < 6:
        return "***"
    
    return tax_id[:3] + '*' * (len(tax_id) - 6) + tax_id[-3:]


def mask_credit_card(card_number: str) -> str:
    """
    إخفاء رقم بطاقة الائتمان
    
    Example:
        4532123456789012 -> 4532********9012
    """
    clean_card = re.sub(r'[\s\-]', '', card_number)
    
    if len(clean_card) < 8:
        return "****"
    
    return clean_card[:4] + '*' * (len(clean_card) - 8) + clean_card[-4:]


def mask_iban(iban: str) -> str:
    """
    إخفاء IBAN
    
    Example:
        SA0380000000608010167519 -> SA03****************7519
    """
    if len(iban) < 8:
        return "****"
    
    return iban[:4] + '*' * (len(iban) - 8) + iban[-4:]


def mask_name(name: str) -> str:
    """
    إخفاء الاسم
    
    Example:
        John Smith -> J*** S***
        أحمد محمد -> أ*** م***
    """
    words = name.split()
    
    masked_words = []
    for word in words:
        if len(word) <= 2:
            masked_words.append(word[0] + '*')
        else:
            masked_words.append(word[0] + '***')
    
    return ' '.join(masked_words)


def hash_pii(value: str, salt: str = "") -> str:
    """
    Hash البيانات الشخصية (لا يمكن عكسها)
    
    Args:
        value: القيمة المراد hash-ها
        salt: ملح إضافي
    
    Returns:
        SHA256 hash
    """
    combined = f"{value}{salt}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════
# Auto Detection & Masking
# ═══════════════════════════════════════════════════

def auto_mask_text(text: str) -> str:
    """
    إخفاء تلقائي للبيانات الشخصية في النص
    
    Args:
        text: النص المحتوي على بيانات شخصية محتملة
    
    Returns:
        نص مع إخفاء البيانات
    """
    if not text:
        return text
    
    # 1. إخفاء Emails
    text = safe_re_sub(
        SafePatterns.EMAIL,
        lambda m: mask_email(m.group(0)),
        text,
        timeout=1
    )
    
    # 2. إخفاء أرقام الهواتف (نمط عام)
    phone_pattern = r'\+?\d{10,15}'
    text = safe_re_sub(
        phone_pattern,
        lambda m: mask_phone(m.group(0)),
        text,
        timeout=1
    )
    
    # 3. إخفاء أرقام البطاقات (16 رقم)
    card_pattern = r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'
    text = safe_re_sub(
        card_pattern,
        lambda m: mask_credit_card(m.group(0)),
        text,
        timeout=1
    )
    
    # 4. إخفاء IBAN
    iban_pattern = r'\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b'
    text = safe_re_sub(
        iban_pattern,
        lambda m: mask_iban(m.group(0)),
        text,
        timeout=1
    )
    
    return text


# ═══════════════════════════════════════════════════
# Structured Data Masking
# ═══════════════════════════════════════════════════

def mask_dict(
    data: Dict[str, Any],
    sensitive_fields: Optional[List[str]] = None,
    mask_strategy: str = "partial"
) -> Dict[str, Any]:
    """
    إخفاء البيانات الحساسة في قاموس
    
    Args:
        data: القاموس المحتوي على بيانات
        sensitive_fields: قائمة الحقول الحساسة
        mask_strategy: "partial", "hash", "remove"
    
    Returns:
        قاموس مع بيانات مخفية
    """
    if sensitive_fields is None:
        # الحقول الحساسة الافتراضية
        sensitive_fields = [
            'email', 'phone', 'tax_id', 'vat_id', 'vat_number',
            'credit_card', 'card_number', 'iban', 'swift',
            'password', 'secret', 'token', 'api_key',
            'ssn', 'national_id', 'passport',
            'customer_name', 'vendor_name', 'name'
        ]
    
    masked = data.copy()
    
    for key, value in data.items():
        # فحص إذا كان الحقل حساس
        is_sensitive = any(
            sensitive.lower() in key.lower()
            for sensitive in sensitive_fields
        )
        
        if is_sensitive and value:
            if mask_strategy == "remove":
                masked[key] = "[REDACTED]"
            
            elif mask_strategy == "hash":
                if isinstance(value, str):
                    masked[key] = hash_pii(value)
            
            else:  # partial masking
                if isinstance(value, str):
                    # تحديد نوع البيانات وإخفاء مناسب
                    if '@' in value:
                        masked[key] = mask_email(value)
                    elif 'phone' in key.lower() or 'tel' in key.lower():
                        masked[key] = mask_phone(value)
                    elif 'tax' in key.lower() or 'vat' in key.lower():
                        masked[key] = mask_tax_id(value)
                    elif 'card' in key.lower():
                        masked[key] = mask_credit_card(value)
                    elif 'iban' in key.lower():
                        masked[key] = mask_iban(value)
                    elif 'name' in key.lower():
                        masked[key] = mask_name(value)
                    else:
                        # إخفاء عام
                        if len(value) > 4:
                            masked[key] = value[:2] + '***' + value[-2:]
                        else:
                            masked[key] = '***'
        
        # معالجة القواميس المتداخلة
        elif isinstance(value, dict):
            masked[key] = mask_dict(value, sensitive_fields, mask_strategy)
        
        # معالجة القوائم
        elif isinstance(value, list):
            masked[key] = [
                mask_dict(item, sensitive_fields, mask_strategy)
                if isinstance(item, dict)
                else item
                for item in value
            ]
    
    return masked


# ═══════════════════════════════════════════════════
# Invoice-Specific Masking
# ═══════════════════════════════════════════════════

def mask_invoice_for_logging(invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    إخفاء بيانات الفاتورة الحساسة للوجينج
    
    Args:
        invoice_data: بيانات الفاتورة
    
    Returns:
        بيانات آمنة للوجينج
    """
    safe_data = {
        # معلومات آمنة (يمكن تسجيلها)
        'invoice_number': invoice_data.get('invoice_number'),
        'invoice_date': str(invoice_data.get('invoice_date')),
        'currency': invoice_data.get('currency'),
        'language_detected': invoice_data.get('language_detected'),
        
        # مبالغ مالية (آمنة)
        'subtotal': float(invoice_data.get('subtotal', 0)) if invoice_data.get('subtotal') else None,
        'total_tax': float(invoice_data.get('total_tax', 0)) if invoice_data.get('total_tax') else None,
        'total_amount': float(invoice_data.get('total_amount', 0)) if invoice_data.get('total_amount') else None,
        
        # عدد البنود (آمن)
        'line_items_count': len(invoice_data.get('line_items', [])),
        
        # معلومات المورد (مخفية)
        'vendor': {
            'name': mask_name(invoice_data.get('vendor', {}).get('name', '')) if invoice_data.get('vendor', {}).get('name') else None,
            'tax_id': mask_tax_id(invoice_data.get('vendor', {}).get('tax_id', '')) if invoice_data.get('vendor', {}).get('tax_id') else None,
            'has_contact': bool(
                invoice_data.get('vendor', {}).get('phone') or 
                invoice_data.get('vendor', {}).get('email')
            )
        } if invoice_data.get('vendor') else None,
        
        # Metadata
        'confidence_score': invoice_data.get('confidence_score'),
        'source_file': invoice_data.get('source_file'),
    }
    
    return safe_data


# ═══════════════════════════════════════════════════
# GDPR-Compliant Logging
# ═══════════════════════════════════════════════════

class PIIFilter:
    """
    Logging filter لإخفاء PII تلقائياً
    
    Usage:
        import logging
        logger = logging.getLogger("app")
        logger.addFilter(PIIFilter())
    """
    
    def __init__(self, mask_strategy: str = "partial"):
        self.mask_strategy = mask_strategy
    
    def filter(self, record):
        """
        تطبيق إخفاء على سجل اللوج
        """
        # إخفاء الرسالة
        if isinstance(record.msg, str):
            record.msg = auto_mask_text(record.msg)
        
        # إخفاء args
        if record.args:
            masked_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    masked_args.append(auto_mask_text(arg))
                elif isinstance(arg, dict):
                    masked_args.append(mask_dict(arg, mask_strategy=self.mask_strategy))
                else:
                    masked_args.append(arg)
            record.args = tuple(masked_args)
        
        return True


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'mask_email',
    'mask_phone',
    'mask_tax_id',
    'mask_credit_card',
    'mask_iban',
    'mask_name',
    'hash_pii',
    'auto_mask_text',
    'mask_dict',
    'mask_invoice_for_logging',
    'PIIFilter',
    'PIICategory',
]