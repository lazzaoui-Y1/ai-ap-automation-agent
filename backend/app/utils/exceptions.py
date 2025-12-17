"""
backend/app/utils/exceptions.py
جميع الاستثناءات المخصصة للنظام
"""

from typing import Optional, Dict, Any


class InvoiceAIException(Exception):
    """الاستثناء الأساسي لجميع أخطاء النظام"""
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_code = error_code or "GENERAL_ERROR"
        self.details = details or {}
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """تحويل الخطأ إلى قاموس للـ API Response"""
        return {
            "error": self.error_code,
            "message": self.message,
            "details": self.details
        }


# ═══════════════════════════════════════════════════
# File & OCR Exceptions
# ═══════════════════════════════════════════════════

class FileProcessingError(InvoiceAIException):
    """خطأ في معالجة الملف"""
    def __init__(self, message: str, filename: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="FILE_PROCESSING_ERROR",
            details={"filename": filename}
        )


class UnsupportedFileTypeError(InvoiceAIException):
    """نوع ملف غير مدعوم"""
    def __init__(self, file_type: str, supported_types: list):
        super().__init__(
            message=f"File type '{file_type}' is not supported",
            error_code="UNSUPPORTED_FILE_TYPE",
            details={
                "file_type": file_type,
                "supported_types": supported_types
            }
        )


class OCRError(InvoiceAIException):
    """خطأ في عملية OCR"""
    def __init__(self, message: str, image_path: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="OCR_ERROR",
            details={"image_path": image_path}
        )


class EmptyFileError(InvoiceAIException):
    """ملف فارغ"""
    def __init__(self, filename: str):
        super().__init__(
            message=f"File '{filename}' is empty or contains no readable content",
            error_code="EMPTY_FILE",
            details={"filename": filename}
        )


# ═══════════════════════════════════════════════════
# LLM & Extraction Exceptions
# ═══════════════════════════════════════════════════

class LLMExtractionError(InvoiceAIException):
    """خطأ في استخراج البيانات من LLM"""
    def __init__(self, message: str, model: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="LLM_EXTRACTION_ERROR",
            details={"model": model}
        )


class LLMTimeoutError(InvoiceAIException):
    """انتهت مهلة LLM"""
    def __init__(self, timeout_seconds: int):
        super().__init__(
            message=f"LLM request timed out after {timeout_seconds} seconds",
            error_code="LLM_TIMEOUT",
            details={"timeout_seconds": timeout_seconds}
        )


class LLMRateLimitError(InvoiceAIException):
    """تجاوز حد معدل الطلبات لـ LLM"""
    def __init__(self, retry_after: Optional[int] = None):
        super().__init__(
            message="LLM rate limit exceeded",
            error_code="LLM_RATE_LIMIT",
            details={"retry_after_seconds": retry_after}
        )


class ValidationError(InvoiceAIException):
    """خطأ في التحقق من صحة البيانات المستخرجة"""
    def __init__(self, message: str, field: Optional[str] = None, validation_errors: Optional[list] = None):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            details={
                "field": field,
                "validation_errors": validation_errors or []
            }
        )


class LowConfidenceError(InvoiceAIException):
    """درجة ثقة منخفضة في الاستخراج"""
    def __init__(self, confidence_score: float, threshold: float):
        super().__init__(
            message=f"Extraction confidence ({confidence_score:.2f}) below threshold ({threshold:.2f})",
            error_code="LOW_CONFIDENCE",
            details={
                "confidence_score": confidence_score,
                "threshold": threshold
            }
        )


# ═══════════════════════════════════════════════════
# ERP Connector Exceptions
# ═══════════════════════════════════════════════════

class ERPConnectionError(InvoiceAIException):
    """خطأ في الاتصال بنظام ERP"""
    def __init__(self, message: str, erp_system: str):
        super().__init__(
            message=message,
            error_code="ERP_CONNECTION_ERROR",
            details={"erp_system": erp_system}
        )


class ERPAuthenticationError(InvoiceAIException):
    """خطأ في المصادقة مع نظام ERP"""
    def __init__(self, erp_system: str):
        super().__init__(
            message=f"Authentication failed for {erp_system}",
            error_code="ERP_AUTH_ERROR",
            details={"erp_system": erp_system}
        )


class ERPDataFormatError(InvoiceAIException):
    """خطأ في صيغة البيانات المرسلة لـ ERP"""
    def __init__(self, message: str, expected_format: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="ERP_DATA_FORMAT_ERROR",
            details={"expected_format": expected_format}
        )


class ERPTimeoutError(InvoiceAIException):
    """انتهت مهلة الاتصال بـ ERP"""
    def __init__(self, erp_system: str, timeout_seconds: int):
        super().__init__(
            message=f"Connection to {erp_system} timed out after {timeout_seconds} seconds",
            error_code="ERP_TIMEOUT",
            details={
                "erp_system": erp_system,
                "timeout_seconds": timeout_seconds
            }
        )


class DuplicateInvoiceError(InvoiceAIException):
    """فاتورة مكررة"""
    def __init__(self, invoice_number: str, existing_id: Optional[str] = None):
        super().__init__(
            message=f"Invoice '{invoice_number}' already exists",
            error_code="DUPLICATE_INVOICE",
            details={
                "invoice_number": invoice_number,
                "existing_id": existing_id
            }
        )


# ═══════════════════════════════════════════════════
# Customer & Configuration Exceptions
# ═══════════════════════════════════════════════════

class CustomerNotFoundError(InvoiceAIException):
    """عميل غير موجود"""
    def __init__(self, customer_id: str):
        super().__init__(
            message=f"Customer '{customer_id}' not found",
            error_code="CUSTOMER_NOT_FOUND",
            details={"customer_id": customer_id}
        )


class ConfigurationError(InvoiceAIException):
    """خطأ في الإعدادات"""
    def __init__(self, message: str, config_file: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="CONFIGURATION_ERROR",
            details={"config_file": config_file}
        )


class VendorMappingError(InvoiceAIException):
    """خطأ في ربط المورد"""
    def __init__(self, vendor_name: str, customer_id: str):
        super().__init__(
            message=f"Vendor '{vendor_name}' not found in mapping for customer '{customer_id}'",
            error_code="VENDOR_MAPPING_ERROR",
            details={
                "vendor_name": vendor_name,
                "customer_id": customer_id
            }
        )


# ═══════════════════════════════════════════════════
# Security Exceptions
# ═══════════════════════════════════════════════════

class AuthenticationError(InvoiceAIException):
    """خطأ في المصادقة"""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            error_code="AUTHENTICATION_ERROR"
        )


class AuthorizationError(InvoiceAIException):
    """خطأ في الصلاحيات"""
    def __init__(self, message: str = "Insufficient permissions", required_permission: Optional[str] = None):
        super().__init__(
            message=message,
            error_code="AUTHORIZATION_ERROR",
            details={"required_permission": required_permission}
        )


# ═══════════════════════════════════════════════════
# Retry Logic
# ═══════════════════════════════════════════════════

class MaxRetriesExceededError(InvoiceAIException):
    """تجاوز الحد الأقصى من المحاولات"""
    def __init__(self, operation: str, max_retries: int):
        super().__init__(
            message=f"Operation '{operation}' failed after {max_retries} retries",
            error_code="MAX_RETRIES_EXCEEDED",
            details={
                "operation": operation,
                "max_retries": max_retries
            }
        )


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def handle_exception(exception: Exception) -> Dict[str, Any]:
    """
    معالج مركزي للاستثناءات - يحول أي استثناء إلى استجابة API موحدة
    """
    if isinstance(exception, InvoiceAIException):
        return exception.to_dict()
    
    # استثناءات Python العامة
    return {
        "error": "INTERNAL_ERROR",
        "message": str(exception),
        "details": {
            "exception_type": type(exception).__name__
        }
    }