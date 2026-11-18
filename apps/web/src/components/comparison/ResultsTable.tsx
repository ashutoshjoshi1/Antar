import { useState } from "react";

import { formatRowValue, groupRows, MEASURED_BY_LABELS, rowWorkloads, SCOPE_LABELS } from "../../lib/comparison";
import type { ComparisonRow, Workload } from "../../lib/types";
import { LocationBadge, Value } from "../ui";

interface ResultsTableProps {
  rows: ComparisonRow[];
  workloads: Workload[];
}

/** The two sides lined up metric by metric, grouped by what each number measures. */
export function ResultsTable({ rows, workloads }: ResultsTableProps) {
  const ids = rowWorkloads(rows);
  const [chosen, setChosen] = useState("all");
  const workload = ids.includes(chosen) ? chosen : (ids[0] ?? "all");
  const groups = groupRows(rows, workload);
  const name = (id: string) =>
    id === "all" ? "All workloads" : (workloads.find((item) => item.id === id)?.name ?? id);

  if (rows.length === 0) {
    return <p className="text-sm text-muted">This comparison produced no results to line up.</p>;
  }

  return (
    <div>
      <label className="flex flex-wrap items-center gap-2 text-sm">
        Results for
        <select
          className="rounded-md border border-line bg-ground px-2 py-1"
          value={workload}
          onChange={(event) => setChosen(event.target.value)}
        >
          {ids.map((id) => (
            <option key={id} value={id}>
              {name(id)}
            </option>
          ))}
        </select>
      </label>

      <div className="relative mt-3 overflow-x-auto">
        <table className="w-full min-w-[38rem] border-separate border-spacing-0 text-sm">
          <caption className="sr-only">Local and cloud results for {name(workload)}</caption>
          <thead className="text-left text-muted">
            <tr>
              <th scope="col" className="pb-2 font-normal">Metric</th>
              <th scope="col" className="pb-2 pl-4 text-right font-normal">
                <LocationBadge location="local" />
              </th>
              <th scope="col" className="pb-2 pl-4 text-right font-normal">
                <LocationBadge location="cloud" />
              </th>
              <th scope="col" className="pb-2 pl-4 font-normal">Measured by</th>
            </tr>
          </thead>
          {groups.map((group) => (
            <tbody key={group.scope} className="tabular">
              <tr>
                <th scope="colgroup" colSpan={4} className="border-t border-line bg-raised/40 px-2 py-1.5 text-left text-xs font-medium">
                  {SCOPE_LABELS[group.scope].title}{" "}
                  <span className="font-normal text-muted">{SCOPE_LABELS[group.scope].help}</span>
                </th>
              </tr>
              {group.rows.map((row) => (
                <tr key={row.metric}>
                  <th scope="row" className="border-t border-line py-2 pr-4 pl-2 text-left font-normal">
                    {row.label}
                  </th>
                  <td className="border-t border-line py-2 pl-4 text-right whitespace-nowrap">
                    <Value>{formatRowValue(row.local, row.unit)}</Value>
                  </td>
                  <td className="border-t border-line py-2 pl-4 text-right whitespace-nowrap">
                    <Value>{formatRowValue(row.cloud, row.unit)}</Value>
                  </td>
                  <td className="border-t border-line py-2 pl-4 whitespace-nowrap text-muted">
                    {MEASURED_BY_LABELS[row.measured_by]}
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      <p className="mt-2 text-xs text-faint">
        "Unavailable" means that side did not report or produce the value. It is never a zero.
      </p>
    </div>
  );
}
