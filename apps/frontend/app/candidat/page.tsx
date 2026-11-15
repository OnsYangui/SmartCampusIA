import type { Metadata } from "next"

import { ComingSoon } from "@/components/coming-soon"

export const metadata: Metadata = { title: "Espace candidat — SmartCampus AI" }

export default function CandidatPage() {
  return (
    <ComingSoon
      title="Espace candidat"
      description="Suivez votre préinscription, votre QCM et votre rendez-vous. Bientôt disponible."
    />
  )
}
