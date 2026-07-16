from typing import List, Literal, Optional

from pydantic import BaseModel, Field


InputMode = Literal["generate", "polish", "direct"]
Platform = Literal["douyin", "xiaohongshu", "kuaishou"]


class VoiceOption(BaseModel):
    id: str
    name: str
    style: Optional[str] = None
    resourceId: Optional[str] = None


class PortraitUploadResponse(BaseModel):
    portraitPath: str
    portraitUrl: str
    fileName: str


class WorkflowPayload(BaseModel):
    inputMode: InputMode = "generate"
    userInput: str = Field(..., min_length=1)
    extractUrl: bool = False
    title: str = ""
    description: str = ""
    portraitAssetId: str = Field(..., min_length=1)
    voiceId: str = "zh_female_shuangkuaisisi_uranus_bigtts"
    speedRatio: float = Field(default=1.0, ge=0.1, le=2.0)
    volumeRatio: float = Field(default=1.0, ge=0.1, le=3.0)
    pitchRatio: float = Field(default=1.0, ge=0.1, le=3.0)
    resolution: Literal["720p", "1080p", "4k"] = "720p"
    aspectRatio: Literal["auto", "16:9", "9:16", "4:5", "5:4", "1:1"] = "auto"
    fit: Optional[Literal["contain", "cover"]] = None
    removeBackground: bool = False
    outputFormat: Literal["mp4", "webm"] = "mp4"
    expressiveness: Literal["low", "medium", "high"] = "low"
    motionPrompt: Optional[str] = None
    backgroundType: Literal["none", "color"] = "none"
    backgroundColor: Optional[str] = "#FFFFFF"
    burnCaptions: bool = False
    publishNow: bool = True
    platforms: List[Platform] = Field(default_factory=lambda: ["douyin", "xiaohongshu"])


class ScriptProcessRequest(BaseModel):
    userInput: str = Field(..., min_length=1)
    mode: InputMode = "generate"
    extractUrl: bool = False


class ScriptProcessResponse(BaseModel):
    script: str


class AudioGenerateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    voiceId: str = "zh_female_shuangkuaisisi_uranus_bigtts"
    speedRatio: float = Field(default=1.0, ge=0.1, le=2.0)
    volumeRatio: float = Field(default=1.0, ge=0.1, le=3.0)
    pitchRatio: float = Field(default=1.0, ge=0.1, le=3.0)
    outputFile: Optional[str] = None


class AudioPreviewRequest(BaseModel):
    voiceId: str = "zh_female_shuangkuaisisi_uranus_bigtts"
    speedRatio: float = Field(default=1.0, ge=0.1, le=2.0)
    volumeRatio: float = Field(default=1.0, ge=0.1, le=3.0)
    pitchRatio: float = Field(default=1.0, ge=0.1, le=3.0)
    text: str = ""


class AudioGenerateResponse(BaseModel):
    audioPath: str
    audioUrl: Optional[str] = None
    requestId: str
    taskId: Optional[str] = None
    sourceAudioUrl: Optional[str] = None


class AudioHistoryItem(BaseModel):
    id: str
    fileName: str
    audioPath: str
    audioUrl: Optional[str] = None
    sourceAudioUrl: Optional[str] = None
    voiceId: Optional[str] = None
    textPreview: Optional[str] = None
    createdAt: str
    sizeBytes: int


class AudioHistoryResponse(BaseModel):
    items: List[AudioHistoryItem] = Field(default_factory=list)


class VideoHistoryItem(BaseModel):
    id: str
    fileName: str
    localVideoPath: str
    videoUrl: Optional[str] = None
    sourceVideoUrl: Optional[str] = None
    taskId: Optional[str] = None
    textPreview: Optional[str] = None
    title: Optional[str] = None
    resolution: Optional[str] = None
    createdAt: str
    sizeBytes: int


class VideoHistoryResponse(BaseModel):
    items: List[VideoHistoryItem] = Field(default_factory=list)


class VideoGenerateRequest(BaseModel):
    portraitAssetId: str = Field(..., min_length=1)
    audioPath: str = Field(..., min_length=1)
    audioUrl: Optional[str] = None
    script: str = Field(..., min_length=1)
    # HeyGen Image-to-Video options
    # https://developers.heygen.com/reference/create-video
    title: Optional[str] = None
    resolution: Literal["720p", "1080p", "4k"] = "720p"
    aspectRatio: Literal["auto", "16:9", "9:16", "4:5", "5:4", "1:1"] = "auto"
    fit: Optional[Literal["contain", "cover"]] = None
    removeBackground: bool = False
    outputFormat: Literal["mp4", "webm"] = "mp4"
    expressiveness: Literal["low", "medium", "high"] = "low"
    motionPrompt: Optional[str] = None
    backgroundType: Literal["none", "color"] = "none"
    backgroundColor: Optional[str] = None
    burnCaptions: bool = False
    volcCvMode: Optional[Literal["normal", "loopy", "loopyb"]] = None


class VideoGenerateResponse(BaseModel):
    videoUrl: Optional[str] = None
    localVideoPath: Optional[str] = None
    taskId: Optional[str] = None
    sourceVideoUrl: Optional[str] = None
    status: Optional[str] = None
    message: Optional[str] = None
    progressPercent: Optional[int] = None
    videoPageUrl: Optional[str] = None


class VideoStatusResponse(BaseModel):
    taskId: str
    status: str
    message: str
    progressPercent: int
    videoUrl: Optional[str] = None
    localVideoPath: Optional[str] = None
    sourceVideoUrl: Optional[str] = None
    videoPageUrl: Optional[str] = None
    failureCode: Optional[str] = None
    failureMessage: Optional[str] = None


class PublishResult(BaseModel):
    platform: Platform
    status: Literal["success", "failed", "skipped"]
    message: Optional[str] = None
    url: Optional[str] = None


class WorkflowResult(BaseModel):
    jobId: str
    script: str
    audioPath: str
    audioUrl: Optional[str] = None
    sourceAudioUrl: Optional[str] = None
    videoUrl: Optional[str] = None
    localVideoPath: Optional[str] = None
    videoTaskId: Optional[str] = None
    sourceVideoUrl: Optional[str] = None
    publishResults: List[PublishResult] = Field(default_factory=list)
