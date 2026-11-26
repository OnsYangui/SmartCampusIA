"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { useAuth } from "@/components/auth-provider"
import { RequireRole } from "@/components/require-role"
import { apiFetch, ROLE_LABELS, type User } from "@/lib/auth"

type DocumentItem = {
  id: string
  institution_id: string
  program_id: string | null
  title: string
  version: number
  status: "active" | "archived"
  created_at: string
}

type Program = { id: string; name: string; institution: { id: string; code: string } }
type Institution = { id: string; code: string; name: string }
type Tab = "active" | "archived"

const INPUT =
  "h-11 rounded-xl border border-slate-300 bg-white px-3.5 text-[15px] font-normal outline-none focus:border-indigo-600 focus:ring-4 focus:ring-indigo-600/15"

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.message === "string") return body.message
  } catch {
    // pas de JSON : message par défaut ci-dessous
  }
  if (response.status === 403) return "Tu n'as pas le droit de faire cette action."
  return "Une erreur est survenue, réessaie."
}

async function fetchList<T>(path: string): Promise<T[]> {
  const response = await apiFetch(path)
  if (!response.ok) throw new Error(await readError(response))
  const data = await response.json()
  return data.items ?? []
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  })
}

function Status({ version }: { version: number }) {
  if (version > 0) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-900">
        <span className="size-1.5 rounded-full bg-green-600" />
        Version {version} indexée
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900">
      <span className="size-1.5 rounded-full bg-amber-600" />
      En attente d&apos;indexation
    </span>
  )
}

function Modal({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string
  subtitle: string
  onClose: () => void
  children: React.ReactNode
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[#0e1a3d]/60 p-4">
      <div
        role="dialog"
        aria-label={title}
        className="flex w-full max-w-lg flex-col gap-5 rounded-3xl bg-white p-7 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-[#0e1a3d]">{title}</h2>
            <p className="mt-1 text-sm text-slate-600">{subtitle}</p>
          </div>
          <button
            type="button"
            aria-label="Fermer"
            onClick={onClose}
            className="size-9 shrink-0 rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

function Buttons({
  busy,
  label,
  busyLabel,
  onClose,
}: {
  busy: boolean
  label: string
  busyLabel: string
  onClose: () => void
}) {
  return (
    <div className="flex justify-end gap-3">
      <button
        type="button"
        onClick={onClose}
        className="h-11 rounded-xl border border-slate-300 px-5 text-sm font-semibold hover:bg-slate-50"
      >
        Annuler
      </button>
      <button
        type="submit"
        disabled={busy}
        className="h-11 rounded-xl bg-indigo-600 px-6 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 hover:bg-indigo-700 disabled:opacity-60"
      >
        {busy ? busyLabel : label}
      </button>
    </div>
  )
}

function ProgramSelect({
  value,
  onChange,
  programs,
}: {
  value: string
  onChange: (value: string) => void
  programs: Program[]
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-semibold">
      <span>
        Formation concernée <span className="font-normal text-slate-600">(facultatif)</span>
      </span>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={INPUT}>
        <option value="">Tout l&apos;établissement</option>
        {programs.map((program) => (
          <option key={program.id} value={program.id}>
            {program.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function ErrorLine({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <p role="alert" className="rounded-xl bg-red-50 px-3.5 py-2.5 text-sm text-red-800">
      {message}
    </p>
  )
}

function AddModal({
  user,
  programs,
  institutions,
  onClose,
  onDone,
}: {
  user: User
  programs: Program[]
  institutions: Institution[]
  onClose: () => void
  onDone: () => void
}) {
  const isAdmin = user.role === "admin"
  const [title, setTitle] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [institutionId, setInstitutionId] = useState("")
  const [programId, setProgramId] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const scope = isAdmin ? institutionId : user.institution_id
  const options = programs.filter((p) => p.institution.id === scope)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!file) {
      setError("Choisis un fichier PDF.")
      return
    }
    if (isAdmin && !institutionId) {
      setError("Choisis l'établissement.")
      return
    }
    setBusy(true)
    setError(null)
    const body = new FormData()
    body.append("title", title.trim())
    body.append("file", file)
    if (isAdmin) body.append("institution_id", institutionId)
    if (programId) body.append("program_id", programId)
    const response = await apiFetch("/documents", { method: "POST", body })
    setBusy(false)
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    onDone()
  }

  return (
    <Modal
      title="Ajouter un document"
      subtitle="Le fichier est conservé puis indexé pour que l'assistant puisse s'en servir."
      onClose={onClose}
    >
      <form onSubmit={submit} className="flex flex-col gap-5">
        <label className="flex flex-col gap-1.5 text-sm font-semibold">
          Titre
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={200}
            className={INPUT}
          />
        </label>

        {isAdmin && (
          <label className="flex flex-col gap-1.5 text-sm font-semibold">
            Établissement
            <select
              value={institutionId}
              onChange={(e) => {
                setInstitutionId(e.target.value)
                setProgramId("")
              }}
              className={INPUT}
            >
              <option value="">Choisir…</option>
              {institutions.map((institution) => (
                <option key={institution.id} value={institution.id}>
                  {institution.code} · {institution.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <ProgramSelect value={programId} onChange={setProgramId} programs={options} />

        <label className="flex cursor-pointer items-center gap-4 rounded-2xl border-2 border-dashed border-indigo-300 bg-indigo-50 p-4">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-indigo-200 bg-white text-xs font-bold text-indigo-700">
            PDF
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-sm font-semibold">
              {file ? file.name : "Choisir un fichier PDF"}
            </span>
            <span className="text-xs text-slate-600">PDF uniquement, 20 Mo maximum</span>
          </span>
          <input
            type="file"
            accept="application/pdf"
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <ErrorLine message={error} />
        <Buttons busy={busy} label="Envoyer le document" busyLabel="Envoi…" onClose={onClose} />
      </form>
    </Modal>
  )
}

function EditModal({
  document,
  programs,
  onClose,
  onDone,
}: {
  document: DocumentItem
  programs: Program[]
  onClose: () => void
  onDone: () => void
}) {
  const [title, setTitle] = useState(document.title)
  const [programId, setProgramId] = useState(document.program_id ?? "")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const options = programs.filter((p) => p.institution.id === document.institution_id)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    const response = await apiFetch(`/documents/${document.id}`, {
      method: "PUT",
      body: JSON.stringify({ title: title.trim(), program_id: programId || null }),
    })
    setBusy(false)
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    onDone()
  }

  return (
    <Modal
      title="Modifier le document"
      subtitle="Change le titre ou la formation concernée."
      onClose={onClose}
    >
      <form onSubmit={submit} className="flex flex-col gap-5">
        <label className="flex flex-col gap-1.5 text-sm font-semibold">
          Titre
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={200}
            className={INPUT}
          />
        </label>
        <ProgramSelect value={programId} onChange={setProgramId} programs={options} />
        <ErrorLine message={error} />
        <Buttons busy={busy} label="Enregistrer" busyLabel="Enregistrement…" onClose={onClose} />
      </form>
    </Modal>
  )
}

function DocumentsContent({ user }: { user: User }) {
  const { signOut } = useAuth()
  const router = useRouter()
  const [tab, setTab] = useState<Tab>("active")
  const [active, setActive] = useState<DocumentItem[]>([])
  const [archived, setArchived] = useState<DocumentItem[]>([])
  const [programs, setPrograms] = useState<Program[]>([])
  const [institutions, setInstitutions] = useState<Institution[]>([])
  const [search, setSearch] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<DocumentItem | null>(null)
  const [menuId, setMenuId] = useState<string | null>(null)
  const versionInput = useRef<HTMLInputElement>(null)
  const versionTarget = useRef<string | null>(null)
      // Pour recharger la liste, on change ce compteur : l'effet ci-dessous se relance.
  const [refresh, setRefresh] = useState(0)
  const reload = useCallback(() => setRefresh((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [a, b] = await Promise.all([
          fetchList<DocumentItem>("/documents?status=active&size=100"),
          fetchList<DocumentItem>("/documents?status=archived&size=100"),
        ])
        if (cancelled) return
        setActive(a)
        setArchived(b)
        setError(null)
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Impossible de charger les documents.")
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    void load()
    return () => {
      cancelled = true
    }
  }, [refresh])

  useEffect(() => {
    void fetchList<Program>("/programs?size=100")
      .then(setPrograms)
      .catch(() => setPrograms([]))
    if (user.role === "admin") {
      void fetchList<Institution>("/institutions?size=100")
        .then(setInstitutions)
        .catch(() => setInstitutions([]))
    }
  }, [user.role])


  const programName = useMemo(() => new Map(programs.map((p) => [p.id, p.name])), [programs])
  const indexed = active.filter((d) => d.version > 0).length
  const pending = active.length - indexed

  const rows = useMemo(() => {
    const list = tab === "active" ? active : archived
    const term = search.trim().toLowerCase()
    return term ? list.filter((d) => d.title.toLowerCase().includes(term)) : list
  }, [tab, active, archived, search])

  async function archive(doc: DocumentItem) {
    setMenuId(null)
    if (!window.confirm(`Retirer « ${doc.title} » ? L'assistant ne l'utilisera plus.`)) return
    const response = await apiFetch(`/documents/${doc.id}`, { method: "DELETE" })
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    await reload()
  }

  async function sendVersion(file: File) {
    const id = versionTarget.current
    if (!id) return
    const body = new FormData()
    body.append("file", file)
    const response = await apiFetch(`/documents/${id}/versions`, { method: "POST", body })
    if (!response.ok) {
      setError(await readError(response))
      return
    }
    setError(null)
    await reload()
  }

  return (
    <div className="flex min-h-svh bg-[#f5f6fb] text-[#0e1a3d]">
      <aside className="hidden w-64 shrink-0 flex-col gap-7 bg-[#0e1a3d] px-4 py-7 text-white md:flex">
        <div className="flex items-center gap-3 px-1.5">
          <div className="flex size-9 items-center justify-center rounded-xl bg-[#ffc83d] text-sm font-bold text-[#0e1a3d]">
            SC
          </div>
          <span className="text-lg font-bold">SmartCampus AI</span>
        </div>
        <nav className="flex flex-col gap-1.5 text-sm font-medium">
          <Link href="/dashboard" className="rounded-xl px-3.5 py-3 text-[#b9c3e6] hover:bg-[#16255a]">
            Tableau de bord
          </Link>
          <span className="rounded-xl bg-[#1d2d63] px-3.5 py-3 font-semibold shadow-[inset_3px_0_0_#ffc83d]">
            Documents
          </span>
          <Link href="/chat" className="rounded-xl px-3.5 py-3 text-[#b9c3e6] hover:bg-[#16255a]">
            Assistant
          </Link>
        </nav>
        <div className="mt-auto flex items-center gap-3 rounded-2xl bg-[#16255a] p-3">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold">
            {user.email.slice(0, 2).toUpperCase()}
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-[13px] font-semibold">{ROLE_LABELS[user.role]}</span>
            <span className="truncate text-xs text-[#b9c3e6]">{user.email}</span>
          </div>
          <button
            type="button"
            aria-label="Se déconnecter"
            title="Se déconnecter"
            onClick={async () => {
              await signOut()
              router.replace("/login")
            }}
            className="size-8 shrink-0 rounded-lg text-[#b9c3e6] hover:bg-[#1d2d63]"
          >
            ⎋
          </button>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col gap-6 px-6 py-8 md:px-10">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Documents officiels</h1>
            <p className="mt-1.5 max-w-xl text-sm text-slate-600">
              Les sources sur lesquelles l&apos;assistant s&apos;appuie pour répondre aux candidats, avec
              leur référence.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="h-11 rounded-xl bg-indigo-600 px-5 text-sm font-semibold text-white shadow-lg shadow-indigo-600/30 hover:bg-indigo-700"
          >
            + Ajouter un document
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          {[
            { value: active.length, label: "Documents actifs", tone: "bg-indigo-100 text-indigo-700" },
            {
              value: indexed,
              label: "Indexés, utilisables par l'assistant",
              tone: "bg-green-100 text-green-800",
            },
            { value: pending, label: "En attente d'indexation", tone: "bg-amber-100 text-amber-800" },
          ].map((card) => (
            <div
              key={card.label}
              className="flex items-center gap-4 rounded-2xl border border-slate-200 bg-white px-5 py-4"
            >
              <span
                className={`flex size-11 items-center justify-center rounded-xl text-xl font-bold ${card.tone}`}
              >
                {card.value}
              </span>
              <span className="text-sm text-slate-600">{card.label}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un document…"
            aria-label="Rechercher un document"
            className="h-10 w-full max-w-sm rounded-xl border border-slate-300 bg-white px-3.5 text-sm outline-none focus:border-indigo-600 focus:ring-4 focus:ring-indigo-600/15"
          />
          <div className="flex gap-1.5 rounded-xl bg-slate-200/70 p-1">
            {(["active", "archived"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setTab(value)}
                className={`h-8 rounded-lg px-4 text-sm ${
                  tab === value ? "bg-white font-semibold shadow-sm" : "text-slate-600"
                }`}
              >
                {value === "active" ? `Actifs · ${active.length}` : `Archivés · ${archived.length}`}
              </button>
            ))}
          </div>
        </div>

        <ErrorLine message={error} />

        <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="hidden grid-cols-[3fr_2fr_2fr_1.2fr_1.8fr] gap-4 rounded-t-2xl border-b border-slate-200 bg-slate-50 px-5 py-3 text-xs font-semibold uppercase tracking-wide text-slate-600 md:grid">
            <span>Document</span>
            <span>Formation</span>
            <span>Indexation</span>
            <span>Ajouté le</span>
            <span className="text-right">Actions</span>
          </div>

          {loading && <p className="px-5 py-8 text-sm text-slate-600">Chargement…</p>}
          {!loading && rows.length === 0 && (
            <p className="px-5 py-8 text-sm text-slate-600">Aucun document.</p>
          )}

          {rows.map((doc) => (
            <div
              key={doc.id}
              className="grid grid-cols-1 items-center gap-3 border-b border-slate-100 px-5 py-3.5 text-sm last:border-b-0 md:grid-cols-[3fr_2fr_2fr_1.2fr_1.8fr] md:gap-4"
            >
              <span className="flex items-center gap-3 font-semibold">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-[11px] font-bold text-indigo-700">
                  PDF
                </span>
                {doc.title}
              </span>
              <span className="text-slate-600">
                {doc.program_id
                  ? (programName.get(doc.program_id) ?? "Formation précise")
                  : "Tout l'établissement"}
              </span>
              <span>
                {doc.status === "archived" ? (
                  <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700">
                    Retiré
                  </span>
                ) : (
                  <Status version={doc.version} />
                )}
              </span>
              <span className="text-slate-600">{formatDate(doc.created_at)}</span>
              <span className="relative flex items-center justify-end gap-2">
                {doc.status === "active" && (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        versionTarget.current = doc.id
                        versionInput.current?.click()
                      }}
                      className="h-8 rounded-lg bg-indigo-100 px-3 text-[13px] font-semibold text-indigo-800 hover:bg-indigo-200"
                    >
                      Nouvelle version
                    </button>
                    <button
                      type="button"
                      aria-label="Plus d'actions"
                      onClick={() => setMenuId(menuId === doc.id ? null : doc.id)}
                      className="size-8 rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-50"
                    >
                      ⋯
                    </button>
                    {menuId === doc.id && (
                      <div className="absolute right-0 top-10 z-10 flex w-44 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
                        <button
                          type="button"
                          onClick={() => {
                            setMenuId(null)
                            setEditing(doc)
                          }}
                          className="px-4 py-2.5 text-left text-sm hover:bg-slate-50"
                        >
                          Modifier
                        </button>
                        <button
                          type="button"
                          onClick={() => void archive(doc)}
                          className="px-4 py-2.5 text-left text-sm text-red-700 hover:bg-red-50"
                        >
                          Retirer
                        </button>
                      </div>
                    )}
                  </>
                )}
              </span>
            </div>
          ))}
        </div>
      </main>

      <input
        ref={versionInput}
        type="file"
        accept="application/pdf"
        className="sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0]
          e.target.value = ""
          if (file) void sendVersion(file)
        }}
      />

      {adding && (
        <AddModal
          user={user}
          programs={programs}
          institutions={institutions}
          onClose={() => setAdding(false)}
          onDone={() => {
            setAdding(false)
            void reload()
          }}
        />
      )}
      {editing && (
        <EditModal
          document={editing}
          programs={programs}
          onClose={() => setEditing(null)}
          onDone={() => {
            setEditing(null)
            void reload()
          }}
        />
      )}
    </div>
  )
}

function DocumentsGate() {
  const { user } = useAuth()
  if (!user) return null
  return <DocumentsContent user={user} />
}

export default function DocumentsPage() {
  // SA-5 : les documents sont réservés aux responsables académiques (leur établissement) et à l'admin.
  return (
    <RequireRole roles={["academic_manager", "admin"]}>
      <DocumentsGate />
    </RequireRole>
  )
}