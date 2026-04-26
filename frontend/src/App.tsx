import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Header } from "./components/layout/Header";
import { FilterBar } from "./components/filters/FilterBar";
import { JobListPanel } from "./components/jobs/JobListPanel";
import { JobDetailPanel } from "./components/jobs/JobDetailPanel";
import { useJobs } from "./hooks/useJobs";

export default function App() {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const {
    filters,
    updateFilter,
    resetFilters,
    setPage,
    activeFilterCount,
    jobs,
    pagination,
    isLoading,
    isFetching,
    isError,
  } = useJobs();

  const handleSelect = (id: string) => {
    setSelectedJobId(id);
  };

  const handleReset = () => {
    resetFilters();
    setSelectedJobId(null);
  };

  return (
    <div className="flex flex-col h-screen bg-[#F5F0E8] overflow-hidden">
      <Header />

      <FilterBar
        filters={filters}
        onUpdate={updateFilter}
        onReset={handleReset}
        activeFilterCount={activeFilterCount}
        totalJobs={pagination?.total ?? null}
      />

      {isError && (
        <div className="px-4 py-2 bg-red-50 border-b border-red-200 text-xs text-red-600" style={{ fontFamily: "var(--font-mono)" }}>
          ⚠ Failed to connect to API. Is the backend running on port 8000?
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Left: job list — fixed 420px */}
        <div className="w-[420px] shrink-0 overflow-hidden flex flex-col">
          <JobListPanel
            jobs={jobs}
            selectedId={selectedJobId}
            onSelect={handleSelect}
            onReset={handleReset}
            isLoading={isLoading}
            isFetching={isFetching}
            pagination={pagination}
            onPageChange={setPage}
          />
        </div>

        {/* Right: detail panel — fluid */}
        <div className="flex-1 overflow-hidden relative bg-[#F5F0E8]">
          <AnimatePresence mode="wait">
            {selectedJobId ? (
              <motion.div
                key={selectedJobId}
                initial={{ opacity: 0, x: 24 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 24 }}
                transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                className="absolute inset-0"
              >
                <JobDetailPanel jobId={selectedJobId} />
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="absolute inset-0"
              >
                <JobDetailPanel jobId={null} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
