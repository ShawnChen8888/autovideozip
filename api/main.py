import os
import shutil
import logging
import asyncio
from typing import Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uuid
import subprocess
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import tempfile
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量
processing_tasks = set()  # 跟踪正在处理的任务
MAX_CONCURRENT_TASKS = 3  # 最大并发任务数
FILE_SIZE_LIMIT = 50 * 1024 * 1024  # 50MB
ALLOWED_ORIGINS = [
    "https://yourdomain.vercel.app",  # 替换为你的实际域名
    "http://localhost:3000",
    "http://localhost:8000"
]

# Vercel 上的临时目录
UPLOAD_DIR = "/tmp/uploads"
OUTPUT_DIR = "/tmp/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 支持的文件类型和 MIME 类型
SUPPORTED_VIDEO_TYPES = {
    '.mp4': 'video/mp4',
    '.mov': 'video/quicktime', 
    '.avi': 'video/x-msvideo',
    '.mkv': 'video/x-matroska',
    '.webm': 'video/webm'
}

SUPPORTED_AUDIO_TYPES = {
    '.mp3': 'audio/mpeg',
    '.aac': 'audio/aac', 
    '.wav': 'audio/wav',
    '.flac': 'audio/flac',
    '.ogg': 'audio/ogg',
    '.m4a': 'audio/m4a'
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时清理临时文件
    cleanup_temp_files()
    yield
    # 关闭时清理
    cleanup_temp_files()

app = FastAPI(
    title="视频音频压缩工具",
    description="高效的在线媒体文件压缩服务",
    version="1.0.0",
    lifespan=lifespan
)

# 安全中间件
app.add_middleware(
    TrustedHostMiddleware, 
    allowed_hosts=["*.vercel.app", "localhost", "127.0.0.1"]
)

# CORS 中间件 - 生产环境限制
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 静态文件服务 - 指向根目录
app.mount("/static", StaticFiles(directory="..", html=True), name="static")

@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")

def cleanup_temp_files():
    """清理超过1小时的临时文件"""
    try:
        temp_dirs = [UPLOAD_DIR, OUTPUT_DIR]
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        for temp_dir in temp_dirs:
            if os.path.exists(temp_dir):
                for file_path in Path(temp_dir).glob('*'):
                    if file_path.stat().st_mtime < cutoff_time.timestamp():
                        file_path.unlink(missing_ok=True)
                        logger.info(f"清理临时文件: {file_path}")
    except Exception as e:
        logger.error(f"清理临时文件失败: {e}")

def validate_file_type(file: UploadFile) -> tuple[bool, str]:
    """严格验证文件类型"""
    if not file.filename:
        return False, "文件名无效"
    
    # 检查文件扩展名
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in {**SUPPORTED_VIDEO_TYPES, **SUPPORTED_AUDIO_TYPES}:
        return False, f"不支持的文件类型: {ext}"
    
    return True, "valid"

def is_video(filename: str) -> bool:
    ext = os.path.splitext(filename.lower())[1]
    return ext in SUPPORTED_VIDEO_TYPES

def is_audio(filename: str) -> bool:
    ext = os.path.splitext(filename.lower())[1]
    return ext in SUPPORTED_AUDIO_TYPES

async def compress_video_async(input_path: str, output_path: str, progress_path: Optional[str] = None):
    # 在 Vercel 上，ffmpeg 路径可能不同
    ffmpeg_cmd = "ffmpeg"
    if os.path.exists("/usr/bin/ffmpeg"):
        ffmpeg_cmd = "/usr/bin/ffmpeg"
    elif os.path.exists("/opt/ffmpeg/bin/ffmpeg"):
        ffmpeg_cmd = "/opt/ffmpeg/bin/ffmpeg"
    
    cmd = [
        ffmpeg_cmd, "-y", "-i", input_path,
        "-vf", "scale=-2:480",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
        "-c:a", "aac", "-b:a", "64k",
    ]
    if progress_path:
        cmd += ["-progress", progress_path, "-nostats"]
    cmd.append(output_path)
    
    try:
        # 使用 asyncio 运行 subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=280)
        
        if process.returncode != 0:
            logger.error(f"FFmpeg 错误: {stderr.decode()}")
            raise subprocess.CalledProcessError(process.returncode, cmd)
            
    except asyncio.TimeoutError:
        if process:
            process.terminate()
            await process.wait()
        raise subprocess.TimeoutExpired(cmd, 280)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="视频处理服务不可用")

async def compress_audio_async(input_path: str, output_path: str, progress_path: Optional[str] = None):
    # 在 Vercel 上，ffmpeg 路径可能不同
    ffmpeg_cmd = "ffmpeg"
    if os.path.exists("/usr/bin/ffmpeg"):
        ffmpeg_cmd = "/usr/bin/ffmpeg"
    elif os.path.exists("/opt/ffmpeg/bin/ffmpeg"):
        ffmpeg_cmd = "/opt/ffmpeg/bin/ffmpeg"
        
    cmd = [
        ffmpeg_cmd, "-y", "-i", input_path,
        "-vn", "-ar", "44100", "-ac", "2", "-b:a", "64k",
    ]
    if progress_path:
        cmd += ["-progress", progress_path, "-nostats"]
    cmd.append(output_path)
    
    try:
        # 使用 asyncio 运行 subprocess
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=280)
        
        if process.returncode != 0:
            logger.error(f"FFmpeg 错误: {stderr.decode()}")
            raise subprocess.CalledProcessError(process.returncode, cmd)
            
    except asyncio.TimeoutError:
        if process:
            process.terminate()
            await process.wait()
        raise subprocess.TimeoutExpired(cmd, 280)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="音频处理服务不可用")

@app.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...), task_id: str = Query(None)):
    # 检查并发任务数
    if len(processing_tasks) >= MAX_CONCURRENT_TASKS:
        raise HTTPException(status_code=429, detail="服务器繁忙，请稍后重试")
    
    # 验证文件
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择文件")
    
    # 文件大小检查
    if hasattr(file, 'size') and file.size and file.size > FILE_SIZE_LIMIT:
        raise HTTPException(status_code=413, detail=f"文件过大，最大支持 {FILE_SIZE_LIMIT//1024//1024}MB")
    
    # 文件类型验证
    is_valid, error_msg = validate_file_type(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 记录客户端信息（用于监控）
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"文件上传请求 - IP: {client_ip}, 文件: {file.filename}, 大小: {getattr(file, 'size', 'unknown')}")
    
    file_id = task_id or str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[-1]
    input_path = os.path.join(UPLOAD_DIR, file_id + ext)
    
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    result = {}
    progress_path = os.path.join(OUTPUT_DIR, file_id + ".progress")
    
    # 添加到处理任务集合
    processing_tasks.add(file_id)
    
    try:
        if is_video(file.filename):
            compressed_video = os.path.join(OUTPUT_DIR, file_id + "_compressed.mp4")
            await compress_video_async(input_path, compressed_video, progress_path)
            result["video"] = f"/download/{os.path.basename(compressed_video)}"
            result["size"] = os.path.getsize(compressed_video)
            result["original_size"] = os.path.getsize(input_path)
        elif is_audio(file.filename):
            compressed_audio = os.path.join(OUTPUT_DIR, file_id + "_compressed.mp3")
            await compress_audio_async(input_path, compressed_audio, progress_path) 
            result["audio"] = f"/download/{os.path.basename(compressed_audio)}"
            result["size"] = os.path.getsize(compressed_audio)
            result["original_size"] = os.path.getsize(input_path)
            
        logger.info(f"处理完成 - 任务ID: {file_id}, 原始大小: {result.get('original_size', 0)}, 压缩后: {result.get('size', 0)}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg 处理失败 - 任务ID: {file_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail="文件处理失败，请检查文件格式")
    except subprocess.TimeoutExpired:
        logger.error(f"处理超时 - 任务ID: {file_id}")
        raise HTTPException(status_code=408, detail="处理超时，文件可能过大或过于复杂")
    except Exception as e:
        logger.error(f"处理异常 - 任务ID: {file_id}, 错误: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
    finally:
        # 从处理任务集合中移除
        processing_tasks.discard(file_id)
        
        # 清理上传文件
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except Exception as e:
            logger.error(f"清理上传文件失败: {e}")
            
        # 处理完成后删除进度文件
        try:
            if os.path.exists(progress_path):
                os.remove(progress_path)
        except Exception as e:
            logger.error(f"清理进度文件失败: {e}")
    
    return JSONResponse(result)

@app.get("/progress")
def get_progress(task_id: str = Query(...)):
    progress_path = os.path.join(OUTPUT_DIR, task_id + ".progress")
    if not os.path.exists(progress_path):
        return {"progress": 100}
    try:
        with open(progress_path, "r") as f:
            lines = f.readlines()
        percent = 0
        for line in lines:
            if line.startswith("out_time_ms"):  # ffmpeg进度
                # 不能直接算百分比，简单用帧数/时长等，暂用80%模拟
                percent = 80
            if line.strip() == "progress=end":
                percent = 100
        return {"progress": percent}
    except Exception:
        return {"progress": 0}

@app.get("/download/{filename}")
def download_file(request: Request, filename: str):
    # 文件名安全检查
    if not filename or '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在或已过期")
    
    # 记录下载日志
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"文件下载 - IP: {client_ip}, 文件: {filename}")
    
    return FileResponse(
        file_path, 
        filename=filename,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )

# 健康检查端点
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "processing_tasks": len(processing_tasks),
        "max_tasks": MAX_CONCURRENT_TASKS
    }

# Vercel 需要的导出
handler = app