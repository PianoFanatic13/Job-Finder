interface EmptyStateProps {
  onReset: () => void;
}

export function EmptyState({ onReset }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-4 px-6 text-center">
      <span
        className="text-6xl font-bold leading-none select-none"
        style={{ fontFamily: "var(--font-display)", color: "#E0D8CC" }}
      >
        0
      </span>
      <p className="text-sm" style={{ color: "#A09AB0" }}>
        No internships match your filters.
      </p>
      <button
        onClick={onReset}
        className="px-3 py-1.5 rounded-md text-xs font-medium text-[#1D5BDA] border border-[#BFDBFE] hover:bg-[#EEF4FF] transition-colors duration-150"
      >
        Clear filters
      </button>
    </div>
  );
}
