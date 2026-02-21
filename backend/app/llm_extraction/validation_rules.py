"""
backend/app/llm_extraction/validation_rules.py
قواعد التحقق من صحة البيانات المستخرجة
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import date, datetime
import re

from ..schemas.invoice_schema import Invoice, InvoiceLineItem, VendorInfo
from ..utils.logging import app_logger


class ValidationRule:
    """قاعدة تحقق أساسية"""
    
    def __init__(self, name: str, severity: str = "error"):
        """
        Args:
            name: اسم القاعدة
            severity: "error" أو "warning"
        """
        self.name = name
        self.severity = severity
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        """
        التحقق من صحة الفاتورة
        
        Returns:
            رسالة الخطأ أو None إذا كانت صحيحة
        """
        raise NotImplementedError


class RequiredFieldsRule(ValidationRule):
    """التحقق من وجود الحقول المطلوبة"""
    
    def __init__(self):
        super().__init__("required_fields", severity="error")
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        missing = []
        
        if not invoice.invoice_number:
            missing.append("invoice_number")
        
        if not invoice.invoice_date:
            missing.append("invoice_date")
        
        if not invoice.vendor or not invoice.vendor.name:
            missing.append("vendor.name")
        
        if not invoice.line_items or len(invoice.line_items) == 0:
            missing.append("line_items")
        
        if invoice.subtotal is None:
            missing.append("subtotal")
        
        if invoice.total_amount is None:
            missing.append("total_amount")
        
        if missing:
            return f"Missing required fields: {', '.join(missing)}"
        
        return None


class DateValidationRule(ValidationRule):
    """التحقق من صحة التواريخ"""
    
    def __init__(self):
        super().__init__("date_validation", severity="warning")
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        errors = []
        
        # التحقق من تاريخ الفاتورة
        if invoice.invoice_date:
            # لا يجب أن يكون في المستقبل البعيد
            if invoice.invoice_date > date.today():
                days_ahead = (invoice.invoice_date - date.today()).days
                if days_ahead > 30:
                    errors.append(
                        f"Invoice date ({invoice.invoice_date}) is {days_ahead} days in the future"
                    )
            
            # لا يجب أن يكون قديماً جداً (أكثر من 10 سنوات)
            years_old = (date.today() - invoice.invoice_date).days / 365
            if years_old > 10:
                errors.append(
                    f"Invoice date ({invoice.invoice_date}) is {int(years_old)} years old"
                )
        
        # التحقق من due_date
        if invoice.payment_info and invoice.payment_info.due_date:
            if invoice.payment_info.due_date < invoice.invoice_date:
                errors.append(
                    f"Due date ({invoice.payment_info.due_date}) is before invoice date"
                )
        
        return " | ".join(errors) if errors else None


class CalculationValidationRule(ValidationRule):
    """التحقق من صحة الحسابات"""
    
    def __init__(self, tolerance: Decimal = Decimal("0.02")):
        super().__init__("calculation_validation", severity="error")
        self.tolerance = tolerance
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        errors = []
        
        # التحقق من line_items totals
        for idx, item in enumerate(invoice.line_items, 1):
            expected_total = (
                Decimal(str(item.quantity)) * item.unit_price
            ) - item.discount + item.tax_amount
            
            diff = abs(expected_total - item.line_total)
            if diff > self.tolerance:
                errors.append(
                    f"Line {idx}: calculated total {expected_total} != "
                    f"stated total {item.line_total} (diff: {diff})"
                )
        
        # التحقق من subtotal
        calculated_subtotal = sum(
            Decimal(str(item.quantity)) * item.unit_price - item.discount
            for item in invoice.line_items
        )
        
        diff = abs(calculated_subtotal - invoice.subtotal)
        if diff > self.tolerance:
            errors.append(
                f"Subtotal mismatch: calculated {calculated_subtotal} != "
                f"stated {invoice.subtotal} (diff: {diff})"
            )
        
        # التحقق من total_amount
        expected_total = invoice.subtotal - invoice.total_discount + invoice.total_tax
        diff = abs(expected_total - invoice.total_amount)
        
        if diff > self.tolerance:
            errors.append(
                f"Total amount mismatch: calculated {expected_total} != "
                f"stated {invoice.total_amount} (diff: {diff})"
            )
        
        return " | ".join(errors) if errors else None


class TaxValidationRule(ValidationRule):
    """التحقق من صحة الضريبة"""
    
    def __init__(self):
        super().__init__("tax_validation", severity="warning")
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        warnings = []
        
        # التحقق من نسبة الضريبة
        if invoice.total_tax > 0 and invoice.subtotal > 0:
            tax_percentage = (invoice.total_tax / invoice.subtotal) * 100
            
            # معدلات ضريبة شائعة
            common_rates = [5, 10, 13, 14, 15, 18, 19, 20, 21, 23, 25, 27]
            
            # البحث عن أقرب معدل
            closest_rate = min(common_rates, key=lambda x: abs(x - tax_percentage))
            
            if abs(tax_percentage - closest_rate) > 1:
                warnings.append(
                    f"Unusual tax rate: {tax_percentage:.2f}% "
                    f"(closest common rate: {closest_rate}%)"
                )
        
        # التحقق من tax_breakdown إذا وجد
        if invoice.tax_breakdown:
            total_from_breakdown = sum(
                tax.tax_amount for tax in invoice.tax_breakdown
            )
            
            diff = abs(total_from_breakdown - invoice.total_tax)
            if diff > Decimal("0.02"):
                warnings.append(
                    f"Tax breakdown total ({total_from_breakdown}) doesn't match "
                    f"total_tax ({invoice.total_tax})"
                )
        
        return " | ".join(warnings) if warnings else None


class VendorValidationRule(ValidationRule):
    """التحقق من صحة بيانات المورد"""
    
    def __init__(self):
        super().__init__("vendor_validation", severity="warning")
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        warnings = []
        vendor = invoice.vendor
        
        # التحقق من الرقم الضريبي السعودي
        if vendor.tax_id:
            # السعودية: 15 رقم يبدأ بـ 3 وينتهي بـ 3
            if len(vendor.tax_id) == 15:
                if not (vendor.tax_id.startswith('3') and vendor.tax_id.endswith('3')):
                    warnings.append(
                        f"Saudi VAT number should start and end with 3: {vendor.tax_id}"
                    )
                
                if not vendor.tax_id.isdigit():
                    warnings.append(
                        f"Saudi VAT number should contain only digits: {vendor.tax_id}"
                    )
        
        # التحقق من وجود معلومات اتصال
        if not vendor.phone and not vendor.email:
            warnings.append("No contact information (phone/email) for vendor")
        
        # التحقق من البريد الإلكتروني
        if vendor.email:
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, vendor.email):
                warnings.append(f"Invalid email format: {vendor.email}")
        
        return " | ".join(warnings) if warnings else None


class LineItemsValidationRule(ValidationRule):
    """التحقق من صحة البنود"""
    
    def __init__(self):
        super().__init__("line_items_validation", severity="warning")
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        warnings = []
        
        if not invoice.line_items:
            return "No line items found"
        
        for idx, item in enumerate(invoice.line_items, 1):
            # التحقق من الكمية
            if item.quantity <= 0:
                warnings.append(f"Line {idx}: Invalid quantity ({item.quantity})")
            
            # التحقق من السعر
            if item.unit_price <= 0:
                warnings.append(f"Line {idx}: Invalid unit price ({item.unit_price})")
            
            # التحقق من الوصف
            if not item.description or len(item.description.strip()) < 2:
                warnings.append(f"Line {idx}: Missing or too short description")
            
            # التحقق من الخصم
            if item.discount > item.unit_price * Decimal(str(item.quantity)):
                warnings.append(
                    f"Line {idx}: Discount ({item.discount}) exceeds line subtotal"
                )
        
        return " | ".join(warnings) if warnings else None


class CurrencyValidationRule(ValidationRule):
    """التحقق من صحة العملة"""
    
    def __init__(self):
        super().__init__("currency_validation", severity="warning")
    
    def validate(self, invoice: Invoice) -> Optional[str]:
        # التحقق من تطابق العملة في البنود
        # (إذا كانت البنود تحتوي على عملة مختلفة)
        
        # للآن، فقط تحذير إذا كانت العملة غير محددة
        if not invoice.currency:
            return "Currency not specified"
        
        return None


class InvoiceValidator:
    """
    المحقق الرئيسي - يجمع جميع القواعد
    """
    
    def __init__(self, custom_rules: Optional[List[ValidationRule]] = None):
        """
        Args:
            custom_rules: قواعد تحقق إضافية مخصصة
        """
        self.logger = app_logger
        
        # القواعد الافتراضية
        self.rules: List[ValidationRule] = [
            RequiredFieldsRule(),
            DateValidationRule(),
            CalculationValidationRule(),
            TaxValidationRule(),
            VendorValidationRule(),
            LineItemsValidationRule(),
            CurrencyValidationRule()
        ]
        
        # إضافة قواعد مخصصة
        if custom_rules:
            self.rules.extend(custom_rules)
    
    def validate(
        self,
        invoice: Invoice,
        raise_on_error: bool = False
    ) -> Dict[str, Any]:
        """
        التحقق من صحة الفاتورة مقابل جميع القواعد
        
        Args:
            invoice: الفاتورة المراد التحقق منها
            raise_on_error: رفع استثناء عند وجود خطأ
        
        Returns:
            قاموس يحتوي على النتائج والأخطاء والتحذيرات
        """
        errors = []
        warnings = []
        
        for rule in self.rules:
            try:
                result = rule.validate(invoice)
                
                if result:
                    if rule.severity == "error":
                        errors.append({
                            "rule": rule.name,
                            "message": result
                        })
                    else:
                        warnings.append({
                            "rule": rule.name,
                            "message": result
                        })
            
            except Exception as e:
                self.logger.error(f"Validation rule '{rule.name}' failed: {str(e)}")
                warnings.append({
                    "rule": rule.name,
                    "message": f"Validation check failed: {str(e)}"
                })
        
        is_valid = len(errors) == 0
        
        result = {
            "is_valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "total_errors": len(errors),
            "total_warnings": len(warnings)
        }
        
        # تسجيل النتائج
        if errors:
            self.logger.warning(
                f"Validation failed for invoice {invoice.invoice_number}: "
                f"{len(errors)} errors, {len(warnings)} warnings"
            )
        elif warnings:
            self.logger.info(
                f"Validation passed with warnings for invoice {invoice.invoice_number}: "
                f"{len(warnings)} warnings"
            )
        else:
            self.logger.info(
                f"Validation passed successfully for invoice {invoice.invoice_number}"
            )
        
        if raise_on_error and not is_valid:
            from ..utils.exceptions import ValidationError
            raise ValidationError(
                f"Invoice validation failed with {len(errors)} errors",
                validation_errors=[e['message'] for e in errors]
            )
        
        return result
    
    def get_validation_summary(self, result: Dict[str, Any]) -> str:
        """الحصول على ملخص نصي للتحقق"""
        if result['is_valid']:
            if result['total_warnings'] == 0:
                return "✓ Validation passed successfully"
            else:
                return f"✓ Validation passed with {result['total_warnings']} warnings"
        else:
            return f"✗ Validation failed: {result['total_errors']} errors, {result['total_warnings']} warnings"


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def validate_invoice(
    invoice: Invoice,
    raise_on_error: bool = False
) -> Dict[str, Any]:
    """
    دالة مساعدة سريعة للتحقق من فاتورة
    """
    validator = InvoiceValidator()
    return validator.validate(invoice, raise_on_error=raise_on_error)


def quick_validate(invoice: Invoice) -> bool:
    """
    تحقق سريع - يرجع True/False فقط
    """
    result = validate_invoice(invoice)
    return result['is_valid']


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'InvoiceValidator',
    'ValidationRule',
    'RequiredFieldsRule',
    'DateValidationRule',
    'CalculationValidationRule',
    'TaxValidationRule',
    'VendorValidationRule',
    'LineItemsValidationRule',
    'validate_invoice',
    'quick_validate'
]