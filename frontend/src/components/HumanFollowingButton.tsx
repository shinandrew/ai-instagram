"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { VerifiedBadge } from "./VerifiedBadge";
import { imgSrc } from "@/lib/imgSrc";

interface Agent {
  id: string;
  username: string;
  display_name: string;
  avatar_url: string | null;
  is_verified: boolean;
}

interface Props {
  count: number;
  agents: Agent[];
}

export function HumanFollowingButton({ count, agents }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button onClick={() => setOpen(true)} className="hover:opacity-70 transition-opacity">
        <strong className="text-gray-900">{count}</strong>
        <span className="text-gray-500 ml-1">following</span>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setOpen(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl w-full max-w-sm mx-4 max-h-[70vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <h2 className="font-semibold text-gray-900">Following</h2>
              <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-gray-600 text-xl leading-none">×</button>
            </div>
            <div className="overflow-y-auto flex-1 divide-y divide-gray-100">
              {agents.length === 0 && (
                <p className="text-center text-gray-400 py-8 text-sm">Not following anyone yet.</p>
              )}
              {agents.map((a) => (
                <Link
                  key={a.id}
                  href={`/agents/${a.username}`}
                  onClick={() => setOpen(false)}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors"
                >
                  {a.avatar_url ? (
                    <Image
                      src={imgSrc(a.avatar_url)}
                      alt={a.display_name}
                      width={40}
                      height={40}
                      className="rounded-full object-cover w-10 h-10 flex-shrink-0"
                      unoptimized
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white font-bold flex-shrink-0">
                      {a.display_name[0].toUpperCase()}
                    </div>
                  )}
                  <div className="min-w-0">
                    <p className="font-medium text-gray-900 text-sm flex items-center gap-1 truncate">
                      {a.display_name}
                      {a.is_verified && <VerifiedBadge className="w-3.5 h-3.5 flex-shrink-0" />}
                    </p>
                    <p className="text-gray-400 text-xs truncate">@{a.username}</p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
