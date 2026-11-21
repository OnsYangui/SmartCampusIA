"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect } from "react"

import { useAuth } from "@/components/auth-provider"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { HOME_BY_ROLE, ROLE_LABELS, type Role } from "@/lib/auth"

/**
 * Shows its content to the listed roles only. This is a convenience for the visitor: the real
 * protection is in the API, which checks the role of the signed token on every request.
 */
export function RequireRole({
  roles,
  children,
}: {
  roles: Role[]
  children: React.ReactNode
}) {
  const { user, loading, signOut } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`)
    }
  }, [loading, user, router, pathname])

  if (loading || !user) {
    return (
      <main className="flex min-h-svh items-center justify-center p-4">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          Vérification de la session…
        </p>
      </main>
    )
  }

  if (!roles.includes(user.role)) {
    return (
      <main className="flex min-h-svh items-center justify-center p-4">
        <Empty>
          <EmptyHeader>
            <EmptyTitle>Accès refusé</EmptyTitle>
            <EmptyDescription>
              Votre compte ({ROLE_LABELS[user.role]}) n&apos;a pas accès à cette
              page.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <div className="flex gap-2">
              <Button
                nativeButton={false}
                render={<Link href={HOME_BY_ROLE[user.role]} />}
              >
                Aller à mon espace
              </Button>
              <Button
                variant="outline"
                onClick={async () => {
                  await signOut()
                  router.replace("/login")
                }}
              >
                Se déconnecter
              </Button>
            </div>
          </EmptyContent>
        </Empty>
      </main>
    )
  }

  return <>{children}</>
}
