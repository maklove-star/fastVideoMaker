# 数字人短视频智能体

一个从文案输入到数字人口播视频生成、再到多平台分发的 Python + Vue 自动化项目。

当前版本已接入：

- 前端：Vue 3 + Vite 响应式工作台
- 后端：FastAPI API 骨架
- 文案：火山方舟豆包 Responses API（`doubao-seed-evolving`）
- 音频：豆包音频 1.0，同步接口兜底；异步长文本 TTS 支持声音克隆 Speaker ID
- 视频：火山视觉「单图音频驱动」（形象创建 + 音频驱动）
  文档：https://docs.volcengine.com/docs/86081/1804513
- 发布：Playwright/social-auto-upload 接入占位

## 配置密钥

复制 `.env.example` 为 `.env`，填入自己的密钥：

```bash
ARK_API_KEY=your_volc_ark_api_key
DOUBAO_AUDIO_API_KEY=your_doubao_audio_api_key
DOUBAO_TTS_APP_ID=your_app_id
DOUBAO_TTS_ACCESS_KEY=your_access_key
```

如果只使用同步 `seed-audio-1.0`，可以先只填 `DOUBAO_AUDIO_API_KEY`。

如果要使用声音克隆，必须配置 `DOUBAO_TTS_APP_ID`、`DOUBAO_TTS_ACCESS_KEY`，并在前端填写已复刻音色的 `Speaker ID`，资源 ID 选择 `seed-icl-1.0` 或 `seed-icl-2.0`。

真实视频生成需要配置：

```bash
ENABLE_REAL_VIDEO=true
VIDEO_PROVIDER=volc_cv
# IAM 访问密钥（控制台 → 头像 → API访问密钥），不是视觉产品 API Key
VOLC_ACCESS_KEY=AKLTxxxxxxxx
VOLC_SECRET_KEY=your_secret_access_key
VOLC_CV_MODE=normal
# 推荐：穿透后的本服务地址。留空则本地开发会把人像/音频临时上传到公网图床（PUBLIC_FILE_HOST=auto）
PUBLIC_BASE_URL=
PUBLIC_FILE_HOST=auto
```

火山接口需要能拉取人像与音频的 **公网 URL**。本地有两种方式：

1. 配置 `PUBLIC_BASE_URL`（Cloudflare Tunnel / cpolar 等）指向本机 `8000`，使 `/output/...` 可外网访问
2. 留空 `PUBLIC_BASE_URL`，保持 `PUBLIC_FILE_HOST=auto`（默认），生成前自动上传临时公网链接（文件会离开本机，注意隐私）

## 后端启动

```bash
pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/health
```

## 前端启动

```bash
cd frontend
pnpm install
pnpm dev
```

默认访问地址：

```text
http://127.0.0.1:8888
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 已实现接口

- `GET /api/health`
- `GET /api/audio/voices`
- `POST /api/scripts/process`
- `POST /api/audio/generate`
- `POST /api/video/generate`
- `POST /api/workflows/generate`

## 当前限制

声音克隆目前按火山官方异步长文本 TTS 文档接入，使用的是已经复刻好的 `Speaker ID`。控制台里的“上传参考音频生成”属于体验中心能力，未在当前代码中硬编码控制台内部接口。

视频生成模块默认使用火山视觉「单图音频驱动」：先 `CVSubmitTask` 创建形象拿到 `resource_id`，再提交音频驱动任务并轮询 `CVGetResult`。未开启真实视频时生成 `output/video/*.json` 占位。
