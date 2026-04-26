import { cn } from "../../utils/cn";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  "data-testid"?: string;
}

export function Toggle({ checked, onChange, label, "data-testid": testId }: ToggleProps) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none" data-testid={testId}>
      <button
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1D5BDA] focus-visible:ring-offset-1",
          checked ? "bg-[#1D5BDA]" : "bg-[#E0D8CC]"
        )}
      >
        <span
          className={cn(
            "inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform duration-150",
            checked ? "translate-x-4.5" : "translate-x-1"
          )}
        />
      </button>
      <span className="text-sm" style={{ color: "#5C5470" }}>{label}</span>
    </label>
  );
}
