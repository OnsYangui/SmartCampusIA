"use client"

import type { FormEvent } from "react"
import { useState } from "react"
type Message = { role: "user" | "assistant"; content: string }

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [pending, setPending] = useState(false)
  const [error, setError] = useState("")

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const message = input.trim()
    if (!message || pending) return

    setMessages((current) => [...current, { role: "user", content: message }])
    setInput("")
    setError("")
    setPending(true)
    try {
      const response = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: messages.slice(-10) }),
      })
      if (!response.ok) throw new Error("L'assistant est indisponible. Vérifiez qu'Ollama est lancé et que qwen3:4b est téléchargé.")
      const result: { message: string } = await response.json()
      setMessages((current) => [...current, { role: "assistant", content: result.message }])
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Une erreur est survenue.")
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-3xl flex-col gap-6 px-4 py-10 sm:px-6">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">Chat d&apos;orientation</h1>
        <p className="text-sm text-muted-foreground">
          Posez vos questions en français, en tunisien ou en Arabizi. Les réponses sur les admissions et les frais doivent être vérifiées auprès des établissements.
        </p>
      </header>

      <section className="flex-1 space-y-4" aria-live="polite" aria-label="Conversation">
        {messages.length === 0 && (
          <p className="rounded-lg border p-4 text-sm text-muted-foreground">
            Bonjour ! Dites-moi ce que vous souhaitez étudier et je vous aiderai à explorer vos options.
          </p>
        )}
        {messages.map((message, index) => (
          <article key={`${message.role}-${index}`} className={`max-w-[90%] whitespace-pre-wrap rounded-lg border p-4 text-sm ${message.role === "user" ? "ml-auto bg-muted" : ""}`}>
            <p className="mb-1 text-xs font-medium text-muted-foreground">{message.role === "user" ? "Vous" : "SmartCampus AI"}</p>
            {message.content}
          </article>
        ))}
        {pending && <p className="text-sm text-muted-foreground">L&apos;assistant réfléchit…</p>}
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      </section>

      <form onSubmit={sendMessage} className="flex items-end gap-2">
        <label className="sr-only" htmlFor="chat-message">Votre message</label>
        <textarea
          id="chat-message"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              event.currentTarget.form?.requestSubmit()
            }
          }}
          maxLength={4000}
          rows={2}
          placeholder="Votre question…"
          className="min-h-12 flex-1 resize-y rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <button type="submit" disabled={pending || !input.trim()} className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50">
          Envoyer
        </button>
      </form>
    </main>
  )
}
