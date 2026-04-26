import { useState, useCallback, useMemo, useRef, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchJobs } from "../api/jobs";
import { DEFAULT_FILTERS, type JobFilters } from "../types/api";

const DEBOUNCE_MS = 350;

export function useJobs() {
  const [filters, setFilters] = useState<JobFilters>(DEFAULT_FILTERS);
  const [debouncedFilters, setDebouncedFilters] =
    useState<JobFilters>(DEFAULT_FILTERS);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateFilter = useCallback(
    <K extends keyof JobFilters>(key: K, value: JobFilters[K]) => {
      setFilters((prev) => {
        const next = { ...prev, [key]: value };
        if (key !== "page") next.page = 1;
        return next;
      });
    },
    []
  );

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      setDebouncedFilters(filters);
    }, DEBOUNCE_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [filters]);

  const queryKey = useMemo(
    () => ["jobs", debouncedFilters] as const,
    [debouncedFilters]
  );

  const query = useQuery({
    queryKey,
    queryFn: () => fetchJobs(debouncedFilters),
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });

  const setPage = useCallback(
    (page: number) => updateFilter("page", page),
    [updateFilter]
  );

  const resetFilters = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
  }, []);

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.grad_year !== null) count++;
    if (filters.grad_year_flex) count++;
    if (filters.min_pay !== null) count++;
    if (filters.max_pay !== null) count++;
    if (filters.tech_stack.length > 0) count++;
    if (filters.remote_only) count++;
    if (filters.sponsors_visa) count++;
    if (filters.source !== null) count++;
    return count;
  }, [filters]);

  return {
    filters,
    updateFilter,
    resetFilters,
    setPage,
    activeFilterCount,
    jobs: query.data?.data ?? [],
    pagination: query.data?.pagination ?? null,
    cacheHit: query.data?.cache_hit ?? false,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
  };
}
