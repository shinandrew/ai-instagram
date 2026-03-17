"use client";
import useSWR from "swr";
import { api } from "@/lib/api";

export function useProfile(username: string) {
  return useSWR(username ? `/profile/${username}` : null, () =>
    api.getAgentProfile(username)
  );
}
