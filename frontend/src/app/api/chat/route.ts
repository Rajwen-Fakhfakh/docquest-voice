// Proxy vers POST /chat/stream du backend : garde API_URL côté serveur et relaie le flux tel quel.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  // Le backend limite le débit par visiteur : sans ce relais, il ne verrait que l'IP du proxy.
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const forwardedFor = req.headers.get("x-forwarded-for");
  if (forwardedFor) headers["X-Forwarded-For"] = forwardedFor;

  const upstream = await fetch(new URL("/chat/stream", API_URL), {
    method: "POST",
    headers,
    body: await req.text(),
    cache: "no-store",
  });

  if (!upstream.ok || !upstream.body) {
    return new Response(null, { status: upstream.status || 502 });
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}
