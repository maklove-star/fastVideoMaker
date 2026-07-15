export type InputMode = 'generate' | 'polish' | 'direct';

export type Platform = 'douyin' | 'xiaohongshu' | 'kuaishou';

export type WorkflowStepKey = 'script' | 'audio' | 'video' | 'publish';

export type StepState = 'idle' | 'running' | 'done' | 'error';

export interface VoiceOption {
  id: string;
  name: string;
  style?: string;
  resourceId?: string;
}

export interface WorkflowPayload {
  inputMode: InputMode;
  userInput: string;
  extractUrl: boolean;
  title: string;
  description: string;
  portraitAssetId: string;
  voiceId: string;
  speedRatio: number;
  volumeRatio: number;
  pitchRatio: number;
  resolution: '720p' | '1080p';
  volcCvMode: 'normal' | 'loopy' | 'loopyb';
  publishNow: boolean;
  platforms: Platform[];
}

export interface AudioGeneratePayload {
  text: string;
  voiceId: string;
  speedRatio: number;
  volumeRatio: number;
  pitchRatio: number;
}

export interface ScriptProcessPayload {
  userInput: string;
  mode: InputMode;
  extractUrl: boolean;
}

export interface ScriptProcessResult {
  script: string;
}

export interface AudioGenerateResult {
  audioPath: string;
  audioUrl?: string;
  requestId: string;
  taskId?: string;
  sourceAudioUrl?: string;
}

export interface AudioHistoryItem {
  id: string;
  fileName: string;
  audioPath: string;
  audioUrl?: string;
  sourceAudioUrl?: string;
  voiceId?: string;
  textPreview?: string;
  createdAt: string;
  sizeBytes: number;
}

export interface PortraitUploadResult {
  portraitPath: string;
  portraitUrl: string;
  fileName: string;
}

export interface VideoGeneratePayload {
  portraitAssetId: string;
  audioPath: string;
  audioUrl?: string;
  script: string;
  resolution: '720p' | '1080p';
  volcCvMode?: 'normal' | 'loopy' | 'loopyb';
}

export interface VideoGenerateResult {
  videoUrl?: string;
  localVideoPath?: string;
  taskId?: string;
  sourceVideoUrl?: string;
}

export interface PublishResult {
  platform: Platform;
  status: 'success' | 'failed' | 'skipped';
  message?: string;
  url?: string;
}

export interface WorkflowResult {
  jobId?: string;
  script?: string;
  audioPath?: string;
  audioUrl?: string;
  sourceAudioUrl?: string;
  videoUrl?: string;
  localVideoPath?: string;
  videoTaskId?: string;
  sourceVideoUrl?: string;
  publishResults?: PublishResult[];
}
