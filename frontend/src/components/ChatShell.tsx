"use client";

import { useCallback, useEffect, useRef, useState, FormEvent } from "react";
import type { ChatTurn } from "@/lib/chat";
import { pageUrl, splitCitations } from "@/lib/citations";
import { RateLimitedError, streamLlm } from "@/lib/llm";
import { applyVoiceMessage, type TranscriptEntry } from "@/lib/transcript";
import { VoiceSession } from "@/lib/voice";

// PDF servi depuis frontend/public.
const DOC_URL = "/deu2025.pdf";

const SUGGESTIONS = [
  "Quel est le dividende proposé par action pour 2025 ?",
  "Quels sont les principaux facteurs de risque du Groupe ?",
  "Quels sont les objectifs du Groupe en matière de neutralité carbone ?",
];

type VoiceStatus ="idle" | "connecting" | "live";

type Message = TranscriptEntry & {
  // Message d'erreur affiché à l'écran : jamais renvoyé au modèle.
  isError?: boolean;
};

export default function ChatShell() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>("idle");
  const [soundOn, setSoundOn] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const voiceRef = useRef<VoiceSession | null>(null);

  const addError = useCallback((content: string) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "assistant", content, isError: true },
    ]);
  }, []);

  const stopVoice = useCallback(() => {
    voiceRef.current?.stop();
    voiceRef.current = null;
  }, []);

  const startVoice = useCallback(async () => {
    setVoiceStatus("connecting");
    setSoundOn(true);
    try {
      const session = await VoiceSession.start({
        onMessage: (message) =>
          setMessages((prev) =>
            applyVoiceMessage<Message>(prev, message, (role, content) => ({
              id: crypto.randomUUID(),
              role,
              content,
            }))
          ),
        onClose: (error) => {
          voiceRef.current = null;
          setVoiceStatus("idle");
          if (error) addError(error);
        },
      });
      voiceRef.current = session;
      setVoiceStatus("live");
    } catch (err) {
      setVoiceStatus("idle");
      addError(
        err instanceof Error && err.name === "NotAllowedError"
          ? "L'accès au micro a été refusé."
          : "Impossible de démarrer le mode vocal."
      );
    }
  }, [addError]);

  // Le micro est coupé par défaut : l'activer ouvre la session vocale, le recouper la ferme.
  function toggleMic() {
    if (voiceStatus === "idle") void startVoice();
    else stopVoice();
  }

  function toggleSound() {
    const next = !soundOn;
    setSoundOn(next);
    voiceRef.current?.setSoundOn(next);
  }

  useEffect(() => stopVoice, [stopVoice]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void send(input);
  }

  async function send(raw: string) {
    const text = raw.trim();
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
    } catch (err) {
      // Une réponse partielle est remplacée par le message d'erreur.
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== assistantId),
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content:
            err instanceof RateLimitedError
              ? "Trop de requêtes pour le moment. Réessayez dans une minute."
              : "Une erreur est survenue. Veuillez réessayer.",
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
        <a className="doc-link" href={DOC_URL} target="_blank" rel="noopener noreferrer">
          Voir le DEU (PDF)
        </a>
      </header>

      <div className="chat-messages">
        {messages.length === 0 && (
          <section className="chat-empty">
            <h1>Interrogez le DEU 2025 de TotalEnergies</h1>
            <p>
              Posez vos questions à l&apos;écrit ou à la voix : les réponses s&apos;appuient sur le{" "}
              <a href={DOC_URL} target="_blank" rel="noopener noreferrer">
                Document d&apos;Enregistrement Universel
              </a>{" "}
              et citent les pages concernées.
            </p>
            <ul className="suggestions" aria-label="Exemples de questions">
              {SUGGESTIONS.map((question) => (
                <li key={question}>
                  <button type="button" onClick={() => void send(question)} disabled={loading}>
                    {question}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-bubble-row ${m.role}`}>
            <div className={`chat-bubble ${m.role}`}>
              {m.role === "assistant" && !m.isError ? <Citations content={m.content} /> : m.content}
            </div>
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
        {voiceStatus === "live" && (
          <button
            type="button"
            className={`send-button sound-button ${soundOn ? "" : "off"}`}
            onClick={toggleSound}
            aria-pressed={!soundOn}
            aria-label={soundOn ? "Couper le son" : "Réactiver le son"}
            title={soundOn ? "Couper le son" : "Réactiver le son"}
          >
            <SpeakerIcon muted={!soundOn} />
          </button>
        )}
        <button
          type="button"
          className={`send-button mic-button ${voiceStatus !== "idle" ? "active" : ""}`}
          onClick={toggleMic}
          disabled={voiceStatus === "connecting"}
          aria-pressed={voiceStatus === "live"}
          aria-label={voiceStatus === "idle" ? "Activer le micro" : "Couper l'écoute"}
          title={voiceStatus === "idle" ? "Activer le micro" : "Couper l'écoute"}
        >
          <MicIcon />
        </button>
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

// Les pages citées par l'assistant deviennent des liens vers la page du PDF.
function Citations({ content }: { content: string }) {
  return (
    <>
      {splitCitations(content).map((s, i) =>
        s.kind === "text" ? (
          s.text
        ) : (
          <a
            key={i}
            className="page-link"
            href={pageUrl(DOC_URL, s.page)}
            target="_blank"
            rel="noopener noreferrer"
            title={`Ouvrir la page ${s.page} du DEU`}
          >
            {s.page}
          </a>
        )
      )}
    </>
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

const iconProps = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function MicIcon() {
  return (
    <svg {...iconProps}>
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  );
}

function SpeakerIcon({ muted }: { muted: boolean }) {
  return (
    <svg {...iconProps}>
      <polygon points="3 9 7 9 12 5 12 19 7 15 3 15" />
      {muted ? (
        <>
          <line x1="16" y1="9" x2="22" y2="15" />
          <line x1="22" y1="9" x2="16" y2="15" />
        </>
      ) : (
        <path d="M16 8.5a5 5 0 0 1 0 7" />
      )}
    </svg>
  );
}
