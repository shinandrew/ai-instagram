interface Props {
  rank: number | null | undefined;
  className?: string;
}

export function RankBadge({ rank, className = "" }: Props) {
  if (!rank) return null;
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded-md bg-amber-100 text-amber-700 text-xs font-bold leading-none shrink-0 ${className}`}
    >
      #{rank}
    </span>
  );
}
