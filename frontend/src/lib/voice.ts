import {
  downsample,
  floatToPcm16,
  INPUT_SAMPLE_RATE,
  OUTPUT_SAMPLE_RATE,
  pcm16ToFloat,
} from "./audio";

// Protocole du WebSocket /ws/voice (voir backend/app/api/routes/voice.py).
export type VoiceServerMessage =
  | { type: "transcript"; role: "user" | "assistant"; text: string }
  | { type: "turn_complete" }
  | { type: "interrupted" }
  | { type: "error"; message: string };

export type VoiceHandlers = {
  onMessage: (message: VoiceServerMessage) => void;
  // Appelé une seule fois à la fin de la session, avec la raison si c'est une panne.
  onClose: (error?: string) => void;
};

// Next ne peut pas proxifier un WebSocket : le navigateur joint directement le backend.
const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

// Worklet inline : renvoie au thread principal les blocs d'échantillons du micro.
const CAPTURE_WORKLET = `
class Capture extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0][0];
    if (channel) this.port.postMessage(channel.slice());
    return true;
  }
}
registerProcessor("capture", Capture);
`;

export class VoiceSession {
  private gain: GainNode;
  private sources = new Set<AudioBufferSourceNode>();
  private playhead = 0;
  private closed = false;

  private constructor(
    private ws: WebSocket,
    private context: AudioContext,
    private stream: MediaStream,
    private handlers: VoiceHandlers
  ) {
    this.gain = context.createGain();
    this.gain.connect(context.destination);
  }

  // Demande le micro, ouvre le WebSocket et démarre capture + lecture.
  static async start(handlers: VoiceHandlers): Promise<VoiceSession> {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true },
    });
    const context = new AudioContext();
    try {
      const ws = await openSocket(`${WS_URL}/ws/voice`);
      const session = new VoiceSession(ws, context, stream, handlers);
      await session.startCapture();
      ws.onmessage = (e) => session.handleFrame(e.data);
      ws.onclose = () => session.finish();
      ws.onerror = () => session.finish("Connexion vocale interrompue.");
      return session;
    } catch (err) {
      stream.getTracks().forEach((t) => t.stop());
      void context.close();
      throw err;
    }
  }

  private async startCapture() {
    const url = URL.createObjectURL(
      new Blob([CAPTURE_WORKLET], { type: "application/javascript" })
    );
    await this.context.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);
    const source = this.context.createMediaStreamSource(this.stream);
    const node = new AudioWorkletNode(this.context, "capture");
    node.port.onmessage = (e: MessageEvent<Float32Array>) => {
      if (this.ws.readyState !== WebSocket.OPEN) return;
      const pcm = downsample(e.data, this.context.sampleRate, INPUT_SAMPLE_RATE);
      this.ws.send(floatToPcm16(pcm));
    };
    source.connect(node);
  }

  private handleFrame(data: unknown) {
    if (data instanceof ArrayBuffer) {
      this.play(data);
      return;
    }
    if (typeof data !== "string") return;
    const message = JSON.parse(data) as VoiceServerMessage;
    if (message.type === "interrupted") this.clearPlayback();
    this.handlers.onMessage(message);
  }

  private play(data: ArrayBuffer) {
    const samples = pcm16ToFloat(data);
    if (samples.length === 0) return;
    const buffer = this.context.createBuffer(1, samples.length, OUTPUT_SAMPLE_RATE);
    buffer.copyToChannel(new Float32Array(samples), 0);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.gain);
    // Enchaîne les morceaux sans trou ni chevauchement.
    this.playhead = Math.max(this.playhead, this.context.currentTime);
    source.start(this.playhead);
    this.playhead += buffer.duration;
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
  }

  private clearPlayback() {
    this.sources.forEach((s) => s.stop());
    this.sources.clear();
    this.playhead = 0;
  }

  // « Couper le son » : la voix du modèle est muette (la réponse reste transcrite).
  setSoundOn(on: boolean) {
    this.gain.gain.value = on ? 1 : 0;
  }

  stop() {
    this.finish();
  }

  private finish(error?: string) {
    if (this.closed) return;
    this.closed = true;
    this.clearPlayback();
    this.stream.getTracks().forEach((t) => t.stop());
    void this.context.close();
    this.ws.close();
    this.handlers.onClose(error);
  }
}

function openSocket(url: string): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    ws.onopen = () => resolve(ws);
    ws.onerror = () => reject(new Error("Impossible de joindre le serveur vocal."));
  });
}
