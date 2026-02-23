"""
backend/app/ingestion/pdf_utils.py
أدوات معالجة ملفات PDF - استخراج النصوص والصور
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional
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
        """التحقق من صحة ملف PDF"""
        # التحقق من وجود الملف (is_file أصح من exists للتأكد أنه ليس مجلداً)
        if not file_path.is_file():
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
        """استخراج النص الكامل من PDF"""
        self.validate_pdf(file_path)
        
        try:
            # استخدام with يضمن إغلاق الملف دائماً وتجنب تسرب الذاكرة
            with fitz.open(file_path) as doc:
                text_content = []
                for page_num, page in enumerate(doc):
                    text = page.get_text()
                    if text.strip():
                        text_content.append(f"--- Page {page_num + 1} ---\n{text}")
                
                full_text = "\n\n".join(text_content)
                
                if not full_text.strip():
                    raise EmptyFileError(filename=str(file_path))
                
                self.logger.info(f"Extracted text from {len(text_content)} pages in {file_path.name}")
                return full_text
                
        except fitz.fitz.FileDataError as e:
            raise FileProcessingError(f"Corrupted PDF file: {str(e)}", filename=str(file_path))
        except EmptyFileError:
            raise
        except Exception as e:
            raise FileProcessingError(f"Failed to extract text: {str(e)}", filename=str(file_path))
    
    def extract_text_by_page(self, file_path: Path) -> List[Dict[str, Any]]:
        """استخراج النص مع الاحتفاظ بتفاصيل كل صفحة"""
        self.validate_pdf(file_path)
        
        try:
            with fitz.open(file_path) as doc:
                pages_data = []
                for page_num, page in enumerate(doc):
                    page_data = {
                        'page_number': page_num + 1,
                        'text': page.get_text(),
                        'width': page.rect.width,
                        'height': page.rect.height,
                        'has_images': len(page.get_images()) > 0,
                        'image_count': len(page.get_images())
                    }
                    pages_data.append(page_data)
                
                self.logger.info(f"Extracted {len(pages_data)} pages from {file_path.name}")
                return pages_data
                
        except Exception as e:
            raise FileProcessingError(f"Failed to extract pages: {str(e)}", filename=str(file_path))
    
    def extract_images(
        self, 
        file_path: Path,
        output_dir: Optional[Path] = None,
        min_width: int = 100,
        min_height: int = 100
    ) -> List[Dict[str, Any]]:
        """استخراج جميع الصور من PDF"""
        self.validate_pdf(file_path)
        
        try:
            with fitz.open(file_path) as doc:
                images_data = []
                for page_num, page in enumerate(doc):
                    image_list = page.get_images()
                    
                    for img_index, img in enumerate(image_list):
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        pil_image = Image.open(io.BytesIO(image_bytes))
                        width, height = pil_image.size
                        
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
                        
                        if output_dir:
                            output_dir.mkdir(parents=True, exist_ok=True)
                            image_filename = f"page_{page_num + 1}_img_{img_index}.{image_ext}"
                            image_path = output_dir / image_filename
                            pil_image.save(image_path)
                            image_info['saved_path'] = str(image_path)
                        else:
                            image_info['base64'] = base64.b64encode(image_bytes).decode('utf-8')
                        
                        images_data.append(image_info)
                
                self.logger.info(f"Extracted {len(images_data)} images from {file_path.name}")
                return images_data
                
        except Exception as e:
            raise FileProcessingError(f"Failed to extract images: {str(e)}", filename=str(file_path))
    
    def convert_to_images(
        self,
        file_path: Path,
        output_dir: Optional[Path] = None,
        dpi: int = 200,
        format: str = 'PNG'
    ) -> List[Dict[str, Any]]:
        """تحويل كل صفحة من PDF إلى صورة"""
        self.validate_pdf(file_path)
        
        try:
            with fitz.open(file_path) as doc:
                images_data = []
                zoom = dpi / 72  
                mat = fitz.Matrix(zoom, zoom)
                
                for page_num, page in enumerate(doc):
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes(format.lower())
                    pil_image = Image.open(io.BytesIO(img_data))
                    
                    image_info = {
                        'page_number': page_num + 1,
                        'width': pil_image.width,
                        'height': pil_image.height,
                        'dpi': dpi,
                        'format': format
                    }
                    
                    if output_dir:
                        output_dir.mkdir(parents=True, exist_ok=True)
                        image_filename = f"page_{page_num + 1}.{format.lower()}"
                        image_path = output_dir / image_filename
                        pil_image.save(image_path, format=format)
                        image_info['saved_path'] = str(image_path)
                    else:
                        buffer = io.BytesIO()
                        pil_image.save(buffer, format=format)
                        image_info['base64'] = base64.b64encode(buffer.getvalue()).decode('utf-8')
                    
                    images_data.append(image_info)
                
                self.logger.info(f"Converted {len(images_data)} pages to images from {file_path.name}")
                return images_data
                
        except Exception as e:
            raise FileProcessingError(f"Failed to convert PDF to images: {str(e)}", filename=str(file_path))
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """استخراج معلومات PDF (metadata)"""
        self.validate_pdf(file_path)
        
        try:
            with fitz.open(file_path) as doc:
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
                
                # تحسين الأداء: الخروج المبكر إذا وجدنا نصوصاً وصوراً لتجنب فحص كامل الملف بلا داعٍ
                for page in doc:
                    if not metadata['has_text'] and page.get_text().strip():
                        metadata['has_text'] = True
                    
                    images = page.get_images()
                    if images:
                        metadata['has_images'] = True
                        metadata['total_images'] += len(images)
                        
                    # إذا اكتشفنا كلاهما، لا داعي لإكمال قراءة النصوص (نكمل فقط لعد الصور إن لزم الأمر)
                    # ملاحظة: إذا كان total_images غير مهم بدقة، يمكننا عمل break هنا لتسريع العملية جداً
                
                return metadata
                
        except Exception as e:
            raise FileProcessingError(f"Failed to extract metadata: {str(e)}", filename=str(file_path))
    
    def is_scanned_pdf(self, file_path: Path, text_threshold: int = 50) -> bool:
        """تحديد ما إذا كان PDF ممسوح ضوئياً"""
        self.validate_pdf(file_path)
        
        try:
            with fitz.open(file_path) as doc:
                total_text_length = 0
                for page in doc:
                    text = page.get_text().strip()
                    total_text_length += len(text)
                    
                    if total_text_length > text_threshold:
                        self.logger.info("PDF type detection: Text-based")
                        return False
                
                is_scanned = total_text_length <= text_threshold
                self.logger.info(f"PDF type detection: Scanned (text length: {total_text_length})")
                return is_scanned
                
        except Exception as e:
            raise FileProcessingError(f"Failed to detect PDF type: {str(e)}", filename=str(file_path))

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
    """
    processor = PDFProcessor()
    
    # تم تقليل استدعاء الدوال هنا لتقليل عدد مرات فتح الملف قدر الإمكان
    # معمارية الكلاس الحالية تتطلب فتح الملف في كل دالة.
    # للعمليات الضخمة جداً، يُفضل بناء دالة "one_pass" تقرأ الملف مرة واحدة.
    
    result = {
        'metadata': processor.get_metadata(file_path),
        'is_scanned': processor.is_scanned_pdf(file_path),
        'text': None,
        'pages': None,
        'extracted_images': None,
        'page_images': None
    }
    
    if not result['is_scanned']:
        result['text'] = processor.extract_text(file_path)
        result['pages'] = processor.extract_text_by_page(file_path)
    
    if extract_images:
        out_path = output_dir / 'extracted_images' if output_dir else None
        result['extracted_images'] = processor.extract_images(file_path, output_dir=out_path)
    
    if convert_to_images or result['is_scanned']:
        out_path = output_dir / 'page_images' if output_dir else None
        result['page_images'] = processor.convert_to_images(file_path, output_dir=out_path, dpi=200)
    
    return result

__all__ = ['PDFProcessor', 'process_pdf_file']