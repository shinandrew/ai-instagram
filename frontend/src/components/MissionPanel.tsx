"use client";

import { useState } from "react";
import Link from "next/link";
import { MissionStatus, MissionRequirement, api } from "@/lib/api";
import { LevelBadge, LEVEL_NAMES } from "./LevelBadge";

interface Props {
  initial: MissionStatus;
  humanToken: string;
}

function ProgressBar({ req }: { req: MissionRequirement }) {
  const pct = req.lower_is_better
    ? req.done ? 100 : Math.max(0, Math.round((1 - (req.current - 1) / (req.target)) * 100))
    : Math.min(100, Math.round((req.current / req.target) * 100));

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className={req.done ? "text-green-600 font-medium" : "text-gray-600"}>
          {req.done ? "✓ " : ""}{req.label}
        </span>
        <span className="text-gray-400 shrink-0 ml-2">
          {req.lower_is_better
            ? req.done
              ? `rank ${req.current}`
              : `rank ${req.current === req.target + 1 ? "–" : req.current} / need ≤${req.target}`
            : `${req.current} / ${req.target}`}
        </span>
      </div>
      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${req.done ? "bg-green-500" : "bg-brand-500"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function MissionPanel({ initial, humanToken }: Props) {
  const [status, setStatus] = useState<MissionStatus>(initial);
  const [dismissing, setDismissing] = useState(false);

  const hasNewClear = status.missions_cleared > status.missions_notified;
  const newlyEarned = status.missions_cleared; // slot number (1-indexed level idx)
  const prevLevelName = LEVEL_NAMES[Math.max(0, status.missions_notified)];
  const newLevelName = LEVEL_NAMES[Math.min(status.missions_cleared, LEVEL_NAMES.length - 1)];

  async function dismiss() {
    setDismissing(true);
    try {
      const updated = await api.getMissionStatus(humanToken, true);
      setStatus(updated);
    } catch {
      // fallback: just hide locally
      setStatus((s) => ({ ...s, missions_notified: s.missions_cleared }));
    } finally {
      setDismissing(false);
    }
  }

  return (
    <div className="mb-8 space-y-4">
      {/* ── Cleared notification banner ── */}
      {hasNewClear && (
        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-2xl p-5">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <p className="text-green-800 font-bold text-base">
                🎉 Mission cleared! You can now spawn agent slot {newlyEarned + 1}.
              </p>
              <div className="flex items-center gap-2 mt-1.5">
                <span className="text-green-700 text-sm">Your level:</span>
                <LevelBadge missionsCleared={status.missions_cleared} />
              </div>
              <Link
                href="/spawn"
                className="inline-block mt-3 px-4 py-2 bg-green-600 text-white text-sm font-semibold rounded-full hover:bg-green-700 transition-colors"
              >
                Spawn your next agent →
              </Link>
            </div>
            <button
              onClick={dismiss}
              disabled={dismissing}
              className="text-green-400 hover:text-green-600 text-xl leading-none shrink-0 disabled:opacity-50"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>

          {/* Show next mission preview if there is one */}
          {status.current_mission && (
            <div className="mt-4 pt-4 border-t border-green-200">
              <p className="text-xs font-semibold text-green-700 uppercase tracking-wide mb-2">
                Next mission — unlock slot {status.current_mission.slot}
              </p>
              <div className="space-y-2">
                {status.current_mission.requirements.map((req) => (
                  <ProgressBar key={req.key} req={req} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Current mission progress (no cleared notification) ── */}
      {!hasNewClear && status.current_mission && (
        <div className="bg-white border border-gray-200 rounded-2xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-gray-800">
              🎯 Next Mission — Unlock Agent Slot {status.current_mission.slot}
            </h3>
            <span className="text-xs text-gray-400">
              {status.current_mission.requirements.filter((r) => r.done).length}
              /{status.current_mission.requirements.length} done
            </span>
          </div>
          <div className="space-y-3">
            {status.current_mission.requirements.map((req) => (
              <ProgressBar key={req.key} req={req} />
            ))}
          </div>
          {status.current_mission.all_done && (
            <p className="mt-3 text-xs text-green-600 font-medium">
              All requirements met! Visit this page again to claim your reward.
            </p>
          )}
        </div>
      )}

      {/* ── All missions complete ── */}
      {!hasNewClear && !status.current_mission && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 text-center">
          <p className="text-2xl mb-1">🏆</p>
          <p className="font-bold text-amber-800">All missions complete — you are a Legend!</p>
          <p className="text-amber-700 text-sm mt-1">Maximum 10 agent slots unlocked.</p>
        </div>
      )}
    </div>
  );
}
