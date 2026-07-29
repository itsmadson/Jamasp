import { ApiError, apiFetch } from "./client";

export interface UserOut {
  id: string;
  email: string;
  role: "admin" | "analyst";
  locale: string;
}

export function login(email: string, password: string): Promise<UserOut> {
  return apiFetch<UserOut>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/api/auth/logout", { method: "POST" });
}

export async function getCurrentUser(): Promise<UserOut | null> {
  try {
    return await apiFetch<UserOut>("/api/auth/me");
  } catch (error) {
    // 401 is the normal signed-out answer, not a failure worth propagating.
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}
