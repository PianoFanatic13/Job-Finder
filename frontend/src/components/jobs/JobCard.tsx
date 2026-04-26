import { cn } from "../../utils/cn";
import { Badge } from "../ui/Badge";
import { formatPay, formatSource } from "../../utils/formatting";
import type { JobSummary } from "../../types/api";

interface JobCardProps {
  job: JobSummary;
  isSelected: boolean;
  onClick: (id: string) => void;
}

export function JobCard({ job, isSelected, onClick }: JobCardProps) {
  const visibleTech = job.tech_stack.slice(0, 3);
  const overflowCount = job.tech_stack.length - 3;

  return (
    <button
      data-testid="job-card"
      onClick={() => onClick(job.id)}
      className={cn(
        "w-full text-left px-4 py-3.5 border-b border-[#F0EAE0] transition-all duration-150 focus-visible:outline-none focus-visible:ring-inset focus-visible:ring-2 focus-visible:ring-[#1D5BDA]",
        isSelected
          ? "bg-[#EEF4FF] border-l-[3px] border-l-[#1D5BDA]"
          : "bg-white hover:bg-[#FAF7F2] border-l-[3px] border-l-transparent"
      )}
    >
      {/* Row 1: company + source */}
      <div className="flex items-center justify-between gap-2 mb-1">
        <span
          className="text-sm font-semibold truncate"
          style={{ color: "#1A1624", fontFamily: "var(--font-sans)" }}
        >
          {job.company_name}
        </span>
        {job.source && (
          <Badge label={formatSource(job.source)} variant="source" className="shrink-0" />
        )}
      </div>

      {/* Row 2: title */}
      <p className="text-xs truncate mb-2" style={{ color: "#5C5470" }}>
        {job.title}
      </p>

      {/* Row 3: badges */}
      <div className="flex flex-wrap items-center gap-1 mb-1.5">
        {job.is_remote && <Badge label="Remote" variant="remote" />}
        {job.required_grad_year && (
          <Badge label={`${job.required_grad_year}`} variant="grad" />
        )}
        {job.estimated_pay_hourly !== null && (
          <Badge label={formatPay(job.estimated_pay_hourly)} variant="pay" />
        )}
        {job.sponsors_visa && <Badge label="Visa" variant="visa" />}
      </div>

      {/* Row 4: tech stack */}
      {job.tech_stack.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {visibleTech.map((tech) => (
            <Badge key={tech} label={tech} variant="tech" />
          ))}
          {overflowCount > 0 && (
            <span
              className="text-[10px]"
              style={{ color: "#A09AB0", fontFamily: "var(--font-mono)" }}
            >
              +{overflowCount}
            </span>
          )}
        </div>
      )}
    </button>
  );
}
