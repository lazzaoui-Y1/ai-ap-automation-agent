"""
backend/app/schemas/invoice_schema.py
المخططات الأساسية لبيانات الفواتير
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


class InvoiceType(str, Enum):
    """أنواع الفواتير"""

    STANDARD = "standard"
    CREDIT_NOTE = "credit_note"
    DEBIT_NOTE = "debit_note"
    PROFORMA = "proforma"


class Currency(str, Enum):
    """العملات المدعومة"""

    SAR = "SAR"
    USD = "USD"
    EUR = "EUR"
    AED = "AED"
    EGP = "EGP"


class Language(str, Enum):
    """اللغات المدعومة"""

    AR = "ar"
    EN = "en"
    FR = "fr"
    MIXED = "mixed"


class InvoiceLineItem(BaseModel):
    """بند واحد من بنود الفاتورة"""

    description: str = Field(..., description="وصف المنتج أو الخدمة")
    description_ar: Optional[str] = Field(None, description="الوصف بالعربية")
    description_en: Optional[str] = Field(None, description="الوصف بالإنجليزية")
    quantity: float = Field(..., gt=0, description="الكمية")
    unit_price: Decimal = Field(..., description="سعر الوحدة")
    unit: Optional[str] = Field(None, description="وحدة القياس (كجم، قطعة، متر، إلخ)")
    discount: Decimal = Field(default=Decimal("0"), ge=0, description="الخصم")
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, description="نسبة الضريبة %")
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, description="مبلغ الضريبة")
    line_total: Decimal = Field(..., description="المجموع الكلي للبند")
    item_code: Optional[str] = Field(None, description="كود الصنف")

    @validator("line_total")
    def validate_line_total(cls, v, values):
        """التحقق من صحة المجموع"""
        if "quantity" in values and "unit_price" in values:
            expected = (
                Decimal(str(values["quantity"])) * values["unit_price"]
            ) - values.get("discount", Decimal("0"))
            expected += values.get("tax_amount", Decimal("0"))
            if abs(expected - v) > Decimal("0.01"):
                raise ValueError(f"Line total mismatch: expected {expected}, got {v}")
        return v


class VendorInfo(BaseModel):
    """معلومات المورد"""

    name: str = Field(..., description="اسم المورد")
    name_ar: Optional[str] = Field(None, description="الاسم بالعربية")
    name_en: Optional[str] = Field(None, description="الاسم بالإنجليزية")
    tax_id: Optional[str] = Field(None, description="الرقم الضريبي / VAT Number")
    registration_number: Optional[str] = Field(
        None, description="رقم السجل التجاري / CR"
    )
    address: Optional[str] = Field(None, description="العنوان الكامل")
    city: Optional[str] = Field(None, description="المدينة")
    country: Optional[str] = Field(None, description="الدولة")
    phone: Optional[str] = Field(None, description="رقم الهاتف")
    email: Optional[str] = Field(None, description="البريد الإلكتروني")
    website: Optional[str] = Field(None, description="الموقع الإلكتروني")
    mapped_vendor_code: Optional[str] = Field(
        None, description="كود المورد في نظام ERP"
    )


class CustomerInfo(BaseModel):
    """معلومات العميل (الشركة المشترية)"""

    name: str = Field(..., description="اسم العميل")
    tax_id: Optional[str] = Field(None, description="الرقم الضريبي")
    registration_number: Optional[str] = Field(None, description="رقم السجل التجاري")
    address: Optional[str] = Field(None, description="العنوان")
    city: Optional[str] = Field(None, description="المدينة")
    country: Optional[str] = Field(None, description="الدولة")
    phone: Optional[str] = Field(None, description="رقم الهاتف")


class TaxBreakdown(BaseModel):
    """تفصيل الضريبة"""

    tax_type: str = Field(..., description="نوع الضريبة (VAT, GST, Excise, etc.)")
    tax_rate: Decimal = Field(..., ge=0, description="نسبة الضريبة %")
    taxable_amount: Decimal = Field(..., ge=0, description="المبلغ الخاضع للضريبة")
    tax_amount: Decimal = Field(..., ge=0, description="مبلغ الضريبة")


class PaymentInfo(BaseModel):
    """معلومات الدفع"""

    payment_method: Optional[str] = Field(
        None, description="طريقة الدفع (نقدي، بنكي، آجل)"
    )
    payment_terms: Optional[str] = Field(
        None, description="شروط الدفع (Net 30, Net 60)"
    )
    due_date: Optional[date] = Field(None, description="تاريخ الاستحقاق")
    bank_name: Optional[str] = Field(None, description="اسم البنك")
    bank_account: Optional[str] = Field(None, description="رقم الحساب البنكي")
    iban: Optional[str] = Field(None, description="IBAN")
    swift_code: Optional[str] = Field(None, description="SWIFT Code")


class Invoice(BaseModel):
    """نموذج الفاتورة الكامل - القلب النابض للنظام"""

    # ═══════════════════════════════════════════════════
    # Basic Information
    # ═══════════════════════════════════════════════════
    invoice_number: str = Field(..., description="رقم الفاتورة")
    invoice_type: InvoiceType = Field(
        default=InvoiceType.STANDARD, description="نوع الفاتورة"
    )
    invoice_date: date = Field(..., description="تاريخ الفاتورة")
    currency: Currency = Field(default=Currency.SAR, description="العملة")
    language_detected: Language = Field(
        default=Language.AR, description="اللغة المكتشفة"
    )

    # ═══════════════════════════════════════════════════
    # Parties Information
    # ═══════════════════════════════════════════════════
    vendor: VendorInfo = Field(..., description="معلومات المورد")
    customer: Optional[CustomerInfo] = Field(None, description="معلومات العميل")

    # ═══════════════════════════════════════════════════
    # Line Items - البنود
    # ═══════════════════════════════════════════════════
    line_items: List[InvoiceLineItem] = Field(
        ..., min_length=1, description="بنود الفاتورة"
    )

    # ═══════════════════════════════════════════════════
    # Financial Amounts
    # ═══════════════════════════════════════════════════
    subtotal: Decimal = Field(
        ..., ge=0, description="المجموع الفرعي قبل الخصم والضريبة"
    )
    total_discount: Decimal = Field(
        default=Decimal("0"), ge=0, description="إجمالي الخصم"
    )
    total_tax: Decimal = Field(default=Decimal("0"), ge=0, description="إجمالي الضريبة")
    total_amount: Decimal = Field(..., ge=0, description="المبلغ الإجمالي النهائي")

    # ═══════════════════════════════════════════════════
    # Tax Details
    # ═══════════════════════════════════════════════════
    tax_breakdown: Optional[List[TaxBreakdown]] = Field(
        None, description="تفصيل الضرائب"
    )

    # ═══════════════════════════════════════════════════
    # Payment Information
    # ═══════════════════════════════════════════════════
    payment_info: Optional[PaymentInfo] = Field(None, description="معلومات الدفع")

    # ═══════════════════════════════════════════════════
    # Additional Metadata
    # ═══════════════════════════════════════════════════
    po_number: Optional[str] = Field(None, description="رقم أمر الشراء Purchase Order")
    reference_number: Optional[str] = Field(None, description="رقم مرجعي")
    notes: Optional[str] = Field(None, description="ملاحظات إضافية")
    qr_code: Optional[str] = Field(None, description="بيانات رمز QR (ZATCA)")

    # ═══════════════════════════════════════════════════
    # Processing Metadata
    # ═══════════════════════════════════════════════════
    confidence_score: float = Field(
        default=0.0, ge=0, le=1, description="درجة الثقة في الاستخراج"
    )
    extraction_timestamp: datetime = Field(
        default_factory=datetime.now, description="وقت الاستخراج"
    )
    source_file: Optional[str] = Field(None, description="اسم الملف المصدر")
    page_count: Optional[int] = Field(None, description="عدد الصفحات")

    @validator("total_amount")
    def validate_total(cls, v, values):
        """التحقق من صحة المجموع النهائي"""
        if (
            "subtotal" in values
            and "total_tax" in values
            and "total_discount" in values
        ):
            expected = (
                values["subtotal"] - values["total_discount"] + values["total_tax"]
            )
            if abs(expected - v) > Decimal("0.01"):
                raise ValueError(f"Total amount mismatch: expected {expected}, got {v}")
        return v

    @validator("invoice_date")
    def validate_date(cls, v):
        """التحقق من أن التاريخ ليس في المستقبل البعيد"""
        if v > date.today():
            if (v - date.today()).days > 30:
                raise ValueError(f"Invoice date {v} is too far in the future")
        return v

    def to_dict(self) -> Dict[str, Any]:
        """تحويل إلى قاموس"""
        return self.dict(exclude_none=True)

    class Config:
        json_encoders = {
            Decimal: lambda v: float(v),
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
        }
        use_enum_values = True


class ExtractionResult(BaseModel):
    """نتيجة عملية الاستخراج - ما يُرجع من الـ Agent"""

    success: bool = Field(..., description="هل نجحت العملية")
    invoice: Optional[Invoice] = Field(None, description="بيانات الفاتورة المستخرجة")
    errors: List[str] = Field(default_factory=list, description="قائمة الأخطاء الحرجة")
    warnings: List[str] = Field(default_factory=list, description="قائمة التحذيرات")
    processing_time: float = Field(..., ge=0, description="وقت المعالجة بالثواني")
    retry_count: int = Field(default=0, ge=0, description="عدد محاولات إعادة المحاولة")
    llm_model_used: Optional[str] = Field(None, description="نموذج LLM المستخدم")


class CustomerConfig(BaseModel):
    """إعدادات العميل من ملف config.yaml"""

    customer_id: str = Field(..., description="معرف العميل الفريد")
    customer_name: str = Field(..., description="اسم العميل")
    connector_type: str = Field(
        ..., description="نوع الموصل: excel, csv, sap_sftp_xml, oracle_rest, webhook"
    )

    # Connector-specific settings
    connector_config: Dict[str, Any] = Field(
        default_factory=dict, description="إعدادات خاصة بالموصل"
    )

    # Processing settings
    auto_process: bool = Field(default=True, description="معالجة تلقائية")
    require_approval: bool = Field(default=False, description="يتطلب موافقة يدوية")
    languages: List[Language] = Field(
        default=[Language.AR, Language.EN], description="اللغات المدعومة"
    )
    default_currency: Currency = Field(
        default=Currency.SAR, description="العملة الافتراضية"
    )

    # Vendor mapping
    vendor_mapping_file: Optional[str] = Field(None, description="ملف ربط الموردين")

    class Config:
        use_enum_values = True
