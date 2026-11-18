import { NavLink, Outlet } from "react-router";

import { useHealth } from "../lib/api";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/playground", label: "Playground" },
  { to: "/vision", label: "Vision" },
  { to: "/models", label: "Models" },
  { to: "/cloud", label: "AMD Cloud" },
  { to: "/benchmarks", label: "Benchmarks" },
  { to: "/compare", label: "Comparison Lab" },
  { to: "/history", label: "History" },
  { to: "/hardware", label: "System" },
  { to: "/optimization", label: "Optimization" },
  { to: "/deployments", label: "Deployments" },
  { to: "/settings", label: "Settings" },
] as const;

function ApiStatus() {
  const health = useHealth();
  if (health.isPending) return <span className="text-faint">Checking API…</span>;
  if (health.isError) {
    return (
      <span className="flex items-center gap-2 text-down">
        <span aria-hidden className="size-2 rounded-full bg-down" />
        API unreachable
      </span>
    );
  }
  return (
    <span className="flex items-center gap-2 text-muted">
      <span aria-hidden className="size-2 rounded-full bg-ok" />
      API connected, v{health.data.version}
    </span>
  );
}

export function AppShell() {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <header className="border-b border-line bg-surface lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:border-r lg:border-b-0">
        <div className="flex items-baseline justify-between gap-3 px-5 pt-5 pb-4">
          <NavLink to="/" className="flex items-baseline gap-2.5" aria-label="Antar home">
            <span lang="sa" className="text-2xl leading-none font-medium text-local">
              अन्तर
            </span>
            <span className="text-lg font-semibold tracking-tight">Antar</span>
          </NavLink>
          <div className="text-xs lg:hidden">
            <ApiStatus />
          </div>
        </div>

        <nav aria-label="Main navigation" className="overflow-x-auto px-3 pb-3 lg:flex-1 lg:pb-0">
          <ul className="flex gap-1 lg:flex-col">
            {NAV.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    `block rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors duration-150 ${
                      isActive
                        ? "bg-raised text-ink shadow-[inset_2px_0_0_var(--color-local)]"
                        : "text-muted hover:bg-raised/60 hover:text-ink"
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="hidden border-t border-line px-5 py-4 text-xs lg:block">
          <ApiStatus />
          <p className="mt-2 text-faint">Cloud-scale intelligence. Local freedom.</p>
        </div>
      </header>

      <main className="min-w-0 px-4 py-8 sm:px-8 lg:px-12 lg:py-10">
        <div className="mx-auto max-w-6xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
