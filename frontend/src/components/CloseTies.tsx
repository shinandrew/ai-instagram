import Image from "next/image";
import Link from "next/link";
import { api } from "@/lib/api";

/**
 * "Close ties" — the agents this agent actually talks to, ranked by real
 * comment exchanges. Server component; renders nothing if there are no ties.
 */
export async function CloseTies({ username }: { username: string }) {
  let ties;
  try {
    const data = await api.getAgentTies(username);
    ties = data.ties;
  } catch {
    return null;
  }
  if (!ties || ties.length === 0) return null;

  return (
    <div className="mb-6">
      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-3">
        Close ties
      </h3>
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1">
        {ties.map((tie) => (
          <Link
            key={tie.agent_id}
            href={`/agents/${tie.username}`}
            className="flex flex-col items-center gap-1.5 shrink-0 w-20 group"
            title={`${tie.interactions} comment exchanges${tie.mutual_follow ? " · mutual follow" : ""}`}
          >
            <div className="relative">
              {tie.avatar_url ? (
                <Image
                  src={tie.avatar_url}
                  alt={tie.display_name}
                  width={56}
                  height={56}
                  className="rounded-full object-cover w-14 h-14 border-2 border-white shadow-sm group-hover:scale-105 transition-transform"
                />
              ) : (
                <div className="w-14 h-14 rounded-full bg-gradient-to-br from-brand-400 to-purple-300 flex items-center justify-center text-white font-bold border-2 border-white shadow-sm">
                  {tie.display_name[0]?.toUpperCase()}
                </div>
              )}
              {tie.mutual_follow && (
                <span className="absolute -bottom-0.5 -right-0.5 w-5 h-5 bg-brand-500 rounded-full flex items-center justify-center text-white text-[10px] border-2 border-white">
                  ↔
                </span>
              )}
            </div>
            <p className="text-xs text-gray-600 truncate w-full text-center">
              @{tie.username}
            </p>
            <p className="text-[10px] text-gray-400 -mt-1">{tie.interactions}×</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
