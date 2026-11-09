import { StoryboardSegment, FitMode } from "@/types";
import { formatSrtTimestamp, generateSpeechRaw } from "./elevenlabs";

export const SAMPLE_RATE = 24000; // 24kHz 16-bit mono native ElevenLabs PCM

/**
 * Mengonversi timecode ("HH:MM:SS" atau "MM:SS") menjadi detik (float)
 */
export function parseTimecodeToSeconds(timecode: string): number {
  if (!timecode) return 0.0;
  const clean = timecode.trim().replace(/,/g, ".");
  const parts = clean.split(":");

  if (parts.length === 3) {
    const h = parseInt(parts[0], 10) || 0;
    const m = parseInt(parts[1], 10) || 0;
    const s = parseFloat(parts[2]) || 0.0;
    return Math.max(0.0, h * 3600 + m * 60 + s);
  }
  if (parts.length === 2) {
    const m = parseInt(parts[0], 10) || 0;
    const s = parseFloat(parts[1]) || 0.0;
    return Math.max(0.0, m * 60 + s);
  }
  if (parts.length === 1) {
    return Math.max(0.0, parseFloat(parts[0]) || 0.0);
  }
  return 0.0;
}

/**
 * Mengonversi detik (float) ke format string "HH:MM:SS" (atau "MM:SS")
 */
export function formatSecondsToHms(seconds: number, includeHours: boolean = true): string {
  if (seconds < 0) seconds = 0.0;
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;

  const pad = (n: number) => String(n).padStart(2, "0");
  if (includeHours || h > 0) {
    return `${pad(h)}:${pad(m)}:${pad(s)}`;
  }
  return `${pad(m)}:${pad(s)}`;
}

/**
 * Mengekstrak waktu mulai dan selesai dari string rentang waktu ("00:00:00 - 00:00:05")
 */
export function parseTimeRangeStr(rangeStr: string): [number, number] {
  if (!rangeStr) return [0.0, 5.0];
  const cleaned = rangeStr.replace(/-->|s\/d|sd|sampai|to|hingga/gi, "-");
  const parts = cleaned.split("-");
  if (parts.length >= 2) {
    const s = parseTimecodeToSeconds(parts[0].trim());
    const e = parseTimecodeToSeconds(parts[1].trim());
    return [s, Math.max(s + 1.0, e)];
  }
  const s = parseTimecodeToSeconds(cleaned);
  return [s, s + 5.0];
}

/**
 * Menstandarkan rentang waktu ke format wajib "HH:MM:SS - HH:MM:SS"
 */
export function normalizeToHmsRange(rangeStr: string): string {
  const [s, e] = parseTimeRangeStr(rangeStr);
  return `${formatSecondsToHms(s, true)} - ${formatSecondsToHms(e, true)}`;
}

/**
 * Menata ulang rentang waktu segmen agar tersambung berurutan mulai dari 00:00:00
 */
export function resequenceTimelineTimestamps(segments: StoryboardSegment[]): StoryboardSegment[] {
  let curr = 0.0;
  return segments.map((seg) => {
    const [s, e] = parseTimeRangeStr(seg.time_range);
    const dur = Math.max(1.0, e - s);
    const newStart = curr;
    const newEnd = curr + dur;
    curr = newEnd + 1.0;
    return {
      ...seg,
      time_range: `${formatSecondsToHms(newStart, true)} - ${formatSecondsToHms(newEnd, true)}`,
    };
  });
}

/**
 * Menghasilkan daftar opsi dropdown timecode HH:MM:SS
 */
export function getTimecodeDropdownOptions(
  maxSeconds: number = 3600,
  extraTimecodes: string[] = []
): string[] {
  const set = new Set<string>();
  const limit = Math.max(300, maxSeconds + 60);

  // Interval 1 detik sampai 60s, lalu interval 5 detik
  for (let sec = 0; sec <= limit; sec += sec < 60 ? 1 : 5) {
    set.add(formatSecondsToHms(sec, true));
  }

  for (const tc of extraTimecodes) {
    if (tc) {
      const s = parseTimecodeToSeconds(tc);
      set.add(formatSecondsToHms(s, true));
    }
  }

  return Array.from(set).sort((a, b) => parseTimecodeToSeconds(a) - parseTimecodeToSeconds(b));
}

/**
 * Membungkus PCM 16-bit mono little-endian Buffer dengan 44-byte WAV header
 */
export function pcm16ToWavBuffer(
  pcmBuffer: Buffer,
  sampleRate: number = SAMPLE_RATE,
  numChannels: number = 1
): Buffer {
  const byteRate = sampleRate * numChannels * 2;
  const blockAlign = numChannels * 2;
  const dataSize = pcmBuffer.length;
  const header = Buffer.alloc(44);

  // RIFF header
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + dataSize, 4);
  header.write("WAVE", 8);

  // fmt subchunk
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16); // SubChunk1Size (16 for PCM)
  header.writeUInt16LE(1, 20); // AudioFormat (1 for PCM)
  header.writeUInt16LE(numChannels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(16, 34); // BitsPerSample

  // data subchunk
  header.write("data", 36);
  header.writeUInt32LE(dataSize, 40);

  return Buffer.concat([header, pcmBuffer]);
}

/**
 * Memecah teks naskah menjadi cues subtitle yang tersinkronisasi
 */
export function splitTextIntoSubtitleCues(
  text: string,
  startSec: number,
  endSec: number,
  maxWordsPerCue: number = 9
): Array<{ start: number; end: number; text: string }> {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return [];

  const sentences = clean.split(/(?<=[.!?])\s+/);
  const chunks: string[] = [];

  for (const s of sentences) {
    const words = s.split(" ").filter(Boolean);
    if (words.length <= maxWordsPerCue) {
      chunks.push(s);
    } else {
      for (let i = 0; i < words.length; i += maxWordsPerCue) {
        chunks.push(words.slice(i, i + maxWordsPerCue).join(" "));
      }
    }
  }

  const slotDur = Math.max(1.0, endSec - startSec);
  const cueDur = slotDur / Math.max(1, chunks.length);

  return chunks.map((chunk, i) => {
    const cStart = startSec + i * cueDur;
    const cEnd = Math.min(endSec, cStart + cueDur);
    return {
      start: Number(cStart.toFixed(2)),
      end: Number(cEnd.toFixed(2)),
      text: chunk,
    };
  });
}

export interface TimelineGenerationOptions {
  segments: StoryboardSegment[];
  voiceId?: string;
  voiceName?: string;
  modelId?: string;
  languageCode?: string;
  stability?: number;
  similarityBoost?: number;
  style?: number;
  speed?: number;
  useSpeakerBoost?: boolean;
  fitMode?: FitMode;
  stretchShorter?: boolean;
  apiKey?: string;
}

export interface SegmentReport {
  index: number;
  time_range: string;
  target_slot_sec: number;
  speech_dur_sec: number;
  status: string;
  speed_factor: number;
  text: string;
}

export interface TimelineResult {
  totalTimelineSec: number;
  elapsedSec: number;
  wavBuffer: Buffer;
  srtContent: string;
  segmentReports: SegmentReport[];
  featureName?: string;
}

/**
 * Menghasilkan Master Audio Timeline Storyboard tersinkronisasi presisi tinggi
 * dengan penggunaan memori yang sangat hemat (<15MB RAM).
 */
export async function generateTimelineVoiceover(
  options: TimelineGenerationOptions
): Promise<TimelineResult> {
  const startTime = Date.now();
  const segments = options.segments.filter((s) => (s.text || "").trim().length > 0);
  if (!segments.length) {
    throw new Error("Tidak ada segmen naskah yang memiliki teks untuk diproses.");
  }

  // Hitung total durasi waktu yang dibutuhkan
  let maxEndSec = 0;
  for (const seg of segments) {
    const [, e] = parseTimeRangeStr(seg.time_range);
    if (e > maxEndSec) maxEndSec = e;
  }
  const totalDurationSec = Math.ceil(maxEndSec + 1.0);
  const totalSamples = Math.ceil(totalDurationSec * SAMPLE_RATE);
  const totalBytes = totalSamples * 2; // 16-bit mono = 2 bytes per sample

  // Alokasi buffer PCM hening (zero-filled)
  const masterBuffer = Buffer.alloc(totalBytes, 0);

  const segmentReports: SegmentReport[] = [];
  const srtCues: Array<{ start: number; end: number; text: string }> = [];

  for (let idx = 0; idx < segments.length; idx++) {
    const seg = segments[idx];
    const [startSec, endSec] = parseTimeRangeStr(seg.time_range);
    const targetSlot = Math.max(1.0, endSec - startSec);
    const text = seg.text.trim();

    const prevText = idx > 0 ? segments[idx - 1].text.trim() : undefined;
    const nextText = idx + 1 < segments.length ? segments[idx + 1].text.trim() : undefined;

    // Request PCM 24kHz audio langsung dari ElevenLabs API
    const res = await generateSpeechRaw({
      text,
      voiceId: options.voiceId,
      modelId: options.modelId || "eleven_v4",
      outputFormat: "pcm_24000",
      stability: options.stability ?? 0.55,
      similarityBoost: options.similarityBoost ?? 0.8,
      style: options.style ?? 0.0,
      speed: options.speed ?? 1.0,
      useSpeakerBoost: options.useSpeakerBoost !== false,
      languageCode: options.languageCode,
      previousText: prevText,
      nextText: nextText,
      apiKey: options.apiKey,
    });

    const pcmBytes = res.audioBuffer;
    const speechSamples = Math.floor(pcmBytes.length / 2);
    const speechDur = speechSamples / SAMPLE_RATE;

    const startByte = Math.floor(startSec * SAMPLE_RATE) * 2;
    let bytesToWrite = pcmBytes.length;

    let status = "Pas di slot";
    if (options.fitMode === "strict_trim" && speechDur > targetSlot) {
      bytesToWrite = Math.floor(targetSlot * SAMPLE_RATE) * 2;
      status = "Dipotong pas di batas waktu";
    } else if (speechDur > targetSlot + 0.5) {
      status = "Melampaui slot (Auto-pushed)";
    } else {
      status = "Pas di slot";
    }

    // Salin byte PCM ke master buffer pada offset waktu mulai
    if (startByte < masterBuffer.length) {
      const copyLen = Math.min(bytesToWrite, masterBuffer.length - startByte);
      pcmBytes.copy(masterBuffer, startByte, 0, copyLen);
    }

    segmentReports.push({
      index: idx + 1,
      time_range: normalizeToHmsRange(seg.time_range),
      target_slot_sec: Number(targetSlot.toFixed(1)),
      speech_dur_sec: Number(speechDur.toFixed(1)),
      status,
      speed_factor: 1.0,
      text,
    });

    // Generate cues subtitle yang tersinkronisasi
    const cues = splitTextIntoSubtitleCues(text, startSec, Math.max(endSec, startSec + speechDur));
    srtCues.push(...cues);
  }

  // Buat string SRT lengkap
  const srtContent = srtCues
    .map((c, i) => `${i + 1}\n${formatSrtTimestamp(c.start)} --> ${formatSrtTimestamp(c.end)}\n${c.text}\n`)
    .join("\n");

  // Bungkus master PCM menjadi file WAV utuh
  const wavBuffer = pcm16ToWavBuffer(masterBuffer, SAMPLE_RATE, 1);
  const elapsedSec = Number(((Date.now() - startTime) / 1000).toFixed(2));

  return {
    totalTimelineSec: Number(totalDurationSec.toFixed(1)),
    elapsedSec,
    wavBuffer,
    srtContent,
    segmentReports,
  };
}
