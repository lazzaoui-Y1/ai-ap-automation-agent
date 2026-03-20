"""
backend/app/erp_connectors/csv_connector.py
موصل CSV - حفظ الفواتير في ملفات CSV
"""

from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime
import csv
from decimal import Decimal

from .base_connector import BaseERPConnector, ConnectorType, ConnectorStatus, ConnectorFactory
from ..schemas.invoice_schema import Invoice
from ..utils.exceptions import ERPConnectionError, ERPDataFormatError


class CSVConnector(BaseERPConnector):
    """
    موصل CSV - يحفظ الفواتير في ملف CSV
    
    الإعدادات المطلوبة في config:
        output_path: مسار ملف CSV
        delimiter: الفاصل (افتراضي: ",")
        encoding: الترميز (افتراضي: "utf-8-sig")
        include_line_items: تضمين البنود (افتراضي: False)
    """
    
    def __init__(self, customer_id: str, config: Dict[str, Any], connector_type: ConnectorType):
        super().__init__(customer_id, config, connector_type)
        
        # الإعدادات
        self.output_path = Path(config.get('output_path', f'./customers/{customer_id}/data/invoices.csv'))
        self.delimiter = config.get('delimiter', ',')
        self.encoding = config.get('encoding', 'utf-8-sig')  # UTF-8 مع BOM للـ Excel
        self.include_line_items = config.get('include_line_items', False)
        
        # Headers
        self.headers = [
            'invoice_number', 'invoice_date', 'invoice_type',
            'vendor_name', 'vendor_tax_id', 'vendor_phone', 'vendor_email',
            'customer_name', 'customer_tax_id',
            'subtotal', 'total_tax', 'total_discount', 'total_amount', 'currency',
            'line_items_count', 'language_detected', 'confidence_score',
            'po_number', 'payment_terms', 'due_date',
            'processed_timestamp', 'source_file'
        ]
        
        if self.include_line_items:
            self.line_items_path = self.output_path.parent / f"{self.output_path.stem}_line_items.csv"
    
    def connect(self) -> bool:
        """التحقق من إمكانية الكتابة"""
        try:
            self.status = ConnectorStatus.CONNECTED
            
            # إنشاء المجلد
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # إنشاء الملف إذا لم يكن موجوداً
            if not self.output_path.exists():
                self._create_file()
            
            # إنشاء ملف البنود إذا لزم الأمر
            if self.include_line_items and not self.line_items_path.exists():
                self._create_line_items_file()
            
            self._log_operation("connect", "success")
            self.logger.info(f"CSV connector connected: {self.output_path}")
            
            return True
        
        except Exception as e:
            self.status = ConnectorStatus.ERROR
            self.last_error = str(e)
            self._log_operation("connect", "failed", {"error": str(e)})
            raise ERPConnectionError(
                f"Failed to connect to CSV: {str(e)}",
                erp_system="csv"
            )
    
    def disconnect(self) -> bool:
        """لا حاجة لإجراء خاص"""
        self.status = ConnectorStatus.DISCONNECTED
        return True
    
    def send_invoice(self, invoice: Invoice) -> Dict[str, Any]:
        """إضافة فاتورة إلى CSV"""
        try:
            # التحقق من الاتصال
            if self.status != ConnectorStatus.CONNECTED:
                self.connect()
            
            # التحقق من البيانات
            self._validate_invoice_data(invoice)
            
            # التحقق من التكرار
            if self._check_duplicate(invoice.invoice_number):
                self.logger.warning(f"Invoice {invoice.invoice_number} already exists in CSV")
                return {
                    "success": True,
                    "erp_id": invoice.invoice_number,
                    "message": "Invoice already exists (not added again)",
                    "details": {"action": "skipped"}
                }
            
            # إضافة إلى CSV
            row_data = self._invoice_to_dict(invoice)
            
            with open(self.output_path, 'a', newline='', encoding=self.encoding) as f:
                writer = csv.DictWriter(f, fieldnames=self.headers, delimiter=self.delimiter)
                writer.writerow(row_data)
            
            # إضافة البنود إذا لزم الأمر
            if self.include_line_items:
                self._write_line_items(invoice)
            
            # تحديث الإحصائيات
            self._update_sync_stats(success=True)
            
            self._log_operation(
                "send_invoice",
                "success",
                {"invoice_number": invoice.invoice_number}
            )
            
            self.logger.info(f"Invoice {invoice.invoice_number} added to CSV")
            
            return {
                "success": True,
                "erp_id": invoice.invoice_number,
                "message": "Invoice added successfully",
                "details": {
                    "file_path": str(self.output_path),
                    "encoding": self.encoding
                }
            }
        
        except Exception as e:
            self._update_sync_stats(success=False)
            self.last_error = str(e)
            
            self._log_operation(
                "send_invoice",
                "failed",
                {"invoice_number": invoice.invoice_number, "error": str(e)}
            )
            
            raise ERPDataFormatError(
                f"Failed to add invoice to CSV: {str(e)}"
            )
    
    def test_connection(self) -> bool:
        """اختبار الاتصال"""
        try:
            return self.connect()
        except:
            return False
    
    def _create_file(self):
        """إنشاء ملف CSV مع العناوين"""
        with open(self.output_path, 'w', newline='', encoding=self.encoding) as f:
            writer = csv.DictWriter(f, fieldnames=self.headers, delimiter=self.delimiter)
            writer.writeheader()
    
    def _create_line_items_file(self):
        """إنشاء ملف البنود"""
        line_items_headers = [
            'invoice_number', 'line_number', 'description', 'description_ar', 'description_en',
            'quantity', 'unit', 'unit_price', 'discount', 'tax_rate', 'tax_amount', 'line_total',
            'item_code'
        ]
        
        with open(self.line_items_path, 'w', newline='', encoding=self.encoding) as f:
            writer = csv.DictWriter(f, fieldnames=line_items_headers, delimiter=self.delimiter)
            writer.writeheader()
    
    def _invoice_to_dict(self, invoice: Invoice) -> Dict[str, str]:
        """تحويل فاتورة إلى قاموس CSV"""
        return {
            'invoice_number': invoice.invoice_number or '',
            'invoice_date': invoice.invoice_date.isoformat() if invoice.invoice_date else '',
            'invoice_type': invoice.invoice_type.value if invoice.invoice_type else '',
            'vendor_name': invoice.vendor.name if invoice.vendor else '',
            'vendor_tax_id': invoice.vendor.tax_id if invoice.vendor else '',
            'vendor_phone': invoice.vendor.phone if invoice.vendor else '',
            'vendor_email': invoice.vendor.email if invoice.vendor else '',
            'customer_name': invoice.customer.name if invoice.customer else '',
            'customer_tax_id': invoice.customer.tax_id if invoice.customer else '',
            'subtotal': str(invoice.subtotal) if invoice.subtotal else '0',
            'total_tax': str(invoice.total_tax) if invoice.total_tax else '0',
            'total_discount': str(invoice.total_discount) if invoice.total_discount else '0',
            'total_amount': str(invoice.total_amount) if invoice.total_amount else '0',
            'currency': invoice.currency.value if invoice.currency else 'SAR',
            'line_items_count': str(len(invoice.line_items)),
            'language_detected': invoice.language_detected.value if invoice.language_detected else '',
            'confidence_score': str(round(invoice.confidence_score, 2)) if invoice.confidence_score else '0',
            'po_number': invoice.po_number or '',
            'payment_terms': invoice.payment_info.payment_terms if invoice.payment_info else '',
            'due_date': invoice.payment_info.due_date.isoformat() if invoice.payment_info and invoice.payment_info.due_date else '',
            'processed_timestamp': datetime.now().isoformat(),
            'source_file': invoice.source_file or ''
        }
    
    def _write_line_items(self, invoice: Invoice):
        """كتابة البنود في ملف منفصل"""
        with open(self.line_items_path, 'a', newline='', encoding=self.encoding) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    'invoice_number', 'line_number', 'description', 'description_ar', 'description_en',
                    'quantity', 'unit', 'unit_price', 'discount', 'tax_rate', 'tax_amount', 'line_total',
                    'item_code'
                ],
                delimiter=self.delimiter
            )
            
            for idx, item in enumerate(invoice.line_items, 1):
                writer.writerow({
                    'invoice_number': invoice.invoice_number,
                    'line_number': str(idx),
                    'description': item.description or '',
                    'description_ar': item.description_ar or '',
                    'description_en': item.description_en or '',
                    'quantity': str(item.quantity) if item.quantity else '0',
                    'unit': item.unit or '',
                    'unit_price': str(item.unit_price) if item.unit_price else '0',
                    'discount': str(item.discount) if item.discount else '0',
                    'tax_rate': str(item.tax_rate) if item.tax_rate else '0',
                    'tax_amount': str(item.tax_amount) if item.tax_amount else '0',
                    'line_total': str(item.line_total) if item.line_total else '0',
                    'item_code': item.item_code or ''
                })
    
    def _check_duplicate(self, invoice_number: str) -> bool:
        """التحقق من وجود فاتورة مكررة"""
        if not self.output_path.exists():
            return False
        
        try:
            with open(self.output_path, 'r', encoding=self.encoding) as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)
                for row in reader:
                    if row.get('invoice_number') == invoice_number:
                        return True
        except Exception as e:
            self.logger.error(f"Error checking duplicate: {str(e)}")
        
        return False
    
    def batch_send_invoices(self, invoices: List[Invoice]) -> List[Dict[str, Any]]:
        """
        إرسال دفعة - محسّن للـ CSV
        """
        results = []
        
        try:
            # فتح الملف مرة واحدة
            with open(self.output_path, 'a', newline='', encoding=self.encoding) as f:
                writer = csv.DictWriter(f, fieldnames=self.headers, delimiter=self.delimiter)
                
                for invoice in invoices:
                    try:
                        # التحقق
                        self._validate_invoice_data(invoice)
                        
                        # كتابة
                        row_data = self._invoice_to_dict(invoice)
                        writer.writerow(row_data)
                        
                        # البنود
                        if self.include_line_items:
                            self._write_line_items(invoice)
                        
                        results.append({
                            "success": True,
                            "erp_id": invoice.invoice_number,
                            "message": "Success"
                        })
                        
                        self._update_sync_stats(success=True)
                    
                    except Exception as e:
                        results.append({
                            "success": False,
                            "invoice_number": invoice.invoice_number,
                            "error": str(e)
                        })
                        self._update_sync_stats(success=False)
            
            self.logger.info(f"Batch sent: {len(invoices)} invoices")
        
        except Exception as e:
            self.logger.error(f"Batch send failed: {str(e)}")
        
        return results


# ═══════════════════════════════════════════════════
# تسجيل في Factory
# ═══════════════════════════════════════════════════

ConnectorFactory.register(ConnectorType.CSV, CSVConnector)

__all__ = ['CSVConnector']