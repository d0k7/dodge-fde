import type { GraphData, GraphStats, NodeDetail, AnalyticsSummary } from '../types';

const BASE = import.meta.env.VITE_API_URL || '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const api = {
  async getGraph(): Promise<GraphData> {
    return request('/graph');
  },

  async getGraphStats(): Promise<GraphStats> {
    return request('/graph/stats');
  },

  async getNodeDetail(nodeId: string): Promise<NodeDetail> {
    return request(`/graph/node/${encodeURIComponent(nodeId)}`);
  },

  async getNeighbors(nodeId: string, depth = 1): Promise<GraphData> {
    return request('/graph/neighbors', {
      method: 'POST',
      body: JSON.stringify({ node_id: nodeId, depth }),
    });
  },

  async sendChat(
    query: string,
    history?: { role: string; content: string }[]
  ): Promise<{
    answer: string;
    sql: string | null;
    results: Record<string, unknown>[];
    is_relevant: boolean;
    error: string | null;
    auto_followup?: string | null;
    auto_followup_reason?: string | null;
  }> {
    return request('/chat', {
      method: 'POST',
      body: JSON.stringify({ query, conversation_history: history }),
    });
  },

  async health(): Promise<{ status: string; nodes: number; edges: number }> {
    return request('/health');
  },

  async getSummary(): Promise<AnalyticsSummary> {
    return request('/analytics/summary');
  },
};
