import { NextRequest, NextResponse } from "next/server";

/**
 * Server-side proxy for authenticated write operations to the StressProof backend.
 *
 * This Next.js Route Handler reads API_WRITE_TOKEN strictly on the server,
 * ensuring the secret token is never bundled into client JavaScript or exposed to visitors.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const backendUrl =
      process.env.BACKEND_INTERNAL_URL ||
      process.env.NEXT_PUBLIC_BACKEND_URL ||
      "http://127.0.0.1:8000";

    const apiWriteToken = process.env.API_WRITE_TOKEN;

    if (!apiWriteToken) {
      console.error("[api/stress/run] Missing API_WRITE_TOKEN on the server.");
      return NextResponse.json(
        {
          detail:
            "Server misconfiguration: API_WRITE_TOKEN is not configured on the server environment.",
        },
        { status: 500 }
      );
    }

    const backendRes = await fetch(`${backendUrl}/stress/run`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiWriteToken}`,
      },
      body: JSON.stringify(body),
    });

    const data = await backendRes.json();

    if (!backendRes.ok) {
      return NextResponse.json(
        { detail: data.detail || "Stress test execution failed on backend" },
        { status: backendRes.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: any) {
    console.error("[api/stress/run] Error proxying write request to backend:", err);
    return NextResponse.json(
      { detail: err.message || "Failed to communicate with stress backend" },
      { status: 500 }
    );
  }
}
