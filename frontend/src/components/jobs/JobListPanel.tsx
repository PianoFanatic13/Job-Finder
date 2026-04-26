import { useEffect, useRef, useCallback } from "react";
import { JobCard } from "./JobCard";
import { JobCardSkeleton } from "./JobCardSkeleton";
import { EmptyState } from "./EmptyState";
import { Pagination } from "../ui/Pagination";
import type { JobSummary, PaginationMeta } from "../../types/api";

interface JobListPanelProps {
  jobs: JobSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onReset: () => void;
  isLoading: boolean;
  isFetching: boolean;
  pagination: PaginationMeta | null;
  onPageChange: (page: number) => void;
}

export function JobListPanel({
  jobs, selectedId, onSelect, onReset,
  isLoading, isFetching, pagination, onPageChange,
}: JobListPanelProps) {
  const listRef = useRef<HTMLDivElement>(null);
  const selectedIndex = jobs.findIndex((j) => j.id === selectedId);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!jobs.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        onSelect(jobs[selectedIndex < jobs.length - 1 ? selectedIndex + 1 : 0].id);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        onSelect(jobs[selectedIndex > 0 ? selectedIndex - 1 : jobs.length - 1].id);
      }
    },
    [jobs, selectedIndex, onSelect]
  );

  useEffect(() => {
    if (!listRef.current || selectedIndex < 0) return;
    const cards = listRef.current.querySelectorAll("[data-testid='job-card']");
    (cards[selectedIndex] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedIndex]);

  return (
    <div className="flex flex-col h-full border-r border-[#E0D8CC] bg-white relative">
      {isFetching && !isLoading && (
        <div className="absolute top-0 left-0 right-0 h-[2px] bg-[#1D5BDA]/40 animate-pulse z-10" />
      )}

      <div
        ref={listRef}
        className="flex-1 overflow-y-auto focus-visible:outline-none"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        aria-label="Job listings"
      >
        {isLoading ? (
          Array.from({ length: 8 }).map((_, i) => <JobCardSkeleton key={i} />)
        ) : jobs.length === 0 ? (
          <EmptyState onReset={onReset} />
        ) : (
          jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              isSelected={job.id === selectedId}
              onClick={onSelect}
            />
          ))
        )}
      </div>

      {pagination && <Pagination pagination={pagination} onPageChange={onPageChange} />}
    </div>
  );
}
