import type { Metadata } from "next"
import Link from "next/link"
import { Suspense } from "react"

import { LoginForm } from "@/components/login-form"
import { Button } from "@/components/ui/button"

export const metadata: Metadata = { title: "Connexion — SmartCampus AI" }

export default function LoginPage() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-4 p-4">
      {}
      <Suspense>
        <LoginForm />
      </Suspense>
      <Button
        variant="ghost"
        size="sm"
        nativeButton={false}
        render={<Link href="/" />}
      >
        Retour à l&apos;accueil
      </Button>
    </main>
  )
}
