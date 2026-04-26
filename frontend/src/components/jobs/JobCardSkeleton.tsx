export function JobCardSkeleton() {
  return (
    <div className="px-4 py-3.5 border-b border-[#F0EAE0] bg-white animate-pulse">
      <div className="flex items-center justify-between mb-1.5">
        <div className="h-3.5 w-28 rounded bg-[#F0EAE0]" />
        <div className="h-3 w-12 rounded-full bg-[#F5F0E8]" />
      </div>
      <div className="h-3 w-48 rounded bg-[#F5F0E8] mb-2.5" />
      <div className="flex gap-1.5 mb-2">
        <div className="h-4 w-16 rounded-full bg-[#F0EAE0]" />
        <div className="h-4 w-12 rounded-full bg-[#F0EAE0]" />
      </div>
      <div className="flex gap-1">
        <div className="h-4 w-12 rounded bg-[#F5F0E8]" />
        <div className="h-4 w-14 rounded bg-[#F5F0E8]" />
        <div className="h-4 w-10 rounded bg-[#F5F0E8]" />
      </div>
    </div>
  );
}
