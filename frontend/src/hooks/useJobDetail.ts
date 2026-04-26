import { useQuery } from "@tanstack/react-query";
import { fetchJobDetail } from "../api/jobs";

export function useJobDetail(id: string | null) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => fetchJobDetail(id!),
    enabled: id !== null,
    staleTime: 5 * 60_000,
  });
}
