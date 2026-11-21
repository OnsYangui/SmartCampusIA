import type { Metadata } from "next"

import { ComingSoon } from "@/components/coming-soon"
import { RequireRole } from "@/components/require-role"

export const metadata: Metadata = { title: "Tableau de bord — SmartCampus AI" }

export default function DashboardPage() {
  // SA-5 §3: statistics are for the management, the academic managers and the administrators.
  return (
    <RequireRole roles={["academic_manager", "management", "admin"]}>
      <ComingSoon
        title="Tableau de bord"
        description="Indicateurs d'orientation et de conversion pour les équipes IIT et ISB. Bientôt disponible."
      />
    </RequireRole>
  )
}
