export type LogFn = (message: string, data?: Record<string, unknown>) => void;

export function log(message: string, data?: Record<string, unknown>): void {
  console.log("[reader.tts]", message, data ?? {});
}
