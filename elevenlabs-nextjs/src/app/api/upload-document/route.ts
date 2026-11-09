import { NextResponse } from "next/server";
import { parseStoryboardBuffer } from "@/lib/document-parser";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return NextResponse.json({ success: false, error: "Tidak ada file yang diunggah" }, { status: 400 });
    }

    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    const segments = await parseStoryboardBuffer(file.name, buffer);

    if (!segments || segments.length === 0) {
      return NextResponse.json(
        {
          success: false,
          error: "Gagal mengekstrak teks naskah. Pastikan dokumen berisi teks/tabel dan tidak terkunci sandi.",
        },
        { status: 400 }
      );
    }

    const baseName = file.name.replace(/\.[^/.]+$/, "").replace(/[^\w-]/g, "_");

    return NextResponse.json({
      success: true,
      fileName: file.name,
      featureName: baseName,
      segments,
      count: segments.length,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Gagal memproses file";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
