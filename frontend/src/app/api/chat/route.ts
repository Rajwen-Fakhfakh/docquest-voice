// Proxy vers POST /chat/stream du backend : garde API_URL côté serveur et relaie le flux tel quel.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  const upstream = await fetch(new URL("/chat/stream", API_URL), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
