import os
import shutil
from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import uuid
import subprocess
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# 允许跨域，方便前端开发
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vercel 上的临时目录
UPLOAD_DIR = "/tmp/uploads"
OUTPUT_DIR = "/tmp/outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 静态文件服务 - 指向根目录
app.mount("/static", StaticFiles(directory="..", html=True), name="static")

@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")

# 判断文件类型（简单判断）
def is_video(filename):
    return filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"))

def is_audio(filename):
    return filename.lower().endswith((".mp3", ".aac", ".wav", ".flac", ".ogg", ".m4a"))

# ffmpeg压缩视频，支持进度写入
def compress_video(input_path, output_path, progress_path=None):
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
        subprocess.run(cmd, check=True, timeout=280)  # 280秒超时，留20秒缓冲
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="处理超时，文件可能过大")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="FFmpeg 未安装或不可用")

def compress_audio(input_path, output_path, progress_path=None):
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
        subprocess.run(cmd, check=True, timeout=280)  # 280秒超时，留20秒缓冲
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=408, detail="处理超时，文件可能过大")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="FFmpeg 未安装或不可用")

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), task_id: str = Query(None)):
    # 文件大小限制（Vercel 限制）
    if file.size and file.size > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(status_code=413, detail="文件过大，最大支持 50MB")
        
    if not (is_video(file.filename) or is_audio(file.filename)):
        raise HTTPException(status_code=400, detail="仅支持常见视频/音频格式")
    
    file_id = task_id or str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[-1]
    input_path = os.path.join(UPLOAD_DIR, file_id + ext)
    
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    result = {}
    progress_path = os.path.join(OUTPUT_DIR, file_id + ".progress")
    
    try:
        if is_video(file.filename):
            compressed_video = os.path.join(OUTPUT_DIR, file_id + "_compressed.mp4")
            compress_video(input_path, compressed_video, progress_path)
            result["video"] = f"/download/{os.path.basename(compressed_video)}"
            result["size"] = os.path.getsize(compressed_video)
        elif is_audio(file.filename):
            compressed_audio = os.path.join(OUTPUT_DIR, file_id + "_compressed.mp3")
            compress_audio(input_path, compressed_audio, progress_path)
            result["audio"] = f"/download/{os.path.basename(compressed_audio)}"
            result["size"] = os.path.getsize(compressed_audio)
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="ffmpeg处理失败")
    finally:
        # 清理上传文件
        if os.path.exists(input_path):
            os.remove(input_path)
        # 处理完成后删除进度文件
        if os.path.exists(progress_path):
            os.remove(progress_path)
    
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
def download_file(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(file_path, filename=filename)

# Vercel 需要的导出
handler = app