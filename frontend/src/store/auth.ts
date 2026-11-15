// Signed-in user + bearer token (persisted). Roles: "admin" (scheduler) and "faculty".
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "../api";

interface AuthState {
  token: string | null;
  user: User | null;
  signIn: (token: string, user: User) => void;
  signOut: (expired?: boolean) => void;
  setUser: (user: User) => void;
  /** Set when a session expired so the login page can explain why. */
  expired: boolean;
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      expired: false,
      signIn: (token, user) => set({ token, user, expired: false }),
      signOut: (expired = false) => set({ token: null, user: null, expired }),
      setUser: (user) => set({ user }),
    }),
    { name: "econ-auth", partialize: (s) => ({ token: s.token, user: s.user }) },
  ),
);

export const useIsAdmin = () => useAuth((s) => s.user?.role === "admin");
