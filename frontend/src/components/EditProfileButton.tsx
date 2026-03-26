"use client";

import { useState } from "react";
import { useSession } from "next-auth/react";
import { EditProfileModal } from "./EditProfileModal";

interface Props {
  username: string;
  displayName: string;
}

export function EditProfileButton({ username, displayName }: Props) {
  const { data: session } = useSession();
  const [open, setOpen] = useState(false);

  if ((session as any)?.human_username !== username) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="mt-3 px-4 py-1.5 border border-gray-300 rounded-full text-sm text-gray-700 hover:bg-gray-50 transition-colors"
      >
        Edit Profile
      </button>
      {open && (
        <EditProfileModal
          currentUsername={username}
          currentDisplayName={displayName}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
