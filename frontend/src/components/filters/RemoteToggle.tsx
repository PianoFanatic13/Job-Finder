import { Toggle } from "../ui/Toggle";

interface RemoteToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function RemoteToggle({ checked, onChange }: RemoteToggleProps) {
  return (
    <div className="flex flex-col gap-1">
      <span
        className="text-[10px] font-semibold uppercase tracking-widest"
        style={{ color: "#A09AB0", letterSpacing: "0.1em" }}
      >
        Remote
      </span>
      <Toggle checked={checked} onChange={onChange} label="Only" data-testid="remote-toggle" />
    </div>
  );
}
