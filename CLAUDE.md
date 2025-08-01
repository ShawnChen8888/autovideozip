# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个基于 FastAPI 的视频/音频压缩工具，提供 Web 界面用于批量压缩媒体文件。

### 架构组件

- **后端**: FastAPI 应用 (`01.自动批量压缩视频/main.py`)
  - 文件上传处理
  - 使用 FFmpeg 进行媒体压缩
  - 进度跟踪和文件下载
- **前端**: 单页 HTML 应用 (`01.自动批量压缩视频/index.html`)
  - 拖拽上传界面
  - 实时进度显示
  - 自动保存功能（支持 File System Access API）

### 核心功能

- 支持视频格式: mp4, mov, avi, mkv, webm, flv
- 支持音频格式: mp3, aac, wav, flac, ogg, m4a
- 视频压缩：缩放到 480p，使用 H.264 编码，CRF 32
- 音频压缩：64k bitrate，AAC 编码
- 实时处理进度跟踪

## 常用命令

### 环境设置
```bash
pip install -r requirements.txt
```

### 运行开发服务器
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 生产环境运行
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Vercel 部署

项目已配置为在 Vercel 上自动部署：

### 部署配置
- `vercel.json` 配置了 Python 运行时和路由
- 函数超时时间设置为 300 秒（5分钟）
- 支持从 Git 仓库自动部署

### 部署步骤
1. 将代码推送到 GitHub/GitLab 仓库
2. 在 Vercel 中连接仓库
3. Vercel 会自动检测配置并部署

### 生产环境优化

#### 安全性改进
- 限制 CORS 来源，仅允许指定域名访问
- 添加文件类型和大小严格验证（最大 50MB）
- 实现文件名安全检查，防止路径遍历攻击
- 添加 TrustedHost 中间件防止 Host 头攻击
- 配置安全 HTTP 头（X-Frame-Options, X-XSS-Protection 等）

#### 性能优化
- 实现并发任务限制（最大 3 个并发）
- 异步处理文件压缩，避免阻塞
- 自动清理超过 1 小时的临时文件
- 优化内存使用，设置 1GB 内存限制

#### 错误处理
- 详细的错误分类和用户友好的错误消息
- 处理超时、文件过大、格式不支持等各种异常
- 完善的日志记录，便于问题排查
- 资源清理保证，防止内存泄漏

#### 用户体验
- 实时进度显示和状态更新
- 支持压缩率计算和显示
- 文件数量限制（最多 5 个）
- 改进的界面设计和响应式布局
- 自动保存功能（支持 File System Access API）

### 注意事项
- Vercel 的 Serverless 函数有执行时间限制（300秒）
- FFmpeg 在 Vercel 上可能需要额外配置
- 文件大小限制为 50MB，适合 Vercel 的限制
- 部署前需要更新 ALLOWED_ORIGINS 为实际域名

## 依赖要求

- **系统依赖**: FFmpeg（必须安装在系统 PATH 中）
- **Python 依赖**: FastAPI, Uvicorn, python-multipart, ffmpeg-python

## 目录结构

```
uploads/     # 临时上传文件存储
outputs/     # 压缩后文件输出
static/      # 静态文件（通过 FastAPI 服务）
```

## API 端点

- `POST /upload` - 文件上传和压缩
- `GET /progress` - 获取处理进度
- `GET /download/{filename}` - 下载压缩文件
- `GET /` - 重定向到主页面

## 注意事项

- 上传的文件会在处理完成后自动删除
- 进度文件在处理完成后会被清理
- 前端支持现代浏览器的 File System Access API
- CORS 配置允许所有来源（开发用途）