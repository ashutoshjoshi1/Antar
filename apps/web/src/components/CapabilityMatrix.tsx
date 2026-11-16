import { titleCase } from "../lib/format";
import { MODALITIES } from "../lib/types";
import type { BackendCapabilities, Modality, SupportLevel } from "../lib/types";

const RANK: readonly SupportLevel[] = ["supported", "documented", "planned", "unsupported"];

const LEVELS: Record<SupportLevel, { label: string; meaning: string; mark: string }> = {
  supported: {
    label: "Runs",
    meaning: "Antar can run this through the backend today",
    mark: "bg-ok border-ok",
  },
  documented: {
    label: "Backend only",
    meaning: "The backend documents it; Antar's adapter is not written",
    mark: "border-local bg-local/25",
  },
  planned: { label: "Planned", meaning: "On the roadmap; nothing runs", mark: "border-dashed border-muted" },
  unsupported: { label: "No", meaning: "Not offered by the backend", mark: "border-transparent" },
};

/** The strongest support level a backend declares for a modality, with its notes. */
export function summarize(
  backend: BackendCapabilities,
  modality: Modality,
): { level: SupportLevel; notes: string[] } {
  const matching = backend.capabilities.filter((capability) => capability.modality === modality);
  const level = RANK.find((candidate) => matching.some((c) => c.support === candidate)) ?? "unsupported";
  const notes = matching
    .filter((capability) => capability.support === level)
    .map((capability) =>
      capability.task ? `${titleCase(capability.task)}: ${capability.note ?? ""}` : (capability.note ?? ""),
    );
  return { level, notes };
}

export function CapabilityMatrix({ backends }: { backends: BackendCapabilities[] }) {
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[30rem] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th scope="col" className="pb-3 text-left font-normal text-muted">
                Backend
              </th>
              {MODALITIES.map((modality) => (
                <th key={modality} scope="col" className="pb-3 text-center font-normal text-muted">
                  {titleCase(modality)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {backends.map((backend) => (
              <tr key={backend.backend}>
                <th scope="row" className="border-t border-line py-3 pr-4 text-left font-medium">
                  {backend.display_name}
                </th>
                {MODALITIES.map((modality) => {
                  const { level, notes } = summarize(backend, modality);
                  const style = LEVELS[level];
                  const simulated = backend.kind === "mock" && level === "supported";
                  return (
                    <td
                      key={modality}
                      title={notes.join("\n") || style.meaning}
                      className="border-t border-line py-3 text-center"
                    >
                      <span aria-hidden className={`inline-block size-3.5 rounded-full border-2 ${simulated ? "border-warn bg-warn/25" : style.mark}`} />
                      <span className="mt-1 block text-2xs text-muted">{simulated ? "Simulated" : style.label}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <dl className="mt-4 grid gap-x-6 gap-y-1.5 border-t border-line pt-4 text-xs sm:grid-cols-2">
        {RANK.filter((level) => level !== "unsupported").map((level) => (
          <div key={level} className="flex items-baseline gap-2">
            <dt className="shrink-0 font-medium">{LEVELS[level].label}</dt>
            <dd className="text-muted">{LEVELS[level].meaning}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
