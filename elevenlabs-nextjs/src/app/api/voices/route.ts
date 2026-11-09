import { NextResponse } from "next/server";
import { fetchVoices } from "@/lib/elevenlabs";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const apiKey = searchParams.get("api_key") || undefined;
    const voices = await fetchVoices(apiKey);
    return NextResponse.json({ success: true, voices });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Terjadi kesalahan";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
