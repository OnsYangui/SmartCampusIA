"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { useEffect, useState } from "react"

import { useAuth } from "@/components/auth-provider"
import { HOME_BY_ROLE, safeNext } from "@/lib/auth"

const DEMO_ACCOUNTS: { label: string; email: string }[] = [
  { label: "Candidat", email: "candidat.c04@example.com" },
  { label: "Responsable académique", email: "resp.academique.iit@example.com" },
  { label: "Responsable entretien", email: "resp.entretien.iit@example.com" },
  { label: "Direction", email: "direction@example.com" },
  { label: "Administrateur", email: "admin@example.com" },
]

const FIELD =
  "h-12 w-full rounded-[14px] border border-slate-300 bg-white pr-3.5 pl-11 text-[15px] outline-none transition focus:border-2 focus:border-indigo-600 focus:ring-4 focus:ring-indigo-600/15 aria-invalid:border-red-500"

export function LoginForm() {
  const { user, loading, signIn } = useAuth()
  const router = useRouter()
  const next = safeNext(useSearchParams().get("next"))

  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!loading && user) router.replace(next ?? HOME_BY_ROLE[user.role])
  }, [loading, user, next, router])

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      const signedIn = await signIn(email.trim(), password)
      router.replace(next ?? HOME_BY_ROLE[signedIn.role])
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Connexion impossible."
      )
      setPending(false)
    }
  }

  return (
    <div
      style={{ animationDelay: "150ms" }}
      className="w-full rounded-3xl bg-white p-7 shadow-[0_30px_80px_rgba(0,0,0,0.45)] sm:p-[30px] motion-safe:animate-login-rise"
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-[18px]" noValidate>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="email" className="text-sm font-semibold">
            Adresse e-mail
          </label>
          <div className="relative">
            <svg
              className="absolute top-1/2 left-3.5 size-[18px] -translate-y-1/2 text-indigo-600"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="M3 7l9 6 9-6" />
            </svg>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={error ? true : undefined}
              className={FIELD}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="password" className="text-sm font-semibold">
            Mot de passe
          </label>
          <div className="relative">
            <svg
              className="absolute top-1/2 left-3.5 size-[18px] -translate-y-1/2 text-slate-500"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <rect x="4" y="11" width="16" height="10" rx="2" />
              <path d="M8 11V7a4 4 0 0 1 8 0v4" />
            </svg>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={error ? true : undefined}
              className={FIELD}
            />
          </div>
        </div>

        {error && (
          <p
            role="alert"
            className="rounded-xl bg-red-50 px-3.5 py-2.5 text-sm text-red-800"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={pending || !email || !password}
          className="relative h-[50px] overflow-hidden rounded-[14px] bg-indigo-600 text-[15px] font-semibold text-white shadow-[0_10px_24px_rgba(79,70,229,0.35)] transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-y-0 left-0 w-2/5 bg-linear-to-r from-transparent via-white/40 to-transparent motion-safe:animate-login-shine"
          />
          <span className="relative">
            {pending ? "Connexion…" : "Se connecter"}
          </span>
        </button>
      </form>

      {process.env.NODE_ENV === "development" && (
        <div className="mt-5 flex flex-col gap-2.5 border-t border-slate-200 pt-4">
          <span className="text-[11px] font-semibold tracking-[1px] text-slate-500 uppercase">
            Démo (développement uniquement)
          </span>
          <div className="flex flex-wrap gap-2">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                onClick={() => setEmail(account.email)}
                className={`rounded-full border px-3 py-1.5 text-xs transition ${
                  email === account.email
                    ? "border-indigo-300 bg-indigo-50 font-semibold text-indigo-800"
                    : "border-slate-300 bg-white hover:bg-slate-50"
                }`}
              >
                {account.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}