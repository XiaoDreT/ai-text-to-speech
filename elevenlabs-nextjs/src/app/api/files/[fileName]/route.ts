import { NextRequest, NextResponse } from "next/server";
import { getOutputFilePath } from "@/lib/history-manager";
import fs from "fs";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ fileName: string }> }
) {
  const { fileName } = await context.params;
  const filePath = getOutputFilePath(fileName);

  if (!filePath || !fs.existsSync(filePath)) {
    return new NextResponse("File tidak ditemukan", { status: 404 });
  }

  const stat = fs.statSync(filePath);
  const fileSize = stat.size;
  const ext = fileName.split(".").pop()?.toLowerCase() || "";

  let contentType = "application/octet-stream";
  if (ext === "mp3") contentType = "audio/mpeg";
  else if (ext === "wav") contentType = "audio/wav";
  else if (ext === "srt") contentType = "text/plain; charset=utf-8";
  else if (ext === "mp4") contentType = "video/mp4";
  else if (ext === "webm") contentType = "video/webm";

  const range = request.headers.get("range");

  if (range) {
    const parts = range.replace(/bytes=/, "").split("-");
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
    const chunksize = end - start + 1;

    const stream = fs.createReadStream(filePath, { start, end });
    // @ts-expect-error Next.js supports NodeJS ReadStream as body
    return new NextResponse(stream, {
      status: 206,
      headers: {
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Accept-Ranges": "bytes",
        "Content-Length": String(chunksize),
        "Content-Type": contentType,
      },
    });
  }

  const stream = fs.createReadStream(filePath);
  // @ts-expect-error Next.js supports NodeJS ReadStream as body
  return new NextResponse(stream, {
    status: 200,
    headers: {
      "Content-Length": String(fileSize),
      "Content-Type": contentType,
      "Accept-Ranges": "bytes",
    },
  });
}
