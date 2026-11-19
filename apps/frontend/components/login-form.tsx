"use client"

import { useRouter, useSearchParams } from "next/navigation"
import { useEffect, useState } from "react"

import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { HOME_BY_ROLE, safeNext } from "@/lib/auth"

const DEMO_ACCOUNTS: { label: string; email: string }[] = [
  { label: "Candidat", email: "candidat.c04@example.com" },
  { label: "Responsable académique", email: "resp.academique.iit@example.com" },
  { label: "Responsable entretien", email: "resp.entretien.iit@example.com" },
  { label: "Direction", email: "direction@example.com" },
  { label: "Administrateur", email: "admin@example.com" },
]

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
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle>Connexion</CardTitle>
        <CardDescription>
          Candidats inscrits et équipes IIT / ISB.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium">
              Adresse e-mail
            </label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={error ? true : undefined}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium">
              Mot de passe
            </label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={error ? true : undefined}
            />
          </div>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}

          <Button type="submit" disabled={pending || !email || !password}>
            {pending ? "Connexion…" : "Se connecter"}
          </Button>
        </form>

        {process.env.NODE_ENV === "development" && (
          <div className="mt-6 border-t pt-4">
            <div className="flex flex-wrap gap-2">
              {DEMO_ACCOUNTS.map((account) => (
                <Button
                  key={account.email}
                  type="button"
                  variant="outline"
                  size="sm"
                  className="rounded-full font-normal"
                  onClick={() => setEmail(account.email)}
                >
                  {account.label}
                </Button>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}