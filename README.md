# 数字人短视频智能体

一个从文案输入到数字人口播视频生成、再到多平台分发的 Python + Vue 自动化项目。

当前版本已接入：

- 前端：Vue 3 + Vite 响应式工作台
- 后端：FastAPI API 骨架
- 文案：火山方舟豆包 Responses API（`doubao-seed-evolving`）
- 音频：豆包音频 1.0，同步接口兜底；异步长文本 TTS 支持声音克隆 Speaker ID
- 视频：HeyGen Image-to-Video（人像图 + 已生成音频做口型驱动）
  文档：https://developers.heygen.com/image-to-video
  Quick start：https://developers.heygen.com/docs/quick-start
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
VIDEO_PROVIDER=heygen
HEYGEN_API_KEY=sk_V2_xxxxxxxxxxxx
HEYGEN_ASPECT_RATIO=auto
```

HeyGen 流程：本地人像/音频先上传到 `POST /v3/assets`，再 `POST /v3/videos`（`type=image` + `audio_asset_id`）做口型驱动，轮询 `GET /v3/videos/{video_id}`。人像建议 JPG/PNG，音频建议 MP3/WAV。
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

视频生成模块默认使用 HeyGen Image-to-Video：本地人像/音频上传 Assets 后，以 `type=image` + `audio_asset_id` 创建视频并轮询结果。未开启真实视频时生成 `output/video/*.json` 占位。
