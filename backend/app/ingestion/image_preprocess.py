"""
backend/app/ingestion/image_preprocess.py
معالجة وتحسين الصور قبل OCR - تحسين جودة الصورة للحصول على نتائج أفضل
"""

from PIL import Image, ImageEnhance, ImageFilter
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Union
import io

from ..utils.exceptions import FileProcessingError, UnsupportedFileTypeError
from ..utils.logging import app_logger


class ImagePreprocessor:
    """معالج الصور - تحسين الجودة قبل OCR"""
    
    SUPPORTED_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']
    
    def __init__(self):
        self.logger = app_logger
    
    def validate_image(self, image_path: Path) -> None:
        """التحقق من صحة ملف الصورة"""
        if not image_path.exists():
            raise FileProcessingError(
                f"Image file not found: {image_path}",
                filename=str(image_path)
            )
        
        if image_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise UnsupportedFileTypeError(
                file_type=image_path.suffix,
                supported_types=self.SUPPORTED_FORMATS
            )
    
    def load_image(self, image_path: Path) -> Image.Image:
        """تحميل صورة من ملف"""
        self.validate_image(image_path)
        try:
            img = Image.open(image_path)
            return img
        except Exception as e:
            raise FileProcessingError(
                f"Failed to load image: {str(e)}",
                filename=str(image_path)
            )
    
    def convert_to_grayscale(self, image: Image.Image) -> Image.Image:
        """تحويل الصورة إلى رمادي (Grayscale)"""
        if image.mode != 'L':
            return image.convert('L')
        return image
    
    def resize_image(
        self,
        image: Image.Image,
        target_width: Optional[int] = None,
        target_height: Optional[int] = None,
        max_dimension: Optional[int] = None
    ) -> Image.Image:
        """
        تغيير حجم الصورة
        
        Args:
            image: الصورة
            target_width: العرض المطلوب
            target_height: الارتفاع المطلوب
            max_dimension: الحد الأقصى للبعد (عرض أو ارتفاع)
        """
        width, height = image.size
        
        if max_dimension:
            # تصغير إذا كان أحد الأبعاد أكبر من الحد الأقصى
            if width > max_dimension or height > max_dimension:
                ratio = min(max_dimension / width, max_dimension / height)
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        elif target_width and target_height:
            return image.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        elif target_width:
            ratio = target_width / width
            new_height = int(height * ratio)
            return image.resize((target_width, new_height), Image.Resampling.LANCZOS)
        
        elif target_height:
            ratio = target_height / height
            new_width = int(width * ratio)
            return image.resize((new_width, target_height), Image.Resampling.LANCZOS)
        
        return image
    
    def increase_contrast(self, image: Image.Image, factor: float = 1.5) -> Image.Image:
        """زيادة التباين (Contrast)"""
        enhancer = ImageEnhance.Contrast(image)
        return enhancer.enhance(factor)
    
    def increase_sharpness(self, image: Image.Image, factor: float = 2.0) -> Image.Image:
        """زيادة الحدة (Sharpness)"""
        enhancer = ImageEnhance.Sharpness(image)
        return enhancer.enhance(factor)
    
    def denoise(self, image: Image.Image) -> Image.Image:
        """إزالة التشويش (Noise Reduction)"""
        # تحويل إلى numpy array لاستخدام OpenCV
        img_array = np.array(image)
        
        if len(img_array.shape) == 2:  # Grayscale
            denoised = cv2.fastNlMeansDenoising(img_array, None, 10, 7, 21)
        else:  # Color
            denoised = cv2.fastNlMeansDenoisingColored(img_array, None, 10, 10, 7, 21)
        
        return Image.fromarray(denoised)
    
    def binarize(
        self,
        image: Image.Image,
        method: str = 'otsu',
        threshold: int = 128
    ) -> Image.Image:
        """
        تحويل إلى صورة ثنائية (أبيض وأسود)
        
        Args:
            image: الصورة
            method: 'otsu' (تلقائي) أو 'manual' (يدوي)
            threshold: قيمة العتبة (للطريقة اليدوية)
        """
        # تحويل إلى grayscale أولاً
        gray = self.convert_to_grayscale(image)
        img_array = np.array(gray)
        
        if method == 'otsu':
            # Otsu's method - تحديد العتبة تلقائياً
            _, binary = cv2.threshold(
                img_array, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
        else:
            # Manual threshold
            _, binary = cv2.threshold(img_array, threshold, 255, cv2.THRESH_BINARY)
        
        return Image.fromarray(binary)
    
    def deskew(self, image: Image.Image) -> Tuple[Image.Image, float]:
        """
        تصحيح الميلان (Deskew) - جعل النص مستقيماً
        
        Returns:
            (الصورة المصححة, زاوية الدوران)
        """
        img_array = np.array(image)
        
        # تحويل إلى grayscale إذا لزم الأمر
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # Threshold
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        
        # حساب الزاوية
        coords = np.column_stack(np.where(thresh > 0))
        angle = cv2.minAreaRect(coords)[-1]
        
        # تصحيح الزاوية
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        
        # تدوير الصورة
        if abs(angle) > 0.5:  # فقط إذا كان الميلان ملحوظاً
            (h, w) = img_array.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                img_array, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            return Image.fromarray(rotated), angle
        
        return image, 0.0
    
    def remove_borders(self, image: Image.Image, threshold: int = 200) -> Image.Image:
        """إزالة الحواف البيضاء الزائدة"""
        img_array = np.array(image)
        
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # العثور على المناطق غير البيضاء
        _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY_INV)
        
        # العثور على الحدود
        coords = np.column_stack(np.where(thresh > 0))
        
        if len(coords) == 0:
            return image
        
        x, y, w, h = cv2.boundingRect(coords)
        
        # Crop
        cropped = img_array[y:y+h, x:x+w]
        
        return Image.fromarray(cropped)
    
    def preprocess_for_ocr(
        self,
        image: Union[Image.Image, Path],
        enhance_quality: bool = True,
        deskew_image: bool = True,
        remove_noise: bool = True,
        binarize_image: bool = False
    ) -> Image.Image:
        """
        معالجة شاملة للصورة قبل OCR
        
        Args:
            image: الصورة أو مسار الصورة
            enhance_quality: تحسين الجودة (تباين، حدة)
            deskew_image: تصحيح الميلان
            remove_noise: إزالة التشويش
            binarize_image: تحويل إلى أبيض وأسود
        
        Returns:
            الصورة المعالجة جاهزة للـ OCR
        """
        # تحميل الصورة إذا كانت Path
        if isinstance(image, Path):
            image = self.load_image(image)
        
        self.logger.debug("Starting OCR preprocessing")
        
        # 1. تصحيح الميلان
        if deskew_image:
            image, angle = self.deskew(image)
            if abs(angle) > 0.5:
                self.logger.debug(f"Deskewed image by {angle:.2f} degrees")
        
        # 2. إزالة الحواف
        image = self.remove_borders(image)
        
        # 3. تحويل إلى grayscale
        image = self.convert_to_grayscale(image)
        
        # 4. إزالة التشويش
        if remove_noise:
            image = self.denoise(image)
            self.logger.debug("Noise removed")
        
        # 5. تحسين الجودة
        if enhance_quality:
            image = self.increase_contrast(image, factor=1.5)
            image = self.increase_sharpness(image, factor=1.5)
            self.logger.debug("Quality enhanced")
        
        # 6. Binarization (اختياري - قد يحسن أو يسوء النتائج حسب الصورة)
        if binarize_image:
            image = self.binarize(image, method='otsu')
            self.logger.debug("Image binarized")
        
        self.logger.info("OCR preprocessing completed")
        return image
    
    def save_image(
        self,
        image: Image.Image,
        output_path: Path,
        format: str = 'PNG',
        quality: int = 95
    ) -> None:
        """حفظ الصورة المعالجة"""
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(output_path, format=format, quality=quality)
            self.logger.debug(f"Image saved to {output_path}")
        except Exception as e:
            raise FileProcessingError(
                f"Failed to save image: {str(e)}",
                filename=str(output_path)
            )
    
    def image_to_bytes(self, image: Image.Image, format: str = 'PNG') -> bytes:
        """تحويل الصورة إلى bytes"""
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return buffer.getvalue()


# ═══════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════

def preprocess_invoice_image(
    image_path: Path,
    output_path: Optional[Path] = None,
    quality_preset: str = 'high'
) -> Image.Image:
    """
    دالة مساعدة لمعالجة صورة فاتورة
    
    Args:
        image_path: مسار الصورة
        output_path: مسار الحفظ (اختياري)
        quality_preset: 'low', 'medium', 'high'
    
    Returns:
        الصورة المعالجة
    """
    preprocessor = ImagePreprocessor()
    
    # إعدادات حسب الجودة المطلوبة
    presets = {
        'low': {
            'enhance_quality': False,
            'deskew_image': True,
            'remove_noise': False,
            'binarize_image': False
        },
        'medium': {
            'enhance_quality': True,
            'deskew_image': True,
            'remove_noise': False,
            'binarize_image': False
        },
        'high': {
            'enhance_quality': True,
            'deskew_image': True,
            'remove_noise': True,
            'binarize_image': False
        }
    }
    
    settings = presets.get(quality_preset, presets['medium'])
    
    # المعالجة
    processed_image = preprocessor.preprocess_for_ocr(image_path, **settings)
    
    # الحفظ إذا طُلب
    if output_path:
        preprocessor.save_image(processed_image, output_path)
    
    return processed_image


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = ['ImagePreprocessor', 'preprocess_invoice_image']