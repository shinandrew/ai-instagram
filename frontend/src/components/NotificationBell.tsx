"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import Image from "next/image";
import { useSession } from "next-auth/react";
import { api, NotificationGroup, NotificationActor } from "@/lib/api";

function actorSummary(actors: NotificationActor[], total: number): string {
  if (actors.length === 0) return "Someone";
  const first = actors[0].display_name;
  if (total === 1) return first;
  if (total === 2) return `${first} and ${actors[1]?.display_name ?? "1 other"}`;
  return `${first} and ${total - 1} others`;
}

function notificationText(n: NotificationGroup): string {
  const who = actorSummary(n.actors, n.total_actor_count);
  const agent = `@${n.target_agent.username}`;
  switch (n.type) {
    case "agent_liked_post":
    case "human_liked_post":
      return `${who} liked ${agent}'s post`;
    case "agent_commented_post":
      return `${who} commented on ${agent}'s post`;
    case "agent_followed_agent":
    case "human_followed_agent":
      return `${who} followed ${agent}`;
    default:
      return `New activity on ${agent}`;
  }
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function ActorAvatar({ actor }: { actor: NotificationActor }) {
  if (actor.avatar_url) {
    return (
      <Image
        src={actor.avatar_url}
        alt={actor.display_name}
        width={20}
        height={20}
        className="rounded-full object-cover w-5 h-5 shrink-0"
        unoptimized
      />
    );
  }
  return (
    <div className="w-5 h-5 rounded-full bg-gradient-to-br from-brand-500 to-purple-300 flex items-center justify-center text-white text-xs font-bold shrink-0">
      {actor.display_name[0]?.toUpperCase()}
    </div>
  );
}

export function NotificationBell() {
  const { data: session } = useSession();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationGroup[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const humanToken = (session as any)?.human_token as string | undefined;

  const fetchNotifications = useCallback(async () => {
    if (!humanToken) return;
    try {
      const data = await api.getNotifications(humanToken);
      setNotifications(data.notifications);
      setUnreadCount(data.unread_count);
    } catch {
      // silently ignore
    }
  }, [humanToken]);

  // Poll every 60s while signed in
  useEffect(() => {
    if (!humanToken) return;
    fetchNotifications();
    const id = setInterval(fetchNotifications, 60_000);
    return () => clearInterval(id);
  }, [humanToken, fetchNotifications]);

  // Close on outside click
  useEffect(() => {
    function handle(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, []);

  async function handleOpen() {
    setOpen((o) => !o);
    if (!open && unreadCount > 0 && humanToken) {
      // mark read optimistically
      setUnreadCount(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      try {
        await api.markNotificationsRead(humanToken);
      } catch {
        // ignore
      }
    }
  }

  if (!humanToken) return null;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={handleOpen}
        aria-label="Notifications"
        className="relative flex items-center justify-center w-8 h-8 rounded-lg hover:bg-gray-100 transition-colors"
      >
        <svg className="w-5 h-5 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex items-center justify-center min-w-[16px] h-4 px-0.5 rounded-full bg-red-500 text-white text-[10px] font-bold leading-none">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-10 w-80 bg-white border border-gray-200 rounded-xl shadow-lg z-50 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-gray-100">
            <p className="text-sm font-semibold text-gray-900">Notifications</p>
          </div>
          <div className="max-h-96 overflow-y-auto divide-y divide-gray-50">
            {notifications.length === 0 ? (
              <p className="text-center text-gray-400 text-sm py-8">No notifications yet</p>
            ) : (
              notifications.map((n, i) => {
                const content = (
                  <div className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50 transition-colors ${!n.is_read ? "bg-blue-50/50" : ""}`}>
                    {/* Stack up to 2 actor avatars */}
                    <div className="relative shrink-0 w-6 h-6">
                      {n.actors[1] && (
                        <div className="absolute -bottom-1 -right-1">
                          <ActorAvatar actor={n.actors[1]} />
                        </div>
                      )}
                      {n.actors[0] && <ActorAvatar actor={n.actors[0]} />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-700 leading-snug">
                        {notificationText(n)}
                      </p>
                      <p className="text-xs text-gray-400 mt-0.5">{timeAgo(n.latest_at)}</p>
                    </div>
                    {!n.is_read && (
                      <span className="shrink-0 w-1.5 h-1.5 rounded-full bg-blue-500 mt-1" />
                    )}
                  </div>
                );

                // Link to the post if it's a post notification, else to the agent
                const href = n.post_id
                  ? `/posts/${n.post_id}`
                  : `/agents/${n.target_agent.username}`;

                return (
                  <Link key={i} href={href} onClick={() => setOpen(false)}>
                    {content}
                  </Link>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
