export interface GraphNode {
    id: string;
    label: string;
    type: 'SalesOrder' | 'Delivery' | 'Invoice' | 'JournalEntry' | 'Customer' | 'Product' | 'Payment' | 'Plant' | 'Unknown' | 'Material';
    color: string;
    metadata: Record<string, string | number | null>;
    // Added by force-graph internally:
    x?: number;
    y?: number;
    vx?: number;
    vy?: number;
  }
  
  export interface GraphLink {
    source: string;
    target: string;
    label: string;
  }
  
  export interface GraphData {
    nodes: GraphNode[];
    links: GraphLink[];
  }
  
  export interface GraphStats {
    total_nodes: number;
    total_edges: number;
    node_types: Record<string, number>;
    avg_degree: number;
  }
  
  export interface ChatMessage {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    sql?: string | null;
    results?: Record<string, unknown>[];
    is_relevant?: boolean;
    timestamp: Date;
  }
  
export interface NodeDetail {
    id: string;
    type: string;
    label: string;
    metadata: Record<string, string | number | null>;
    connections: number;
    predecessors: string[];
    successors: string[];
  }

export interface AnalyticsSummary {
    totals: Record<string, number>;
    top_products: { material: string; description: string | null; billing_docs: number }[];
    top_products_revenue: { material: string; description: string | null; revenue: number; billing_docs: number }[];
    top_customers: { customer: string; name: string | null; total_billed: number; billing_docs: number }[];
    top_plants: { plant: string; name: string | null; deliveries: number }[];
    top_regions: { region: string; country: string; total_billed: number; billing_docs: number }[];
    top_countries: { country: string; total_billed: number; billing_docs: number }[];
    broken_flows: {
        delivered_not_billed: { count: number; sample: string[] };
        billed_no_delivery: { count: number; sample: string[] };
        billed_no_journal: { count: number; sample: string[] };
        unpaid: { count: number; sample: string[] };
    };
}
