"""
backend/app/main.py
نقطة البداية - FastAPI Application
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from pathlib import Path
from typing import List, Optional
import shutil
import tempfile
from datetime import datetime

from .agents.invoice_agent import InvoiceAgent, create_agent_for_customer
from .schemas.invoice_schema import (
    ExtractionResult,
    CustomerConfig,
    Invoice
)
from .utils.exceptions import (
    InvoiceAIException,
    handle_exception,
    CustomerNotFoundError
)
from .utils.logging import app_logger, log_invoice_processing
from .utils.security import (
    get_current_user,
    TokenData,
    PermissionChecker,
    Permission,
    verify_customer_access,
    create_user_tokens,
    hash_password,
    verify_password,
    UserRole
)
from .utils.rate_limit import (
    limiter,
    custom_rate_limit_exceeded_handler,
    RateLimitConfig,
    get_user_key
)
from .utils.file_security import (
    SecureFileHandler,
    validate_file_upload,
    MAX_FILE_SIZE
)
from .utils.pii_masking import mask_invoice_for_logging


# ═══════════════════════════════════════════════════
# FastAPI App Setup
# ═══════════════════════════════════════════════════

app = FastAPI(
    title="AI Invoice Processing API",
    description="AI-powered invoice automation system with OCR and LLM extraction",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Rate Limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: تحديد النطاقات المسموحة في الإنتاج
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════
# Startup & Shutdown Events
# ═══════════════════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    """تنفذ عند بدء التطبيق"""
    app_logger.info("="*60)
    app_logger.info("🚀 AI Invoice Processing System Starting...")
    app_logger.info("="*60)
    
    # إنشاء المجلدات الأساسية
    base_dirs = [
        Path("./customers"),
        Path("./logs"),
        Path("./temp")
    ]
    
    for dir_path in base_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
    
    app_logger.info("✓ Base directories created")
    app_logger.info("✓ Application ready to accept requests")


@app.on_event("shutdown")
async def shutdown_event():
    """تنفذ عند إيقاف التطبيق"""
    app_logger.info("="*60)
    app_logger.info("🛑 AI Invoice Processing System Shutting Down...")
    app_logger.info("="*60)


# ═══════════════════════════════════════════════════
# Health Check Endpoint
# ═══════════════════════════════════════════════════

@app.get("/", tags=["Health"])
async def root():
    """جذر API - معلومات أساسية"""
    return {
        "service": "AI Invoice Processing API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """فحص صحة النظام"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "checks": {
            "api": "ok",
            "storage": "ok",
            # TODO: إضافة فحوصات للـ OCR, LLM, Database
        }
    }


# ═══════════════════════════════════════════════════
# Invoice Processing Endpoints (SECURED)
# ═══════════════════════════════════════════════════

@app.post("/api/v1/invoices/process/{customer_id}", 
          response_model=ExtractionResult,
          tags=["Invoice Processing"])
@limiter.limit(RateLimitConfig.INVOICE_PROCESS, key_func=get_user_key)
async def process_invoice(
    request: Request,
    customer_id: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    user: TokenData = Depends(verify_customer_access)
):
    """
    معالجة فاتورة واحدة (محمي بـ JWT + Rate Limiting)
    
    - **customer_id**: معرف العميل
    - **file**: ملف الفاتورة (PDF أو صورة)
    
    Security:
        - يتطلب JWT token
        - Rate limit: 20 requests/minute
        - Max file size: 50MB
        - Customer isolation enforced
    
    Returns:
        نتيجة الاستخراج مع بيانات الفاتورة
    """
    temp_file_path = None
    
    try:
        app_logger.info(
            f"Received invoice for customer: {customer_id} "
            f"from user: {user.username}"
        )
        
        # ═══════════════════════════════════════════════════
        # Security: File Validation
        # ═══════════════════════════════════════════════════
        is_valid, error = await validate_file_upload(file, max_size=MAX_FILE_SIZE)
        
        if not is_valid:
            app_logger.warning(f"File validation failed: {error}")
            raise HTTPException(status_code=400, detail=error)
        
        # ═══════════════════════════════════════════════════
        # Security: Secure File Saving with UUID
        # ═══════════════════════════════════════════════════
        temp_dir = Path("./temp")
        temp_dir.mkdir(exist_ok=True)
        
        file_handler = SecureFileHandler(temp_dir)
        temp_file_path, original_filename = await file_handler.save_upload_file(
            file=file,
            customer_id=customer_id,
            use_uuid=True,
            prefix="inv"
        )
        
        app_logger.info(f"File saved securely: {original_filename} -> {temp_file_path.name}")
        
        # ═══════════════════════════════════════════════════
        # Processing
        # ═══════════════════════════════════════════════════
        agent = create_agent_for_customer(customer_id)
        result = agent.process_invoice(temp_file_path)
        
        # ═══════════════════════════════════════════════════
        # Security: PII Masking for Logs
        # ═══════════════════════════════════════════════════
        if result.success and result.invoice:
            safe_invoice_data = mask_invoice_for_logging(result.invoice.dict())
            app_logger.info(
                f"Invoice processed successfully: {safe_invoice_data['invoice_number']} "
                f"(confidence: {safe_invoice_data['confidence_score']:.2%})"
            )
            
            # حفظ الفاتورة في مجلد العميل
            customer_data_dir = Path(f"./customers/{customer_id}/data/processed")
            customer_data_dir.mkdir(parents=True, exist_ok=True)
            
            final_path = customer_data_dir / temp_file_path.name
            shutil.copy(temp_file_path, final_path)
        
        return result
        
    except InvoiceAIException as e:
        app_logger.error(f"Invoice processing failed: {e.message}")
        raise HTTPException(status_code=422, detail=handle_exception(e))
        
    except Exception as e:
        app_logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # حذف الملف المؤقت
        if temp_file_path and temp_file_path.exists():
            try:
                temp_file_path.unlink()
                app_logger.debug(f"Temporary file deleted: {temp_file_path.name}")
            except Exception as e:
                app_logger.warning(f"Failed to delete temp file: {str(e)}")


@app.post("/api/v1/invoices/batch/{customer_id}",
          tags=["Invoice Processing"])
async def batch_process_invoices(
    customer_id: str,
    files: List[UploadFile] = File(...)
):
    """
    معالجة عدة فواتير دفعة واحدة
    
    - **customer_id**: معرف العميل
    - **files**: قائمة ملفات الفواتير
    
    Returns:
        قائمة نتائج الاستخراج
    """
    temp_files = []
    
    try:
        app_logger.info(f"Batch processing {len(files)} files for customer: {customer_id}")
        
        # حفظ الملفات مؤقتاً
        temp_dir = Path("./temp")
        temp_dir.mkdir(exist_ok=True)
        
        for file in files:
            temp_path = temp_dir / f"{customer_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            
            with temp_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            temp_files.append(temp_path)
        
        # إنشاء Agent
        agent = create_agent_for_customer(customer_id)
        
        # معالجة دفعة
        results = agent.batch_process(temp_files)
        
        # حفظ الفواتير الناجحة
        customer_data_dir = Path(f"./customers/{customer_id}/data/processed")
        customer_data_dir.mkdir(parents=True, exist_ok=True)
        
        for result, temp_file in zip(results, temp_files):
            if result.success:
                final_path = customer_data_dir / temp_file.name
                shutil.copy(temp_file, final_path)
        
        return {
            "total_files": len(files),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "results": results
        }
        
    except Exception as e:
        app_logger.error(f"Batch processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
        
    finally:
        # حذف الملفات المؤقتة
        for temp_file in temp_files:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass


# ═══════════════════════════════════════════════════
# Customer Management Endpoints
# ═══════════════════════════════════════════════════

@app.get("/api/v1/customers", tags=["Customer Management"])
async def list_customers():
    """عرض قائمة جميع العملاء"""
    customers_dir = Path("./customers")
    
    if not customers_dir.exists():
        return {"customers": []}
    
    customers = []
    for customer_path in customers_dir.iterdir():
        if customer_path.is_dir() and customer_path.name != "template":
            customers.append({
                "customer_id": customer_path.name,
                "path": str(customer_path)
            })
    
    return {"customers": customers}


@app.get("/api/v1/customers/{customer_id}", tags=["Customer Management"])
async def get_customer_info(customer_id: str):
    """الحصول على معلومات عميل معين"""
    customer_path = Path(f"./customers/{customer_id}")
    
    if not customer_path.exists():
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")
    
    config_path = customer_path / "config.yaml"
    
    return {
        "customer_id": customer_id,
        "path": str(customer_path),
        "has_config": config_path.exists(),
        "data_directory": str(customer_path / "data")
    }


# ═══════════════════════════════════════════════════
# Statistics & Monitoring Endpoints
# ═══════════════════════════════════════════════════

@app.get("/api/v1/stats/{customer_id}", tags=["Statistics"])
async def get_customer_stats(customer_id: str):
    """إحصائيات معالجة الفواتير لعميل معين"""
    
    # TODO: قراءة من قاعدة بيانات أو ملفات اللوج
    
    return {
        "customer_id": customer_id,
        "total_processed": 0,
        "successful": 0,
        "failed": 0,
        "average_processing_time": 0.0,
        "last_processed": None
    }


# ═══════════════════════════════════════════════════
# Error Handlers
# ═══════════════════════════════════════════════════

@app.exception_handler(InvoiceAIException)
async def invoice_ai_exception_handler(request, exc: InvoiceAIException):
    """معالج الاستثناءات المخصصة"""
    return JSONResponse(
        status_code=422,
        content=exc.to_dict()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """معالج الاستثناءات العامة"""
    app_logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": {"exception": str(exc)}
        }
    )


# ═══════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # للتطوير فقط
        log_level="info"
    )