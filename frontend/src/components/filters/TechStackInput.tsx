import { useState, useRef } from "react";

interface TechStackInputProps {
  value: string[];
  onChange: (techs: string[]) => void;
}

export function TechStackInput({ value, onChange }: TechStackInputProps) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const addTech = (raw: string) => {
    const tech = raw.trim().toLowerCase();
    if (tech && !value.includes(tech)) onChange([...value, tech]);
    setInput("");
  };

  const removeTech = (tech: string) => onChange(value.filter((t) => t !== tech));

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTech(input);
    } else if (e.key === "Backspace" && input === "" && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-col gap-1">
      <label
        className="text-[10px] font-semibold uppercase tracking-widest"
        style={{ color: "#A09AB0", letterSpacing: "0.1em" }}
      >
        Tech Stack
      </label>
      <div
        className="flex flex-wrap items-center gap-1 min-h-[32px] px-2 py-1 rounded-md cursor-text"
        style={{ background: "#F5F0E8", border: "1px solid #E0D8CC" }}
        onClick={() => inputRef.current?.focus()}
      >
        {value.map((tech) => (
          <span
            key={tech}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] text-[#1D5BDA] bg-[#DBEAFE]"
            style={{ fontFamily: "var(--font-mono)" }}
          >
            {tech}
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); removeTech(tech); }}
              className="leading-none hover:text-[#1A1624] transition-colors"
              style={{ color: "#93BFFC" }}
            >
              ×
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => { if (input.trim()) addTech(input); }}
          placeholder={value.length === 0 ? "Python, React…" : ""}
          style={{
            background: "transparent",
            border: "none",
            outline: "none",
            color: "#1A1624",
            fontSize: "12px",
            fontFamily: "var(--font-mono)",
            width: "80px",
            minWidth: "60px",
          }}
        />
      </div>
    </div>
  );
}
