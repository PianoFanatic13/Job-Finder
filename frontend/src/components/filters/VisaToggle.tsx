import { Toggle } from "../ui/Toggle";

interface VisaToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function VisaToggle({ checked, onChange }: VisaToggleProps) {
  return (
    <div className="flex flex-col gap-1">
      <span
        className="text-[10px] font-semibold uppercase tracking-widest"
        style={{ color: "#A09AB0", letterSpacing: "0.1em" }}
      >
        Visa Sponsor
      </span>
      <Toggle checked={checked} onChange={onChange} label="Required" data-testid="visa-toggle" />
    </div>
  );
}
