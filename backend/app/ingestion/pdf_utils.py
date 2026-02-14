"""
backend/app/ingestion/pdf_utils.py
أدوات معالجة ملفات PDF - استخراج النصوص والصور
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import io
import base64

from ..utils.exceptions import (
    FileProcessingError,
    UnsupportedFileTypeError,
    EmptyFileError
)
from ..utils.logging import app_logger


class PDFProcessor:
    """معالج ملفات PDF - استخراج نصوص وصور"""
    
    SUPPORTED_EXTENSIONS = ['.pdf']
    MAX_FILE_SIZE_MB = 50
    
    def __init__(self):
        self.logger = app_logger
    
    def validate_pdf(self, file_path: Path) -> None:
        """
        التحقق من صحة ملف PDF
        """
        # التحقق من وجود الملف
        if not file_path.exists():
            raise FileProcessingError(
                f"File not found: {file_path}",
                filename=str(file_path)
            )
        
        # التحقق من الامتداد
        if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                file_type=file_path.suffix,
                supported_types=self.SUPPORTED_EXTENSIONS
            )
        
        # التحقق من حجم الملف
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.MAX_FILE_SIZE_MB:
            raise FileProcessingError(
                f"File size ({file_size_mb:.2f} MB) exceeds maximum allowed size ({self.MAX_FILE_SIZE_MB} MB)",
                filename=str(file_path)
            )
        
        self.logger.debug(f"PDF validation passed: {file_path.name}")
    
    def extract_text(self, file_path: Path) -> str:
        """
        استخراج النص الكامل من PDF
        
        Returns:
            النص المستخرج من جميع الصفحات
        """
        self.validate_pdf(file_path)
        
        try:
            doc = fitz.open(file_path)
            text_content = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                if text.strip():
                    text_content.append(f"--- Page {page_num + 1} ---\n{text}")
            
            doc.close()
            
            full_text = "\n\n".join(text_content)
            
            if not full_text.strip():
                raise EmptyFileError(filename=str(file_path))
            
            self.logger.info(f"Extracted text from {len(text_content)} pages in {file_path.name}")
            return full_text
            
        except fitz.fitz.FileDataError as e:
            raise FileProcessingError(
                f"Corrupted PDF file: {str(e)}",
                filename=str(file_path)
            )
        except Exception as e:
            raise FileProcessingError(
                f"Failed to extract text: {str(e)}",
                filename=str(file_path)
            )
    
    def extract_text_by_page(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        استخراج النص مع الاحتفاظ بتفاصيل كل صفحة
        
        Returns:
            قائمة من القواميس لكل صفحة
        """
        self.validate_pdf(file_path)
        
        try:
            doc = fitz.open(file_path)
            pages_data = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                page_data = {
                    'page_number': page_num + 1,
                    'text': page.get_text(),
                    'width': page.rect.width,
                    'height': page.rect.height,
                    'has_images': len(page.get_images()) > 0,
                    'image_count': len(page.get_images())
                }
                
                pages_data.append(page_data)
            
            doc.close()
            
            self.logger.info(f"Extracted {len(pages_data)} pages from {file_path.name}")
            return pages_data
            
        except Exception as e:
            raise FileProcessingError(
                f"Failed to extract pages: {str(e)}",
                filename=str(file_path)
            )
    
    def extract_images(
        self, 
        file_path: Path,
        output_dir: Optional[Path] = None,
        min_width: int = 100,
        min_height: int = 100
    ) -> List[Dict[str, Any]]:
        """
        استخراج جميع الصور من PDF
        
        Args:
            file_path: مسار ملف PDF
            output_dir: مجلد حفظ الصور (اختياري)
            min_width: الحد الأدنى للعرض
            min_height: الحد الأدنى للارتفاع
        
        Returns:
            قائمة بمعلومات الصور المستخرجة
        """
        self.validate_pdf(file_path)
        
        try:
            doc = fitz.open(file_path)
            images_data = []
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    xref = img[0]
                    base_image = doc.extract_image(xref)
                    
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    
                    # تحويل إلى PIL Image للتحقق من الأبعاد
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    width, height = pil_image.size
                    
                    # تجاهل الصور الصغيرة جداً (عادة شعارات أو أيقونات)
                    if width < min_width or height < min_height:
                        continue
                    
                    image_info = {
                        'page_number': page_num + 1,
                        'image_index': img_index,
                        'width': width,
                        'height': height,
                        'extension': image_ext,
                        'size_bytes': len(image_bytes)
                    }
                    
                    # حفظ الصورة إذا تم تحديد مجلد
                    if output_dir:
                        output_dir.mkdir(parents=True, exist_ok=True)
                        image_filename = f"page_{page_num + 1}_img_{img_index}.{image_ext}"
                        image_path = output_dir / image_filename
                        pil_image.save(image_path)
                        image_info['saved_path'] = str(image_path)
                    else:
                        # تحويل إلى base64 للاستخدام المباشر
                        image_info['base64'] = base64.b64encode(image_bytes).decode('utf-8')
                    
                    images_data.append(image_info)
            
            doc.close()
            
            self.logger.info(f"Extracted {len(images_data)} images from {file_path.name}")
            return images_data
            
        except Exception as e:
            raise FileProcessingError(
                f"Failed to extract images: {str(e)}",
                filename=str(file_path)
            )
    
    def convert_to_images(
        self,
        file_path: Path,
        output_dir: Optional[Path] = None,
        dpi: int = 200,
        format: str = 'PNG'
    ) -> List[Dict[str, Any]]:
        """
        تحويل كل صفحة من PDF إلى صورة
        مفيد للفواتير الممسوحة ضوئياً (Scanned PDFs)
        
        Args:
            file_path: مسار ملف PDF
            output_dir: مجلد حفظ الصور
            dpi: دقة الصورة (200 موصى به للـ OCR)
            format: صيغة الصورة (PNG, JPEG)
        
        Returns:
            قائمة بمعلومات الصور المُنشأة
        """
        self.validate_pdf(file_path)
        
        try:
            doc = fitz.open(file_path)
            images_data = []
            
            # Matrix للتحكم في الدقة
            zoom = dpi / 72  # 72 DPI هو الافتراضي
            mat = fitz.Matrix(zoom, zoom)
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                # تحويل الصفحة إلى صورة
                pix = page.get_pixmap(matrix=mat)
                
                # تحويل إلى PIL Image
                img_data = pix.tobytes(format.lower())
                pil_image = Image.open(io.BytesIO(img_data))
                
                image_info = {
                    'page_number': page_num + 1,
                    'width': pil_image.width,
                    'height': pil_image.height,
                    'dpi': dpi,
                    'format': format
                }
                
                # حفظ الصورة
                if output_dir:
                    output_dir.mkdir(parents=True, exist_ok=True)
                    image_filename = f"page_{page_num + 1}.{format.lower()}"
                    image_path = output_dir / image_filename
                    pil_image.save(image_path, format=format)
                    image_info['saved_path'] = str(image_path)
                else:
                    # تحويل إلى base64
                    buffer = io.BytesIO()
                    pil_image.save(buffer, format=format)
                    image_info['base64'] = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                images_data.append(image_info)
            
            doc.close()
            
            self.logger.info(f"Converted {len(images_data)} pages to images from {file_path.name}")
            return images_data
            
        except Exception as e:
            raise FileProcessingError(
                f"Failed to convert PDF to images: {str(e)}",
                filename=str(file_path)
            )
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        استخراج معلومات PDF (metadata)
        """
        self.validate_pdf(file_path)
        
        try:
            doc = fitz.open(file_path)
            
            metadata = {
                'filename': file_path.name,
                'file_size_bytes': file_path.stat().st_size,
                'file_size_mb': round(file_path.stat().st_size / (1024 * 1024), 2),
                'page_count': len(doc),
                'is_encrypted': doc.is_encrypted,
                'is_pdf': doc.is_pdf,
                'metadata': doc.metadata,
                'has_text': False,
                'has_images': False,
                'total_images': 0
            }
            
            # التحقق من وجود نصوص وصور
            for page_num in range(len(doc)):
                page = doc[page_num]
                
                if not metadata['has_text'] and page.get_text().strip():
                    metadata['has_text'] = True
                
                images = page.get_images()
                if images:
                    metadata['has_images'] = True
                    metadata['total_images'] += len(images)
            
            doc.close()
            
            return metadata
            
        except Exception as e:
            raise FileProcessingError(
                f"Failed to extract metadata: {str(e)}",
                filename=str(file_path)
            )
    
    def is_scanned_pdf(self, file_path: Path, text_threshold: int = 50) -> bool:
        """
        تحديد ما إذا كان PDF ممسوح ضوئياً (يحتاج OCR) أم نصي
        
        Args:
            file_path: مسار الملف
            text_threshold: الحد الأدنى لعدد الأحرف للاعتبار كـ PDF نصي
        
        Returns:
            True إذا كان PDF ممسوح ضوئياً (يحتاج OCR)
        """
        self.validate_pdf(file_path)
        
        try:
            doc = fitz.open(file_path)
            total_text_length = 0
            
            for page in doc:
                text = page.get_text().strip()
                total_text_length += len(text)
                
                # إذا وجدنا نص كافٍ، فهو PDF نصي
                if total_text_length > text_threshold:
                    doc.close()
                    return False
            
            doc.close()
            
            # إذا كان النص قليل جداً، فهو PDF ممسوح ضوئياً
            is_scanned = total_text_length <= text_threshold
            
            self.logger.info(
                f"PDF type detection: {'Scanned' if is_scanned else 'Text-based'} "
                f"(text length: {total_text_length})"
            )
            
            return is_scanned
            
        except Exception as e:
            raise FileProcessingError(
                f"Failed to detect PDF type: {str(e)}",
                filename=str(file_path)
            )


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def process_pdf_file(
    file_path: Path,
    extract_images: bool = False,
    convert_to_images: bool = False,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    دالة شاملة لمعالجة ملف PDF
    
    Returns:
        قاموس يحتوي على جميع البيانات المستخرجة
    """
    processor = PDFProcessor()
    
    result = {
        'metadata': processor.get_metadata(file_path),
        'is_scanned': processor.is_scanned_pdf(file_path),
        'text': None,
        'pages': None,
        'extracted_images': None,
        'page_images': None
    }
    
    # استخراج النص
    if not result['is_scanned']:
        result['text'] = processor.extract_text(file_path)
        result['pages'] = processor.extract_text_by_page(file_path)
    
    # استخراج الصور المضمنة
    if extract_images:
        result['extracted_images'] = processor.extract_images(
            file_path,
            output_dir=output_dir / 'extracted_images' if output_dir else None
        )
    
    # تحويل الصفحات إلى صور (للـ OCR)
    if convert_to_images or result['is_scanned']:
        result['page_images'] = processor.convert_to_images(
            file_path,
            output_dir=output_dir / 'page_images' if output_dir else None,
            dpi=200
        )
    
    return result


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = ['PDFProcessor', 'process_pdf_file']