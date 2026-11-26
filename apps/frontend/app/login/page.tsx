import type { Metadata } from "next"
import { Space_Grotesk } from "next/font/google"
import Link from "next/link"
import { Suspense } from "react"

import { LoginForm } from "@/components/login-form"

export const metadata: Metadata = { title: "Connexion — SmartCampus AI" }

const grotesk = Space_Grotesk({ subsets: ["latin"], weight: ["500", "700"] })

// Les points du réseau : [x, y, rayon, décalage de l'animation en secondes]
const NODES: [number, number, number, number][] = [
  [110, 170, 5, 0],
  [250, 260, 7, 0.6],
  [190, 410, 5, 1.2],
  [390, 215, 4, 1.8],
  [330, 500, 6, 0.3],
  [160, 600, 4, 2.2],
  [1090, 210, 5, 0.9],
  [1000, 330, 7, 1.5],
  [1150, 420, 5, 2.1],
  [920, 470, 4, 0.4],
  [1070, 560, 6, 1],
]

const LINKS: [number, number, number, number][] = [
  [110, 170, 250, 260],
  [250, 260, 190, 410],
  [250, 260, 390, 215],
  [190, 410, 330, 500],
  [330, 500, 160, 600],
  [1090, 210, 1000, 330],
  [1000, 330, 1150, 420],
  [1000, 330, 920, 470],
  [1150, 420, 1070, 560],
  [920, 470, 1070, 560],
]

function Decor() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div className="absolute -top-44 -left-40 size-[560px] rounded-full bg-[radial-gradient(circle,rgba(79,70,229,0.6)_0%,rgba(79,70,229,0)_70%)] motion-safe:animate-login-drift-a" />
      <div className="absolute -right-36 -bottom-48 size-[620px] rounded-full bg-[radial-gradient(circle,rgba(255,200,61,0.3)_0%,rgba(255,200,61,0)_70%)] motion-safe:animate-login-drift-b" />
      <div className="absolute -top-28 right-44 size-[420px] rounded-full bg-[radial-gradient(circle,rgba(99,102,241,0.4)_0%,rgba(99,102,241,0)_70%)] motion-safe:animate-login-drift-c" />

      <svg
        viewBox="0 0 1280 800"
        preserveAspectRatio="xMidYMid slice"
        className="absolute inset-0 hidden size-full md:block"
      >
        <g stroke="#4a5aa0" strokeWidth="1.2" fill="none">
          {LINKS.map(([x1, y1, x2, y2]) => (
            <line
              key={`${x1}-${y1}-${x2}-${y2}`}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              strokeDasharray="6 8"
              className="motion-safe:animate-login-flow"
            />
          ))}
        </g>
        <g fill="#6366f1">
          {NODES.map(([cx, cy, r, delay]) => (
            <circle
              key={`${cx}-${cy}`}
              cx={cx}
              cy={cy}
              r={r}
              style={{ animationDelay: `${delay}s` }}
              className="origin-center [transform-box:fill-box] motion-safe:animate-login-pulse"
            />
          ))}
        </g>
      </svg>

      <div className="absolute top-24 left-[90px] hidden lg:block motion-safe:animate-login-float-a">
        <div className="flex items-center gap-1.5 rounded-[18px_18px_18px_4px] border border-white/20 bg-white/10 px-[18px] py-3.5">
          {[0, 0.2, 0.4].map((delay) => (
            <span
              key={delay}
              style={{ animationDelay: `${delay}s` }}
              className="inline-block size-[7px] rounded-full bg-[#ffc83d] motion-safe:animate-login-dot"
            />
          ))}
        </div>
      </div>
      <div className="absolute top-[92px] right-16 hidden max-w-[250px] lg:block motion-safe:animate-login-float-a">
        <div className="rounded-[18px_18px_4px_18px] bg-[#4f46e5] px-4 py-3 text-sm leading-5 text-white shadow-[0_10px_30px_rgba(79,70,229,0.45)]">
          D&apos;après le guide d&apos;admission officiel, voici les étapes à suivre…
        </div>
      </div>
      <div className="absolute bottom-[110px] left-[70px] hidden max-w-[250px] lg:block motion-safe:animate-login-float-b">
        <div className="rounded-[18px_18px_18px_4px] border border-white/20 bg-white/10 px-4 py-3 text-sm leading-5 text-[#e1e6f7]">
          Quelles sont les conditions d&apos;admission en licence ?
        </div>
      </div>
      <div className="absolute right-[90px] bottom-[110px] hidden items-center gap-2 rounded-full border border-[#ffc83d]/40 bg-[#ffc83d]/10 px-4 py-2 text-[13px] font-semibold text-[#ffe08a] lg:flex motion-safe:animate-login-float-b">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#ffc83d">
          <path d="M12 2l2.2 6.3L20.5 10l-6.3 1.7L12 18l-2.2-6.3L3.5 10l6.3-1.7z" />
        </svg>
        Source officielle IIT
      </div>
    </div>
  )
}

export default function LoginPage() {
  return (
    <main className="relative flex min-h-svh items-center justify-center overflow-hidden bg-[#0e1a3d] px-4 py-10 text-[#0e1a3d]">
      <Decor />
      <div className="relative z-10 flex w-full max-w-[440px] flex-col items-center gap-6">
        <div className="flex flex-col items-center gap-3 text-center motion-safe:animate-login-rise">
          <span
            className={`${grotesk.className} text-[15px] font-bold tracking-[3px] text-[#ffc83d] uppercase`}
          >
            SmartCampus AI
          </span>
          <h1
            className={`${grotesk.className} bg-[linear-gradient(90deg,#ffffff,#ffc83d,#a5a0f5,#ffffff)] bg-[length:200%_auto] bg-clip-text pb-1 text-4xl leading-tight font-bold tracking-tight text-transparent sm:text-[42px] motion-safe:animate-login-shimmer`}
          >
            Ravi de te revoir
          </h1>
          <p className="text-[15px] leading-[22px] text-[#b9c3e6]">
            Connecte-toi pour retrouver l&apos;assistant d&apos;orientation IIT / ISB.
          </p>
        </div>

        <Suspense>
          <LoginForm />
        </Suspense>

        <Link
          href="/"
          className="text-sm font-medium text-[#b9c3e6] transition-colors hover:text-white"
        >
          ← Retour à l&apos;accueil
        </Link>
      </div>
    </main>
  )
}