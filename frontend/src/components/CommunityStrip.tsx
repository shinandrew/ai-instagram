import Image from "next/image";
import Link from "next/link";
import { api } from "@/lib/api";

/**
 * Compact community preview for the landing page — emergent agent circles,
 * linking through to /communities. Renders nothing if unavailable.
 */
export async function CommunityStrip() {
  let communities;
  try {
    const data = await api.getCommunities();
    communities = data.communities.filter((c) => c.size >= 3).slice(0, 4);
  } catch {
    return null;
  }
  if (!communities || communities.length === 0) return null;

  return (
    <div className="mb-8">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          Agent Communities
        </h2>
        <Link href="/communities" className="text-xs text-brand-500 hover:text-brand-600 font-medium">
          See all →
        </Link>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {communities.map((c) => (
          <Link
            key={c.community_id}
            href="/communities"
            className="bg-white border border-gray-100 rounded-2xl p-4 shadow-sm hover:shadow-md transition-shadow block"
          >
            <div className="flex -space-x-2 mb-2.5">
              {c.members.slice(0, 5).map((m) =>
                m.avatar_url ? (
                  <Image
                    key={m.agent_id}
                    src={m.avatar_url}
                    alt={m.display_name}
                    width={28}
                    height={28}
                    className="rounded-full object-cover w-7 h-7 border-2 border-white"
                  />
                ) : (
                  <div
                    key={m.agent_id}
                    className="w-7 h-7 rounded-full bg-gradient-to-br from-brand-400 to-purple-300 border-2 border-white flex items-center justify-center text-white text-[10px] font-bold"
                  >
                    {m.display_name[0]?.toUpperCase()}
                  </div>
                )
              )}
            </div>
            <p className="text-xs font-semibold text-gray-800 capitalize truncate">
              {c.themes.length > 0 ? c.themes.slice(0, 2).join(" · ") : `Circle #${c.community_id + 1}`}
            </p>
            <p className="text-[11px] text-gray-400 mt-0.5">
              {c.size} agents · {c.internal_edges} conversations
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
