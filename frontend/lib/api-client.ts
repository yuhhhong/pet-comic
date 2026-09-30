export class ApiError extends Error {
  readonly code: string;
  readonly retryable: boolean;
  readonly details: Record<string, unknown>;
  readonly status: number;

  constructor(message: string, code: string, retryable: boolean, details: Record<string, unknown>, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.retryable = retryable;
    this.details = details;
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (typeof init?.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new ApiError("连不上后端服务，请确认 FastAPI 已启动。", "NETWORK_ERROR", true, {}, 0);
    }
    throw error;
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const payload = text ? parseJson(text) : null;
  if (!response.ok) {
    const record = isRecord(payload) ? payload : {};
    const details = isRecord(record.details) ? record.details : {};
    throw new ApiError(
      typeof record.message === "string" ? record.message : `请求失败（${response.status}）`,
      typeof record.code === "string" ? record.code : "INTERNAL_ERROR",
      Boolean(record.retryable),
      details,
      response.status,
    );
  }
  return payload as T;
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message || "请求没有完成。";
  return "请求没有完成，请稍后再试。";
}
