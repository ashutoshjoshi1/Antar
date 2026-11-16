import { Bar, BarChart, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { MetricDelta } from "../lib/format";

const ROW_HEIGHT = 44;
const percent = (value: number) => `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`;

/** Relative change per metric against baseline. Colour encodes better or worse, not sign. */
export default function DeltaChart({ deltas }: { deltas: MetricDelta[] }) {
  return (
    <ResponsiveContainer width="100%" height={deltas.length * ROW_HEIGHT + 40}>
      <BarChart data={deltas} layout="vertical" margin={{ left: 8, right: 24 }}>
        <XAxis
          type="number"
          tickFormatter={percent}
          stroke="var(--color-faint)"
          tick={{ fill: "var(--color-muted)", fontSize: 12 }}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={170}
          stroke="var(--color-faint)"
          tick={{ fill: "var(--color-ink)", fontSize: 12 }}
        />
        <ReferenceLine x={0} stroke="var(--color-muted)" />
        <Tooltip
          cursor={{ fill: "var(--color-raised)" }}
          formatter={(value) => [percent(Number(value)), "Change from baseline"]}
          contentStyle={{
            background: "var(--color-ground)",
            border: "1px solid var(--color-line)",
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Bar dataKey="change" barSize={14} radius={3} isAnimationActive={false}>
          {deltas.map((delta) => (
            <Cell key={delta.key} fill={delta.change === 0 ? "var(--color-faint)" : delta.improved ? "var(--color-ok)" : "var(--color-down)"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
