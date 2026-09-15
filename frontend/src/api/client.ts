// API client — all backend communication goes through this module
import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120000,
});

// ── Types ──────────────────────────────────────────────────
export interface Session {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface Source {
  chunk_id: string;
  content: string;
  score: number;
  title: string;
  guest: string | null;
  published_date: string | null;
  episode_url: string | null;
  citation: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  llm_provider?: string;
  llm_model?: string;
  latency_ms?: number;
  sources?: Source[];
  retrieval_hits?: number;
}

export interface ChatResponse {
  message_id: string;
  session_id: string;
  content: string;
  role: string;
  sources: Source[];
  retrieval_hits: number;
  provider: string;
  model: string;
  latency_ms: number;
  grounded: boolean;
}

export interface Artifact {
  id: string;
  session_id: string;
  title: string;
  artifact_type: 'markdown' | 'html';
  content: string;
  sanitized_content: string | null;
  security_notes: string;
  created_at: string;
}

export interface ProviderInfo {
  provider: string;
  model: string;
  base_url: string | null;
}

export interface HealthStatus {
  status: string;
  version: string;
  environment: string;
  components: {
    database: { status: string; error?: string };
    vector_store: { status: string; chunk_count?: number; error?: string };
    llm: { status: string; provider?: string; model?: string; error?: string };
  };
}

// ── Sessions ───────────────────────────────────────────────
export const sessionsApi = {
  list: () => api.get<Session[]>('/api/sessions').then(r => r.data),
  create: (title?: string) => api.post<Session>('/api/sessions', { title }).then(r => r.data),
  get: (id: string) => api.get<Session>(`/api/sessions/${id}`).then(r => r.data),
  delete: (id: string) => api.delete(`/api/sessions/${id}`),
  getMessages: (id: string) => api.get<Message[]>(`/api/sessions/${id}/messages`).then(r => r.data),
};

// ── Chat ──────────────────────────────────────────────────
export const chatApi = {
  send: (sessionId: string, message: string) =>
    api.post<ChatResponse>('/api/chat/message', { session_id: sessionId, message }).then(r => r.data),

  getProvider: () => api.get<ProviderInfo>('/api/chat/provider').then(r => r.data),

  generateEssay: (sessionId: string, topic: string, customAngle?: string) =>
    api.post('/api/chat/essay', { session_id: sessionId, topic, custom_angle: customAngle }).then(r => r.data),

  streamUrl: () =>
    `${BASE_URL}/api/chat/stream`,

  streamMessage: async (
    sessionId: string,
    message: string,
    onToken: (token: string) => void,
    onMetadata: (meta: { sources: Source[]; retrieval_hits: number }) => void,
    onError: (err: string) => void,
    onDone: () => void,
  ) => {
    try {
      const response = await fetch(`${BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message, stream: true }),
      });

      if (!response.ok) {
        const err = await response.json();
        onError(err?.error?.message || 'Request failed');
        return;
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) { onError('Stream not available'); return; }

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6);
          if (raw === '[DONE]') { onDone(); return; }
          try {
            const data = JSON.parse(raw);
            if (data.type === 'token') onToken(data.content);
            else if (data.type === 'metadata') onMetadata(data);
            else if (data.type === 'error') onError(data.message);
          } catch { /* skip malformed */ }
        }
      }
      onDone();
    } catch (err: any) {
      onError(err?.message || 'Stream connection failed');
    }
  },
};

// ── Artifacts ─────────────────────────────────────────────
export const artifactsApi = {
  generate: (sessionId: string, artifactType: 'markdown' | 'html', description: string, context: string) =>
    api.post<Artifact>('/api/artifacts', {
      session_id: sessionId,
      artifact_type: artifactType,
      description,
      conversation_context: context,
    }).then(r => r.data),

  get: (id: string) => api.get<Artifact>(`/api/artifacts/${id}`).then(r => r.data),
  listForSession: (sessionId: string) =>
    api.get<Artifact[]>(`/api/artifacts/session/${sessionId}`).then(r => r.data),
};

// ── Health ─────────────────────────────────────────────────
export const healthApi = {
  check: () => api.get<HealthStatus>('/health').then(r => r.data),
};
