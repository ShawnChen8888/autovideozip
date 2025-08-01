import os
import shutil
import tempfile
import asyncio
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, File, UploadFile, HTTPException, Query, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.security.utils import get_authorization_scheme_param
import uuid

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Video Compression Tool", version="1.0.0")

# 生产环境安全配置
ALLOWED_ORIGINS = [
    "https://your-domain.vercel.app",  # 替换为你的实际域名
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000"
]

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 添加信任主机中间件
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # 在生产环境中应该限制为特定域名
)

# 全局配置
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_FILES_PER_REQUEST = 5
MAX_CONCURRENT_TASKS = 3
TEMP_FILE_LIFETIME = timedelta(hours=1)

# 使用临时目录
TEMP_DIR = tempfile.gettempdir()
UPLOAD_DIR = os.path.join(TEMP_DIR, "video_compress_uploads")
OUTPUT_DIR = os.path.join(TEMP_DIR, "video_compress_outputs")

# 确保目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 并发控制
current_tasks = 0
task_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

# 文件类型检查
SUPPORTED_VIDEO_FORMATS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv'}
SUPPORTED_AUDIO_FORMATS = {'.mp3', '.aac', '.wav', '.flac', '.ogg', '.m4a'}

def is_video(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_VIDEO_FORMATS

def is_audio(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_AUDIO_FORMATS

def is_supported_format(filename: str) -> bool:
    return is_video(filename) or is_audio(filename)

def validate_filename(filename: str) -> bool:
    """验证文件名安全性"""
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        return False
    return True

def check_ffmpeg_available() -> bool:
    """检查 FFmpeg 是否可用"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        return False

async def compress_video_async(input_path: str, output_path: str, progress_callback=None) -> None:
    """异步压缩视频"""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", "scale=-2:480",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
        "-c:a", "aac", "-b:a", "64k",
        "-movflags", "+faststart",  # 优化 web 播放
        output_path
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(f"FFmpeg error: {error_msg}")
            raise subprocess.CalledProcessError(process.returncode, cmd, stderr)
            
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="视频处理超时")
    except Exception as e:
        logger.error(f"Video compression failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"视频压缩失败: {str(e)}")

async def compress_audio_async(input_path: str, output_path: str, progress_callback=None) -> None:
    """异步压缩音频"""
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vn", "-ar", "44100", "-ac", "2", "-b:a", "64k",
        "-acodec", "aac",
        output_path
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            logger.error(f"FFmpeg error: {error_msg}")
            raise subprocess.CalledProcessError(process.returncode, cmd, stderr)
            
    except asyncio.TimeoutError:
        raise HTTPException(status_code=408, detail="音频处理超时")
    except Exception as e:
        logger.error(f"Audio compression failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"音频压缩失败: {str(e)}")

def cleanup_old_files():
    """清理超过生命周期的临时文件"""
    try:
        cutoff_time = datetime.now() - TEMP_FILE_LIFETIME
        
        for directory in [UPLOAD_DIR, OUTPUT_DIR]:
            if not os.path.exists(directory):
                continue
                
            for file_path in Path(directory).glob("*"):
                if file_path.is_file():
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_time:
                        try:
                            file_path.unlink()
                            logger.info(f"Cleaned up old file: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to clean up {file_path}: {e}")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

@app.on_event("startup")
async def startup_event():
    """应用启动时的初始化"""
    logger.info("Starting Video Compression API")
    cleanup_old_files()

@app.get("/")
async def read_root():
    """主页重定向到简单的欢迎页面"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>视频压缩API</title>
        <meta charset="utf-8">
    </head>
    <body>
        <h1>视频压缩API</h1>
        <p>API 正在运行中...</p>
        <p>支持的端点：</p>
        <ul>
            <li>POST /upload - 上传并压缩文件</li>
            <li>GET /download/{filename} - 下载压缩文件</li>
            <li>GET /health - 健康检查</li>
            <li>GET /ffmpeg-check - FFmpeg 可用性检查</li>
        </ul>
    </body>
    </html>
    """)

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "video-compression",
        "timestamp": datetime.now().isoformat(),
        "ffmpeg_available": check_ffmpeg_available()
    }

@app.get("/ffmpeg-check")
async def ffmpeg_availability():
    """检查 FFmpeg 可用性"""
    available = check_ffmpeg_available()
    return {
        "ffmpeg_available": available,
        "status": "ready" if available else "ffmpeg_not_found"
    }

@app.post("/upload")
async def upload_and_compress(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    task_id: Optional[str] = Query(None)
):
    """上传并压缩文件"""
    global current_tasks
    
    # 检查 FFmpeg 可用性
    if not check_ffmpeg_available():
        raise HTTPException(
            status_code=503, 
            detail="FFmpeg 不可用，无法处理媒体文件"
        )
    
    # 验证文件数量
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(
            status_code=400, 
            detail=f"最多只能同时上传 {MAX_FILES_PER_REQUEST} 个文件"
        )
    
    # 验证文件
    for file in files:
        if not file.filename or not validate_filename(file.filename):
            raise HTTPException(status_code=400, detail=f"无效的文件名: {file.filename}")
        
        if not is_supported_format(file.filename):
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的文件格式: {file.filename}. 支持的格式: {', '.join(SUPPORTED_VIDEO_FORMATS | SUPPORTED_AUDIO_FORMATS)}"
            )
    
    # 并发控制
    async with task_semaphore:
        current_tasks += 1
        try:
            results = []
            
            for file in files:
                file_id = task_id or str(uuid.uuid4())
                file_ext = Path(file.filename).suffix.lower()
                
                # 检查文件大小
                content = await file.read()
                if len(content) > MAX_FILE_SIZE:
                    current_tasks -= 1
                    raise HTTPException(
                        status_code=413, 
                        detail=f"文件 {file.filename} 超过最大限制 {MAX_FILE_SIZE//1024//1024}MB"
                    )
                
                # 保存上传文件
                input_path = os.path.join(UPLOAD_DIR, f"{file_id}{file_ext}")
                try:
                    with open(input_path, "wb") as f:
                        f.write(content)
                        
                    original_size = len(content)
                    
                    # 根据文件类型选择压缩方式
                    if is_video(file.filename):
                        output_filename = f"{file_id}_compressed.mp4"
                        output_path = os.path.join(OUTPUT_DIR, output_filename)
                        await compress_video_async(input_path, output_path)
                    else:  # 音频文件
                        output_filename = f"{file_id}_compressed.mp3"
                        output_path = os.path.join(OUTPUT_DIR, output_filename)
                        await compress_audio_async(input_path, output_path)
                    
                    # 获取压缩后文件大小
                    compressed_size = os.path.getsize(output_path)
                    compression_ratio = (1 - compressed_size / original_size) * 100
                    
                    results.append({
                        "original_filename": file.filename,
                        "download_url": f"/download/{output_filename}",
                        "original_size": original_size,
                        "compressed_size": compressed_size,
                        "compression_ratio": round(compression_ratio, 2),
                        "status": "success"
                    })
                    
                except Exception as e:
                    logger.error(f"Processing failed for {file.filename}: {str(e)}")
                    results.append({
                        "original_filename": file.filename,
                        "status": "failed",
                        "error": str(e)
                    })
                finally:
                    # 清理上传文件
                    if os.path.exists(input_path):
                        try:
                            os.remove(input_path)
                        except Exception as e:
                            logger.warning(f"Failed to remove {input_path}: {e}")
            
            # 添加清理任务
            background_tasks.add_task(cleanup_old_files)
            
            return JSONResponse({
                "results": results,
                "total_files": len(files),
                "successful": len([r for r in results if r.get("status") == "success"]),
                "failed": len([r for r in results if r.get("status") == "failed"])
            })
            
        finally:
            current_tasks -= 1

@app.get("/download/{filename}")
async def download_file(filename: str):
    """下载压缩后的文件"""
    if not validate_filename(filename):
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    file_path = os.path.join(OUTPUT_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    
    return FileResponse(
        file_path, 
        filename=filename,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/status")
async def get_status():
    """获取服务状态"""
    return {
        "current_tasks": current_tasks,
        "max_concurrent_tasks": MAX_CONCURRENT_TASKS,
        "max_file_size_mb": MAX_FILE_SIZE // 1024 // 1024,
        "supported_video_formats": list(SUPPORTED_VIDEO_FORMATS),
        "supported_audio_formats": list(SUPPORTED_AUDIO_FORMATS),
        "ffmpeg_available": check_ffmpeg_available()
    }

# 错误处理
@app.exception_handler(413)
async def request_entity_too_large_handler(request, exc):
    return JSONResponse(
        status_code=413,
        content={"detail": f"文件过大，最大允许 {MAX_FILE_SIZE//1024//1024}MB"}
    )

@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"}
    )