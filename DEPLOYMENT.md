# Vercel 部署指南

## 🚀 快速部署

### 1. 推送最简化配置
```bash
git add .
git commit -m "最简化 Vercel 部署配置"
git push origin main
```

### 2. Vercel 部署步骤
1. 访问 [vercel.com](https://vercel.com)
2. 连接你的 GitHub 仓库
3. 选择 `autovideozip` 项目
4. 保持默认设置，点击 Deploy

## 📋 当前配置说明

### 文件结构
```
├── api/
│   └── index.py          # 最简化的 FastAPI 应用
├── index.html            # 部署测试页面
├── requirements.txt      # 仅包含 fastapi 和 uvicorn
└── vercel.json          # 最简化的 Vercel 配置
```

### API 端点
- `GET /api/` - 基础 API 测试
- `GET /api/health` - 健康检查
- `GET /api/test` - 部署测试端点

## 🔍 部署验证

### 部署成功后访问：
1. **主页面**: `https://your-app.vercel.app`
2. **API 测试**: `https://your-app.vercel.app/api/`
3. **健康检查**: `https://your-app.vercel.app/api/health`

### 预期响应：
```json
// GET /api/
{
  "message": "Video Compression API is running",
  "status": "healthy"
}

// GET /api/health
{
  "status": "healthy",
  "service": "video-compression"
}
```

## 🛠️ 故障排除

### 常见部署失败原因：

1. **Python 版本问题**
   - Vercel 默认使用 Python 3.12
   - 如需指定版本，创建 `runtime.txt`: `python-3.12`

2. **依赖安装失败**
   - 检查 `requirements.txt` 格式
   - 确保所有依赖都兼容 Python 3.12

3. **文件路径错误**
   - API 文件必须在 `api/` 目录下
   - 入口文件应命名为 `index.py`

4. **ASGI 应用配置**
   - 确保 FastAPI 应用变量名为 `app`
   - 不需要额外的 handler 或 export

### 调试步骤：

1. **查看部署日志**
   - 在 Vercel 控制台查看构建和部署日志
   - 查找具体错误信息

2. **本地测试**
   ```bash
   cd api
   python -m uvicorn index:app --reload
   ```

3. **逐步添加功能**
   - 确保基础部署成功后
   - 再逐步添加复杂功能

## 📈 下一步计划

### 基础部署成功后：

1. **恢复视频压缩功能**
   - 添加文件上传处理
   - 集成 FFmpeg 或第三方 API

2. **添加前端功能**
   - 文件拖拽上传
   - 进度显示
   - 结果下载

3. **生产环境优化**
   - 限制 CORS 来源
   - 添加安全中间件
   - 性能监控

## 🔧 备用方案

### 如果 Vercel 持续失败：

1. **使用 Railway**
   ```bash
   railway login
   railway init
   railway up
   ```

2. **使用 Render**
   - 连接 GitHub 仓库
   - 选择 Web Service
   - 构建命令: `pip install -r requirements.txt`
   - 启动命令: `uvicorn api.index:app --host 0.0.0.0 --port $PORT`

3. **使用 Heroku**
   - 需要 `Procfile`: `web: uvicorn api.index:app --host 0.0.0.0 --port $PORT`

## 📞 获取帮助

如果部署仍然失败，请提供：
1. Vercel 控制台的错误日志
2. 构建失败的具体信息
3. 项目的 GitHub 仓库链接

我们将根据具体错误信息提供针对性的解决方案。