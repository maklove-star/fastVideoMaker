<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type { Component } from 'vue';
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Download,
  FileText,
  Hash,
  ImagePlus,
  Link2,
  Loader2,
  Mic2,
  Monitor,
  RefreshCcw,
  History,
  Smartphone,
  Sparkles,
  UploadCloud,
  Video,
  Volume2,
  Wand2,
  XCircle,
} from '@lucide/vue';
import { generateAudio, generateVideo, listAudioHistory, listVoices, previewAudio, processScript, uploadPortrait } from './api/digitalHuman';
import type {
  AudioGenerateResult,
  AudioHistoryItem,
  InputMode,
  StepState,
  VideoGenerateResult,
  VoiceOption,
  WorkflowPayload,
  WorkflowResult,
  WorkflowStepKey,
} from './types';

interface ModeOption {
  value: InputMode;
  label: string;
  icon: Component;
}

interface StepItem {
  key: WorkflowStepKey;
  label: string;
  state: StepState;
}

const defaultVoices: VoiceOption[] = [
  { id: 'zh_female_shuangkuaisisi_uranus_bigtts', name: '爽快思思 2.0', style: '通用场景', resourceId: 'seed-tts-2.0' },
  { id: 'zh_female_vv_uranus_bigtts', name: 'Vivi 2.0', style: '通用场景', resourceId: 'seed-tts-2.0' },
  { id: 'zh_male_m191_uranus_bigtts', name: '云舟 2.0', style: '通用场景', resourceId: 'seed-tts-2.0' },
];

const modeOptions: ModeOption[] = [
  { value: 'generate', label: 'AI 生成', icon: Sparkles },
  { value: 'polish', label: '润色文案', icon: Wand2 },
  { value: 'direct', label: '直接使用', icon: FileText },
];

const form = reactive<WorkflowPayload>({
  inputMode: 'generate',
  userInput: '',
  extractUrl: false,
  title: '',
  description: '',
  portraitAssetId: '',
  voiceId: defaultVoices[0].id,
  speedRatio: 1,
  volumeRatio: 1,
  pitchRatio: 1,
  resolution: '720p',
  volcCvMode: 'normal',
  publishNow: false,
  platforms: [],
});

const steps = reactive<StepItem[]>([
  { key: 'script', label: '文案处理', state: 'idle' },
  { key: 'audio', label: '音频生成', state: 'idle' },
  { key: 'video', label: '数字人视频', state: 'idle' },
]);

const voiceOptions = ref<VoiceOption[]>(defaultVoices);
const voiceKeyword = ref('');
const result = ref<WorkflowResult | null>(null);
const audioResult = ref<AudioGenerateResult | null>(null);
const audioHistory = ref<AudioHistoryItem[]>([]);
const selectedAudioHistoryId = ref('');
const audioHistoryLoading = ref(false);
const videoResult = ref<VideoGenerateResult | null>(null);
const voicePreviewUrl = ref('');
const voicePreviewHint = ref('');
const scriptErrorMessage = ref('');
const audioErrorMessage = ref('');
const videoErrorMessage = ref('');
const voicePreviewError = ref('');
const scriptProcessing = ref(false);
const audioGenerating = ref(false);
const voicePreviewing = ref(false);
const videoGenerating = ref(false);
const portraitUploading = ref(false);
const portraitPreviewUrl = ref('');
const portraitFileName = ref('');
const portraitErrorMessage = ref('');
const portraitInput = ref<HTMLInputElement | null>(null);
const loadingVoices = ref(false);
const audioUnlocked = ref(false);
const apiStatus = ref<'checking' | 'ready' | 'offline'>('checking');
const previewPlayer = ref<HTMLAudioElement | null>(null);

const inputLabel = computed(() => {
  if (form.inputMode === 'generate') return '主题或关键词';
  if (form.inputMode === 'polish') return '待润色文案或链接';
  return '口播文案';
});

const inputPlaceholder = computed(() => {
  if (form.inputMode === 'generate') return '例如：AI 工具如何提升短视频团队的选题效率';
  if (form.inputMode === 'polish') return '粘贴已有文案，或粘贴抖音分享口令 / 链接用于提取';
  return '粘贴口播文案；抖音分享口令可点「提取链接文案」自动听视频转写口播全文';
});

const estimatedDuration = computed(() => {
  const length = form.userInput.trim().length || 240;
  return Math.min(90, Math.max(15, Math.round(length / 4.2)));
});

const canUseAudioConfig = computed(() => {
  return Boolean(form.voiceId);
});

const canGenerateAudio = computed(() => {
  return Boolean(form.userInput.trim() && canUseAudioConfig.value);
});

const filteredVoices = computed(() => {
  const keyword = voiceKeyword.value.trim().toLowerCase();
  const selected = voiceOptions.value.find((voice) => voice.id === form.voiceId);
  if (!keyword) return voiceOptions.value;
  const matched = voiceOptions.value.filter((voice) => {
    const haystack = `${voice.name} ${voice.style || ''} ${voice.id} ${voice.resourceId || ''}`.toLowerCase();
    return haystack.includes(keyword);
  });
  if (selected && !matched.some((voice) => voice.id === selected.id)) {
    return [selected, ...matched];
  }
  return matched;
});

const selectedVoiceLabel = computed(() => {
  const voice = voiceOptions.value.find((item) => item.id === form.voiceId);
  if (!voice) return form.voiceId;
  return `${voice.name}${voice.style ? ` · ${voice.style}` : ''}`;
});

const canExtractLinkScript = computed(() => {
  return Boolean(form.userInput.trim() && !scriptProcessing.value);
});

const latestAudioPath = computed(() => {
  return result.value?.audioPath || audioResult.value?.audioPath || '';
});

const latestAudioRemoteUrl = computed(() => {
  const candidates = [
    result.value?.sourceAudioUrl,
    audioResult.value?.sourceAudioUrl,
    result.value?.audioUrl,
    audioResult.value?.audioUrl,
  ];
  for (const url of candidates) {
    if (!url) continue;
    // Only pass true remote URLs to the video API; /output/... is local.
    if (url.startsWith('https://') || url.startsWith('http://')) {
      if (url.includes('127.0.0.1') || url.includes('localhost')) continue;
      return url;
    }
  }
  return '';
});

const scriptForVideo = computed(() => {
  return result.value?.script || form.userInput.trim();
});

const canGenerateVideo = computed(() => {
  return Boolean(form.portraitAssetId.trim() && latestAudioPath.value && scriptForVideo.value.trim());
});

const audioPreviewUrl = computed(() => {
  return result.value?.audioUrl || audioResult.value?.audioUrl || '';
});

const audioDownloadName = computed(() => {
  const path = latestAudioPath.value || audioPreviewUrl.value;
  const parts = path.split(/[/\\]/);
  const name = parts[parts.length - 1] || 'voiceover.mp3';
  return name.endsWith('.mp3') ? name : `${name}.mp3`;
});

const videoPreviewUrl = computed(() => {
  return result.value?.videoUrl || videoResult.value?.videoUrl || result.value?.sourceVideoUrl || videoResult.value?.sourceVideoUrl || '';
});

const showVideoPlayer = computed(() => {
  const url = videoPreviewUrl.value.toLowerCase();
  return Boolean(url && (url.includes('.mp4') || url.includes('.mov') || url.includes('.webm')));
});

function resetSteps() {
  steps.forEach((step) => {
    step.state = 'idle';
  });
}

function setStepState(key: WorkflowStepKey, state: StepState) {
  const step = steps.find((item) => item.key === key);
  if (step) step.state = state;
}

async function refreshVoices() {
  loadingVoices.value = true;
  apiStatus.value = 'checking';
  try {
    const voices = await listVoices();
    voiceOptions.value = voices.length ? voices : defaultVoices;
    if (!voiceOptions.value.some((voice) => voice.id === form.voiceId)) {
      form.voiceId = voiceOptions.value[0]?.id || '';
    }
    apiStatus.value = 'ready';
  } catch {
    voiceOptions.value = defaultVoices;
    apiStatus.value = 'offline';
  } finally {
    loadingVoices.value = false;
  }
}

function formatAudioTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function formatAudioSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function voiceLabel(voiceId?: string): string {
  if (!voiceId) return '';
  const voice = voiceOptions.value.find((item) => item.id === voiceId);
  return voice ? voice.name : voiceId;
}

async function refreshAudioHistory() {
  audioHistoryLoading.value = true;
  try {
    audioHistory.value = await listAudioHistory(50);
    if (
      selectedAudioHistoryId.value &&
      !audioHistory.value.some((item) => item.id === selectedAudioHistoryId.value)
    ) {
      selectedAudioHistoryId.value = '';
    }
  } catch {
    // keep previous list if API temporarily offline
  } finally {
    audioHistoryLoading.value = false;
  }
}

function selectAudioHistory(item: AudioHistoryItem) {
  selectedAudioHistoryId.value = item.id;
  audioResult.value = {
    audioPath: item.audioPath,
    audioUrl: item.audioUrl,
    requestId: item.id,
    sourceAudioUrl: item.sourceAudioUrl,
  };
  result.value = {
    ...(result.value || {}),
    audioPath: item.audioPath,
    audioUrl: item.audioUrl,
    sourceAudioUrl: item.sourceAudioUrl,
  };
  audioErrorMessage.value = '';
  setStepState('audio', 'done');
}

async function unlockPreviewPlayer() {
  const player = previewPlayer.value;
  if (!player || audioUnlocked.value) return;
  // Tiny silent mp3 to keep this element unlocked across awaited TTS requests.
  const silent =
    'data:audio/mpeg;base64,//uQxAAAAAAAAAAAAAAAAAAAAAAAWGluZwAAAA8AAAACAAACcQCAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICA//////////////////////////////////////////////////////////////////8AAAA8TEFNRTMuMTAwAc0AAAAAAAAAABSAJAJAQgAAgAAAAnGpv5G5AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';
  player.src = silent;
  try {
    await player.play();
    player.pause();
    player.currentTime = 0;
    audioUnlocked.value = true;
  } catch {
    // Ignore unlock failures; we still show a manual play hint later.
  }
}

async function runVoicePreview() {
  if (!form.voiceId || voicePreviewing.value) return;

  voicePreviewing.value = true;
  voicePreviewError.value = '';
  voicePreviewHint.value = '';

  try {
    await unlockPreviewPlayer();

    const preview = await previewAudio({
      text: '',
      voiceId: form.voiceId,
      speedRatio: form.speedRatio,
      volumeRatio: form.volumeRatio,
      pitchRatio: form.pitchRatio,
    });
    const url = preview.audioUrl || '';
    if (!url) {
      throw new Error('试听音频未返回地址');
    }
    const playableUrl = `${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`;
    voicePreviewUrl.value = playableUrl;
    apiStatus.value = 'ready';

    const played = await playPreview(playableUrl);
    voicePreviewHint.value = played
      ? `正在试听：${selectedVoiceLabel.value}`
      : '试听音频已生成，请点击下方播放按钮收听';
  } catch (error) {
    voicePreviewError.value = error instanceof Error ? error.message : '音色试听失败';
  } finally {
    voicePreviewing.value = false;
  }
}

async function playPreview(url: string): Promise<boolean> {
  const player = previewPlayer.value;
  if (!player) return false;

  player.pause();
  player.src = url;
  player.load();

  await new Promise<void>((resolve) => {
    const onReady = () => {
      player.removeEventListener('canplay', onReady);
      resolve();
    };
    if (player.readyState >= 2) {
      resolve();
      return;
    }
    player.addEventListener('canplay', onReady, { once: true });
    window.setTimeout(() => {
      player.removeEventListener('canplay', onReady);
      resolve();
    }, 2500);
  });

  try {
    await player.play();
    return true;
  } catch {
    return false;
  }
}

async function runLinkScriptExtraction() {
  if (!canExtractLinkScript.value) return;

  scriptProcessing.value = true;
  scriptErrorMessage.value = '';
  setStepState('script', 'running');

  try {
    const processed = await processScript({
      userInput: form.userInput.trim(),
      mode: 'direct',
      extractUrl: true,
    });
    form.userInput = processed.script;
    form.inputMode = 'direct';
    form.extractUrl = false;
    result.value = {
      ...(result.value || {}),
      script: processed.script,
    };
    audioResult.value = null;
    videoResult.value = null;
    setStepState('script', 'done');
    apiStatus.value = 'ready';
  } catch (error) {
    setStepState('script', 'error');
    apiStatus.value = 'offline';
    scriptErrorMessage.value = error instanceof Error ? error.message : '链接文案提取失败';
  } finally {
    scriptProcessing.value = false;
  }
}

async function runAudioGeneration() {
  if (!canGenerateAudio.value || audioGenerating.value) return;

  audioGenerating.value = true;
  audioErrorMessage.value = '';
  setStepState('audio', 'running');

  try {
    const generatedAudio = await generateAudio({
      text: form.userInput,
      voiceId: form.voiceId,
      speedRatio: form.speedRatio,
      volumeRatio: form.volumeRatio,
      pitchRatio: form.pitchRatio,
    });
    audioResult.value = generatedAudio;
    selectedAudioHistoryId.value = generatedAudio.requestId;
    result.value = {
      ...(result.value || {}),
      jobId: generatedAudio.taskId || generatedAudio.requestId,
      audioPath: generatedAudio.audioPath,
      audioUrl: generatedAudio.audioUrl,
      sourceAudioUrl: generatedAudio.sourceAudioUrl,
    };
    setStepState('audio', 'done');
    apiStatus.value = 'ready';
    void refreshAudioHistory();
  } catch (error) {
    setStepState('audio', 'error');
    apiStatus.value = 'offline';
    audioErrorMessage.value = error instanceof Error ? error.message : '音频生成失败';
  } finally {
    audioGenerating.value = false;
  }
}

async function runVideoGeneration() {
  if (!canGenerateVideo.value || videoGenerating.value) return;

  videoGenerating.value = true;
  videoErrorMessage.value = '';
  setStepState('video', 'running');

  try {
    const generatedVideo = await generateVideo({
      portraitAssetId: form.portraitAssetId,
      audioPath: latestAudioPath.value,
      audioUrl: latestAudioRemoteUrl.value || undefined,
      script: scriptForVideo.value,
      resolution: form.resolution,
      volcCvMode: form.volcCvMode,
    });
    videoResult.value = generatedVideo;
    result.value = {
      ...(result.value || {}),
      videoUrl: generatedVideo.videoUrl,
      localVideoPath: generatedVideo.localVideoPath,
      videoTaskId: generatedVideo.taskId,
      sourceVideoUrl: generatedVideo.sourceVideoUrl,
    };
    setStepState('video', 'done');
    apiStatus.value = 'ready';
  } catch (error) {
    setStepState('video', 'error');
    apiStatus.value = 'offline';
    videoErrorMessage.value = error instanceof Error ? error.message : '视频生成失败';
  } finally {
    videoGenerating.value = false;
  }
}

async function onPortraitSelected(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  portraitUploading.value = true;
  portraitErrorMessage.value = '';

  try {
    const uploaded = await uploadPortrait(file);
    form.portraitAssetId = uploaded.portraitPath;
    portraitPreviewUrl.value = uploaded.portraitUrl;
    portraitFileName.value = uploaded.fileName;
    apiStatus.value = 'ready';
  } catch (error) {
    form.portraitAssetId = '';
    portraitPreviewUrl.value = '';
    portraitFileName.value = '';
    portraitErrorMessage.value = error instanceof Error ? error.message : '人像上传失败';
  } finally {
    portraitUploading.value = false;
    input.value = '';
  }
}

function clearPortrait() {
  form.portraitAssetId = '';
  portraitPreviewUrl.value = '';
  portraitFileName.value = '';
  portraitErrorMessage.value = '';
  if (portraitInput.value) portraitInput.value.value = '';
}

async function downloadGeneratedAudio() {
  if (!audioPreviewUrl.value) return;
  try {
    const response = await fetch(audioPreviewUrl.value);
    if (!response.ok) {
      throw new Error(`下载失败 HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = audioDownloadName.value;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  } catch (error) {
    audioErrorMessage.value = error instanceof Error ? error.message : '音频下载失败';
  }
}

onMounted(() => {
  resetSteps();
  void refreshVoices();
  void refreshAudioHistory();
});
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand-lockup">
        <div class="brand-mark" aria-hidden="true">
          <Video :size="24" />
        </div>
        <div>
          <h1>数字人短视频智能体</h1>
          <span>Vue 3 + FastAPI 工作台</span>
        </div>
      </div>

      <div class="topbar-actions">
        <span class="status-pill" :class="apiStatus">
          <Loader2 v-if="apiStatus === 'checking'" :size="16" class="spin" />
          <CheckCircle2 v-else-if="apiStatus === 'ready'" :size="16" />
          <XCircle v-else :size="16" />
          {{ apiStatus === 'ready' ? 'API 就绪' : apiStatus === 'checking' ? '检查接口' : 'API 未连接' }}
        </span>
        <span class="device-pill">
          <Monitor :size="16" />
          <Smartphone :size="16" />
        </span>
      </div>
    </header>

    <main class="workspace">
      <section class="panel input-panel" aria-labelledby="input-title">
        <div class="panel-heading">
          <div>
            <span class="eyebrow">GLM Script</span>
            <h2 id="input-title">任务输入</h2>
          </div>
          <span class="summary-chip">{{ estimatedDuration }} 秒预估</span>
        </div>

        <div class="segmented" role="tablist" aria-label="输入模式">
          <button
            v-for="mode in modeOptions"
            :key="mode.value"
            type="button"
            :class="{ active: form.inputMode === mode.value }"
            @click="form.inputMode = mode.value"
          >
            <component :is="mode.icon" :size="18" />
            <span>{{ mode.label }}</span>
          </button>
        </div>

        <label class="field wide-field">
          <span>{{ inputLabel }}</span>
          <textarea
            v-model="form.userInput"
            :placeholder="inputPlaceholder"
            rows="9"
            maxlength="20000"
          />
        </label>

        <div class="inline-controls">
          <label class="switch-line">
            <input v-model="form.extractUrl" type="checkbox" />
            <span class="switch" aria-hidden="true"></span>
            <span>提取链接正文</span>
          </label>
          <div class="script-actions">
            <button
              class="small-action"
              type="button"
              :disabled="!canExtractLinkScript"
              @click="runLinkScriptExtraction"
            >
              <Loader2 v-if="scriptProcessing" :size="17" class="spin" />
              <Link2 v-else :size="17" />
              <span>{{ scriptProcessing ? '听视频转写中' : '提取链接文案' }}</span>
            </button>
            <span class="counter">{{ form.userInput.length }}/20000</span>
          </div>
        </div>

        <p v-if="scriptErrorMessage" class="error-message compact-message">
          <AlertTriangle :size="16" />
          <span>{{ scriptErrorMessage }}</span>
        </p>
      </section>

      <section class="panel config-panel" aria-labelledby="config-title">
        <div class="panel-heading">
          <div>
            <span class="eyebrow">Doubao Audio</span>
            <h2 id="config-title">音频生成</h2>
          </div>
          <Mic2 :size="20" />
        </div>

        <div class="voice-toolbar">
          <label class="field voice-search">
            <span>搜索音色（共 {{ voiceOptions.length }}）</span>
            <input v-model="voiceKeyword" type="search" placeholder="名称 / 场景 / voice_type" />
          </label>
          <button class="icon-button" type="button" title="刷新音色列表" @click="refreshVoices">
            <Loader2 v-if="loadingVoices" :size="18" class="spin" />
            <RefreshCcw v-else :size="18" />
          </button>
        </div>

        <div class="voice-row">
          <label class="field">
            <span>音色 · {{ filteredVoices.length }} 可选</span>
            <select v-model="form.voiceId">
              <option v-for="voice in filteredVoices" :key="voice.id" :value="voice.id">
                {{ voice.name }}{{ voice.style ? ` · ${voice.style}` : '' }} · {{ voice.resourceId === 'seed-tts-2.0' ? '2.0' : '1.0' }}
              </option>
            </select>
          </label>
          <button
            class="preview-button"
            type="button"
            :disabled="!form.voiceId || voicePreviewing"
            title="试听当前音色"
            @click="runVoicePreview"
          >
            <Loader2 v-if="voicePreviewing" :size="18" class="spin" />
            <Volume2 v-else :size="18" />
            <span>{{ voicePreviewing ? '试听中' : '试听' }}</span>
          </button>
        </div>

        <p class="voice-hint">当前：{{ selectedVoiceLabel }}</p>
        <audio
          ref="previewPlayer"
          class="voice-preview-player"
          :class="{ ready: Boolean(voicePreviewUrl) }"
          :src="voicePreviewUrl || undefined"
          controls
          preload="auto"
        />
        <p v-if="voicePreviewHint" class="voice-hint success">{{ voicePreviewHint }}</p>

        <p v-if="voicePreviewError" class="error-message compact-message">
          <AlertTriangle :size="16" />
          <span>{{ voicePreviewError }}</span>
        </p>

        <div class="tts-params">
          <label class="field slider-field">
            <span>语速 <em>{{ form.speedRatio.toFixed(1) }}x</em></span>
            <input v-model.number="form.speedRatio" type="range" min="0.5" max="2" step="0.1" />
          </label>
          <label class="field slider-field">
            <span>音量 <em>{{ form.volumeRatio.toFixed(1) }}x</em></span>
            <input v-model.number="form.volumeRatio" type="range" min="0.5" max="2" step="0.1" />
          </label>
          <label class="field slider-field">
            <span>音调 <em>{{ form.pitchRatio.toFixed(1) }}x</em></span>
            <input v-model.number="form.pitchRatio" type="range" min="0.5" max="2" step="0.1" />
          </label>
        </div>

        <div class="audio-actions">
          <button class="primary-action" type="button" :disabled="!canGenerateAudio || audioGenerating" @click="runAudioGeneration">
            <Loader2 v-if="audioGenerating" :size="19" class="spin" />
            <Mic2 v-else :size="19" />
            <span>{{ audioGenerating ? '音频生成中' : '生成音频' }}</span>
          </button>
          <button
            class="secondary-action download-action"
            type="button"
            :disabled="!audioPreviewUrl"
            @click="downloadGeneratedAudio"
          >
            <Download :size="19" />
            <span>下载音频</span>
          </button>
        </div>

        <div class="audio-history">
          <div class="audio-history-head">
            <div class="audio-history-title">
              <History :size="16" />
              <span>历史音频</span>
            </div>
            <button
              class="icon-button"
              type="button"
              title="刷新历史"
              :disabled="audioHistoryLoading"
              @click="refreshAudioHistory"
            >
              <Loader2 v-if="audioHistoryLoading" :size="16" class="spin" />
              <RefreshCcw v-else :size="16" />
            </button>
          </div>
          <p v-if="!audioHistory.length && !audioHistoryLoading" class="voice-hint">暂无历史，生成后会出现在这里，可直接选用。</p>
          <ul v-else class="audio-history-list">
            <li v-for="item in audioHistory" :key="item.id">
              <button
                type="button"
                class="audio-history-item"
                :class="{ active: selectedAudioHistoryId === item.id || latestAudioPath === item.audioPath }"
                @click="selectAudioHistory(item)"
              >
                <span class="audio-history-name">{{ item.fileName }}</span>
                <span class="audio-history-meta">
                  {{ formatAudioTime(item.createdAt) }}
                  · {{ formatAudioSize(item.sizeBytes) }}
                  <template v-if="item.voiceId"> · {{ voiceLabel(item.voiceId) }}</template>
                </span>
                <span v-if="item.textPreview" class="audio-history-preview">{{ item.textPreview }}</span>
              </button>
            </li>
          </ul>
        </div>

        <p v-if="audioErrorMessage" class="error-message">
          <AlertTriangle :size="16" />
          <span>{{ audioErrorMessage }}</span>
        </p>
      </section>

      <aside class="side-stack">
        <section class="panel video-panel" aria-labelledby="video-title">
          <div class="panel-heading">
            <div>
              <span class="eyebrow">Volc CV · 单图音频驱动</span>
              <h2 id="video-title">视频生成</h2>
            </div>
            <Video :size="20" />
          </div>

          <div class="video-config">
            <div class="portrait-upload">
              <input
                ref="portraitInput"
                class="sr-only"
                type="file"
                accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                @change="onPortraitSelected"
              />
              <button
                class="secondary-action portrait-upload-button"
                type="button"
                :disabled="portraitUploading"
                @click="portraitInput?.click()"
              >
                <Loader2 v-if="portraitUploading" :size="18" class="spin" />
                <ImagePlus v-else :size="18" />
                <span>{{ portraitUploading ? '上传中' : portraitPreviewUrl ? '重新上传人像' : '上传人像图片' }}</span>
              </button>
              <button
                v-if="portraitPreviewUrl"
                class="icon-button"
                type="button"
                title="清除人像"
                @click="clearPortrait"
              >
                <XCircle :size="18" />
              </button>
            </div>

            <div v-if="portraitPreviewUrl" class="portrait-preview">
              <img :src="portraitPreviewUrl" :alt="portraitFileName || '人像预览'" />
              <span v-if="portraitFileName">{{ portraitFileName }}</span>
            </div>
            <p v-else class="voice-hint">支持 JPG / PNG / WEBP。本地开发未配置 PUBLIC_BASE_URL 时，会自动上传临时公网地址供火山拉取。</p>

            <label class="field">
              <span>驱动模式</span>
              <select v-model="form.volcCvMode">
                <option value="normal">普通模式（嘴部）</option>
                <option value="loopy">灵动模式（全脸）</option>
                <option value="loopyb">大画幅灵动</option>
              </select>
            </label>

            <p v-if="portraitErrorMessage" class="error-message compact-message">
              <AlertTriangle :size="16" />
              <span>{{ portraitErrorMessage }}</span>
            </p>
          </div>

          <p class="voice-hint">使用已生成音频做口型驱动（火山单图音频驱动），不重新 TTS。</p>

          <button class="primary-action" type="button" :disabled="!canGenerateVideo || videoGenerating" @click="runVideoGeneration">
            <Loader2 v-if="videoGenerating" :size="19" class="spin" />
            <Video v-else :size="19" />
            <span>{{ videoGenerating ? '视频生成中' : '生成视频' }}</span>
          </button>

          <p v-if="videoErrorMessage" class="error-message">
            <AlertTriangle :size="16" />
            <span>{{ videoErrorMessage }}</span>
          </p>
        </section>

        <section class="panel result-panel" aria-labelledby="result-title">
          <div class="panel-heading tight">
            <div>
              <span class="eyebrow">Output</span>
              <h2 id="result-title">生成结果</h2>
            </div>
            <UploadCloud :size="20" />
          </div>

          <ol class="timeline compact-timeline">
            <li v-for="step in steps" :key="step.key" :class="step.state">
              <span class="step-icon">
                <Loader2 v-if="step.state === 'running'" :size="16" class="spin" />
                <CheckCircle2 v-else-if="step.state === 'done'" :size="16" />
                <AlertTriangle v-else-if="step.state === 'error'" :size="16" />
                <Circle v-else :size="16" />
              </span>
              <span>{{ step.label }}</span>
            </li>
          </ol>

          <div v-if="audioPreviewUrl" class="audio-player">
            <Mic2 :size="18" />
            <audio :src="audioPreviewUrl" controls />
            <button class="icon-button" type="button" title="下载音频" @click="downloadGeneratedAudio">
              <Download :size="18" />
            </button>
          </div>

          <div class="result-frame">
            <video v-if="showVideoPlayer" class="video-player" :src="videoPreviewUrl" controls playsinline />
            <div v-else-if="videoPreviewUrl || result?.localVideoPath || videoResult?.localVideoPath" class="video-placeholder ready">
              <Video :size="36" />
              <span>{{ videoPreviewUrl || result?.localVideoPath || videoResult?.localVideoPath }}</span>
            </div>
            <div v-else class="video-placeholder">
              <Video :size="36" />
              <span>{{ audioPreviewUrl ? '音频已生成，等待视频生成' : '等待生成' }}</span>
            </div>
          </div>

          <dl class="result-list">
            <div>
              <dt><Hash :size="15" />任务 ID</dt>
              <dd>{{ result?.videoTaskId || videoResult?.taskId || result?.jobId || audioResult?.taskId || audioResult?.requestId || '未创建' }}</dd>
            </div>
            <div>
              <dt><Mic2 :size="15" />音频</dt>
              <dd>{{ result?.audioPath || audioResult?.audioPath || '未生成' }}</dd>
            </div>
          </dl>
        </section>
      </aside>
    </main>
  </div>
</template>
