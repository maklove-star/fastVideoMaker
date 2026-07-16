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
  resolution: '720p' | '1080p' | '4k';
  aspectRatio: 'auto' | '16:9' | '9:16' | '4:5' | '5:4' | '1:1';
  fit: '' | 'contain' | 'cover';
  removeBackground: boolean;
  outputFormat: 'mp4' | 'webm';
  expressiveness: 'low' | 'medium' | 'high';
  motionPrompt: string;
  backgroundType: 'none' | 'color';
  backgroundColor: string;
  burnCaptions: boolean;
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

export interface VideoHistoryItem {
  id: string;
  fileName: string;
  localVideoPath: string;
  videoUrl?: string;
  sourceVideoUrl?: string;
  taskId?: string;
  textPreview?: string;
  title?: string;
  resolution?: string;
  createdAt: string;
  sizeBytes: number;
}

export interface PortraitUploadResult {
  portraitPath: string;
  portraitUrl: string;
  fileName: string;
}

export interface PortraitHistoryItem {
  id: string;
  fileName: string;
  portraitPath: string;
  portraitUrl: string;
  createdAt: string;
  sizeBytes: number;
}

export interface VideoGeneratePayload {
  portraitAssetId: string;
  audioPath: string;
  audioUrl?: string;
  script: string;
  title?: string;
  resolution: '720p' | '1080p' | '4k';
  aspectRatio?: 'auto' | '16:9' | '9:16' | '4:5' | '5:4' | '1:1';
  fit?: '' | 'contain' | 'cover';
  removeBackground?: boolean;
  outputFormat?: 'mp4' | 'webm';
  expressiveness?: 'low' | 'medium' | 'high';
  motionPrompt?: string;
  backgroundType?: 'none' | 'color';
  backgroundColor?: string;
  burnCaptions?: boolean;
  volcCvMode?: 'normal' | 'loopy' | 'loopyb';
}

export interface VideoGenerateResult {
  videoUrl?: string;
  localVideoPath?: string;
  taskId?: string;
  sourceVideoUrl?: string;
  status?: string;
  message?: string;
  progressPercent?: number;
  videoPageUrl?: string;
}

export interface VideoStatusResult {
  taskId: string;
  status: string;
  message: string;
  progressPercent: number;
  videoUrl?: string;
  localVideoPath?: string;
  sourceVideoUrl?: string;
  videoPageUrl?: string;
  failureCode?: string;
  failureMessage?: string;
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

export interface CopywritingItem {
  id: string;
  title: string;
  content: string;
  tags: string;
  inputMode: InputMode;
  notes: string;
  wordCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface CopywritingPayload {
  title?: string;
  content: string;
  tags?: string;
  inputMode?: InputMode;
  notes?: string;
}

export interface CopywritingListResult {
  items: CopywritingItem[];
  total: number;
}
