import Link from "next/link"

import { ApiStatus } from "@/components/api-status"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

const NAV = [
  { href: "/chat", label: "Chat" },
  { href: "/candidat", label: "Espace candidat" },
  { href: "/dashboard", label: "Tableau de bord" },
]

const PILLARS = [
  {
    title: "Conversation multilingue",
    description:
      "Échangez en français, en dialecte tunisien ou en Arabizi, par texte ou par message vocal.",
  },
  {
    title: "Orientation justifiée",
    description:
      "Comparez les parcours Licence, Prépa et Ingénierie de l'IIT et les formations de l'ISB.",
  },
  {
    title: "Préinscription & suivi",
    description:
      "Préinscription guidée, QCM ciblé et suivi jusqu'au rendez-vous d'inscription.",
  },
]

export default function HomePage() {
  return (
    <div className="flex min-h-svh flex-col">
      <header className="border-b">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <span className="font-semibold">SmartCampus AI</span>
          <nav
            aria-label="Navigation principale"
            className="flex flex-wrap items-center gap-1"
          >
            {NAV.map((item) => (
              <Button
                key={item.href}
                variant="ghost"
                size="sm"
                nativeButton={false}
                render={<Link href={item.href} />}
              >
                {item.label}
              </Button>
            ))}
            <ApiStatus />
          </nav>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-4 py-12 sm:px-6 sm:py-20">
        <section className="flex flex-col items-start gap-5">
          <Badge variant="outline">IIT · ISB — Socle technique</Badge>
          <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-5xl">
            Votre orientation universitaire, en conversation.
          </h1>
          <p className="max-w-2xl text-base text-muted-foreground sm:text-lg">
            SmartCampus AI accompagne les futurs étudiants de la découverte des
            formations jusqu&apos;au rendez-vous d&apos;inscription.
          </p>
          <Button disabled>Démarrer la conversation (bientôt)</Button>
        </section>

        <section
          className="grid gap-4 sm:grid-cols-3"
          aria-label="Fonctionnalités prévues"
        >
          {PILLARS.map((pillar) => (
            <Card key={pillar.title}>
              <CardHeader>
                <CardTitle>{pillar.title}</CardTitle>
                <CardDescription>{pillar.description}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </section>
      </main>

      <footer className="border-t">
        <p className="mx-auto w-full max-w-5xl px-4 py-4 text-xs text-muted-foreground sm:px-6">
          Projet IA générative — IIT 2026-2027
        </p>
      </footer>
    </div>
  )
}
