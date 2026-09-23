import { ApiError, apiFetch } from "@/lib/api-client";

export type PetStatus = "draft" | "ready" | "disabled";

export type PetError = {
  code: string;
  message: string;
  retryable: boolean;
};

export type PetArtifact = {
  artifact_id: string;
  kind: "id_photo" | "appearance" | "character_card";
  version: number;
  path: string | null;
  status: "succeeded" | "failed";
  error_code: string | null;
  created_at: string;
};

export type PetAppearance = {
  species: string;
  breed: string;
  coat_color: string;
  coat_pattern: string;
  eye_color: string;
  body_size: string;
  distinctive_marks: string[];
  summary: string;
};

export type PetDetail = {
  pet_id: string;
  name: string;
  personality: string;
  species: string | null;
  appearance: PetAppearance | null;
  appearance_summary: string | null;
  status: PetStatus;
  active_character_card_id: string | null;
  id_photos: PetArtifact[];
  character_cards: PetArtifact[];
  error: PetError | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PetSummary = {
  pet_id: string;
  name: string;
  personality: string;
  species: string | null;
  appearance_summary: string | null;
  status: PetStatus;
  thumbnail_path: string | null;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
};

export const STATUS_LABEL: Record<PetStatus, string> = {
  draft: "草稿",
  ready: "可用",
  disabled: "已停用",
};

export function petFileUrl(petId: string, path: string | null): string | null {
  if (!path) return null;
  const encoded = path.split("/").map((part) => encodeURIComponent(part)).join("/");
  return `/api/pets/${petId}/files/${encoded}`;
}

export function listPets(filter: "all" | PetStatus | "trashed"): Promise<PetSummary[]> {
  const query = new URLSearchParams();
  if (filter === "trashed") query.set("trashed", "true");
  else if (filter !== "all") query.set("status", filter);
  const suffix = query.size ? `?${query}` : "";
  return apiFetch<PetSummary[]>(`/pets${suffix}`);
}

export function getPet(petId: string): Promise<PetDetail> {
  return apiFetch<PetDetail>(`/pets/${petId}`);
}

export function createPet(input: { name: string; personality: string; photos: File[] }): Promise<PetDetail> {
  const form = new FormData();
  form.append("payload", JSON.stringify({ name: input.name, personality: input.personality }));
  for (const photo of input.photos) form.append("photos", photo);
  return apiFetch<PetDetail>("/pets", { method: "POST", body: form });
}

export function updatePet(
  petId: string,
  body: { name?: string; personality?: string; enabled?: boolean },
): Promise<PetDetail> {
  return apiFetch<PetDetail>(`/pets/${petId}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function retryPet(petId: string): Promise<PetDetail> {
  return apiFetch<PetDetail>(`/pets/${petId}/retry`, { method: "POST" });
}

export function retryCharacterCard(petId: string): Promise<PetDetail> {
  return apiFetch<PetDetail>(`/pets/${petId}/character-card/retry`, { method: "POST" });
}

export function trashPet(petId: string): Promise<PetDetail> {
  return apiFetch<PetDetail>(`/pets/${petId}/trash`, { method: "POST" });
}

export function deletePet(petId: string): Promise<void> {
  return apiFetch<void>(`/pets/${petId}`, { method: "DELETE" });
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) return error.message || "请求没有完成。";
  return "请求没有完成，请稍后再试。";
}

export function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}
