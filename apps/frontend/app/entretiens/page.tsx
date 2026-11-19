import type { Metadata } from "next"

import { ComingSoon } from "@/components/coming-soon"
import { RequireRole } from "@/components/require-role"

export const metadata: Metadata = { title: "Entretiens — SmartCampus AI" }

export default function InterviewsPage() {
  return (
    <RequireRole roles={["interview_manager"]}>
      <ComingSoon
        title="Entretiens"
        description="Candidats prêts pour l'entretien, publication des créneaux et décisions. Bientôt disponible."
      />
    </RequireRole>
  )
}
