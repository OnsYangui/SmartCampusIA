"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"

import { useAuth } from "@/components/auth-provider"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { HOME_BY_ROLE, ROLE_LABELS } from "@/lib/auth"

export function UserMenu() {
  const { user, loading, signOut } = useAuth()
  const router = useRouter()

  if (loading) return null

  if (!user) {
    return (
      <Button size="sm" nativeButton={false} render={<Link href="/login" />}>
        Se connecter
      </Button>
    )
  }

  return (
    <>
      <Badge variant="outline" title={user.email}>
        {ROLE_LABELS[user.role]}
      </Badge>
      <Button
        variant="ghost"
        size="sm"
        nativeButton={false}
        render={<Link href={HOME_BY_ROLE[user.role]} />}
      >
        Mon espace
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={async () => {
          await signOut()
          router.refresh()
        }}
      >
        Déconnexion
      </Button>
    </>
  )
}
