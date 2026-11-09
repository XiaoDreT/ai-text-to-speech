import { NextResponse } from "next/server";
import { generateSpeechRaw } from "@/lib/elevenlabs";
import { saveHistoryItem, saveOutputFile } from "@/lib/history-manager";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const {
      text,
      voiceId,
      voiceName,
      modelId,
      stability,
      similarityBoost,
      style,
      speed,
      useSpeakerBoost,
      outputFormat,
      languageCode,
      withTimestamps,
      apiKey,
    } = body;

    if (!text || !text.trim()) {
      return NextResponse.json({ success: false, error: "Teks tidak boleh kosong" }, { status: 400 });
    }

    const start = Date.now();
    const res = await generateSpeechRaw({
      text: text.trim(),
      voiceId,
      modelId,
      stability,
      similarityBoost,
      style,
      speed,
      useSpeakerBoost,
      outputFormat: outputFormat || "mp3_44100_128",
      languageCode,
      withTimestamps,
      apiKey,
    });

    const elapsedSec = Number(((Date.now() - start) / 1000).toFixed(2));
    const timestampStr = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);
    const cleanVoiceName = (voiceName || "Zen").replace(/[^\w-]/g, "_");

    const baseName = `tts_${timestampStr}_${cleanVoiceName}`;
    const audioFileName = `${baseName}.${res.extension}`;
    saveOutputFile(audioFileName, res.audioBuffer);

    let srtFileName: string | undefined;
    if (res.srtContent) {
      srtFileName = `${baseName}.srt`;
      saveOutputFile(srtFileName, res.srtContent);
    }

    const audioUrl = `/api/files/${audioFileName}`;
    const srtUrl = srtFileName ? `/api/files/${srtFileName}` : undefined;

    saveHistoryItem({
      id: baseName,
      timestamp: new Date().toLocaleString("id-ID"),
      mode: "single_tts",
      voice_id: voiceId || "3OAL9h0y2edOwGJbMU4X",
      voice_name: voiceName || "Zen",
      model_id: modelId || "eleven_multilingual_v2",
      text: text.trim(),
      settings: {
        stability: stability ?? 0.55,
        similarity_boost: similarityBoost ?? 0.8,
        style: style ?? 0,
        speed: speed ?? 1,
        use_speaker_boost: useSpeakerBoost !== false,
      },
      output_format: outputFormat || "mp3_44100_128",
      audio_url: audioUrl,
      srt_url: srtUrl,
      size_bytes: res.audioBuffer.length,
      elapsed_sec: elapsedSec,
    });

    return NextResponse.json({
      success: true,
      audioUrl,
      srtUrl,
      srtContent: res.srtContent,
      elapsedSec,
      sizeBytes: res.audioBuffer.length,
      extension: res.extension,
      mimeType: res.mimeType,
    });
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : "Gagal generate TTS";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
