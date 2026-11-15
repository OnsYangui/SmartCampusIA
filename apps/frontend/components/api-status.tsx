"use client"

import { useEffect, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { API_BASE } from "@/lib/config"

type Status = "checking" | "online" | "offline"

const LABELS: Record<Status, string> = {
  checking: "API : vérification…",
  online: "API : en ligne",
  offline: "API : hors ligne",
}

const VARIANTS = {
  checking: "outline",
  online: "secondary",
  offline: "destructive",
} as const

export function ApiStatus() {
  const [status, setStatus] = useState<Status>("checking")

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${API_BASE}/health`, { signal: controller.signal })
      .then((res) => setStatus(res.ok ? "online" : "offline"))
      .catch(() => {
        if (!controller.signal.aborted) setStatus("offline")
      })
    return () => controller.abort()
  }, [])

  return (
    <Badge variant={VARIANTS[status]} aria-live="polite">
      {LABELS[status]}
    </Badge>
  )
}
