import { useEffect, useState } from 'react';
import { X, Network, ArrowRight, ArrowLeft, Maximize2 } from 'lucide-react';
import { api } from '../api/client';
import type { NodeDetail, GraphNode } from '../types';

interface Props {
  node: GraphNode | null;
  onClose: () => void;
  onExpandNeighbors: (nodeId: string) => void;
}

const TYPE_COLORS: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  SalesOrder:    { bg: '#3B82F610', border: '#3B82F630', text: '#93C5FD', dot: '#3B82F6' },
  Delivery:      { bg: '#10B98110', border: '#10B98130', text: '#6EE7B7', dot: '#10B981' },
  Invoice:       { bg: '#F59E0B10', border: '#F59E0B30', text: '#FCD34D', dot: '#F59E0B' },
  JournalEntry:  { bg: '#8B5CF610', border: '#8B5CF630', text: '#C4B5FD', dot: '#8B5CF6' },
  Customer:      { bg: '#EF444410', border: '#EF444430', text: '#FCA5A5', dot: '#EF4444' },
  Product:       { bg: '#06B6D410', border: '#06B6D430', text: '#67E8F9', dot: '#06B6D4' },
  Plant:         { bg: '#84CC1610', border: '#84CC1630', text: '#BEF264', dot: '#84CC16' },
  Payment:       { bg: '#F9731610', border: '#F9731630', text: '#FDBA74', dot: '#F97316' },
};

export function NodeMetadataPanel({ node, onClose, onExpandNeighbors }: Props) {
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!node) { setDetail(null); return; }
    setLoading(true);
    api.getNodeDetail(node.id).then(setDetail).catch(console.error).finally(() => setLoading(false));
  }, [node?.id]);

  if (!node) return null;

  const theme = TYPE_COLORS[node.type] ?? { bg: '#ffffff08', border: '#ffffff15', text: '#ffffff60', dot: '#6B7280' };

  return (
    <div className="absolute top-4 left-4 z-20 w-72 rounded-2xl overflow-hidden shadow-2xl border"
      style={{ background: 'rgba(10,11,15,0.92)', borderColor: 'rgba(255,255,255,0.08)', backdropFilter: 'blur(20px)' }}>

      {/* Header */}
      <div className="p-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: theme.dot, boxShadow: `0 0 6px ${theme.dot}80` }} />
              <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: theme.text }}>
                {node.type}
              </span>
            </div>
            <p className="text-sm font-semibold text-white/85 leading-tight truncate">{node.label}</p>
          </div>
          <button onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-white/10 text-white/30 hover:text-white/60 transition-colors shrink-0">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Metadata */}
      <div className="p-4 max-h-64 overflow-y-auto">
        {loading ? (
          <div className="space-y-2.5">
            {[...Array(6)].map((_,i) => (
              <div key={i} className="h-3 rounded-full animate-pulse" style={{ background: 'rgba(255,255,255,0.06)', width: `${60 + (i % 3) * 15}%` }} />
            ))}
          </div>
        ) : detail ? (
          <div className="space-y-2">
            {Object.entries(detail.metadata)
              .filter(([, v]) => v !== null && v !== '' && v !== '0')
              .slice(0, 12)
              .map(([key, value]) => (
                <div key={key} className="flex justify-between gap-3 py-1 border-b" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
                  <span className="text-[11px] text-white/30 capitalize shrink-0 leading-tight">
                    {key.replace(/([A-Z])/g, ' $1').trim()}
                  </span>
                  <span className="text-[11px] text-white/65 font-medium text-right leading-tight" style={{ maxWidth: '55%', wordBreak: 'break-all' }}>
                    {String(value)}
                  </span>
                </div>
              ))}
            {Object.keys(detail.metadata).length > 12 && (
              <p className="text-[10px] text-white/20 italic pt-1">+{Object.keys(detail.metadata).length - 12} more fields hidden</p>
            )}
          </div>
        ) : (
          <p className="text-xs text-white/20">No metadata available</p>
        )}
      </div>

      {/* Connections */}
      {detail && (
        <div className="px-4 pb-3 border-t" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          <div className="flex items-center gap-2 pt-3 mb-2">
            <Network size={11} className="text-white/25" />
            <span className="text-[11px] text-white/30">
              <strong className="text-white/60">{detail.connections}</strong> connections
            </span>
          </div>
          {detail.predecessors.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap mb-1">
              <ArrowLeft size={9} className="text-white/20 shrink-0" />
              {detail.predecessors.slice(0, 3).map(p => (
                <span key={p} className="text-[10px] px-1.5 py-0.5 rounded-md text-white/40 border border-white/10"
                  style={{ background: 'rgba(255,255,255,0.04)' }}>
                  {p.split('_')[0]}
                </span>
              ))}
              {detail.predecessors.length > 3 && <span className="text-[10px] text-white/20">+{detail.predecessors.length - 3}</span>}
            </div>
          )}
          {detail.successors.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <ArrowRight size={9} className="text-white/20 shrink-0" />
              {detail.successors.slice(0, 3).map(s => (
                <span key={s} className="text-[10px] px-1.5 py-0.5 rounded-md text-white/40 border border-white/10"
                  style={{ background: 'rgba(255,255,255,0.04)' }}>
                  {s.split('_')[0]}
                </span>
              ))}
              {detail.successors.length > 3 && <span className="text-[10px] text-white/20">+{detail.successors.length - 3}</span>}
            </div>
          )}
        </div>
      )}

      {/* Expand button */}
      <div className="px-4 pb-4">
        <button
          onClick={() => onExpandNeighbors(node.id)}
          className="w-full flex items-center justify-center gap-2 py-2 rounded-xl text-xs font-medium transition-all border"
          style={{ background: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.5)' }}
          onMouseEnter={e => { (e.target as HTMLElement).style.background = 'rgba(255,255,255,0.09)'; (e.target as HTMLElement).style.color = 'rgba(255,255,255,0.8)'; }}
          onMouseLeave={e => { (e.target as HTMLElement).style.background = 'rgba(255,255,255,0.05)'; (e.target as HTMLElement).style.color = 'rgba(255,255,255,0.5)'; }}
        >
          <Maximize2 size={12} />
          Expand Neighbors
        </button>
      </div>
    </div>
  );
}