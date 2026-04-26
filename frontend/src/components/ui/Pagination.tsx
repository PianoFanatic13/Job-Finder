import { cn } from "../../utils/cn";
import type { PaginationMeta } from "../../types/api";

interface PaginationProps {
  pagination: PaginationMeta;
  onPageChange: (page: number) => void;
}

export function Pagination({ pagination, onPageChange }: PaginationProps) {
  const { page, page_size, total } = pagination;
  const totalPages = Math.ceil(total / page_size);
  if (totalPages <= 1) return null;

  const start = (page - 1) * page_size + 1;
  const end = Math.min(page * page_size, total);

  return (
    <div className="flex items-center justify-between px-4 py-2.5 border-t border-[#E0D8CC] bg-white">
      <span className="text-[11px] text-[#A09AB0]" style={{ fontFamily: "var(--font-mono)" }}>
        {start}–{end} of {total}
      </span>
      <div className="flex items-center gap-0.5">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
          className={cn(
            "px-2 py-1 rounded text-xs transition-colors duration-150",
            page <= 1
              ? "text-[#C8BDB0] cursor-not-allowed"
              : "text-[#5C5470] hover:text-[#1A1624] hover:bg-[#F0EAE0]"
          )}
        >
          ←
        </button>
        {getPageNumbers(page, totalPages).map((p, i) =>
          p === "..." ? (
            <span key={`e-${i}`} className="px-1 text-xs text-[#C8BDB0]">…</span>
          ) : (
            <button
              key={p}
              onClick={() => onPageChange(p as number)}
              className={cn(
                "min-w-[28px] px-2 py-1 rounded text-xs transition-colors duration-150",
                p === page
                  ? "bg-[#1D5BDA] text-white font-medium"
                  : "text-[#5C5470] hover:text-[#1A1624] hover:bg-[#F0EAE0]"
              )}
              style={p !== page ? { fontFamily: "var(--font-mono)" } : { fontFamily: "var(--font-mono)" }}
            >
              {p}
            </button>
          )
        )}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
          className={cn(
            "px-2 py-1 rounded text-xs transition-colors duration-150",
            page >= totalPages
              ? "text-[#C8BDB0] cursor-not-allowed"
              : "text-[#5C5470] hover:text-[#1A1624] hover:bg-[#F0EAE0]"
          )}
        >
          →
        </button>
      </div>
    </div>
  );
}

function getPageNumbers(current: number, total: number): (number | "...")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages: (number | "...")[] = [1];
  if (current > 3) pages.push("...");
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  for (let i = start; i <= end; i++) pages.push(i);
  if (current < total - 2) pages.push("...");
  pages.push(total);
  return pages;
}
