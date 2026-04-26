import { useState } from "react";
import { useJobDetail } from "../../hooks/useJobDetail";
import { JobDetailSkeleton } from "./JobDetailSkeleton";
import { Badge } from "../ui/Badge";
import { NullValue } from "../ui/NullValue";
import { formatPay, formatDate, formatSource, formatConfidence } from "../../utils/formatting";

interface JobDetailPanelProps {
  jobId: string | null;
}

function MetaRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt
        className="text-[10px] font-semibold uppercase tracking-widest mb-1"
        style={{ color: "#A09AB0", letterSpacing: "0.1em" }}
      >
        {label}
      </dt>
      <dd className="text-sm" style={{ color: "#1A1624" }}>{children}</dd>
    </div>
  );
}

function CollapsibleSection({
  title,
  children,
  defaultOpen = false,
}: {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-t border-[#F0EAE0] pt-4">
      <button
        className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest hover:text-[#1A1624] transition-colors duration-150 mb-3 w-full text-left"
        style={{ color: "#A09AB0", letterSpacing: "0.1em" }}
        onClick={() => setOpen((o) => !o)}
      >
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px" }}>
          {open ? "▾" : "▸"}
        </span>
        {title}
      </button>
      {open && children}
    </div>
  );
}

export function JobDetailPanel({ jobId }: JobDetailPanelProps) {
  const { data: job, isLoading } = useJobDetail(jobId);

  if (!jobId) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-center px-8 bg-[#F5F0E8]">
        <span
          className="text-5xl select-none"
          style={{ color: "#E0D8CC", fontFamily: "var(--font-display)" }}
        >
          ←
        </span>
        <p className="text-sm" style={{ color: "#C8BDB0" }}>
          Select a listing to view details
        </p>
      </div>
    );
  }

  if (isLoading) return <JobDetailSkeleton />;

  if (!job) {
    return (
      <div className="flex items-center justify-center h-full bg-[#F5F0E8]">
        <p className="text-sm" style={{ color: "#A09AB0" }}>Failed to load job details.</p>
      </div>
    );
  }

  const visaLabel =
    job.sponsors_visa === true ? "Yes" : job.sponsors_visa === false ? "No" : "Unknown";
  const statusVariant =
    job.ai_extraction_status === "success"
      ? "success"
      : job.ai_extraction_status === "partial"
      ? "partial"
      : "warning";

  return (
    <div data-testid="job-detail-panel" className="h-full overflow-y-auto bg-[#F5F0E8]">
      {/* Sticky header */}
      <div className="sticky top-0 bg-white border-b border-[#E0D8CC] px-6 py-4 z-10">
        <p
          className="text-xs font-semibold mb-1 uppercase tracking-widest"
          style={{ color: "#1D5BDA", letterSpacing: "0.08em" }}
        >
          {job.company_name}
        </p>
        <h1
          className="text-xl font-bold leading-snug mb-3"
          style={{ color: "#1A1624", fontFamily: "var(--font-display)" }}
        >
          {job.title}
        </h1>
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="view-posting-link"
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold bg-[#1D5BDA] text-white hover:bg-[#1448BE] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1D5BDA] focus-visible:ring-offset-2"
        >
          View Original Posting
          <span className="text-[10px] opacity-75">↗</span>
        </a>
      </div>

      <div className="px-6 py-5 space-y-6">
        {/* Metadata grid */}
        <dl className="grid grid-cols-2 gap-x-6 gap-y-5">
          <MetaRow label="Pay">
            {job.estimated_pay_hourly !== null ? (
              <span style={{ fontFamily: "var(--font-mono)", color: "#0891B2", fontWeight: 500 }}>
                {formatPay(job.estimated_pay_hourly)}
              </span>
            ) : <NullValue />}
          </MetaRow>

          <MetaRow label="Grad Year">
            {job.required_grad_year !== null ? (
              <span>
                {job.required_grad_year}
                {job.grad_year_flexible && (
                  <span className="ml-1 text-xs" style={{ color: "#A09AB0" }}>(flexible)</span>
                )}
              </span>
            ) : <NullValue />}
          </MetaRow>

          <MetaRow label="Location">
            {job.location.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {job.is_remote && <Badge label="Remote" variant="remote" />}
                {job.location
                  .filter((l) => l.toLowerCase() !== "remote")
                  .map((l) => <Badge key={l} label={l} variant="default" />)}
              </div>
            ) : <NullValue />}
          </MetaRow>

          <MetaRow label="Visa Sponsorship">
            {job.sponsors_visa !== null ? (
              <Badge label={visaLabel} variant={job.sponsors_visa ? "visa" : "default"} />
            ) : (
              <Badge label="Unknown" variant="unknown" />
            )}
          </MetaRow>

          <MetaRow label="Source">
            <Badge label={formatSource(job.source)} variant="source" />
          </MetaRow>

          <MetaRow label="Posted">
            {job.date_posted ? (
              <span>{formatDate(job.date_posted)}</span>
            ) : (
              <span className="text-xs" style={{ color: "#A09AB0" }}>
                Ingested {formatDate(job.date_ingested)}
              </span>
            )}
          </MetaRow>
        </dl>

        {/* Tech stack */}
        {job.tech_stack.length > 0 && (
          <div>
            <p
              className="text-[10px] font-semibold uppercase tracking-widest mb-2"
              style={{ color: "#A09AB0", letterSpacing: "0.1em" }}
            >
              Tech Stack
            </p>
            <div className="flex flex-wrap gap-1.5">
              {job.tech_stack.map((tech) => (
                <Badge key={tech} label={tech} variant="tech" />
              ))}
            </div>
          </div>
        )}

        {/* AI metadata */}
        <CollapsibleSection title="AI Extraction">
          <div className="flex flex-wrap gap-3 text-xs" style={{ color: "#5C5470" }}>
            <span>Status: <Badge label={job.ai_extraction_status} variant={statusVariant} /></span>
            {job.ai_confidence_score !== null && (
              <span>
                Confidence:{" "}
                <span style={{ fontFamily: "var(--font-mono)", color: "#1D5BDA" }}>
                  {formatConfidence(job.ai_confidence_score)}
                </span>
              </span>
            )}
            {job.date_processed && (
              <span>
                Processed:{" "}
                <span style={{ fontFamily: "var(--font-mono)" }}>{formatDate(job.date_processed)}</span>
              </span>
            )}
          </div>
        </CollapsibleSection>

        {/* Raw description */}
        {job.raw_description && (
          <CollapsibleSection title="Raw Description">
            <pre
              className="text-[11px] whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto rounded-lg p-3 border border-[#E0D8CC]"
              style={{ fontFamily: "var(--font-mono)", color: "#5C5470", background: "white" }}
            >
              {job.raw_description}
            </pre>
          </CollapsibleSection>
        )}
      </div>
    </div>
  );
}
