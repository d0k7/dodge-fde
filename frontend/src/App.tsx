import { useState, useEffect, useCallback } from 'react';
import { RefreshCw, PanelRightClose, PanelRightOpen, Activity, GitBranch, Layers, Zap } from 'lucide-react';
import { GraphVisualization } from './components/GraphVisualization';
import { ChatInterface } from './components/ChatInterface';
import { NodeMetadataPanel } from './components/NodeMetadataPanel';
import { api } from './api/client';
import type { GraphData, GraphNode, GraphStats } from './types';

export default function App() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [isGraphLoading, setIsGraphLoading] = useState(true);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [highlightedNodes, setHighlightedNodes] = useState<Set<string>>(new Set());
  const [chatOpen, setChatOpen] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadGraph = useCallback(async () => {
    setIsGraphLoading(true);
    setError(null);
    try {
      const [data, s] = await Promise.all([api.getGraph(), api.getGraphStats()]);
      setGraphData(data);
      setStats(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load graph');
    } finally {
      setIsGraphLoading(false);
    }
  }, []);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    setHighlightedNodes(new Set([node.id]));
  }, []);

  const handleExpandNeighbors = useCallback(async (nodeId: string) => {
    try {
      const sub = await api.getNeighbors(nodeId, 1);
      setGraphData(prev => {
        const existingIds = new Set(prev.nodes.map(n => n.id));
        const existingLinks = new Set(prev.links.map(l => {
          const s = typeof l.source === 'string' ? l.source : (l.source as GraphNode).id;
          const t = typeof l.target === 'string' ? l.target : (l.target as GraphNode).id;
          return `${s}__${t}`;
        }));
        return {
          nodes: [...prev.nodes, ...sub.nodes.filter(n => !existingIds.has(n.id))],
          links: [...prev.links, ...sub.links.filter(l => !existingLinks.has(`${l.source}__${l.target}`))],
        };
      });
      setHighlightedNodes(new Set(sub.nodes.map(n => n.id)));
    } catch (e) { console.error(e); }
  }, []);

  return (
    <div className="flex flex-col h-screen bg-[#0A0B0F] text-white overflow-hidden" style={{ fontFamily: "'Inter', 'DM Sans', sans-serif" }}>
      
      {/* ── Top nav ── */}
      <header className="flex items-center h-14 px-5 border-b border-white/[0.06] shrink-0 bg-[#0D0E14]/80 backdrop-blur-xl z-20">
        <div className="flex items-center gap-2 mr-6">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/25">
            <Layers size={14} className="text-white" />
          </div>
          <span className="text-sm font-semibold text-white/90 tracking-tight">Dodge AI</span>
        </div>

        <div className="flex items-center gap-1.5 text-sm">
          <span className="text-white/30">Mapping</span>
          <span className="text-white/20">/</span>
          <span className="font-medium text-white/90">Order to Cash</span>
        </div>

        {/* Stats pills */}
        {stats && (
          <div className="ml-6 flex items-center gap-2">
            {[
              { icon: GitBranch, label: `${stats.total_nodes} nodes`, color: 'text-blue-400' },
              { icon: Activity,  label: `${stats.total_edges} edges`, color: 'text-emerald-400' },
              { icon: Zap,       label: `${Object.keys(stats.node_types).length} types`, color: 'text-amber-400' },
            ].map(({ icon: Icon, label, color }) => (
              <div key={label} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-white/[0.05] border border-white/[0.08]">
                <Icon size={11} className={color} />
                <span className="text-xs text-white/60 font-medium">{label}</span>
              </div>
            ))}
          </div>
        )}

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={loadGraph}
            disabled={isGraphLoading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white/50 hover:text-white/80 hover:bg-white/[0.06] rounded-lg transition-all disabled:opacity-40"
          >
            <RefreshCw size={12} className={isGraphLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <div className="w-px h-4 bg-white/10" />
          <button
            onClick={() => setChatOpen(v => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white/50 hover:text-white/80 hover:bg-white/[0.06] rounded-lg transition-all"
          >
            {chatOpen ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
            {chatOpen ? 'Hide' : 'Show'} Chat
          </button>
        </div>
      </header>

      {/* ── Main ── */}
      <div className="flex flex-1 min-h-0 relative">

        {/* Graph */}
        <div className="flex-1 relative min-w-0">
          {error ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center">
                <div className="w-12 h-12 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center mx-auto mb-4">
                  <span className="text-red-400 text-xl">!</span>
                </div>
                <p className="text-sm font-medium text-white/70 mb-1">Failed to load graph</p>
                <p className="text-xs text-white/30 mb-4">{error}</p>
                <button onClick={loadGraph} className="px-4 py-2 bg-white/10 hover:bg-white/15 text-white text-xs rounded-xl transition-all border border-white/10">
                  Retry
                </button>
              </div>
            </div>
          ) : (
            <GraphVisualization
              data={graphData}
              highlightedNodes={highlightedNodes}
              onNodeClick={handleNodeClick}
              onExpandNeighbors={handleExpandNeighbors}
              isLoading={isGraphLoading}
            />
          )}

          {selectedNode && (
            <NodeMetadataPanel
              node={selectedNode}
              onClose={() => { setSelectedNode(null); setHighlightedNodes(new Set()); }}
              onExpandNeighbors={handleExpandNeighbors}
            />
          )}
        </div>

        {/* Chat */}
        {chatOpen && (
          <div className="w-[360px] shrink-0 border-l border-white/[0.06] flex flex-col min-h-0 bg-[#0D0E14]">
            <ChatInterface onNodeHighlight={ids => setHighlightedNodes(new Set(ids))} />
          </div>
        )}
      </div>

      <footer className="h-8 px-5 flex items-center justify-between border-t border-white/[0.06] text-[11px] text-white/40 bg-[#0D0E14]/80 backdrop-blur-xl">
        <span>© Dheeraj Mishra</span>
        <span>d0k7/https://github.com/d0k7</span>
      </footer>
    </div>
  );
}
