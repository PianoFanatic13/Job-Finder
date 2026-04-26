import { GradYearSelect } from "./GradYearSelect";
import { PayRangeSlider } from "./PayRangeSlider";
import { TechStackInput } from "./TechStackInput";
import { RemoteToggle } from "./RemoteToggle";
import { VisaToggle } from "./VisaToggle";
import { SourceSelect } from "./SourceSelect";
import { SortSelect } from "./SortSelect";
import type { JobFilters, SortOption, Source } from "../../types/api";

interface FilterBarProps {
  filters: JobFilters;
  onUpdate: <K extends keyof JobFilters>(key: K, value: JobFilters[K]) => void;
  onReset: () => void;
  activeFilterCount: number;
  totalJobs: number | null;
}

export function FilterBar({ filters, onUpdate, onReset, activeFilterCount, totalJobs }: FilterBarProps) {
  return (
    <div
      data-testid="filter-bar"
      className="flex items-end gap-4 flex-wrap px-5 py-3 border-b border-[#E0D8CC] bg-white sticky top-0 z-10"
    >
      <GradYearSelect
        value={filters.grad_year}
        onChange={(v) => onUpdate("grad_year", v)}
      />
      <PayRangeSlider
        minPay={filters.min_pay}
        maxPay={filters.max_pay}
        onMinChange={(v) => onUpdate("min_pay", v)}
        onMaxChange={(v) => onUpdate("max_pay", v)}
      />
      <TechStackInput
        value={filters.tech_stack}
        onChange={(v) => onUpdate("tech_stack", v)}
      />
      <RemoteToggle checked={filters.remote_only} onChange={(v) => onUpdate("remote_only", v)} />
      <VisaToggle checked={filters.sponsors_visa} onChange={(v) => onUpdate("sponsors_visa", v)} />
      <SourceSelect value={filters.source} onChange={(v) => onUpdate("source", v as Source | null)} />
      <SortSelect value={filters.sort} onChange={(v) => onUpdate("sort", v as SortOption)} />

      <div className="flex items-end gap-3 ml-auto">
        {totalJobs !== null && (
          <span
            className="text-[11px] mb-1.5"
            style={{ color: "#A09AB0", fontFamily: "var(--font-mono)" }}
          >
            {totalJobs.toLocaleString()} results
          </span>
        )}
        {activeFilterCount > 0 && (
          <button
            onClick={onReset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold text-[#1D5BDA] border border-[#BFDBFE] hover:bg-[#EEF4FF] transition-colors duration-150 mb-0.5"
          >
            Clear
            <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-[#1D5BDA] text-white text-[10px] font-bold leading-none">
              {activeFilterCount}
            </span>
          </button>
        )}
      </div>
    </div>
  );
}
