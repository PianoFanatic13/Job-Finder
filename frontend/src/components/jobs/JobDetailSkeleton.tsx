export function JobDetailSkeleton() {
  return (
    <div className="h-full overflow-y-auto px-6 py-6 bg-[#F5F0E8] animate-pulse">
      <div className="h-3.5 w-24 rounded bg-[#E0D8CC] mb-2" />
      <div className="h-6 w-72 rounded bg-[#E8E0D4] mb-4" />
      <div className="h-9 w-40 rounded-lg bg-[#E0D8CC] mb-8" />

      <div className="grid grid-cols-2 gap-4 mb-8">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i}>
            <div className="h-2.5 w-16 rounded bg-[#E0D8CC] mb-2" />
            <div className="h-4 w-24 rounded bg-[#E8E0D4]" />
          </div>
        ))}
      </div>

      <div className="h-2.5 w-20 rounded bg-[#E0D8CC] mb-3" />
      <div className="flex flex-wrap gap-1.5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-5 w-16 rounded-full bg-[#E0D8CC]" />
        ))}
      </div>
    </div>
  );
}
