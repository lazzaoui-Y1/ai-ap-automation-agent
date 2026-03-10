"""
backend/app/utils/file_security.py
أمان الملفات: UUID Filenames, File Validation, Path Sanitization
"""

import uuid
import mimetypes
import magic
from pathlib import Path
from typing import Optional, Tuple, List
import re
import hashlib
from fastapi import UploadFile, HTTPException

from .exceptions import FileProcessingError, UnsupportedFileTypeError
from .logging import app_logger


# ═══════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════

# الامتدادات المسموحة
ALLOWED_EXTENSIONS = {
    'pdf': 'application/pdf',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'bmp': 'image/bmp',
    'tiff': 'image/tiff',
    'tif': 'image/tiff'
}

# الحد الأقصى لحجم الملف (بالبايت)
MAX_FILE_SIZE = int(50 * 1024 * 1024)  # 50 MB

# الحد الأقصى لطول اسم الملف
MAX_FILENAME_LENGTH = 255

# نمط آمن لأسماء الملفات
SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]+$')


# ═══════════════════════════════════════════════════
# UUID Filename Generation
# ═══════════════════════════════════════════════════

def generate_uuid_filename(original_filename: str) -> str:
    """
    توليد اسم ملف آمن باستخدام UUID
    
    Args:
        original_filename: الاسم الأصلي للملف
    
    Returns:
        اسم ملف بصيغة: {uuid}.{extension}
    
    Example:
        "invoice.pdf" -> "550e8400-e29b-41d4-a716-446655440000.pdf"
    """
    # استخراج الامتداد
    extension = Path(original_filename).suffix.lower().lstrip('.')
    
    # التحقق من أن الامتداد مسموح
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            file_type=extension,
            supported_types=list(ALLOWED_EXTENSIONS.keys())
        )
    
    # توليد UUID
    unique_id = uuid.uuid4()
    
    # اسم الملف الجديد
    safe_filename = f"{unique_id}.{extension}"
    
    app_logger.debug(f"Generated UUID filename: {original_filename} -> {safe_filename}")
    
    return safe_filename


def generate_structured_uuid_filename(
    original_filename: str,
    customer_id: str,
    prefix: Optional[str] = None
) -> str:
    """
    توليد اسم ملف منظم مع UUID
    
    Args:
        original_filename: الاسم الأصلي
        customer_id: معرف العميل
        prefix: بادئة اختيارية
    
    Returns:
        {prefix}_{customer_id}_{uuid}.{extension}
    
    Example:
        "invoice.pdf", "cust123", "inv" -> "inv_cust123_550e8400.pdf"
    """
    extension = Path(original_filename).suffix.lower().lstrip('.')
    
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedFileTypeError(
            file_type=extension,
            supported_types=list(ALLOWED_EXTENSIONS.keys())
        )
    
    # توليد UUID قصير (8 أحرف)
    short_uuid = str(uuid.uuid4())[:8]
    
    # تنظيف customer_id
    safe_customer_id = sanitize_path_component(customer_id)
    
    # بناء الاسم
    parts = []
    if prefix:
        parts.append(sanitize_path_component(prefix))
    parts.extend([safe_customer_id, short_uuid])
    
    safe_filename = f"{'_'.join(parts)}.{extension}"
    
    return safe_filename


# ═══════════════════════════════════════════════════
# Path Sanitization
# ═══════════════════════════════════════════════════

def sanitize_path_component(component: str) -> str:
    """
    تنظيف مكون المسار من الأحرف الخطرة
    
    Args:
        component: المكون المراد تنظيفه
    
    Returns:
        مكون آمن
    
    Example:
        "../../../etc/passwd" -> "etcpasswd"
        "customer-123" -> "customer-123"
    """
    # إزالة الأحرف الخطرة
    safe = re.sub(r'[^\w\-.]', '', component)
    
    # إزالة النقاط المتعددة
    safe = re.sub(r'\.{2,}', '', safe)
    
    # إزالة النقاط في البداية
    safe = safe.lstrip('.')
    
    # التأكد من عدم الفراغ
    if not safe:
        safe = str(uuid.uuid4())[:8]
    
    return safe


def validate_path_safety(file_path: Path, base_dir: Path) -> bool:
    """
    التحقق من أن المسار آمن ولا يخرج عن المجلد الأساسي
    
    Args:
        file_path: المسار المراد التحقق منه
        base_dir: المجلد الأساسي المسموح
    
    Returns:
        True إذا كان آمناً
    
    Raises:
        FileProcessingError: إذا كان المسار خطراً
    """
    try:
        # تحويل إلى absolute paths
        abs_file = file_path.resolve()
        abs_base = base_dir.resolve()
        
        # التحقق من أن الملف داخل المجلد الأساسي
        if not str(abs_file).startswith(str(abs_base)):
            raise FileProcessingError(
                "Path traversal detected: File path is outside allowed directory",
                filename=str(file_path)
            )
        
        return True
    
    except Exception as e:
        raise FileProcessingError(
            f"Path validation failed: {str(e)}",
            filename=str(file_path)
        )


# ═══════════════════════════════════════════════════
# File Validation
# ═══════════════════════════════════════════════════

async def validate_file_upload(
    file: UploadFile,
    max_size: int = MAX_FILE_SIZE,
    allowed_types: Optional[List[str]] = None
) -> Tuple[bool, Optional[str]]:
    """
    التحقق من صحة الملف المرفوع
    
    Args:
        file: الملف المرفوع
        max_size: الحد الأقصى للحجم
        allowed_types: الأنواع المسموحة
    
    Returns:
        (is_valid, error_message)
    """
    if allowed_types is None:
        allowed_types = list(ALLOWED_EXTENSIONS.keys())
    
    # 1. التحقق من اسم الملف
    if not file.filename:
        return False, "No filename provided"
    
    # 2. التحقق من طول اسم الملف
    if len(file.filename) > MAX_FILENAME_LENGTH:
        return False, f"Filename too long (max {MAX_FILENAME_LENGTH} characters)"
    
    # 3. التحقق من الامتداد
    extension = Path(file.filename).suffix.lower().lstrip('.')
    
    if extension not in allowed_types:
        return False, f"File type '{extension}' not allowed. Allowed: {allowed_types}"
    
    # 4. التحقق من حجم الملف
    file.file.seek(0, 2)  # الذهاب إلى نهاية الملف
    file_size = file.file.tell()
    file.file.seek(0)  # العودة إلى البداية
    
    if file_size > max_size:
        max_mb = max_size / (1024 * 1024)
        actual_mb = file_size / (1024 * 1024)
        return False, f"File too large ({actual_mb:.2f} MB). Maximum: {max_mb:.2f} MB"
    
    if file_size == 0:
        return False, "File is empty"
    
    # 5. التحقق من نوع الملف الفعلي (Magic Numbers)
    try:
        # قراءة أول 2048 بايت للتحقق
        chunk = await file.read(2048)
        file.file.seek(0)  # العودة إلى البداية
        
        # استخدام python-magic للتحقق من النوع الفعلي
        mime_type = magic.from_buffer(chunk, mime=True)
        
        expected_mime = ALLOWED_EXTENSIONS.get(extension)
        
        if mime_type != expected_mime:
            app_logger.warning(
                f"MIME type mismatch: filename suggests {expected_mime} "
                f"but actual type is {mime_type}"
            )
            # نسمح ببعض التباين في MIME types
            if not mime_type.startswith('image/') and not mime_type.startswith('application/'):
                return False, f"Invalid file type: {mime_type}"
    
    except Exception as e:
        app_logger.warning(f"MIME type validation failed: {str(e)}")
        # نستمر حتى لو فشل الفحص
    
    app_logger.debug(
        f"File validation passed: {file.filename} "
        f"({file_size / 1024:.2f} KB, {extension})"
    )
    
    return True, None


# ═══════════════════════════════════════════════════
# File Hash (للتحقق من التكرار)
# ═══════════════════════════════════════════════════

async def calculate_file_hash(
    file: UploadFile,
    algorithm: str = 'sha256'
) -> str:
    """
    حساب Hash للملف
    
    Args:
        file: الملف
        algorithm: خوارزمية Hash (md5, sha1, sha256)
    
    Returns:
        Hash بصيغة hex
    """
    hasher = hashlib.new(algorithm)
    
    # قراءة الملف على دفعات
    chunk_size = 8192
    file.file.seek(0)
    
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
    
    file.file.seek(0)  # العودة إلى البداية
    
    file_hash = hasher.hexdigest()
    
    app_logger.debug(f"File hash ({algorithm}): {file_hash}")
    
    return file_hash


# ═══════════════════════════════════════════════════
# Secure File Storage
# ═══════════════════════════════════════════════════

class SecureFileHandler:
    """
    معالج آمن للملفات
    """
    
    def __init__(
        self,
        base_dir: Path,
        max_size: int = MAX_FILE_SIZE,
        create_dirs: bool = True
    ):
        self.base_dir = Path(base_dir)
        self.max_size = max_size
        
        if create_dirs:
            self.base_dir.mkdir(parents=True, exist_ok=True)
    
    async def save_upload_file(
        self,
        file: UploadFile,
        customer_id: str,
        use_uuid: bool = True,
        prefix: Optional[str] = None
    ) -> Tuple[Path, str]:
        """
        حفظ ملف مرفوع بشكل آمن
        
        Args:
            file: الملف المرفوع
            customer_id: معرف العميل
            use_uuid: استخدام UUID لاسم الملف
            prefix: بادئة اختيارية
        
        Returns:
            (file_path, original_filename)
        """
        # 1. التحقق من الملف
        is_valid, error = await validate_file_upload(file, self.max_size)
        
        if not is_valid:
            raise FileProcessingError(error, filename=file.filename)
        
        # 2. توليد اسم آمن
        if use_uuid:
            safe_filename = generate_structured_uuid_filename(
                file.filename,
                customer_id,
                prefix
            )
        else:
            safe_filename = sanitize_path_component(file.filename)
        
        # 3. إنشاء المسار الكامل
        customer_dir = self.base_dir / sanitize_path_component(customer_id)
        customer_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = customer_dir / safe_filename
        
        # 4. التحقق من أمان المسار
        validate_path_safety(file_path, self.base_dir)
        
        # 5. حفظ الملف
        try:
            with file_path.open('wb') as f:
                # قراءة وكتابة على دفعات لتجنب استهلاك الذاكرة
                chunk_size = 8192
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
            
            app_logger.info(
                f"File saved securely: {file.filename} -> {file_path.name} "
                f"(customer: {customer_id})"
            )
            
            return file_path, file.filename
        
        except Exception as e:
            # حذف الملف إذا فشل الحفظ
            if file_path.exists():
                file_path.unlink()
            
            raise FileProcessingError(
                f"Failed to save file: {str(e)}",
                filename=file.filename
            )
    
    def delete_file(self, file_path: Path) -> bool:
        """حذف ملف بشكل آمن"""
        try:
            # التحقق من أن الملف داخل base_dir
            validate_path_safety(file_path, self.base_dir)
            
            if file_path.exists():
                file_path.unlink()
                app_logger.info(f"File deleted: {file_path}")
                return True
            
            return False
        
        except Exception as e:
            app_logger.error(f"Failed to delete file: {str(e)}")
            return False


# ═══════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════

__all__ = [
    'generate_uuid_filename',
    'generate_structured_uuid_filename',
    'sanitize_path_component',
    'validate_path_safety',
    'validate_file_upload',
    'calculate_file_hash',
    'SecureFileHandler',
    'ALLOWED_EXTENSIONS',
    'MAX_FILE_SIZE',
]