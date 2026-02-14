"""
backend/app/agents/invoice_agent.py
العقل المدبر - Agent الرئيسي لمعالجة الفواتير
يدير العملية من البداية للنهاية: OCR → LLM Extraction → Validation → ERP
"""

from pathlib import Path
from typing import Dict, Any, Optional, List
import time
from datetime import datetime

from ..ingestion.pdf_utils import PDFProcessor, process_pdf_file
from ..ingestion.ocr_service import OCRService
from ..ingestion.image_preprocess import ImagePreprocessor
from ..schemas.invoice_schema import (
    Invoice, ExtractionResult, CustomerConfig, Language
)
from ..utils.exceptions import (
    InvoiceAIException,
    FileProcessingError,
    EmptyFileError,
    LowConfidenceError,
    MaxRetriesExceededError
)
from ..utils.logging import get_customer_logger, log_invoice_processing


class InvoiceAgent:
    """
    الـ Agent الرئيسي لمعالجة الفواتير
    
    المسؤوليات:
    1. تحديد نوع الملف (PDF نصي أو ممسوح، صورة)
    2. استخراج النص (مباشرة من PDF أو عبر OCR)
    3. إرسال النص إلى LLM للاستخراج
    4. التحقق من صحة البيانات
    5. ربط المورد (Vendor Mapping)
    6. إعادة المحاولة عند الفشل
    """
    
    def __init__(
        self,
        customer_config: CustomerConfig,
        llm_extractor: Optional[Any] = None,  # سيتم تطويره في المرحلة الثانية
        confidence_threshold: float = 0.7,
        max_retries: int = 3
    ):
        """
        Args:
            customer_config: إعدادات العميل
            llm_extractor: محرك استخراج LLM
            confidence_threshold: الحد الأدنى لدرجة الثقة
            max_retries: عدد المحاولات عند الفشل
        """
        self.customer_config = customer_config
        self.llm_extractor = llm_extractor
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries
        
        # Logging خاص بالعميل
        self.logger = get_customer_logger(customer_config.customer_id)
        
        # Initialize processors
        self.pdf_processor = PDFProcessor()
        self.ocr_service = OCRService(
            default_lang=self._get_default_lang()
        )
        self.image_preprocessor = ImagePreprocessor()
        
        self.logger.info(
            f"InvoiceAgent initialized for customer: {customer_config.customer_name}"
        )
    
    def _get_default_lang(self) -> str:
        """تحديد اللغة الافتراضية من إعدادات العميل"""
        if not self.customer_config.languages:
            return 'mixed'
        
        # إذا كان هناك لغة واحدة فقط
        if len(self.customer_config.languages) == 1:
            lang_map = {
                Language.AR: 'ar',
                Language.EN: 'en',
                Language.FR: 'fr'
            }
            return lang_map.get(self.customer_config.languages[0], 'mixed')
        
        return 'mixed'
    
    def process_invoice(
        self,
        file_path: Path,
        invoice_metadata: Optional[Dict[str, Any]] = None
    ) -> ExtractionResult:
        """
        معالجة فاتورة كاملة - العملية الشاملة
        
        Args:
            file_path: مسار ملف الفاتورة (PDF أو صورة)
            invoice_metadata: بيانات إضافية (اختياري)
        
        Returns:
            نتيجة الاستخراج مع البيانات المستخرجة أو الأخطاء
        """
        start_time = time.time()
        retry_count = 0
        errors = []
        warnings = []
        
        self.logger.info(f"Starting invoice processing: {file_path.name}")
        
        try:
            # ═══════════════════════════════════════════════════
            # المرحلة 1: استخراج النص
            # ═══════════════════════════════════════════════════
            text_content = self._extract_text_from_file(file_path)
            
            if not text_content.strip():
                raise EmptyFileError(filename=str(file_path))
            
            self.logger.info(f"Text extracted: {len(text_content)} characters")
            
            # ═══════════════════════════════════════════════════
            # المرحلة 2: استخراج البيانات باستخدام LLM
            # ═══════════════════════════════════════════════════
            # TODO: سيتم تطويره في المرحلة الثانية
            # للآن نرجع نتيجة mock
            invoice_data = self._mock_llm_extraction(text_content, file_path)
            
            # ═══════════════════════════════════════════════════
            # المرحلة 3: التحقق من صحة البيانات
            # ═══════════════════════════════════════════════════
            validation_errors = self._validate_invoice(invoice_data)
            
            if validation_errors:
                errors.extend(validation_errors)
                self.logger.warning(f"Validation errors found: {len(validation_errors)}")
            
            # ═══════════════════════════════════════════════════
            # المرحلة 4: التحقق من درجة الثقة
            # ═══════════════════════════════════════════════════
            if invoice_data.confidence_score < self.confidence_threshold:
                warning_msg = (
                    f"Low confidence score: {invoice_data.confidence_score:.2f} "
                    f"(threshold: {self.confidence_threshold})"
                )
                warnings.append(warning_msg)
                self.logger.warning(warning_msg)
                
                # إذا كانت الثقة منخفضة جداً، نعتبرها فشل
                if invoice_data.confidence_score < 0.5:
                    raise LowConfidenceError(
                        invoice_data.confidence_score,
                        self.confidence_threshold
                    )
            
            # ═══════════════════════════════════════════════════
            # المرحلة 5: ربط المورد (Vendor Mapping)
            # ═══════════════════════════════════════════════════
            if self.customer_config.vendor_mapping_file:
                vendor_code = self._map_vendor(invoice_data.vendor.name)
                if vendor_code:
                    invoice_data.vendor.mapped_vendor_code = vendor_code
                else:
                    warnings.append(f"Vendor '{invoice_data.vendor.name}' not found in mapping")
            
            # ═══════════════════════════════════════════════════
            # النجاح!
            # ═══════════════════════════════════════════════════
            processing_time = time.time() - start_time
            
            log_invoice_processing(
                self.logger,
                invoice_number=invoice_data.invoice_number,
                customer_id=self.customer_config.customer_id,
                status="success",
                processing_time=processing_time
            )
            
            return ExtractionResult(
                success=True,
                invoice=invoice_data,
                errors=errors,
                warnings=warnings,
                processing_time=processing_time,
                retry_count=retry_count,
                llm_model_used="mock"  # TODO: من الـ LLM extractor
            )
            
        except InvoiceAIException as e:
            # خطأ معروف
            processing_time = time.time() - start_time
            
            log_invoice_processing(
                self.logger,
                invoice_number=file_path.stem,
                customer_id=self.customer_config.customer_id,
                status="failed",
                processing_time=processing_time,
                error_message=e.message
            )
            
            return ExtractionResult(
                success=False,
                invoice=None,
                errors=[e.message],
                warnings=warnings,
                processing_time=processing_time,
                retry_count=retry_count
            )
            
        except Exception as e:
            # خطأ غير متوقع
            processing_time = time.time() - start_time
            error_msg = f"Unexpected error: {str(e)}"
            
            log_invoice_processing(
                self.logger,
                invoice_number=file_path.stem,
                customer_id=self.customer_config.customer_id,
                status="failed",
                processing_time=processing_time,
                error_message=error_msg
            )
            
            return ExtractionResult(
                success=False,
                invoice=None,
                errors=[error_msg],
                warnings=warnings,
                processing_time=processing_time,
                retry_count=retry_count
            )
    
    def _extract_text_from_file(self, file_path: Path) -> str:
        """
        استخراج النص من ملف (PDF أو صورة)
        يحدد النوع تلقائياً ويختار الطريقة المناسبة
        """
        file_ext = file_path.suffix.lower()
        
        # ═══════════════════════════════════════════════════
        # PDF Files
        # ═══════════════════════════════════════════════════
        if file_ext == '.pdf':
            # التحقق: هل PDF نصي أم ممسوح؟
            is_scanned = self.pdf_processor.is_scanned_pdf(file_path)
            
            if is_scanned:
                self.logger.info("Scanned PDF detected, using OCR")
                # تحويل إلى صور ثم OCR
                page_images = self.pdf_processor.convert_to_images(
                    file_path,
                    dpi=200
                )
                
                # OCR لكل صفحة
                texts = []
                for page_data in page_images:
                    if 'base64' in page_data:
                        # تحويل base64 إلى PIL Image
                        import base64
                        import io
                        from PIL import Image
                        
                        img_bytes = base64.b64decode(page_data['base64'])
                        image = Image.open(io.BytesIO(img_bytes))
                        
                        text = self.ocr_service.extract_text(image, preprocess=True)
                        if text.strip():
                            texts.append(f"--- Page {page_data['page_number']} ---\n{text}")
                
                return '\n\n'.join(texts)
            else:
                self.logger.info("Text-based PDF detected, extracting text directly")
                return self.pdf_processor.extract_text(file_path)
        
        # ═══════════════════════════════════════════════════
        # Image Files
        # ═══════════════════════════════════════════════════
        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
            self.logger.info("Image file detected, using OCR")
            return self.ocr_service.extract_text(
                file_path,
                preprocess=True
            )
        
        else:
            raise FileProcessingError(
                f"Unsupported file type: {file_ext}",
                filename=str(file_path)
            )
    
    def _mock_llm_extraction(
        self,
        text_content: str,
        file_path: Path
    ) -> Invoice:
        """
        Mock extraction - للاختبار فقط
        TODO: استبدال بـ LLM حقيقي في المرحلة الثانية
        """
        from decimal import Decimal
        from ..schemas.invoice_schema import (
            VendorInfo, InvoiceLineItem, Currency, Language, InvoiceType
        )
        
        # Mock data
        return Invoice(
            invoice_number="INV-2024-001",
            invoice_type=InvoiceType.STANDARD,
            invoice_date=datetime.now().date(),
            currency=Currency.SAR,
            language_detected=Language.AR,
            vendor=VendorInfo(
                name="شركة الاختبار المحدودة",
                tax_id="300000000000003",
                phone="+966 12 345 6789"
            ),
            line_items=[
                InvoiceLineItem(
                    description="منتج اختباري",
                    quantity=10.0,
                    unit_price=Decimal("100.00"),
                    tax_rate=Decimal("15"),
                    tax_amount=Decimal("150.00"),
                    line_total=Decimal("1150.00")
                )
            ],
            subtotal=Decimal("1000.00"),
            total_tax=Decimal("150.00"),
            total_amount=Decimal("1150.00"),
            confidence_score=0.85,
            source_file=file_path.name
        )
    
    def _validate_invoice(self, invoice: Invoice) -> List[str]:
        """
        التحقق من صحة البيانات المستخرجة
        """
        errors = []
        
        # TODO: تطوير قواعد التحقق في validation_rules.py
        # للآن فقط فحص أساسي
        
        if not invoice.invoice_number:
            errors.append("Missing invoice number")
        
        if not invoice.vendor or not invoice.vendor.name:
            errors.append("Missing vendor information")
        
        if not invoice.line_items:
            errors.append("No line items found")
        
        return errors
    
    def _map_vendor(self, vendor_name: str) -> Optional[str]:
        """
        ربط المورد بكود ERP
        TODO: قراءة من ملف Excel vendor_mapping.xlsx
        """
        # Mock للآن
        vendor_mapping = {
            "شركة الاختبار المحدودة": "VENDOR_001",
            "Test Company Ltd": "VENDOR_001"
        }
        
        return vendor_mapping.get(vendor_name)
    
    def batch_process(
        self,
        file_paths: List[Path]
    ) -> List[ExtractionResult]:
        """
        معالجة عدة فواتير دفعة واحدة
        """
        results = []
        
        self.logger.info(f"Starting batch processing: {len(file_paths)} files")
        
        for idx, file_path in enumerate(file_paths, 1):
            self.logger.info(f"Processing file {idx}/{len(file_paths)}: {file_path.name}")
            
            result = self.process_invoice(file_path)
            results.append(result)
            
            if result.success:
                self.logger.info(f"✓ Success: {file_path.name}")
            else:
                self.logger.error(f"✗ Failed: {file_path.name} - {result.errors}")
        
        # ملخص
        success_count = sum(1 for r in results if r.success)
        self.logger.info(
            f"Batch processing completed: {success_count}/{len(file_paths)} successful"
        )
        
        return results


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def create_agent_for_customer(customer_id: str) -> InvoiceAgent:
    """
    إنشاء Agent لعميل معين
    TODO: قراءة الإعدادات من config.yaml
    """
    from ..schemas.invoice_schema import CustomerConfig
    
    # Mock config للآن
    config = CustomerConfig(
        customer_id=customer_id,
        customer_name=f"Customer {customer_id}",
        connector_type="excel",
        auto_process=True
    )
    
    return InvoiceAgent(customer_config=config)


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = ['InvoiceAgent', 'create_agent_for_customer']