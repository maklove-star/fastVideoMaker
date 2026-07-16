<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
  X,
} from '@lucide/vue';
import {
  createCopywriting,
  deleteCopywriting,
  listCopywriting,
  updateCopywriting,
} from '../api/digitalHuman';
import type { CopywritingItem, InputMode } from '../types';

const router = useRouter();

const items = ref<CopywritingItem[]>([]);
const total = ref(0);
const keyword = ref('');
const loading = ref(false);
const saving = ref(false);
const errorMessage = ref('');
const successMessage = ref('');
const editorOpen = ref(false);
const editingId = ref<string | null>(null);

const draft = reactive({
  title: '',
  content: '',
  tags: '',
  notes: '',
  inputMode: 'direct' as InputMode,
});

const editorTitle = computed(() => (editingId.value ? '编辑文案' : '新建文案'));

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

function previewText(content: string): string {
  const text = content.replace(/\s+/g, ' ').trim();
  return text.length > 120 ? `${text.slice(0, 117)}...` : text;
}

function resetDraft() {
  draft.title = '';
  draft.content = '';
  draft.tags = '';
  draft.notes = '';
  draft.inputMode = 'direct';
  editingId.value = null;
}

function openCreate() {
  resetDraft();
  editorOpen.value = true;
  errorMessage.value = '';
  successMessage.value = '';
}

function openEdit(item: CopywritingItem) {
  editingId.value = item.id;
  draft.title = item.title;
  draft.content = item.content;
  draft.tags = item.tags || '';
  draft.notes = item.notes || '';
  draft.inputMode = item.inputMode || 'direct';
  editorOpen.value = true;
  errorMessage.value = '';
  successMessage.value = '';
}

function closeEditor() {
  editorOpen.value = false;
  resetDraft();
}

async function refreshList() {
  loading.value = true;
  errorMessage.value = '';
  try {
    const data = await listCopywriting({ q: keyword.value.trim(), limit: 100 });
    items.value = data.items || [];
    total.value = data.total || 0;
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载文案列表失败';
  } finally {
    loading.value = false;
  }
}

async function saveDraft() {
  const content = draft.content.trim();
  if (!content) {
    errorMessage.value = '文案内容不能为空。';
    return;
  }
  saving.value = true;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    const payload = {
      title: draft.title.trim(),
      content,
      tags: draft.tags.trim(),
      notes: draft.notes.trim(),
      inputMode: draft.inputMode,
    };
    if (editingId.value) {
      await updateCopywriting(editingId.value, payload);
      successMessage.value = '文案已更新';
    } else {
      await createCopywriting(payload);
      successMessage.value = '文案已创建';
    }
    closeEditor();
    await refreshList();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '保存失败';
  } finally {
    saving.value = false;
  }
}

async function removeItem(item: CopywritingItem) {
  if (!window.confirm(`确定删除「${item.title}」？`)) return;
  errorMessage.value = '';
  successMessage.value = '';
  try {
    await deleteCopywriting(item.id);
    if (editingId.value === item.id) closeEditor();
    successMessage.value = '已删除';
    await refreshList();
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '删除失败';
  }
}

function useItem(item: CopywritingItem) {
  void router.push({ name: 'workspace', query: { scriptId: item.id } });
}

onMounted(() => {
  void refreshList();
});
</script>

<template>
  <div class="app-shell library-shell">
    <header class="library-header panel">
      <div class="library-header-main">
        <button class="icon-button" type="button" title="返回工作台" @click="router.push({ name: 'workspace' })">
          <ArrowLeft :size="18" />
        </button>
        <div>
          <span class="eyebrow">Copywriting Library</span>
          <h1>文案库</h1>
        </div>
      </div>
      <div class="library-header-actions">
        <label class="library-search">
          <Search :size="16" />
          <input
            v-model="keyword"
            type="search"
            placeholder="搜索标题 / 正文 / 标签"
            @keydown.enter.prevent="refreshList"
          />
        </label>
        <button class="small-action" type="button" @click="refreshList">
          <Loader2 v-if="loading" :size="17" class="spin" />
          <Search v-else :size="17" />
          <span>搜索</span>
        </button>
        <button class="primary-action" type="button" @click="openCreate">
          <Plus :size="17" />
          <span>新建文案</span>
        </button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-message compact-message">
      <AlertTriangle :size="16" />
      <span>{{ errorMessage }}</span>
    </p>
    <p v-if="successMessage" class="hint-message compact-message">
      <CheckCircle2 :size="16" />
      <span>{{ successMessage }}</span>
    </p>

    <section class="library-layout">
      <div class="panel library-list-panel">
        <div class="panel-heading tight">
          <div>
            <span class="eyebrow">共 {{ total }} 篇</span>
            <h2>文案列表</h2>
          </div>
        </div>

        <div v-if="loading && !items.length" class="library-empty">加载中…</div>
        <div v-else-if="!items.length" class="library-empty">
          暂无文案，点击右上角「新建文案」开始管理。
        </div>
        <ul v-else class="library-list">
          <li v-for="item in items" :key="item.id" class="library-card">
            <div class="library-card-main">
              <h3>{{ item.title }}</h3>
              <p>{{ previewText(item.content) }}</p>
              <div class="library-meta">
                <span>{{ item.wordCount }} 字</span>
                <span v-if="item.tags">{{ item.tags }}</span>
                <span>更新于 {{ formatTime(item.updatedAt) }}</span>
              </div>
            </div>
            <div class="library-card-actions">
              <button class="small-action" type="button" @click="useItem(item)">选用</button>
              <button class="icon-button" type="button" title="编辑" @click="openEdit(item)">
                <Pencil :size="16" />
              </button>
              <button class="icon-button danger" type="button" title="删除" @click="removeItem(item)">
                <Trash2 :size="16" />
              </button>
            </div>
          </li>
        </ul>
      </div>

      <aside v-if="editorOpen" class="panel library-editor-panel">
        <div class="panel-heading tight">
          <div>
            <span class="eyebrow">Editor</span>
            <h2>{{ editorTitle }}</h2>
          </div>
          <button class="icon-button" type="button" title="关闭" @click="closeEditor">
            <X :size="18" />
          </button>
        </div>

        <label class="field wide-field">
          <span>标题</span>
          <input v-model="draft.title" type="text" maxlength="120" placeholder="例如：今日复盘口播" />
        </label>

        <label class="field wide-field">
          <span>标签（逗号分隔）</span>
          <input v-model="draft.tags" type="text" maxlength="200" placeholder="财经, 复盘, 抖音" />
        </label>

        <label class="field wide-field">
          <span>输入模式</span>
          <select v-model="draft.inputMode">
            <option value="direct">直接使用</option>
            <option value="polish">润色文案</option>
            <option value="generate">AI 生成</option>
          </select>
        </label>

        <label class="field wide-field">
          <span>正文</span>
          <textarea v-model="draft.content" rows="14" maxlength="20000" placeholder="在这里编写口播文案…" />
        </label>

        <label class="field wide-field">
          <span>备注</span>
          <textarea v-model="draft.notes" rows="3" maxlength="1000" placeholder="可选：来源、用途、版本说明" />
        </label>

        <div class="library-editor-actions">
          <button class="small-action" type="button" @click="closeEditor">取消</button>
          <button class="primary-action" type="button" :disabled="saving" @click="saveDraft">
            <Loader2 v-if="saving" :size="17" class="spin" />
            <span>{{ saving ? '保存中' : '保存' }}</span>
          </button>
        </div>
      </aside>
    </section>
  </div>
</template>
