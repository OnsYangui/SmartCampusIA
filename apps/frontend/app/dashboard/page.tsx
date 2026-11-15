import type { Metadata } from "next"

import { ComingSoon } from "@/components/coming-soon"

export const metadata: Metadata = { title: "Tableau de bord — SmartCampus AI" }

export default function DashboardPage() {
  return (
    <ComingSoon
      title="Tableau de bord"
      description="Indicateurs d'orientation et de conversion pour les équipes IIT et ISB. Bientôt disponible."
    />
  )
}
