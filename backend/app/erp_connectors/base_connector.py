"""
backend/app/erp_connectors/base_connector.py
الواجهة الأساسية لجميع موصلات ERP
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from enum import Enum
from datetime import datetime
from pathlib import Path

from ..schemas.invoice_schema import Invoice
from ..utils.exceptions import (
    ERPConnectionError,
    ERPAuthenticationError,
    ERPDataFormatError,
    DuplicateInvoiceError
)
from ..utils.logging import app_logger, log_erp_operation


# ═══════════════════════════════════════════════════
# Connector Status & Types
# ═══════════════════════════════════════════════════

class ConnectorStatus(str, Enum):
    """حالة الموصل"""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    AUTHENTICATING = "authenticating"


class ConnectorType(str, Enum):
    """أنواع الموصلات"""
    EXCEL = "excel"
    CSV = "csv"
    SAP_SFTP_XML = "sap_sftp_xml"
    ORACLE_REST = "oracle_rest_api"
    ODOO_XMLRPC = "odoo_xmlrpc"
    WEBHOOK = "webhook"
    MOCK = "mock"


# ═══════════════════════════════════════════════════
# Base Connector Abstract Class
# ═══════════════════════════════════════════════════

class BaseERPConnector(ABC):
    """
    الواجهة الأساسية لجميع موصلات ERP
    
    كل موصل يجب أن يرث من هذا الكلاس ويطبق الدوال المطلوبة
    """
    
    def __init__(
        self,
        customer_id: str,
        config: Dict[str, Any],
        connector_type: ConnectorType
    ):
        """
        Args:
            customer_id: معرف العميل
            config: إعدادات الموصل من config.yaml
            connector_type: نوع الموصل
        """
        self.customer_id = customer_id
        self.config = config
        self.connector_type = connector_type
        self.status = ConnectorStatus.DISCONNECTED
        self.logger = app_logger
        
        # Metadata
        self.last_sync = None
        self.total_synced = 0
        self.error_count = 0
        self.last_error = None
    
    # ═══════════════════════════════════════════════════
    # Abstract Methods (يجب تطبيقها في كل موصل)
    # ═══════════════════════════════════════════════════
    
    @abstractmethod
    def connect(self) -> bool:
        """
        الاتصال بنظام ERP
        
        Returns:
            True إذا نجح الاتصال
        
        Raises:
            ERPConnectionError: إذا فشل الاتصال
            ERPAuthenticationError: إذا فشلت المصادقة
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        قطع الاتصال بنظام ERP
        
        Returns:
            True إذا نجح قطع الاتصال
        """
        pass
    
    @abstractmethod
    def send_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        """
        إرسال فاتورة إلى نظام ERP
        
        Args:
            invoice: بيانات الفاتورة
        
        Returns:
            نتيجة الإرسال مع معلومات إضافية
            {
                "success": bool,
                "erp_id": str,  # معرف الفاتورة في ERP
                "message": str,
                "details": dict
            }
        
        Raises:
            ERPDataFormatError: إذا كانت البيانات غير صحيحة
            DuplicateInvoiceError: إذا كانت الفاتورة موجودة مسبقاً
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """
        اختبار الاتصال بنظام ERP
        
        Returns:
            True إذا كان الاتصال يعمل
        """
        pass
    
    # ═══════════════════════════════════════════════════
    # Optional Methods (اختيارية حسب نوع الموصل)
    # ═══════════════════════════════════════════════════
    
    def get_invoice_status(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """
        الحصول على حالة فاتورة من ERP
        
        Args:
            erp_id: معرف الفاتورة في ERP
        
        Returns:
            معلومات حالة الفاتورة أو None
        """
        self.logger.warning(
            f"{self.connector_type.value} does not support get_invoice_status"
        )
        return None
    
    def update_invoice(
        self,
        erp_id: str,
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        تحديث فاتورة في ERP
        
        Args:
            erp_id: معرف الفاتورة في ERP
            updates: التحديثات المطلوبة
        
        Returns:
            نتيجة التحديث
        """
        self.logger.warning(
            f"{self.connector_type.value} does not support update_invoice"
        )
        return {"success": False, "message": "Not supported"}
    
    def delete_invoice(self, erp_id: str) -> bool:
        """
        حذف فاتورة من ERP
        
        Args:
            erp_id: معرف الفاتورة في ERP
        
        Returns:
            True إذا نجح الحذف
        """
        self.logger.warning(
            f"{self.connector_type.value} does not support delete_invoice"
        )
        return False
    
    def batch_send_invoices(
        self,
        invoices: List[Invoice]
    ) -> List[Dict[str, Any]]:
        """
        إرسال عدة فواتير دفعة واحدة
        
        Args:
            invoices: قائمة الفواتير
        
        Returns:
            قائمة النتائج
        """
        results = []
        
        for invoice in invoices:
            try:
                result = self.send_invoice(invoice)
                results.append(result)
            except Exception as e:
                results.append({
                    "success": False,
                    "invoice_number": invoice.invoice_number,
                    "error": str(e)
                })
        
        return results
    
    # ═══════════════════════════════════════════════════
    # Utility Methods
    # ═══════════════════════════════════════════════════
    
    def get_status(self) -> Dict[str, Any]:
        """الحصول على حالة الموصل"""
        return {
            "connector_type": self.connector_type.value,
            "customer_id": self.customer_id,
            "status": self.status.value,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "total_synced": self.total_synced,
            "error_count": self.error_count,
            "last_error": self.last_error
        }
    
    def _log_operation(
        self,
        operation: str,
        status: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """تسجيل عملية ERP"""
        log_erp_operation(
            self.logger,
            customer_id=self.customer_id,
            erp_system=self.connector_type.value,
            operation=operation,
            status=status,
            details=details
        )
    
    def _update_sync_stats(self, success: bool):
        """تحديث إحصائيات المزامنة"""
        self.last_sync = datetime.now()
        
        if success:
            self.total_synced += 1
        else:
            self.error_count += 1
    
    def _validate_invoice_data(self, invoice: Invoice) -> bool:
        """
        التحقق من صحة بيانات الفاتورة قبل الإرسال
        
        Returns:
            True إذا كانت البيانات صحيحة
        
        Raises:
            ERPDataFormatError: إذا كانت البيانات غير صحيحة
        """
        # التحقق من الحقول المطلوبة
        required_fields = [
            ('invoice_number', invoice.invoice_number),
            ('invoice_date', invoice.invoice_date),
            ('vendor.name', invoice.vendor.name if invoice.vendor else None),
            ('total_amount', invoice.total_amount),
        ]
        
        missing_fields = []
        for field_name, field_value in required_fields:
            if not field_value:
                missing_fields.append(field_name)
        
        if missing_fields:
            raise ERPDataFormatError(
                f"Missing required fields: {', '.join(missing_fields)}"
            )
        
        # التحقق من وجود بنود
        if not invoice.line_items or len(invoice.line_items) == 0:
            raise ERPDataFormatError("Invoice must have at least one line item")
        
        return True
    
    def _check_duplicate(self, invoice_number: str) -> bool:
        """
        التحقق من عدم وجود فاتورة مكررة
        يجب تطبيقها في الموصلات التي تدعم ذلك
        
        Returns:
            True إذا كانت الفاتورة موجودة مسبقاً
        """
        # Default implementation - يمكن override في الموصلات
        return False
    
    # ═══════════════════════════════════════════════════
    # Context Manager Support
    # ═══════════════════════════════════════════════════
    
    def __enter__(self):
        """دعم with statement"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """دعم with statement"""
        self.disconnect()
        return False
    
    # ═══════════════════════════════════════════════════
    # String Representation
    # ═══════════════════════════════════════════════════
    
    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            f"customer={self.customer_id} "
            f"type={self.connector_type.value} "
            f"status={self.status.value}>"
        )


# ═══════════════════════════════════════════════════
# Connector Factory
# ═══════════════════════════════════════════════════

class ConnectorFactory:
    """
    مصنع لإنشاء الموصلات حسب النوع
    """
    
    _connectors = {}
    
    @classmethod
    def register(cls, connector_type: ConnectorType, connector_class):
        """تسجيل موصل جديد"""
        cls._connectors[connector_type] = connector_class
    
    @classmethod
    def create(
        cls,
        connector_type: ConnectorType,
        customer_id: str,
        config: Dict[str, Any]
    ) -> BaseERPConnector:
        """
        إنشاء موصل
        
        Args:
            connector_type: نوع الموصل
            customer_id: معرف العميل
            config: إعدادات الموصل
        
        Returns:
            instance من الموصل المطلوب
        
        Raises:
            ValueError: إذا كان النوع غير مسجل
        """
        connector_class = cls._connectors.get(connector_type)
        
        if not connector_class:
            raise ValueError(
                f"Connector type '{connector_type.value}' is not registered. "
                f"Available types: {list(cls._connectors.keys())}"
            )
        
        return connector_class(
            customer_id=customer_id,
            config=config,
            connector_type=connector_type
        )
    
    @classmethod
    def get_available_connectors(cls) -> List[str]:
        """الحصول على قائمة الموصلات المتاحة"""
        return [ct.value for ct in cls._connectors.keys()]


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'BaseERPConnector',
    'ConnectorFactory',
    'ConnectorStatus',
    'ConnectorType',
]