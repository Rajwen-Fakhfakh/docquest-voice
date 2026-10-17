// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { streamLlm } = vi.hoisted(() => ({ streamLlm: vi.fn() }));
vi.mock("@/lib/llm", async () => ({
  ...(await vi.importActual<typeof import("@/lib/llm")>("@/lib/llm")),
  streamLlm,
}));

const { voiceSessionStart, voiceSessionStop, voiceSessionSetSoundOn } = vi.hoisted(() => ({
  voiceSessionStart: vi.fn(),
  voiceSessionStop: vi.fn(),
  voiceSessionSetSoundOn: vi.fn(),
}));
vi.mock("@/lib/voice", () => ({
  VoiceSession: { start: voiceSessionStart },
}));

import { RateLimitedError } from "@/lib/llm";
import ChatShell from "./ChatShell";

beforeEach(() => {
  vi.stubGlobal("crypto", { randomUUID: () => Math.random().toString(36).slice(2) });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("ChatShell", () => {
  it("affiche l'invite initiale quand il n'y a pas de message", () => {
    render(<ChatShell />);
    expect(screen.getByText(/Posez une question pour démarrer/i)).toBeInTheDocument();
  });

  it("désactive le bouton d'envoi quand le champ est vide", () => {
    render(<ChatShell />);
    expect(screen.getByLabelText("Envoyer")).toBeDisabled();
  });

  it("envoie un message et affiche la réponse en streaming", async () => {
    const user = userEvent.setup();
    streamLlm.mockImplementation(async (_history: unknown, onChunk: (c: string) => void) => {
      onChunk("Bonjour");
      onChunk(" !");
      return "Bonjour !";
    });

    render(<ChatShell />);
    await user.type(screen.getByLabelText("Message"), "Salut");
    await user.click(screen.getByLabelText("Envoyer"));

    expect(await screen.findByText("Salut")).toBeInTheDocument();
    expect(await screen.findByText("Bonjour !")).toBeInTheDocument();
    expect(streamLlm).toHaveBeenCalledTimes(1);
  });

  it("désactive le bouton d'envoi pendant que la réponse arrive", async () => {
    const user = userEvent.setup();
    let resolveStream!: (value: string) => void;
    streamLlm.mockImplementation(
      () =>
        new Promise<string>((resolve) => {
          resolveStream = resolve;
        })
    );

    render(<ChatShell />);
    await user.type(screen.getByLabelText("Message"), "Salut");
    await user.click(screen.getByLabelText("Envoyer"));

    expect(screen.getByLabelText("Envoyer")).toBeDisabled();
    resolveStream("ok");
    await screen.findByText("Salut");
  });

  it("affiche un message d'erreur si l'envoi échoue", async () => {
    const user = userEvent.setup();
    streamLlm.mockRejectedValue(new Error("boom"));

    render(<ChatShell />);
    await user.type(screen.getByLabelText("Message"), "Salut");
    await user.click(screen.getByLabelText("Envoyer"));

    expect(
      await screen.findByText("Une erreur est survenue. Veuillez réessayer.")
    ).toBeInTheDocument();
  });

  it("affiche un message dédié quand le backend limite le débit", async () => {
    const user = userEvent.setup();
    streamLlm.mockRejectedValue(new RateLimitedError());

    render(<ChatShell />);
    await user.type(screen.getByLabelText("Message"), "Salut");
    await user.click(screen.getByLabelText("Envoyer"));

    expect(await screen.findByText(/Trop de requêtes/)).toBeInTheDocument();
  });

  it("le clic sur le micro démarre une session vocale", async () => {
    const user = userEvent.setup();
    voiceSessionStart.mockResolvedValue({
      stop: voiceSessionStop,
      setSoundOn: voiceSessionSetSoundOn,
    });

    render(<ChatShell />);
    await user.click(screen.getByLabelText("Activer le micro"));

    expect(voiceSessionStart).toHaveBeenCalledTimes(1);
    expect(await screen.findByLabelText("Couper l'écoute")).toBeInTheDocument();
  });
});
