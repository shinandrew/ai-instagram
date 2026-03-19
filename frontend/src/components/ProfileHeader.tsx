import Image from "next/image";
import { Agent } from "@/lib/api";
import { VerifiedBadge } from "./VerifiedBadge";

export function ProfileHeader({ agent }: { agent: Agent }) {
  return (
    <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6 py-8">
      {agent.avatar_url ? (
        <Image
          src={agent.avatar_url}
          alt={agent.display_name}
          width={96}
          height={96}
          className="rounded-full object-cover w-24 h-24 border-4 border-brand-500"
          unoptimized
        />
      ) : (
        <div className="w-24 h-24 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-3xl font-bold border-4 border-brand-500">
          {agent.display_name[0].toUpperCase()}
        </div>
      )}

      <div className="flex-1 text-center sm:text-left">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center justify-center sm:justify-start gap-2">
          {agent.display_name}
          {agent.is_verified && <VerifiedBadge className="w-5 h-5" />}
          {agent.owner_claimed && (
            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
              Claimed
            </span>
          )}
        </h1>
        <p className="text-gray-500 text-sm mt-0.5">@{agent.username}</p>
        {agent.bio && <p className="text-gray-700 mt-2 max-w-md">{agent.bio}</p>}

        <div className="flex gap-6 mt-4 justify-center sm:justify-start text-sm">
          <div className="text-center">
            <span className="font-bold text-gray-900 block">{agent.post_count}</span>
            <span className="text-gray-500">posts</span>
          </div>
          <div className="text-center">
            <span className="font-bold text-gray-900 block">{agent.follower_count}</span>
            <span className="text-gray-500">followers</span>
          </div>
          <div className="text-center">
            <span className="font-bold text-gray-900 block">{agent.following_count}</span>
            <span className="text-gray-500">following</span>
          </div>
        </div>
      </div>
    </div>
  );
}
