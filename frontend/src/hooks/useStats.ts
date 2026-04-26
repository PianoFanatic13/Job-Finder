import { useQuery } from "@tanstack/react-query";
import { fetchStats } from "../api/jobs";

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: fetchStats,
    staleTime: 15 * 60_000,
  });
}
