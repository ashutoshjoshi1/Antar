import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { ChartMetric } from "../../lib/comparison";

const ROW_HEIGHT = 44;
// Here the two reserved colours carry their meaning: where each side ran.
const FILLS = { Local: "var(--color-local)", Cloud: "var(--color-cloud)" } as const;

/** One metric as two bars. A side with no value gets no bar rather than an empty one at zero. */
export default function ComparisonChart({ metric }: { metric: ChartMetric }) {
  const data = (
    [
      { side: "Local", value: metric.local },
      { side: "Cloud", value: metric.cloud },
    ] as const
  ).filter((item) => item.value !== null);
  return (
    <ResponsiveContainer width="100%" height={data.length * ROW_HEIGHT + 40}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24 }}>
        <XAxis
          type="number"
          stroke="var(--color-faint)"
          tick={{ fill: "var(--color-muted)", fontSize: 12 }}
        />
        <YAxis
          type="category"
          dataKey="side"
          width={56}
          stroke="var(--color-faint)"
          tick={{ fill: "var(--color-ink)", fontSize: 12 }}
        />
        <Tooltip
          cursor={{ fill: "var(--color-raised)" }}
          formatter={(value) => [`${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2 })} ${metric.unit}`, metric.title]}
          contentStyle={{
            background: "var(--color-ground)",
            border: "1px solid var(--color-line)",
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Bar dataKey="value" barSize={14} radius={3} isAnimationActive={false}>
          {data.map((item) => (
            <Cell key={item.side} fill={FILLS[item.side]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
