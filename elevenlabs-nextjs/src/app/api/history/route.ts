import { NextResponse } from "next/server";
import { getHistory, clearHistory } from "@/lib/history-manager";

export async function GET() {
  const history = getHistory();
  return NextResponse.json({ success: true, history });
}

export async function DELETE() {
  clearHistory();
  return NextResponse.json({ success: true, message: "Riwayat berhasil dibersihkan" });
}
