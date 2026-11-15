import type { Metadata } from "next"

import { ComingSoon } from "@/components/coming-soon"

export const metadata: Metadata = { title: "Chat — SmartCampus AI" }

export default function ChatPage() {
  return (
    <ComingSoon
      title="Chat d'orientation"
      description="Échangez avec l'assistant en français, en tunisien ou en Arabizi. Bientôt disponible."
    />
  )
}
