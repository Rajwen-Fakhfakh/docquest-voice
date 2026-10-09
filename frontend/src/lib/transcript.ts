import type { ChatTurn } from "./chat";
import type { VoiceServerMessage } from "./voice";

export type TranscriptEntry = ChatTurn & {
  id: string;
  // Vrai tant que la transcription de ce tour est en cours : les morceaux suivants
  // du même rôle s'y ajoutent au lieu de créer une nouvelle bulle.
  open?: boolean;
};

// Intègre un message du serveur vocal dans la liste des messages du chat.
export function applyVoiceMessage<T extends TranscriptEntry>(
  messages: T[],
  message: VoiceServerMessage,
  makeEntry: (role: T["role"], text: string) => T
): T[] {
  if (message.type === "transcript") {
    const { role, text } = message;
    const current = messages.findLast((m) => m.open && m.role === role);
    if (current) {
      return messages.map((m) =>
        m === current ? { ...m, content: m.content + text } : m
      );
    }
    // Un nouveau tour de parole clôt celui de l'autre interlocuteur.
    const closed = messages.map((m) => (m.open ? { ...m, open: false } : m));
    return [...closed, { ...makeEntry(role, text), open: true }];
  }
  if (message.type === "turn_complete" || message.type === "interrupted") {
    return messages.some((m) => m.open)
      ? messages.map((m) => (m.open ? { ...m, open: false } : m))
      : messages;
  }
  return messages;
}
