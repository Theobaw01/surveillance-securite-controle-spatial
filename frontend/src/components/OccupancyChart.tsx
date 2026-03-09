"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

interface Props {
  data: Record<string, number>;
}

export default function OccupancyChart({ data }: Props) {
  const chartData = Object.entries(data).map(([hour, count]) => ({
    hour,
    personnes: count,
  }));

  if (chartData.length === 0) {
    return (
      <div className="bg-surface-card border border-surface-border rounded-xl p-6 h-64 flex items-center justify-center">
        <p className="text-sm text-gray-500">
          Pas encore de données d&apos;occupation
        </p>
      </div>
    );
  }

  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4">
      <h3 className="text-sm font-semibold text-gray-300 mb-4">
        Occupation par heure
      </h3>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
            <XAxis
              dataKey="hour"
              tick={{ fill: "#666", fontSize: 11 }}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
            />
            <YAxis
              tick={{ fill: "#666", fontSize: 11 }}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
            />
            <Tooltip
              contentStyle={{
                background: "rgba(12,12,12,0.95)",
                border: "1px solid rgba(255,255,255,0.06)",
                borderRadius: 8,
                color: "#e2e8f0",
                fontSize: 12,
                boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
              }}
            />
            <Bar
              dataKey="personnes"
              fill="#6366f1"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
