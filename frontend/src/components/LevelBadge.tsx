export const LEVEL_NAMES = [
  "Novice",      // 0 cleared → 1 agent
  "Curious",     // 1 cleared → 2 agents
  "Explorer",    // 2 cleared → 3 agents
  "Apprentice",  // 3 cleared → 4 agents
  "Enthusiast",  // 4 cleared → 5 agents
  "Curator",     // 5 cleared → 6 agents
  "Expert",      // 6 cleared → 7 agents
  "Influencer",  // 7 cleared → 8 agents
  "Champion",    // 8 cleared → 9 agents
  "Legend",      // 9 cleared → 10 agents
];

const LEVEL_COLORS = [
  "bg-gray-100 text-gray-600",
  "bg-sky-100 text-sky-700",
  "bg-teal-100 text-teal-700",
  "bg-green-100 text-green-700",
  "bg-yellow-100 text-yellow-700",
  "bg-orange-100 text-orange-700",
  "bg-red-100 text-red-700",
  "bg-purple-100 text-purple-700",
  "bg-indigo-100 text-indigo-700",
  "bg-amber-200 text-amber-800 font-bold",
];

interface Props {
  missionsCleared: number;
  className?: string;
}

export function LevelBadge({ missionsCleared, className = "" }: Props) {
  const idx = Math.min(missionsCleared, LEVEL_NAMES.length - 1);
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${LEVEL_COLORS[idx]} ${className}`}
    >
      {LEVEL_NAMES[idx]}
    </span>
  );
}
