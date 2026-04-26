export type AiExtractionStatus = "success" | "partial" | "failed";
export type Source = "pittcsc" | "ouckah";
export type SortOption = "date_desc" | "pay_desc" | "company";

export interface JobSummary {
  id: string;
  url: string;
  company_name: string;
  title: string;
  location: string[];
  is_remote: boolean | null;
  required_grad_year: number | null;
  grad_year_flexible: boolean | null;
  estimated_pay_hourly: number | null;
  tech_stack: string[];
  sponsors_visa: boolean | null;
  ai_extraction_status: AiExtractionStatus;
  ai_confidence_score: number | null;
  source: Source | null;
  date_posted: string | null;
  date_ingested: string;
}

export interface JobDetail extends JobSummary {
  raw_description: string | null;
  date_processed: string | null;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
}

export interface JobsResponse {
  data: JobSummary[];
  pagination: PaginationMeta;
  cache_hit: boolean;
}

export interface StatsResponse {
  total: number;
  by_source: Record<string, number>;
  by_grad_year: Record<string, number>;
  by_status: Record<string, number>;
}

export interface JobFilters {
  grad_year: number | null;
  grad_year_flex: boolean;
  min_pay: number | null;
  max_pay: number | null;
  tech_stack: string[];
  remote_only: boolean;
  sponsors_visa: boolean;
  source: Source | null;
  sort: SortOption;
  page: number;
  page_size: number;
}

export const DEFAULT_FILTERS: JobFilters = {
  grad_year: null,
  grad_year_flex: false,
  min_pay: null,
  max_pay: null,
  tech_stack: [],
  remote_only: false,
  sponsors_visa: false,
  source: null,
  sort: "date_desc",
  page: 1,
  page_size: 25,
};
