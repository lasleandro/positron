/**
 * Visible watermark burned into the rendered PDF pixels for grantees.
 *
 * Deterrent, not protection: no visible mark survives every edit or AI inpainting. What raises
 * the cost here:
 * - it is drawn INTO the canvas (deleting a DOM element in devtools does not remove it);
 * - tiles are irregular (seeded jitter in position, angle, size and opacity): no periodic
 *   pattern for a removal model to learn and subtract;
 * - it crosses the content itself, with thin hairlines over glyphs;
 * - it carries a reference that identifies the grant, so a leaked image is traceable in the
 *   owner's "Compartilhamentos" list and history.
 */

export interface Watermark {
  /** Stable per grant so re-renders look the same, different across grants. */
  seed: string;
  lines: string[];
}

/** Short, human-readable reference for a grant id (shown in the mark and in the owner's list). */
export function grantRef(id: string): string {
  return id.replace(/-/g, "").slice(0, 8).toUpperCase();
}

/** Deterministic PRNG (FNV-1a hash -> mulberry32). */
function seeded(seed: string): () => number {
  let hash = 2166136261;
  for (let index = 0; index < seed.length; index++) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  let state = hash >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const INK = ["44, 41, 35", "120, 52, 18"]; // grafite and a warm brown

export function burnWatermark(canvas: HTMLCanvasElement, mark: Watermark, page: number): void {
  const context = canvas.getContext("2d");
  if (!context || !mark.lines.length) return;
  const random = seeded(`${mark.seed}:${page}`);
  const { width, height } = canvas;
  const base = Math.max(11, width / 58);
  const lineGap = base * 1.45;
  const blockHeight = lineGap * mark.lines.length;
  context.save();
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.textBaseline = "middle";

  // Rotate the whole field around the page centre, then walk a jittered grid wide enough to
  // cover the corners after rotation.
  const diagonal = Math.hypot(width, height);
  const stepX = base * 26;
  const stepY = blockHeight * 2.6;
  context.translate(width / 2, height / 2);
  context.rotate((-24 + (random() - 0.5) * 6) * (Math.PI / 180));
  for (let y = -diagonal / 2; y < diagonal / 2; y += stepY) {
    const rowOffset = random() * stepX;
    for (let x = -diagonal / 2 - rowOffset; x < diagonal / 2; x += stepX) {
      const scale = 0.85 + random() * 0.3;
      const alpha = 0.1 + random() * 0.1;
      context.save();
      context.translate(x + (random() - 0.5) * stepX * 0.35, y + (random() - 0.5) * stepY * 0.35);
      context.rotate((random() - 0.5) * 0.12);
      context.fillStyle = `rgba(${INK[Math.floor(random() * INK.length)]}, ${alpha.toFixed(3)})`;
      mark.lines.forEach((line, index) => {
        context.font = `${index === 0 ? 700 : 600} ${(base * scale * (index === 0 ? 1.08 : 0.92)).toFixed(1)}px ui-monospace, monospace`;
        context.fillText(line, 0, index * lineGap * scale);
      });
      context.restore();
    }
  }
  context.restore();

  // A few faint hairlines across the page, crossing glyph strokes.
  context.save();
  context.lineWidth = Math.max(1, width / 900);
  for (let index = 0; index < 5; index++) {
    context.strokeStyle = `rgba(${INK[0]}, ${(0.06 + random() * 0.06).toFixed(3)})`;
    context.beginPath();
    context.moveTo(0, random() * height);
    context.bezierCurveTo(width * 0.33, random() * height, width * 0.66, random() * height, width, random() * height);
    context.stroke();
  }
  context.restore();
}
