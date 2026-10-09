"use client";

import { useEffect, useRef, useState, FormEvent } from "react";
import type { ChatTurn } from "@/lib/chat";
import { streamLlm } from "@/lib/llm";

type Message = ChatTurn & {
  id: string;
  // Message d'erreur affiché à l'écran : jamais renvoyé au modèle.
  isError?: boolean;
};

export default function ChatShell() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    const history: ChatTurn[] = [...messages, userMessage]
      .filter((m) => !m.isError)
      .map(({ role, content }) => ({ role, content }));

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    const assistantId = crypto.randomUUID();
    try {
      await streamLlm(history, (chunk) => {
        setMessages((prev) => {
          const exists = prev.some((m) => m.id === assistantId);
          if (!exists) {
            return [...prev, { id: assistantId, role: "assistant", content: chunk }];
          }
          return prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + chunk } : m
          );
        });
      });
    } catch {
      // Une réponse partielle est remplacée par le message d'erreur.
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== assistantId),
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "Une erreur est survenue. Veuillez réessayer.",
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="chat-main">
      <header className="chat-header">
        <span className="chat-title">DocQuest</span>
      </header>

      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-empty">
            Posez une question pour démarrer la conversation.
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-bubble-row ${m.role}`}>
            <div className={`chat-bubble ${m.role}`}>{m.content}</div>
          </div>
        ))}
        {/* L'indicateur de saisie disparaît dès que la réponse commence à arriver. */}
        {loading && messages[messages.length - 1]?.role === "user" && (
          <div className="chat-bubble-row assistant">
            <div className="chat-bubble assistant typing">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} className="chat-input-bar">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Écrivez un message..."
          aria-label="Message"
        />
        <button
          type="submit"
          className="send-button"
          disabled={!input.trim() || loading}
          aria-label="Envoyer"
        >
          <SendIcon />
        </button>
      </form>
    </main>
  );
}

function SendIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="12" y1="19" x2="12" y2="5" />
      <polyline points="5 12 12 5 19 12" />
    </svg>
  );
}
