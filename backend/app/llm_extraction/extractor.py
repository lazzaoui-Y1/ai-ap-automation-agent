"""
backend/app/llm_extraction/extractor.py
المحرك الرئيسي لاستخراج البيانات باستخدام LLM (Groq)
"""

from groq import Groq
import json
import re
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, date
import os
from tenacity import retry, stop_after_attempt, wait_exponential

from .prompt_builder import PromptBuilder
from ..schemas.invoice_schema import Invoice, Language
from ..utils.exceptions import (
    LLMExtractionError,
    LLMTimeoutError,
    LLMRateLimitError,
    ValidationError
)
from ..utils.logging import app_logger, log_llm_request


class LLMExtractor:
    """
    محرك استخراج البيانات باستخدام Groq's Llama-3.3-70B
    """
    
    # نماذج Groq المدعومة
    MODELS = {
        'llama-3.3-70b': 'llama-3.3-70b-versatile',
        'llama-3.1-70b': 'llama-3.1-70b-versatile',
        'llama-3.1-8b': 'llama-3.1-8b-instant',
        'mixtral-8x7b': 'mixtral-8x7b-32768'
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = 'llama-3.3-70b',
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: int = 60
    ):
        """
        Args:
            api_key: مفتاح Groq API (أو من .env)
            model: اسم النموذج
            temperature: درجة الحرارة (0.0-1.0) - أقل = أكثر دقة
            max_tokens: الحد الأقصى للـ tokens
            timeout: مهلة الطلب بالثواني
        """
        self.api_key = api_key or os.getenv('GROQ_API_KEY')
        
        if not self.api_key:
            raise LLMExtractionError(
                "GROQ_API_KEY not found. Set it in .env file or pass it to the constructor."
            )
        
        self.client = Groq(api_key=self.api_key)
        self.model = self.MODELS.get(model, self.MODELS['llama-3.3-70b'])
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.logger = app_logger
        
        # Prompt Builder
        self.prompt_builder = PromptBuilder()
        
        self.logger.info(f"LLMExtractor initialized with model: {self.model}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    def extract(
        self,
        text: str,
        language: Language = Language.MIXED,
        customer_hints: Optional[Dict[str, Any]] = None,
        validate: bool = True
    ) -> Tuple[Invoice, float]:
        """
        استخراج البيانات من نص الفاتورة
        
        Args:
            text: نص الفاتورة
            language: لغة الفاتورة
            customer_hints: تلميحات خاصة بالعميل
            validate: التحقق من صحة البيانات
        
        Returns:
            (فاتورة مستخرجة، درجة الثقة)
        """
        start_time = datetime.now()
        
        try:
            # بناء Prompt
            prompt = self.prompt_builder.build_prompt(
                text=text,
                language=language,
                customer_hints=customer_hints,
                include_examples=True
            )
            
            self.logger.debug(f"Prompt length: {len(prompt)} characters")
            
            # استدعاء LLM
            response = self._call_llm(prompt)
            
            # استخراج JSON من الاستجابة
            json_data = self._extract_json(response)
            
            # تحويل إلى كائن Invoice
            invoice = self._parse_invoice(json_data)
            
            # حساب درجة الثقة
            confidence_score = self._calculate_confidence(invoice, json_data)
            invoice.confidence_score = confidence_score
            
            # التحقق من الصحة
            if validate:
                validation_errors = self._validate_extraction(invoice, text)
                if validation_errors:
                    self.logger.warning(f"Validation warnings: {validation_errors}")
            
            # تسجيل النجاح
            processing_time = (datetime.now() - start_time).total_seconds()
            log_llm_request(
                self.logger,
                model=self.model,
                response_time=processing_time,
                success=True
            )
            
            self.logger.info(
                f"Extraction successful: {invoice.invoice_number} "
                f"(confidence: {confidence_score:.2f})"
            )
            
            return invoice, confidence_score
            
        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            log_llm_request(
                self.logger,
                model=self.model,
                response_time=processing_time,
                success=False
            )
            
            raise LLMExtractionError(
                f"Extraction failed: {str(e)}",
                model=self.model
            )
    
    def _call_llm(self, prompt: str) -> str:
        """استدعاء Groq API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert AI for invoice data extraction. Always return valid JSON without any markdown formatting or explanations."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout
            )
            
            content = response.choices[0].message.content
            
            # تسجيل معلومات الاستخدام
            if hasattr(response, 'usage'):
                self.logger.debug(
                    f"Tokens used: {response.usage.total_tokens} "
                    f"(prompt: {response.usage.prompt_tokens}, "
                    f"completion: {response.usage.completion_tokens})"
                )
            
            return content
            
        except Exception as e:
            error_msg = str(e).lower()
            
            if 'rate limit' in error_msg or '429' in error_msg:
                raise LLMRateLimitError()
            elif 'timeout' in error_msg:
                raise LLMTimeoutError(timeout_seconds=self.timeout)
            else:
                raise LLMExtractionError(f"LLM API call failed: {str(e)}")
    
    def _extract_json(self, response: str) -> Dict[str, Any]:
        """
        استخراج JSON من استجابة LLM
        يتعامل مع markdown code blocks والنصوص الإضافية
        """
        # إزالة markdown code blocks
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        
        # البحث عن JSON object
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        
        if not json_match:
            raise LLMExtractionError(
                "No valid JSON found in LLM response",
                model=self.model
            )
        
        json_str = json_match.group(0)
        
        try:
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            raise LLMExtractionError(
                f"Invalid JSON in response: {str(e)}",
                model=self.model
            )
    
    def _parse_invoice(self, data: Dict[str, Any]) -> Invoice:
        """
        تحويل JSON إلى كائن Invoice مع التحقق من الأنواع
        """
        try:
            # تحويل الأرقام إلى Decimal
            if 'subtotal' in data:
                data['subtotal'] = Decimal(str(data['subtotal']))
            
            if 'total_discount' in data:
                data['total_discount'] = Decimal(str(data.get('total_discount', 0)))
            
            if 'total_tax' in data:
                data['total_tax'] = Decimal(str(data.get('total_tax', 0)))
            
            if 'total_amount' in data:
                data['total_amount'] = Decimal(str(data['total_amount']))
            
            # معالجة line_items
            if 'line_items' in data:
                for item in data['line_items']:
                    if 'unit_price' in item:
                        item['unit_price'] = Decimal(str(item['unit_price']))
                    if 'discount' in item:
                        item['discount'] = Decimal(str(item.get('discount', 0)))
                    if 'tax_rate' in item:
                        item['tax_rate'] = Decimal(str(item.get('tax_rate', 0)))
                    if 'tax_amount' in item:
                        item['tax_amount'] = Decimal(str(item.get('tax_amount', 0)))
                    if 'line_total' in item:
                        item['line_total'] = Decimal(str(item['line_total']))
            
            # معالجة tax_breakdown
            if 'tax_breakdown' in data and data['tax_breakdown']:
                for tax in data['tax_breakdown']:
                    if 'tax_rate' in tax:
                        tax['tax_rate'] = Decimal(str(tax['tax_rate']))
                    if 'taxable_amount' in tax:
                        tax['taxable_amount'] = Decimal(str(tax['taxable_amount']))
                    if 'tax_amount' in tax:
                        tax['tax_amount'] = Decimal(str(tax['tax_amount']))
            
            # تحويل التاريخ
            if 'invoice_date' in data and isinstance(data['invoice_date'], str):
                try:
                    data['invoice_date'] = datetime.fromisoformat(data['invoice_date']).date()
                except:
                    # محاولة صيغ أخرى
                    for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                        try:
                            data['invoice_date'] = datetime.strptime(data['invoice_date'], fmt).date()
                            break
                        except:
                            continue
            
            # معالجة due_date في payment_info
            if 'payment_info' in data and data['payment_info']:
                if 'due_date' in data['payment_info'] and isinstance(data['payment_info']['due_date'], str):
                    try:
                        data['payment_info']['due_date'] = datetime.fromisoformat(
                            data['payment_info']['due_date']
                        ).date()
                    except:
                        pass
            
            # إنشاء كائن Invoice باستخدام Pydantic
            invoice = Invoice(**data)
            
            return invoice
            
        except Exception as e:
            raise ValidationError(
                f"Failed to parse invoice data: {str(e)}",
                validation_errors=[str(e)]
            )
    
    def _calculate_confidence(
        self,
        invoice: Invoice,
        raw_data: Dict[str, Any]
    ) -> float:
        """
        حساب درجة الثقة في الاستخراج
        
        معايير الثقة:
        - وجود الحقول المطلوبة
        - صحة الحسابات
        - اكتمال البيانات
        """
        confidence = 1.0
        
        # الحقول المطلوبة
        required_fields = [
            'invoice_number', 'invoice_date', 'vendor',
            'line_items', 'subtotal', 'total_amount'
        ]
        
        missing_fields = 0
        for field in required_fields:
            if not getattr(invoice, field, None):
                missing_fields += 1
                confidence -= 0.15
        
        # صحة الحسابات
        try:
            # التحقق من line_items totals
            calculated_subtotal = sum(item.line_total for item in invoice.line_items)
            if abs(calculated_subtotal - invoice.subtotal) > Decimal('0.01'):
                confidence -= 0.1
            
            # التحقق من total_amount
            expected_total = invoice.subtotal - invoice.total_discount + invoice.total_tax
            if abs(expected_total - invoice.total_amount) > Decimal('0.01'):
                confidence -= 0.1
        except:
            confidence -= 0.2
        
        # معلومات المورد
        if not invoice.vendor.tax_id:
            confidence -= 0.05
        
        if not invoice.vendor.address:
            confidence -= 0.03
        
        # البنود
        if len(invoice.line_items) == 0:
            confidence -= 0.3
        
        # التأكد من عدم النزول تحت 0
        confidence = max(0.0, min(1.0, confidence))
        
        return round(confidence, 2)
    
    def _validate_extraction(
        self,
        invoice: Invoice,
        original_text: str
    ) -> list:
        """
        التحقق من صحة البيانات المستخرجة
        """
        warnings = []
        
        # التحقق من رقم الفاتورة في النص
        if invoice.invoice_number not in original_text:
            warnings.append(f"Invoice number '{invoice.invoice_number}' not found in original text")
        
        # التحقق من اسم المورد
        if invoice.vendor.name not in original_text:
            # قد يكون جزء من الاسم
            name_parts = invoice.vendor.name.split()
            if not any(part in original_text for part in name_parts if len(part) > 3):
                warnings.append(f"Vendor name '{invoice.vendor.name}' not found in text")
        
        # التحقق من التاريخ في المستقبل
        if invoice.invoice_date > date.today():
            if (invoice.invoice_date - date.today()).days > 30:
                warnings.append(f"Invoice date {invoice.invoice_date} is far in the future")
        
        return warnings
    
    def extract_with_validation(
        self,
        text: str,
        language: Language = Language.MIXED,
        customer_hints: Optional[Dict[str, Any]] = None
    ) -> Tuple[Invoice, float, Dict[str, Any]]:
        """
        استخراج مع تحقق إضافي من LLM
        """
        # الاستخراج الأولي
        invoice, confidence = self.extract(
            text=text,
            language=language,
            customer_hints=customer_hints,
            validate=True
        )
        
        # طلب التحقق من LLM
        validation_prompt = self.prompt_builder.build_validation_prompt(
            extracted_data=invoice.dict(),
            original_text=text
        )
        
        try:
            validation_response = self._call_llm(validation_prompt)
            validation_data = self._extract_json(validation_response)
            
            # تطبيق التصحيحات إذا وجدت
            if validation_data.get('corrected_data'):
                # TODO: تطبيق التصحيحات
                pass
            
            # تحديث درجة الثقة
            if 'confidence_score' in validation_data:
                confidence = max(confidence, validation_data['confidence_score'])
            
            return invoice, confidence, validation_data
            
        except Exception as e:
            self.logger.warning(f"Validation step failed: {str(e)}")
            return invoice, confidence, {}


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def extract_invoice_data(
    text: str,
    language: Language = Language.MIXED,
    api_key: Optional[str] = None
) -> Invoice:
    """
    دالة مساعدة سريعة لاستخراج فاتورة
    """
    extractor = LLMExtractor(api_key=api_key)
    invoice, confidence = extractor.extract(text, language)
    return invoice


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = ['LLMExtractor', 'extract_invoice_data']