import { describe, expect, it } from "vitest";
import { downsample, floatToPcm16, pcm16ToFloat } from "./audio";

describe("downsample", () => {
  it("réduit 48 kHz vers 16 kHz en moyennant par groupes de trois", () => {
    const input = new Float32Array([0, 0.3, 0.6, 1, 1, 1]);
    const out = downsample(input, 48000, 16000);
    expect(out).toHaveLength(2);
    expect(out[0]).toBeCloseTo(0.3);
    expect(out[1]).toBeCloseTo(1);
  });

  it("laisse le signal intact si la fréquence cible est supérieure", () => {
    const input = new Float32Array([0.1, 0.2]);
    expect(downsample(input, 16000, 16000)).toBe(input);
  });
});

describe("PCM 16 bits", () => {
  it("encode en little-endian et borne les valeurs", () => {
    const view = new DataView(floatToPcm16(new Float32Array([0, 1, -1, 2])));
    expect(view.getInt16(0, true)).toBe(0);
    expect(view.getInt16(2, true)).toBe(0x7fff);
    expect(view.getInt16(4, true)).toBe(-0x8000);
    expect(view.getInt16(6, true)).toBe(0x7fff);
  });

  it("fait l'aller-retour float → PCM → float", () => {
    const input = new Float32Array([0, 0.5, -0.5]);
    const out = pcm16ToFloat(floatToPcm16(input));
    input.forEach((v, i) => expect(out[i]).toBeCloseTo(v, 3));
  });

  it("ignore un octet orphelin en fin de trame", () => {
    expect(pcm16ToFloat(new ArrayBuffer(3))).toHaveLength(1);
  });
});
