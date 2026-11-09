import { NextResponse } from "next/server";
import { generateSpeechRaw } from "@/lib/elevenlabs";
import { saveHistoryItem, saveOutputFile } from "@/lib/history-manager";
import { DialogueLine } from "@/types";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const {
      segments,
      modelId,
      stability,
      similarityBoost,
      style,
      speed,
      apiKey,
    }: {
      segments: DialogueLine[];
      modelId?: string;
      stability?: number;
      similarityBoost?: number;
      style?: number;
      speed?: number;
      apiKey?: string;
    } = body;

    const validSegments = (segments || []).filter((s) => s.text && s.text.trim());
    if (!validSegments.length) {
      return NextResponse.json({ success: false, error: "Tidak ada baris dialog yang valid" }, { status: 400 });
    }

    const start = Date.now();
    const audioChunks: Buffer[] = [];
    const segmentResults: Array<{ index: number; voice_name: string; text: string }> = [];

    for (let i = 0; i < validSegments.length; i++) {
      const seg = validSegments[i];
      const prevText = i > 0 ? validSegments[i - 1].text.trim() : undefined;
      const nextText = i + 1 < validSegments.length ? validSegments[i + 1].text.trim() : undefined;

      const res = await generateSpeechRaw({
        text: seg.text.trim(),
        voiceId: seg.voice_id,
        modelId: modelId || "eleven_multilingual_v2",
        outputFormat: "mp3_44100_128",
        stability: stability ?? 0.55,
        similarityBoost: similarityBoost ?? 0.8,
        style: style ?? 0,
        speed: speed ?? 1,
        previousText: prevText,
        nextText: nextText,
        apiKey,
      });

      audioChunks.push(res.audioBuffer);
      segmentResults.push({
        index: i + 1,
        voice_name: seg.voice_name || `Speaker ${i + 1}`,
        text: seg.text.trim(),
      });
    }

    const combinedBuffer = Buffer.concat(audioChunks);
    const elapsedSec = Number(((Date.now() - start) / 1000).toFixed(2));
    const timestampStr = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);

    const baseName = `dialog_${timestampStr}`;
    const audioFileName = `${baseName}.mp3`;
    saveOutputFile(audioFileName, combinedBuffer);

    const audioUrl = `/api/files/${audioFileName}`;
    const fullScript = segmentResults.map((s) => `[${s.voice_name}]: ${s.text}`).join("\n");

    saveHistoryItem({
      id: baseName,
      timestamp: new Date().toLocaleString("id-ID"),
      mode: "dialog",
      voice_id: "multi-speaker",
      voice_name: "Multi-Speaker Dialog",
      model_id: modelId || "eleven_multilingual_v2",
      text: fullScript,
      settings: {
        stability: stability ?? 0.55,
        similarity_boost: similarityBoost ?? 0.8,
        style: style ?? 0,
        speed: speed ?? 1,
        use_speaker_boost: true,
      },
      output_format: "mp3_44100_128",
      audio_url: audioUrl,
      size_bytes: combinedBuffer.length,
      elapsed_sec: elapsedSec,
      segments: segmentResults,
    });

    return NextResponse.json({
      success: true,
      audioUrl,
      elapsedSec,
      sizeBytes: combinedBuffer.length,
      segments: segmentResults,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Gagal generate dialog";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
