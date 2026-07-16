import type {
  AudioGeneratePayload,
  AudioGenerateResult,
  AudioHistoryItem,
  PortraitUploadResult,
  ScriptProcessPayload,
  ScriptProcessResult,
  VideoGeneratePayload,
  VideoGenerateResult,
  VideoHistoryItem,
  VideoStatusResult,
  VoiceOption,
  WorkflowPayload,
  WorkflowResult,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

async function requestJson<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(formatApiError(detail, response.status));
  }

  return response.json() as Promise<T>;
}

function formatApiError(detail: string, status: number): string {
  try {
    const parsed = JSON.parse(detail) as { detail?: unknown; message?: unknown };
    const payload = parsed.detail ?? parsed.message ?? detail;
    if (typeof payload === 'string') return payload;
    if (Array.isArray(payload)) {
      return payload
        .map((item) => {
          if (typeof item === 'string') return item;
          if (item && typeof item === 'object' && 'msg' in item) return String((item as { msg: unknown }).msg);
          return JSON.stringify(item);
        })
        .join('；');
    }
    if (payload && typeof payload === 'object') return JSON.stringify(payload);
  } catch {
    // keep raw text
  }
  return detail || `HTTP ${status}`;
}

export async function listVoices(): Promise<VoiceOption[]> {
  const data = await requestJson<{ voices: VoiceOption[] } | VoiceOption[]>('/api/audio/voices');
  return Array.isArray(data) ? data : data.voices;
}

export async function listAudioHistory(limit = 50): Promise<AudioHistoryItem[]> {
  const data = await requestJson<{ items: AudioHistoryItem[] }>('/api/audio/history?limit=' + limit);
  return data.items || [];
}

export async function listVideoHistory(limit = 50): Promise<VideoHistoryItem[]> {
  const data = await requestJson<{ items: VideoHistoryItem[] }>('/api/video/history?limit=' + limit);
  return data.items || [];
}

export async function previewAudio(payload: AudioGeneratePayload): Promise<AudioGenerateResult> {
  return requestJson<AudioGenerateResult>('/api/audio/preview', {
    method: 'POST',
    body: JSON.stringify({
      voiceId: payload.voiceId,
      speedRatio: payload.speedRatio,
      volumeRatio: payload.volumeRatio,
      pitchRatio: payload.pitchRatio,
      text: payload.text || '',
    }),
  });
}

export async function startWorkflow(payload: WorkflowPayload): Promise<WorkflowResult> {
  return requestJson<WorkflowResult>('/api/workflows/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function processScript(payload: ScriptProcessPayload): Promise<ScriptProcessResult> {
  return requestJson<ScriptProcessResult>('/api/scripts/process', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function generateAudio(payload: AudioGeneratePayload): Promise<AudioGenerateResult> {
  return requestJson<AudioGenerateResult>('/api/audio/generate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function generateVideo(payload: VideoGeneratePayload): Promise<VideoGenerateResult> {
  return requestJson<VideoGenerateResult>('/api/video/generate', {
    method: 'POST',
    body: JSON.stringify({
      portraitAssetId: payload.portraitAssetId,
      audioPath: payload.audioPath,
      audioUrl: payload.audioUrl,
      script: payload.script,
      title: payload.title || undefined,
      resolution: payload.resolution,
      aspectRatio: payload.aspectRatio || 'auto',
      fit: payload.fit || null,
      removeBackground: Boolean(payload.removeBackground),
      outputFormat: payload.outputFormat || 'mp4',
      expressiveness: payload.expressiveness || 'low',
      motionPrompt: payload.motionPrompt || undefined,
      backgroundType: payload.backgroundType || 'none',
      backgroundColor: payload.backgroundColor || undefined,
      burnCaptions: Boolean(payload.burnCaptions),
      volcCvMode: payload.volcCvMode,
    }),
  });
}

export async function queryVideoStatus(taskId: string): Promise<VideoStatusResult> {
  return requestJson<VideoStatusResult>(`/api/video/status/${encodeURIComponent(taskId)}`);
}

export async function uploadPortrait(file: File): Promise<PortraitUploadResult> {
  const body = new FormData();
  body.append('file', file);

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 60_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/portraits/upload`, {
      method: 'POST',
      body,
      signal: controller.signal,
    });

    if (!response.ok) {
      const detail = await response.text();
      throw new Error(formatApiError(detail, response.status));
    }

    return (await response.json()) as PortraitUploadResult;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('上传超时：请确认后端已启动（http://127.0.0.1:8000）。');
    }
    if (error instanceof TypeError) {
      throw new Error('无法连接后端，请先启动 API 服务。');
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}
