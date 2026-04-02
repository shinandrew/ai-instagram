interface Props {
  rank: number | null | undefined;
  prevRank?: number | null;
  className?: string;
}

export function RankBadge({ rank, prevRank, className = "" }: Props) {
  if (!rank) return null;

  let arrow: React.ReactNode = null;
  if (prevRank != null && prevRank !== rank) {
    if (rank < prevRank) {
      // Rank number decreased → moved up
      arrow = (
        <svg className="w-3 h-3 text-red-500 shrink-0" viewBox="0 0 12 12" fill="currentColor">
          <path d="M6 1L11 8H1L6 1Z" />
        </svg>
      );
    } else {
      // Rank number increased → moved down
      arrow = (
        <svg className="w-3 h-3 text-blue-700 shrink-0" viewBox="0 0 12 12" fill="currentColor">
          <path d="M6 11L1 4H11L6 11Z" />
        </svg>
      );
    }
  }

  return (
    <span
      className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 text-xs font-bold leading-none shrink-0 ${className}`}
    >
      {arrow}
      #{rank}
    </span>
  );
}
