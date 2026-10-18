import "server-only";
import { cookies } from "next/headers";

export type User = { id: string; name: string; email: string; role: "ADMIN" | "OFFICER" | "VIEWER" };
export async function getCurrentUser(): Promise<{ user: User | null; unavailable: boolean }> {
  try {
    const response = await fetch(
      `${process.env.INTERNAL_API_URL ?? "http://api:8000"}/api/v1/auth/me`,
      { headers: { cookie: (await cookies()).toString() }, cache: "no-store",
        signal: AbortSignal.timeout(5000) },
    );
    if (response.status === 401) return { user: null, unavailable: false };
    if (!response.ok) return { user: null, unavailable: true };
    return { user: await response.json() as User, unavailable: false };
  } catch {
    return { user: null, unavailable: true };
  }
}
