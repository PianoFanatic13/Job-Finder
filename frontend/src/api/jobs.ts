import axios from "axios";
import type {
  JobFilters,
  JobsResponse,
  JobDetail,
  StatsResponse,
} from "../types/api";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? "",
  timeout: 10_000,
});

export async function fetchJobs(filters: JobFilters): Promise<JobsResponse> {
  const params: Record<string, string | number | boolean> = {
    sort: filters.sort,
    page: filters.page,
    page_size: filters.page_size,
  };

  if (filters.grad_year !== null) params.grad_year = filters.grad_year;
  if (filters.grad_year_flex) params.grad_year_flex = true;
  if (filters.min_pay !== null) params.min_pay = filters.min_pay;
  if (filters.max_pay !== null) params.max_pay = filters.max_pay;
  if (filters.tech_stack.length > 0)
    params.tech_stack = filters.tech_stack.join(",");
  if (filters.remote_only) params.remote_only = true;
  if (filters.sponsors_visa) params.sponsors_visa = true;
  if (filters.source) params.source = filters.source;

  const { data } = await client.get<JobsResponse>("/api/jobs", { params });
  return data;
}

export async function fetchJobDetail(id: string): Promise<JobDetail> {
  const { data } = await client.get<JobDetail>(`/api/jobs/${id}`);
  return data;
}

export async function fetchStats(): Promise<StatsResponse> {
  const { data } = await client.get<StatsResponse>("/api/stats");
  return data;
}
