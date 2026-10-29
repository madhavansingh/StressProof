import { NextRequest, NextResponse } from "next/server";

// Simple in-memory rate limiter: max 30 requests per 60 seconds per IP
const rateLimitMap = new Map<string, { count: number; resetAt: number }>();

function checkRateLimit(ip: string): boolean {
  const now = Date.now();
  const record = rateLimitMap.get(ip);
  if (!record || now > record.resetAt) {
    rateLimitMap.set(ip, { count: 1, resetAt: now + 60_000 });
    return true;
  }
  if (record.count >= 30) {
    return false;
  }
  record.count += 1;
  return true;
}

/**
 * Server-side proxy for authenticated write operations to the StressProof backend.
 * Validates body shape per Task F15 before forwarding to backend.
 */
export async function POST(req: NextRequest) {
  try {
    const ip = req.headers.get("x-forwarded-for") || req.ip || "127.0.0.1";
    if (!checkRateLimit(ip)) {
      return NextResponse.json(
        { detail: "Too many requests. Please wait a minute before running another stress simulation." },
        { status: 429 }
      );
    }

    let body: any;
    try {
      body = await req.json();
    } catch {
      return NextResponse.json(
        { detail: "Malformed JSON payload in request body" },
        { status: 422 }
      );
    }

    // Strict validation per Task F15
    if (
      !body ||
      typeof body !== "object" ||
      typeof body.datasetId !== "string" ||
      !body.datasetId.trim() ||
      !body.scenario ||
      typeof body.scenario !== "object" ||
      body.scenario.asset !== "WETH" ||
      typeof body.scenario.shockBps !== "number" ||
      body.scenario.shockBps > 0 ||
      body.scenario.shockBps < -10000
    ) {
      return NextResponse.json(
        {
          detail:
            "Invalid body shape: datasetId (string) and scenario with asset='WETH' and shockBps (negative number) are required.",
        },
        { status: 422 }
      );
    }

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
