import type { Metadata } from "next"

import { ComingSoon } from "@/components/coming-soon"
import { RequireRole } from "@/components/require-role"

export const metadata: Metadata = { title: "Espace candidat — SmartCampus AI" }

export default function CandidatPage() {
  return (
    <RequireRole roles={["candidate"]}>
      <ComingSoon
        title="Espace candidat"
        description="Suivez votre préinscription, votre QCM et votre rendez-vous. Bientôt disponible."
      />
    </RequireRole>
  )
}
