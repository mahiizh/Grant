import { Card } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { AreaChart, Area, ResponsiveContainer } from "recharts";
import { Network, GitFork, Boxes, Compass, TrendingUp } from "lucide-react";

export interface StatCardsProps {
  stats: {
    totalEntities: number;
    totalRelationships: number;
    clustersDetected: number;
    avgPathDepth: number;
    avgDegree: number;
  };
}

const SPARKLINE_1 = [{ v: 24 }, { v: 28 }, { v: 32 }, { v: 35 }, { v: 34 }, { v: 38 }, { v: 40 }];
const SPARKLINE_2 = [{ v: 45 }, { v: 52 }, { v: 60 }, { v: 68 }, { v: 72 }, { v: 78 }, { v: 84 }];
const SPARKLINE_3 = [{ v: 2 }, { v: 3 }, { v: 4 }, { v: 4 }, { v: 5 }, { v: 5 }, { v: 6 }];
const SPARKLINE_4 = [{ v: 2.1 }, { v: 2.3 }, { v: 2.6 }, { v: 2.7 }, { v: 2.8 }, { v: 2.85 }, { v: 2.85 }];

export function StatCards({ stats }: StatCardsProps) {
  const cards = [
    {
      title: "Total Entities",
      value: stats.totalEntities.toString(),
      trend: "+12% this week",
      footnote: "Across 3 ingested documents",
      icon: Network,
      color: "#38BDF8", // sky
      sparkline: SPARKLINE_1,
    },
    {
      title: "Relationships",
      value: stats.totalRelationships.toString(),
      trend: "+18.4% density",
      footnote: `Avg ${stats.avgDegree} edges per entity`,
      icon: GitFork,
      color: "#8B5CF6", // violet
      sparkline: SPARKLINE_2,
    },
    {
      title: "Clusters Detected",
      value: stats.clustersDetected.toString(),
      trend: "Louvain Modular",
      footnote: "Optimal modularity partition",
      icon: Boxes,
      color: "#10B981", // emerald
      sparkline: SPARKLINE_3,
    },
    {
      title: "Avg Path Depth",
      value: `${stats.avgPathDepth} hops`,
      trend: "Bi-directional BFS",
      footnote: "Max diameter 4 hops",
      icon: Compass,
      color: "#F59E0B", // amber
      sparkline: SPARKLINE_4,
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((c) => {
        const Icon = c.icon;
        return (
          <Card key={c.title} className="border-zinc-800/80 bg-zinc-900/50 p-5 relative overflow-hidden backdrop-blur">
            <div className="flex items-center justify-between pb-2">
              <span className="text-xs font-medium text-zinc-400">{c.title}</span>
              <div className="p-1.5 rounded-lg bg-zinc-800/60 text-zinc-300">
                <Icon className="h-4 w-4" style={{ color: c.color }} />
              </div>
            </div>

            <div className="flex items-baseline justify-between">
              <div className="text-2xl font-bold font-mono tracking-tight text-zinc-100">
                {c.value}
              </div>
              <Badge variant="outline" className="text-[10px] py-0 px-1.5 border-zinc-700/80 text-zinc-300 flex items-center gap-1">
                <TrendingUp className="h-2.5 w-2.5 text-emerald-400" />
                {c.trend}
              </Badge>
            </div>

            <div className="flex items-center justify-between mt-3 pt-2 border-t border-zinc-800/60">
              <span className="text-[11px] text-zinc-500">{c.footnote}</span>

              {/* Sparkline chart */}
              <div className="w-16 h-7 opacity-80">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={c.sparkline}>
                    <defs>
                      <linearGradient id={`grad-${c.title}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor={c.color} stopOpacity={0.6} />
                        <stop offset="95%" stopColor={c.color} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <Area
                      type="monotone"
                      dataKey="v"
                      stroke={c.color}
                      strokeWidth={1.5}
                      fillOpacity={1}
                      fill={`url(#grad-${c.title})`}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
