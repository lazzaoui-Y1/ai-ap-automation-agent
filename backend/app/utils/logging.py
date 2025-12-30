"""
backend/app/utils/logging.py
نظام Logging متقدم لتتبع جميع العمليات
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import json


# ═══════════════════════════════════════════════════
# Colors for Console Output
# ═══════════════════════════════════════════════════

class LogColors:
    """ألوان للـ Console"""
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"


# ═══════════════════════════════════════════════════
# Custom Formatter
# ═══════════════════════════════════════════════════

class ColoredFormatter(logging.Formatter):
    """Formatter مع ألوان للـ Console"""
    
    COLORS = {
        'DEBUG': LogColors.CYAN,
        'INFO': LogColors.GREEN,
        'WARNING': LogColors.YELLOW,
        'ERROR': LogColors.RED,
        'CRITICAL': LogColors.RED + LogColors.BOLD,
    }
    
    def format(self, record):
        log_color = self.COLORS.get(record.levelname, LogColors.WHITE)
        record.levelname = f"{log_color}{record.levelname}{LogColors.RESET}"
        record.msg = f"{log_color}{record.msg}{LogColors.RESET}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Formatter لحفظ اللوجات بصيغة JSON"""
    
    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # إضافة بيانات إضافية إذا كانت موجودة
        customer_id = getattr(record, "customer_id", None)
        if customer_id is not None:
            log_data["customer_id"] = customer_id
        
        invoice_number = getattr(record, "invoice_number", None)
        if invoice_number:
            log_data["invoice_number"] = invoice_number
        
        processing_time = getattr(record, "processing_time", None)
        if processing_time:
            log_data["processing_time"] = processing_time
        
        error_code = getattr(record, "error_code", None)
        if error_code:
            log_data["error_code"] = error_code
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


# ═══════════════════════════════════════════════════
# Logger Setup
# ═══════════════════════════════════════════════════

def setup_logger(
    name: str = "invoice_ai",
    log_level: str = "INFO",
    log_file: Optional[str] = None,
    log_dir: str = "./logs",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    json_format: bool = False,
    customer_id: Optional[str] = None
) -> logging.Logger:
    """
    إعداد Logger مخصص
    
    Args:
        name: اسم الـ Logger
        log_level: مستوى اللوج (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: اسم ملف اللوج (اختياري)
        log_dir: مجلد اللوجات
        max_bytes: الحد الأقصى لحجم الملف قبل التدوير
        backup_count: عدد الملفات الاحتياطية
        json_format: حفظ اللوجات بصيغة JSON
        customer_id: معرف العميل (لإنشاء ملف خاص)
    """
    
    # إنشاء Logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # تجنب تكرار الـ Handlers
    if logger.handlers:
        return logger
    
    # ═══════════════════════════════════════════════════
    # Console Handler
    # ═══════════════════════════════════════════════════
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    
    console_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    console_formatter = ColoredFormatter(
        console_format,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # ═══════════════════════════════════════════════════
    # File Handler
    # ═══════════════════════════════════════════════════
    if log_file or customer_id:
        # إنشاء مجلد اللوجات
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # تحديد اسم الملف
        if customer_id:
            log_file = f"{customer_id}_{datetime.now().strftime('%Y%m')}.log"
        elif not log_file:
            log_file = f"app_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_path = log_path / log_file
        
        # Rotating File Handler
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # اختيار الـ Formatter
        if json_format:
            file_formatter = JSONFormatter()
        else:
            file_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s"
            file_formatter = logging.Formatter(
                file_format,
                datefmt="%Y-%m-%d %H:%M:%S"
            )
        
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


# ═══════════════════════════════════════════════════
# Customer-Specific Logger
# ═══════════════════════════════════════════════════

def get_customer_logger(customer_id: str, log_level: str = "INFO") -> logging.Logger:
    """
    الحصول على Logger خاص بعميل معين
    كل عميل له ملف لوج خاص به
    """
    logger_name = f"customer.{customer_id}"
    log_dir = f"./customers/{customer_id}/data/logs"
    
    return setup_logger(
        name=logger_name,
        log_level=log_level,
        log_dir=log_dir,
        customer_id=customer_id,
        json_format=True  # JSON للعملاء للتحليل السهل
    )


# ═══════════════════════════════════════════════════
# Logging Helpers
# ═══════════════════════════════════════════════════

def log_invoice_processing(
    logger: logging.Logger,
    invoice_number: str,
    customer_id: str,
    status: str,
    processing_time: Optional[float] = None,
    error_message: Optional[str] = None
):
    """
    تسجيل معالجة فاتورة
    """
    log_data = {
        'customer_id': customer_id,
        'invoice_number': invoice_number,
        'status': status
    }
    
    if processing_time:
        log_data['processing_time'] = f"{processing_time:.2f}s"
    
    message = f"Invoice {invoice_number} | Customer: {customer_id} | Status: {status}"
    
    if processing_time:
        message += f" | Time: {processing_time:.2f}s"
    
    if status == "success":
        logger.info(message, extra=log_data)
    elif status == "failed":
        if error_message:
            message += f" | Error: {error_message}"
            log_data['error'] = error_message
        logger.error(message, extra=log_data)
    else:
        logger.warning(message, extra=log_data)


def log_erp_operation(
    logger: logging.Logger,
    customer_id: str,
    erp_system: str,
    operation: str,
    status: str,
    details: Optional[dict] = None
):
    """
    تسجيل عملية ERP
    """
    message = f"ERP Operation | Customer: {customer_id} | System: {erp_system} | Operation: {operation} | Status: {status}"
    
    log_data = {
        'customer_id': customer_id,
        'erp_system': erp_system,
        'operation': operation,
        'status': status
    }
    
    if details:
        log_data.update(details)
        message += f" | Details: {details}"
    
    if status == "success":
        logger.info(message, extra=log_data)
    else:
        logger.error(message, extra=log_data)


def log_llm_request(
    logger: logging.Logger,
    model: str,
    tokens_used: Optional[int] = None,
    response_time: Optional[float] = None,
    success: bool = True
):
    """
    تسجيل طلب LLM
    """
    message = f"LLM Request | Model: {model}"
    
    log_data = {'model': model, 'success': success}
    
    if tokens_used:
        message += f" | Tokens: {tokens_used}"
        log_data['tokens_used'] = tokens_used
    
    if response_time:
        message += f" | Time: {response_time:.2f}s"
        log_data['response_time'] = response_time
    
    if success:
        logger.info(message, extra=log_data)
    else:
        logger.error(message, extra=log_data)


# ═══════════════════════════════════════════════════
# Application Logger (Default)
# ═══════════════════════════════════════════════════

app_logger = setup_logger(
    name="invoice_ai",
    log_level="INFO",
    log_file="app.log",
    log_dir="./logs"
)


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'setup_logger',
    'get_customer_logger',
    'log_invoice_processing',
    'log_erp_operation',
    'log_llm_request',
    'app_logger'
]