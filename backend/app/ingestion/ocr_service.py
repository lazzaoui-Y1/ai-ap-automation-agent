"""
backend/app/ingestion/ocr_service.py
خدمة OCR - استخراج النصوص من الصور باستخدام Tesseract
دعم كامل للعربية والإنجليزية والفرنسية
"""

import pytesseract
from PIL import Image
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
import re

from .image_preprocess import ImagePreprocessor
from ..utils.exceptions import OCRError, FileProcessingError
from ..utils.logging import app_logger


class OCRService:
    """
    خدمة OCR متقدمة
    دعم اللغات: العربية، الإنجليزية، الفرنسية
    """
    
    # Tesseract language codes
    LANGUAGE_CODES = {
        'ar': 'ara',      # Arabic
        'en': 'eng',      # English
        'fr': 'fra',      # French
        'mixed': 'ara+eng+fra'  # مختلط
    }
    
    def __init__(
        self,
        tesseract_cmd: Optional[str] = None,
        default_lang: str = 'mixed'
    ):
        """
        Args:
            tesseract_cmd: مسار Tesseract (اختياري)
            default_lang: اللغة الافتراضية
        """
        self.logger = app_logger
        self.preprocessor = ImagePreprocessor()
        self.default_lang = default_lang
        
        # تعيين مسار Tesseract إذا تم تحديده
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # التحقق من تثبيت Tesseract
        self._verify_tesseract()
    
    def _verify_tesseract(self) -> None:
        """التحقق من تثبيت Tesseract واللغات"""
        try:
            version = pytesseract.get_tesseract_version()
            self.logger.info(f"Tesseract version: {version}")
            
            # التحقق من اللغات المثبتة
            langs = pytesseract.get_languages()
            
            required_langs = ['ara', 'eng', 'fra']
            missing_langs = [lang for lang in required_langs if lang not in langs]
            
            if missing_langs:
                self.logger.warning(
                    f"Missing Tesseract languages: {', '.join(missing_langs)}. "
                    f"Install with: sudo apt-get install tesseract-ocr-{'-'.join(missing_langs)}"
                )
            else:
                self.logger.info("All required languages are installed (ara, eng, fra)")
                
        except Exception as e:
            raise OCRError(
                f"Tesseract is not installed or not configured properly: {str(e)}"
            )
    
    def extract_text(
        self,
        image: Union[Image.Image, Path, str],
        lang: Optional[str] = None,
        preprocess: bool = True,
        config: Optional[str] = None
    ) -> str:
        """
        استخراج النص من صورة
        
        Args:
            image: الصورة (PIL Image أو مسار)
            lang: اللغة (ar, en, fr, mixed)
            preprocess: معالجة الصورة قبل OCR
            config: إعدادات Tesseract إضافية
        
        Returns:
            النص المستخرج
        """
        try:
            # تحميل الصورة إذا كانت مسار
            if isinstance(image, (Path, str)):
                image = Image.open(image)
            
            # معالجة الصورة
            if preprocess:
                image = self.preprocessor.preprocess_for_ocr(
                    image,
                    enhance_quality=True,
                    deskew_image=True,
                    remove_noise=True
                )
            
            # تحديد اللغة
            lang_code = self.LANGUAGE_CODES.get(
                lang or self.default_lang,
                self.LANGUAGE_CODES['mixed']
            )
            
            # إعدادات Tesseract الافتراضية
            if not config:
                config = '--psm 6 --oem 3'  # PSM 6: Assume uniform block of text
            
            # OCR
            text = pytesseract.image_to_string(
                image,
                lang=lang_code,
                config=config
            )
            
            # تنظيف النص
            text = self._clean_text(text)
            
            if not text.strip():
                self.logger.warning("OCR returned empty text")
            else:
                self.logger.info(f"OCR extracted {len(text)} characters")
            
            return text
            
        except Exception as e:
            raise OCRError(f"OCR extraction failed: {str(e)}")
    
    def extract_with_details(
        self,
        image: Union[Image.Image, Path, str],
        lang: Optional[str] = None,
        preprocess: bool = True
    ) -> Dict[str, Any]:
        """
        استخراج النص مع معلومات تفصيلية (مواقع، ثقة، إلخ)
        
        Returns:
            قاموس يحتوي على النص والبيانات التفصيلية
        """
        try:
            # تحميل ومعالجة الصورة
            if isinstance(image, (Path, str)):
                image = Image.open(image)
            
            if preprocess:
                image = self.preprocessor.preprocess_for_ocr(image)
            
            # تحديد اللغة
            lang_code = self.LANGUAGE_CODES.get(
                lang or self.default_lang,
                self.LANGUAGE_CODES['mixed']
            )
            
            # استخراج البيانات التفصيلية
            data = pytesseract.image_to_data(
                image,
                lang=lang_code,
                output_type=pytesseract.Output.DICT
            )
            
            # النص الكامل
            full_text = pytesseract.image_to_string(image, lang=lang_code)
            
            # حساب متوسط الثقة
            confidences = [
                int(conf) for conf in data['conf']
                if conf != '-1'
            ]
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0
            
            return {
                'text': self._clean_text(full_text),
                'word_count': len([w for w in data['text'] if w.strip()]),
                'average_confidence': round(avg_confidence, 2),
                'language': lang or self.default_lang,
                'details': data
            }
            
        except Exception as e:
            raise OCRError(f"OCR detailed extraction failed: {str(e)}")
    
    def detect_language(self, image: Union[Image.Image, Path, str]) -> str:
        """
        اكتشاف لغة النص في الصورة
        
        Returns:
            'ar', 'en', 'fr', أو 'mixed'
        """
        try:
            if isinstance(image, (Path, str)):
                image = Image.open(image)
            
            # استخراج نص صغير لاختبار اللغة
            sample_text = pytesseract.image_to_string(
                image,
                lang=self.LANGUAGE_CODES['mixed'],
                config='--psm 6'
            )[:500]  # أول 500 حرف
            
            # تحليل اللغة
            has_arabic = bool(re.search(r'[\u0600-\u06FF]', sample_text))
            has_latin = bool(re.search(r'[a-zA-Z]', sample_text))
            has_french = bool(re.search(r'[àâäéèêëïîôùûüÿç]', sample_text, re.IGNORECASE))
            
            if has_arabic and has_latin:
                return 'mixed'
            elif has_arabic:
                return 'ar'
            elif has_french:
                return 'fr'
            elif has_latin:
                return 'en'
            else:
                return 'mixed'  # افتراضي
                
        except Exception as e:
            self.logger.warning(f"Language detection failed: {str(e)}")
            return 'mixed'
    
    def extract_from_pdf_page(
        self,
        image: Image.Image,
        page_number: int,
        lang: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        استخراج نص من صفحة PDF محولة إلى صورة
        """
        text = self.extract_text(image, lang=lang, preprocess=True)
        
        return {
            'page_number': page_number,
            'text': text,
            'char_count': len(text),
            'has_content': bool(text.strip())
        }
    
    def batch_extract(
        self,
        images: List[Union[Image.Image, Path]],
        lang: Optional[str] = None,
        preprocess: bool = True
    ) -> List[Dict[str, Any]]:
        """
        استخراج نصوص من عدة صور دفعة واحدة
        
        Returns:
            قائمة من النتائج لكل صورة
        """
        results = []
        
        for idx, image in enumerate(images):
            try:
                text = self.extract_text(image, lang=lang, preprocess=preprocess)
                
                results.append({
                    'index': idx,
                    'text': text,
                    'success': True,
                    'error': None
                })
                
            except Exception as e:
                self.logger.error(f"Failed to extract text from image {idx}: {str(e)}")
                results.append({
                    'index': idx,
                    'text': '',
                    'success': False,
                    'error': str(e)
                })
        
        return results
    
    def _clean_text(self, text: str) -> str:
        """
        تنظيف النص المستخرج
        - إزالة الأسطر الفارغة الزائدة
        - تنظيف المسافات
        """
        # إزالة الأسطر الفارغة المتعددة
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # تنظيف المسافات في بداية ونهاية كل سطر
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        
        # إزالة المسافات الزائدة بين الكلمات
        text = re.sub(r' +', ' ', text)
        
        return text.strip()


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def extract_text_from_image(
    image_path: Path,
    lang: str = 'mixed',
    preprocess: bool = True
) -> str:
    """
    دالة مساعدة سريعة لاستخراج نص من صورة
    """
    ocr_service = OCRService(default_lang=lang)
    return ocr_service.extract_text(image_path, preprocess=preprocess)


def extract_text_from_images(
    image_paths: List[Path],
    lang: str = 'mixed',
    preprocess: bool = True
) -> str:
    """
    استخراج نص من عدة صور ودمجها
    """
    ocr_service = OCRService(default_lang=lang)
    results = ocr_service.batch_extract(image_paths, lang=lang, preprocess=preprocess)
    
    # دمج النصوص
    texts = [
        f"=== Image {r['index'] + 1} ===\n{r['text']}"
        for r in results
        if r['success'] and r['text'].strip()
    ]
    
    return '\n\n'.join(texts)


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'OCRService',
    'extract_text_from_image',
    'extract_text_from_images'
]