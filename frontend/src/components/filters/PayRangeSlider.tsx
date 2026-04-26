interface PayRangeSliderProps {
  minPay: number | null;
  maxPay: number | null;
  onMinChange: (val: number | null) => void;
  onMaxChange: (val: number | null) => void;
}

const inputStyle: React.CSSProperties = {
  background: "#F5F0E8",
  color: "#1A1624",
  border: "1px solid #E0D8CC",
  borderRadius: "6px",
  padding: "5px 8px",
  fontSize: "12px",
  fontFamily: "var(--font-mono)",
  outline: "none",
  width: "68px",
};

export function PayRangeSlider({ minPay, maxPay, onMinChange, onMaxChange }: PayRangeSliderProps) {
  return (
    <div className="flex flex-col gap-1">
      <label
        className="text-[10px] font-semibold uppercase tracking-widest"
        style={{ color: "#A09AB0", letterSpacing: "0.1em" }}
      >
        Pay ($/hr)
      </label>
      <div className="flex items-center gap-1.5">
        <input
          type="number"
          placeholder="Min"
          style={inputStyle}
          value={minPay ?? ""}
          min={0}
          onChange={(e) => onMinChange(e.target.value ? parseInt(e.target.value) : null)}
        />
        <span className="text-xs" style={{ color: "#C8BDB0" }}>–</span>
        <input
          type="number"
          placeholder="Max"
          style={inputStyle}
          value={maxPay ?? ""}
          min={0}
          onChange={(e) => onMaxChange(e.target.value ? parseInt(e.target.value) : null)}
        />
      </div>
    </div>
  );
}
