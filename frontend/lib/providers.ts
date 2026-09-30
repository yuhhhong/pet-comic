import { apiFetch } from "@/lib/api-client";

export type Provider = {
  id: string;
  display_name: string;
  base_url: string;
  enabled: boolean;
  has_api_key: boolean;
  api_key_hint: string;
  last_model_refresh_at: string | null;
  last_model_refresh_error: string | null;
  created_at: string;
  updated_at: string;
};

export type RemoteModelList = {
  provider_id: string;
  models: string[];
  refreshed_at: string | null;
  error: string | null;
};

export type ModelBinding = {
  provider_id: string;
  provider_name: string;
  model_id: string;
  provider_enabled: boolean;
};

export type ModelBindings = {
  vision: ModelBinding | null;
  script: ModelBinding | null;
  image: ModelBinding | null;
};

export type ModelRole = keyof ModelBindings;

export const MODEL_ROLES: { role: ModelRole; label: string; description: string }[] = [
  { role: "vision", label: "视觉理解", description: "提取外观，理解任务图片" },
  { role: "script", label: "剧本", description: "写九格漫画剧本" },
  { role: "image", label: "图像生成", description: "画角色卡和漫画格" },
];

export function listProviders(): Promise<Provider[]> {
  return apiFetch<Provider[]>("/providers");
}

export function createProvider(body: {
  display_name: string;
  base_url: string;
  api_key: string;
  enabled: boolean;
}): Promise<Provider> {
  return apiFetch<Provider>("/providers", { method: "POST", body: JSON.stringify(body) });
}

export function updateProvider(
  providerId: string,
  body: { display_name?: string; base_url?: string; api_key?: string; enabled?: boolean },
): Promise<Provider> {
  return apiFetch<Provider>(`/providers/${providerId}`, { method: "PATCH", body: JSON.stringify(body) });
}

export function refreshProviderModels(providerId: string): Promise<Provider> {
  return apiFetch<Provider>(`/providers/${providerId}/refresh-models`, { method: "POST" });
}

export function listProviderModels(providerId: string): Promise<RemoteModelList> {
  return apiFetch<RemoteModelList>(`/providers/${providerId}/models`);
}

export function getModelBindings(): Promise<ModelBindings> {
  return apiFetch<ModelBindings>("/model-bindings");
}

export function saveModelBindings(body: {
  vision: { provider_id: string; model_id: string } | null;
  script: { provider_id: string; model_id: string } | null;
  image: { provider_id: string; model_id: string } | null;
}): Promise<ModelBindings> {
  return apiFetch<ModelBindings>("/model-bindings", { method: "PUT", body: JSON.stringify(body) });
}
