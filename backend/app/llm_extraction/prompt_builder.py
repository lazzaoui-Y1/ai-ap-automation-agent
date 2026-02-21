"""
backend/app/llm_extraction/prompt_builder.py
بناء Prompts ديناميكية للـ LLM حسب اللغة ونوع الفاتورة
"""

from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader, Template
import json

from ..schemas.invoice_schema import Language, Currency
from ..utils.logging import app_logger


class PromptBuilder:
    """
    بناء Prompts للـ LLM
    يدعم القوالب الديناميكية والتخصيص حسب العميل
    """
    
    def __init__(self, prompts_dir: str = "./shared/prompts_base"):
        """
        Args:
            prompts_dir: مجلد قوالب Prompts
        """
        self.prompts_dir = Path(prompts_dir)
        self.logger = app_logger
        
        # تحميل القوالب
        self.templates = self._load_templates()
        
        # JSON Schema للفاتورة
        self.invoice_schema = self._get_invoice_schema()
    
    def _load_templates(self) -> Dict[str, str]:
        """تحميل جميع قوالب Prompts"""
        templates = {}
        
        template_files = {
            'ar': 'ar_invoice_prompt_v7.txt',
            'en': 'en_invoice_prompt_v7.txt',
            'fr': 'fr_invoice_prompt_v7.txt',
            'mixed': 'mixed_language_prompt.txt'
        }
        
        for lang, filename in template_files.items():
            template_path = self.prompts_dir / filename
            
            if template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    templates[lang] = f.read()
                self.logger.debug(f"Loaded template for {lang}")
            else:
                self.logger.warning(f"Template not found: {template_path}")
                # استخدام قالب افتراضي
                templates[lang] = self._get_default_template(lang)
        
        return templates
    
    def _get_default_template(self, lang: str) -> str:
        """قالب افتراضي إذا لم يوجد ملف"""
        return f"""You are an AI expert in invoice data extraction.

Extract structured data from the following invoice text.

Language: {lang}

Return a valid JSON object with this structure:
{self.invoice_schema}

Invoice Text:
{{{{text}}}}

Response (JSON only):"""
    
    def _get_invoice_schema(self) -> str:
        """الحصول على JSON Schema للفاتورة"""
        schema = {
            "invoice_number": "string (required)",
            "invoice_date": "YYYY-MM-DD (required)",
            "invoice_type": "standard|credit_note|debit_note|proforma",
            "currency": "SAR|USD|EUR|AED|EGP",
            "language_detected": "ar|en|fr|mixed",
            
            "vendor": {
                "name": "string (required)",
                "name_ar": "string (optional)",
                "name_en": "string (optional)",
                "tax_id": "string (VAT/Tax ID)",
                "registration_number": "string (Commercial Registration)",
                "address": "string",
                "city": "string",
                "country": "string",
                "phone": "string",
                "email": "string"
            },
            
            "customer": {
                "name": "string",
                "tax_id": "string",
                "address": "string"
            },
            
            "line_items": [
                {
                    "description": "string (required)",
                    "description_ar": "string",
                    "description_en": "string",
                    "quantity": "number (required)",
                    "unit_price": "number (required)",
                    "unit": "string (kg, piece, meter, etc)",
                    "discount": "number (default 0)",
                    "tax_rate": "number (percentage)",
                    "tax_amount": "number",
                    "line_total": "number (required)",
                    "item_code": "string"
                }
            ],
            
            "subtotal": "number (before tax and discount)",
            "total_discount": "number",
            "total_tax": "number",
            "total_amount": "number (final amount)",
            
            "tax_breakdown": [
                {
                    "tax_type": "VAT|GST|Excise",
                    "tax_rate": "number",
                    "taxable_amount": "number",
                    "tax_amount": "number"
                }
            ],
            
            "payment_info": {
                "payment_method": "cash|bank|credit",
                "payment_terms": "Net 30|Net 60|etc",
                "due_date": "YYYY-MM-DD",
                "bank_name": "string",
                "bank_account": "string",
                "iban": "string",
                "swift_code": "string"
            },
            
            "po_number": "string (Purchase Order)",
            "reference_number": "string",
            "notes": "string",
            "qr_code": "string (ZATCA QR data if exists)"
        }
        
        return json.dumps(schema, ensure_ascii=False, indent=2)
    
    def build_prompt(
        self,
        text: str,
        language: Language = Language.MIXED,
        customer_hints: Optional[Dict[str, Any]] = None,
        include_examples: bool = True
    ) -> str:
        """
        بناء Prompt كامل للـ LLM
        
        Args:
            text: نص الفاتورة المستخرج
            language: لغة الفاتورة
            customer_hints: تلميحات خاصة بالعميل (اختياري)
            include_examples: تضمين أمثلة
        
        Returns:
            Prompt جاهز للإرسال للـ LLM
        """
        # اختيار القالب المناسب
        lang_key = language.value if language else 'mixed'
        template_text = self.templates.get(lang_key, self.templates['mixed'])
        
        # بناء Prompt
        prompt = template_text
        
        # استبدال المتغيرات
        prompt = prompt.replace("{{text}}", text)
        prompt = prompt.replace("{{schema}}", self.invoice_schema)
        
        # إضافة تلميحات العميل
        if customer_hints:
            hints_text = self._format_customer_hints(customer_hints)
            prompt = prompt.replace("{{customer_hints}}", hints_text)
        else:
            prompt = prompt.replace("{{customer_hints}}", "")
        
        # إضافة أمثلة
        if include_examples:
            examples = self._get_examples(lang_key)
            prompt = prompt.replace("{{examples}}", examples)
        else:
            prompt = prompt.replace("{{examples}}", "")
        
        return prompt
    
    def _format_customer_hints(self, hints: Dict[str, Any]) -> str:
        """تنسيق تلميحات العميل"""
        hints_text = "\n=== Customer-Specific Information ===\n"
        
        if 'default_currency' in hints:
            hints_text += f"- Default Currency: {hints['default_currency']}\n"
        
        if 'tax_rate' in hints:
            hints_text += f"- Standard Tax Rate: {hints['tax_rate']}%\n"
        
        if 'known_vendors' in hints:
            vendors = ", ".join(hints['known_vendors'][:5])
            hints_text += f"- Known Vendors: {vendors}\n"
        
        if 'custom_fields' in hints:
            hints_text += f"- Custom Fields: {hints['custom_fields']}\n"
        
        hints_text += "=====================================\n\n"
        
        return hints_text
    
    def _get_examples(self, lang: str) -> str:
        """الحصول على أمثلة حسب اللغة"""
        examples = {
            'ar': """
=== مثال على الاستخراج ===

نص الفاتورة:
```
فاتورة ضريبية
رقم الفاتورة: INV-2024-001
التاريخ: 2024-02-07

البائع: شركة النور التجارية
الرقم الضريبي: 300123456789003

البنود:
1. كمبيوتر محمول - الكمية: 2 - السعر: 3000 ريال
2. طابعة - الكمية: 1 - السعر: 500 ريال

المجموع الفرعي: 6500 ريال
ضريبة القيمة المضافة (15%): 975 ريال
الإجمالي: 7475 ريال
```

JSON المتوقع:
```json
{
  "invoice_number": "INV-2024-001",
  "invoice_date": "2024-02-07",
  "currency": "SAR",
  "vendor": {
    "name": "شركة النور التجارية",
    "tax_id": "300123456789003"
  },
  "line_items": [
    {
      "description": "كمبيوتر محمول",
      "quantity": 2,
      "unit_price": 3000,
      "line_total": 6000
    },
    {
      "description": "طابعة",
      "quantity": 1,
      "unit_price": 500,
      "line_total": 500
    }
  ],
  "subtotal": 6500,
  "total_tax": 975,
  "total_amount": 7475
}
```
==============================
""",
            'en': """
=== Example Extraction ===

Invoice Text:
```
TAX INVOICE
Invoice #: INV-2024-001
Date: 2024-02-07

Vendor: Tech Solutions Ltd
VAT ID: 300123456789003

Items:
1. Laptop Computer - Qty: 2 - Price: $1500
2. Printer - Qty: 1 - Price: $250

Subtotal: $3250
VAT (15%): $487.50
Total: $3737.50
```

Expected JSON:
```json
{
  "invoice_number": "INV-2024-001",
  "invoice_date": "2024-02-07",
  "currency": "USD",
  "vendor": {
    "name": "Tech Solutions Ltd",
    "tax_id": "300123456789003"
  },
  "line_items": [
    {
      "description": "Laptop Computer",
      "quantity": 2,
      "unit_price": 1500,
      "line_total": 3000
    }
  ],
  "subtotal": 3250,
  "total_tax": 487.50,
  "total_amount": 3737.50
}
```
==============================
""",
            'fr': """
=== Exemple d'Extraction ===

Texte de la facture:
```
FACTURE
N° de facture: INV-2024-001
Date: 2024-02-07

Fournisseur: Solutions Tech SARL
N° TVA: FR300123456789003

Articles:
1. Ordinateur portable - Qté: 2 - Prix: 1500€
2. Imprimante - Qté: 1 - Prix: 250€

Sous-total: 3250€
TVA (20%): 650€
Total: 3900€
```

JSON attendu:
```json
{
  "invoice_number": "INV-2024-001",
  "invoice_date": "2024-02-07",
  "currency": "EUR",
  "vendor": {
    "name": "Solutions Tech SARL",
    "tax_id": "FR300123456789003"
  },
  "line_items": [
    {
      "description": "Ordinateur portable",
      "quantity": 2,
      "unit_price": 1500,
      "line_total": 3000
    }
  ],
  "subtotal": 3250,
  "total_tax": 650,
  "total_amount": 3900
}
```
==============================
"""
        }
        
        return examples.get(lang, examples['en'])
    
    def build_validation_prompt(
        self,
        extracted_data: Dict[str, Any],
        original_text: str
    ) -> str:
        """
        بناء Prompt للتحقق من صحة البيانات المستخرجة
        """
        prompt = f"""You are an AI validator for invoice data extraction.

Please review the extracted data and check for errors or inconsistencies.

Original Invoice Text:
```
{original_text[:1000]}...
```

Extracted Data:
```json
{json.dumps(extracted_data, ensure_ascii=False, indent=2)}
```

Tasks:
1. Verify all calculations (line totals, subtotal, tax, final total)
2. Check for missing required fields
3. Validate data formats (dates, numbers, tax IDs)
4. Flag any inconsistencies

Provide:
1. is_valid: true/false
2. errors: list of critical errors
3. warnings: list of warnings
4. confidence_score: 0.0 to 1.0
5. corrected_data: if any corrections needed

Response (JSON only):
```json
{{
  "is_valid": true,
  "errors": [],
  "warnings": [],
  "confidence_score": 0.95,
  "corrected_data": {{}}
}}
```

Your response:"""
        
        return prompt
    
    def build_retry_prompt(
        self,
        original_prompt: str,
        previous_error: str,
        attempt_number: int
    ) -> str:
        """
        بناء Prompt لإعادة المحاولة بعد فشل
        """
        retry_prompt = f"""RETRY ATTEMPT #{attempt_number}

Previous attempt failed with error:
{previous_error}

Please try again with more focus on:
1. Extracting ALL required fields
2. Ensuring valid JSON format
3. Using correct data types (numbers as numbers, not strings)
4. Following the exact schema structure

{original_prompt}

IMPORTANT: Return ONLY valid JSON, no explanations or markdown.
"""
        
        return retry_prompt


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def create_prompt_for_invoice(
    text: str,
    language: Language = Language.MIXED,
    customer_config: Optional[Dict[str, Any]] = None
) -> str:
    """
    دالة مساعدة سريعة لإنشاء Prompt
    """
    builder = PromptBuilder()
    
    customer_hints = None
    if customer_config:
        customer_hints = {
            'default_currency': customer_config.get('default_currency', 'SAR'),
            'tax_rate': customer_config.get('tax_rate', 15),
        }
    
    return builder.build_prompt(
        text=text,
        language=language,
        customer_hints=customer_hints,
        include_examples=True
    )


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = ['PromptBuilder', 'create_prompt_for_invoice']