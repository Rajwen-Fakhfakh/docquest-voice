// Contrat de l'API backend POST /chat (voir backend/app/api/schemas.py).

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
};

// Le backend refuse plus de 50 messages par requête.
export const MAX_HISTORY = 50;

export type ChatRequest = { messages: ChatTurn[] };
export type ChatResponse = { answer: string };
