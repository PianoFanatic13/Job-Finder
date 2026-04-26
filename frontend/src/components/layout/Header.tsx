import { useStats } from "../../hooks/useStats";

export function Header() {
  const { data: stats } = useStats();

  return (
    <header className="flex items-center justify-between px-6 h-14 border-b border-[#E0D8CC] bg-white shrink-0 z-20">
      <div className="flex items-center gap-3">
        <span
          className="text-xl tracking-tight select-none"
          style={{ fontFamily: "var(--font-display)", fontWeight: 800 }}
        >
          <span style={{ color: "#1A1624" }}>Intern</span>
          <span style={{ color: "#1D5BDA" }}>IQ</span>
        </span>
        <span
          className="hidden sm:block text-[11px] font-medium tracking-wide uppercase"
          style={{ color: "#A09AB0", letterSpacing: "0.08em" }}
        >
          AI-powered internship search
        </span>
      </div>

      {stats && (
        <div className="flex items-center gap-5">
          <span className="text-xs" style={{ color: "#A09AB0", fontFamily: "var(--font-mono)" }}>
            <span style={{ color: "#1D5BDA", fontWeight: 600 }}>{stats.total.toLocaleString()}</span> listings
          </span>
          <div className="hidden sm:flex items-center gap-3">
            {Object.entries(stats.by_source).map(([source, count]) => (
              <span key={source} className="text-[11px]" style={{ color: "#A09AB0", fontFamily: "var(--font-mono)" }}>
                {source === "pittcsc" ? "PittCSC" : "Ouckah"}: {count}
              </span>
            ))}
          </div>
        </div>
      )}
    </header>
  );
}
