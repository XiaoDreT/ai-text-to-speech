import { NextResponse } from "next/server";
import { saveOutputFile } from "@/lib/history-manager";

export async function POST(request: Request) {
  try {
    const formData = await request.formData();
    const file = formData.get("file") as File | null;

    if (!file) {
      return NextResponse.json({ success: false, error: "Tidak ada video yang diunggah" }, { status: 400 });
    }

    const rawName = file.name;
    const ext = rawName.split(".").pop() || "mp4";
    const baseClean = rawName.replace(/\.[^/.]+$/, "").replace(/[^\w-]/g, "_").slice(0, 50);
    const safeFileName = `video_${Date.now()}_${baseClean}.${ext}`;

    const arrayBuffer = await file.arrayBuffer();
    const buffer = Buffer.from(arrayBuffer);

    saveOutputFile(safeFileName, buffer);

    const videoUrl = `/api/files/${safeFileName}`;

    return NextResponse.json({
      success: true,
      fileName: rawName,
      safeFileName,
      videoUrl,
      sizeBytes: buffer.length,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Gagal mengunggah video";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
