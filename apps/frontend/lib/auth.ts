import { API_BASE } from "@/lib/config"

export type Role =
  | "candidate"
  | "academic_manager"
  | "interview_manager"
  | "management"
  | "admin"

export type User = {
  id: string
  email: string
  role: Role
  institution_id: string | null
}

export const ROLE_LABELS: Record<Role, string> = {
  candidate: "Candidat",
  academic_manager: "Responsable académique",
  interview_manager: "Responsable entretien",
  management: "Direction",
  admin: "Administrateur",
}

// Where each actor lands after signing in (SA-5 §3: what each role may use).
export const HOME_BY_ROLE: Record<Role, string> = {
  candidate: "/candidat",
  academic_manager: "/documents",
  interview_manager: "/entretiens",
  management: "/dashboard",
  admin: "/dashboard",
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const AUTH_PATHS = new Set(["/auth/login", "/auth/refresh", "/auth/logout"])
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"])

// The only cookie JavaScript can read: its value goes back in the X-CSRF-Token header (SA-5).
function readCsrfToken(): string {
  const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ""
}

function send(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase()
  const headers = new Headers(init.headers)
   if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json")
  }
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCsrfToken()
    if (csrf) headers.set("X-CSRF-Token", csrf)
  }
  // Same origin (Next.js proxy): the HttpOnly cookies travel without extra options.
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}

let refreshing: Promise<boolean> | null = null

// One renewal at a time, even if several requests expire together.
function refreshSession(): Promise<boolean> {
  refreshing ??= send("/auth/refresh", { method: "POST" })
    .then((response) => response.ok)
    .catch(() => false)
    .finally(() => {
      refreshing = null
    })
  return refreshing
}

/** fetch() for the API: adds the CSRF header and renews the session once on a 401. */
export async function apiFetch(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const response = await send(path, init)
  if (response.status === 401 && !AUTH_PATHS.has(path)) {
    if (await refreshSession()) return send(path, init)
  }
  return response
}

async function errorOf(response: Response): Promise<ApiError> {
  try {
    const body = await response.json()
    if (typeof body?.message === "string") {
      return new ApiError(response.status, body.message)
    }
  } catch {
    // body is not JSON: fall through
  }
  return new ApiError(response.status, "Une erreur est survenue.")
}

export async function login(email: string, password: string): Promise<User> {
  let response: Response
  try {
    response = await send("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    })
  } catch {
    throw new ApiError(0, "Impossible de joindre le serveur.")
  }
  if (!response.ok) throw await errorOf(response)
  return response.json()
}

export async function logout(): Promise<void> {
  await send("/auth/logout", { method: "POST" })
}

export async function fetchCurrentUser(): Promise<User | null> {
  const response = await apiFetch("/auth/me")
  return response.ok ? response.json() : null
}

/** Only same-site paths are accepted as a post-login destination (no open redirect). */
export function safeNext(next: string | null): string | null {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null
}
