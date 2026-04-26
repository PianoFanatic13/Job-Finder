import { cn } from "../../utils/cn";

export type BadgeVariant =
  | "default"
  | "remote"
  | "visa"
  | "pay"
  | "tech"
  | "source"
  | "grad"
  | "success"
  | "warning"
  | "partial"
  | "unknown";

const variantStyles: Record<BadgeVariant, string> = {
  default:  "bg-[#F0EAE0] text-[#5C5470]",
  remote:   "bg-cyan-50 text-cyan-700 ring-1 ring-cyan-200",
  visa:     "bg-violet-50 text-violet-700 ring-1 ring-violet-200",
  pay:      "bg-blue-50 text-[#1D5BDA] ring-1 ring-blue-200",
  tech:     "bg-[#F0EAE0] text-[#1D5BDA]",
  source:   "bg-[#F5F0E8] text-[#A09AB0]",
  grad:     "bg-blue-50 text-[#1D5BDA] ring-1 ring-blue-100",
  success:  "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  warning:  "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  partial:  "bg-amber-50 text-amber-600",
  unknown:  "bg-[#F0EAE0] text-[#A09AB0]",
};

const monoVariants: BadgeVariant[] = ["pay", "tech", "source"];

interface BadgeProps {
  label: string;
  variant?: BadgeVariant;
  className?: string;
}

export function Badge({ label, variant = "default", className }: BadgeProps) {
  const isMono = monoVariants.includes(variant);
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium leading-none",
        variantStyles[variant],
        className
      )}
      style={isMono ? { fontFamily: "var(--font-mono)", fontSize: "11px" } : undefined}
    >
      {label}
    </span>
  );
}
