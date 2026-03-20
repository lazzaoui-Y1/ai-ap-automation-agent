"""
backend/app/erp_connectors/mock_connector.py
موصل تجريبي للاختبار - لا يرسل البيانات فعلياً
"""

from typing import Dict, Any, List
from datetime import datetime
import time
import random

from .base_connector import BaseERPConnector, ConnectorType, ConnectorStatus, ConnectorFactory
from ..schemas.invoice_schema import Invoice
from ..utils.exceptions import ERPConnectionError


class MockConnector(BaseERPConnector):
    """
    موصل تجريبي - يحاكي عمل ERP بدون إرسال حقيقي
    
    مفيد للـ:
    - الاختبار والتطوير
    - Demo
    - التدريب
    
    الإعدادات المتاحة في config:
        simulate_delay: محاكاة تأخير (ثواني، افتراضي: 0.5)
        failure_rate: نسبة الفشل للاختبار (0-1، افتراضي: 0)
        store_in_memory: حفظ في الذاكرة (افتراضي: True)
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any], connector_type: ConnectorType):
        super().__init__(customer_id, config, connector_type)
        
        # الإعدادات
        self.simulate_delay = config.get('simulate_delay', 0.5)
        self.failure_rate = config.get('failure_rate', 0.0)
        self.store_in_memory = config.get('store_in_memory', True)
        
        # تخزين في الذاكرة
        self.invoices = {}  # {invoice_number: invoice_data}
        self.connection_attempts = 0
        self.send_count = 0
    
    def connect(self) -> bool:
        """محاكاة الاتصال"""
        self.connection_attempts += 1
        
        # محاكاة تأخير
        time.sleep(min(self.simulate_delay, 2.0))
        
        # محاكاة فشل عشوائي
        if random.random() < self.failure_rate:
            self.status = ConnectorStatus.ERROR
            raise ERPConnectionError(
                "Mock connection failed (simulated error)",
                erp_system="mock"
            )
        
        self.status = ConnectorStatus.CONNECTED
        self._log_operation("connect", "success")
        self.logger.info("Mock connector connected (simulation)")
        
        return True
    
    def disconnect(self) -> bool:
        """محاكاة قطع الاتصال"""
        self.status = ConnectorStatus.DISCONNECTED
        self._log_operation("disconnect", "success")
        return True
    
    def send_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        """محاكاة إرسال فاتورة"""
        self.send_count += 1
        
        # محاكاة تأخير
        time.sleep(min(self.simulate_delay, 1.0))
        
        # التحقق من البيانات
        self._validate_invoice_data(invoice)
        
        # محاكاة فشل عشوائي
        if random.random() < self.failure_rate:
            self._update_sync_stats(success=False)
            self.last_error = "Simulated failure"
            
            return {
                "success": False,
                "erp_id": None,
                "message": "Mock send failed (simulated error)",
                "details": {"error": "Random failure for testing"}
            }
        
        # توليد ERP ID تجريبي
        erp_id = f"MOCK-ERP-{self.customer_id}-{self.send_count:06d}"
        
        # حفظ في الذاكرة
        if self.store_in_memory:
            self.invoices[invoice.invoice_number] = {
                "invoice": invoice.dict(),
                "erp_id": erp_id,
                "timestamp": datetime.now(),
                "status": "processed"
            }
        
        # تحديث الإحصائيات
        self._update_sync_stats(success=True)
        
        self._log_operation(
            "send_invoice",
            "success",
            {"invoice_number": invoice.invoice_number, "erp_id": erp_id}
        )
        
        self.logger.info(
            f"Mock: Invoice {invoice.invoice_number} 'sent' with ID {erp_id}"
        )
        
        return {
            "success": True,
            "erp_id": erp_id,
            "message": "Invoice sent successfully (mock)",
            "details": {
                "mock": True,
                "stored_in_memory": self.store_in_memory,
                "total_invoices": len(self.invoices)
            }
        }
    
    def test_connection(self) -> bool:
        """اختبار الاتصال"""
        try:
            # محاكاة سريعة
            original_delay = self.simulate_delay
            self.simulate_delay = 0.1
            
            result = self.connect()
            self.disconnect()
            
            self.simulate_delay = original_delay
            return result
        except:
            return False
    
    def get_invoice_status(self, erp_id: str) -> Dict[str, Any]:
        """الحصول على حالة فاتورة"""
        # البحث في الذاكرة
        for inv_num, inv_data in self.invoices.items():
            if inv_data['erp_id'] == erp_id:
                return {
                    "found": True,
                    "erp_id": erp_id,
                    "invoice_number": inv_num,
                    "status": inv_data['status'],
                    "timestamp": inv_data['timestamp'].isoformat()
                }
        
        return {"found": False, "erp_id": erp_id}
    
    def update_invoice(self, erp_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """تحديث فاتورة (mock)"""
        # البحث
        for inv_num, inv_data in self.invoices.items():
            if inv_data['erp_id'] == erp_id:
                # تحديث
                inv_data['invoice'].update(updates)
                inv_data['last_updated'] = datetime.now()
                
                self.logger.info(f"Mock: Invoice {erp_id} updated")
                
                return {
                    "success": True,
                    "message": "Invoice updated (mock)",
                    "erp_id": erp_id
                }
        
        return {
            "success": False,
            "message": "Invoice not found",
            "erp_id": erp_id
        }
    
    def delete_invoice(self, erp_id: str) -> bool:
        """حذف فاتورة (mock)"""
        # البحث والحذف
        for inv_num, inv_data in list(self.invoices.items()):
            if inv_data['erp_id'] == erp_id:
                del self.invoices[inv_num]
                self.logger.info(f"Mock: Invoice {erp_id} deleted")
                return True
        
        return False
    
    def get_all_invoices(self) -> List[Dict[str, Any]]:
        """الحصول على جميع الفواتير المخزنة"""
        return [
            {
                "invoice_number": inv_num,
                "erp_id": inv_data['erp_id'],
                "timestamp": inv_data['timestamp'].isoformat(),
                "status": inv_data['status']
            }
            for inv_num, inv_data in self.invoices.items()
        ]
    
    def clear_storage(self):
        """مسح التخزين"""
        self.invoices.clear()
        self.logger.info("Mock: Storage cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """إحصائيات الموصل التجريبي"""
        return {
            **self.get_status(),
            "connection_attempts": self.connection_attempts,
            "send_count": self.send_count,
            "stored_invoices": len(self.invoices),
            "failure_rate": self.failure_rate,
            "simulate_delay": self.simulate_delay
        }


# ═══════════════════════════════════════════════════
# تسجيل في Factory
# ═══════════════════════════════════════════════════

ConnectorFactory.register(ConnectorType.MOCK, MockConnector)

__all__ = ['MockConnector']