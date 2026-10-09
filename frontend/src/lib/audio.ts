// Conversions audio pures (testables hors navigateur) pour le mode vocal.
// Le backend attend du PCM 16 bits mono à 16 kHz et renvoie du PCM 16 bits mono à 24 kHz.

export const INPUT_SAMPLE_RATE = 16000;
export const OUTPUT_SAMPLE_RATE = 24000;

// Rééchantillonne par moyenne des échantillons voisins (suffisant pour de la voix).
export function downsample(
  input: Float32Array,
  fromRate: number,
  toRate: number
): Float32Array {
  if (toRate >= fromRate) return input;
  const ratio = fromRate / toRate;
  const length = Math.floor(input.length / ratio);
  const output = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0;
    for (let j = start; j < end; j++) sum += input[j];
    output[i] = sum / Math.max(end - start, 1);
  }
  return output;
}

export function floatToPcm16(input: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

export function pcm16ToFloat(buffer: ArrayBuffer): Float32Array {
  const view = new DataView(buffer, 0, buffer.byteLength - (buffer.byteLength % 2));
  const output = new Float32Array(view.byteLength / 2);
  for (let i = 0; i < output.length; i++) {
    output[i] = view.getInt16(i * 2, true) / 0x8000;
  }
  return output;
}
