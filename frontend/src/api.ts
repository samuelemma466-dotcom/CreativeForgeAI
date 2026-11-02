import type {
  Brand,
  ChatRequest,
  ChatResponse,
  Dashboard,
  FreeModel,
  MediaAsset,
  Project,
  ProviderChain,
  ProviderStatus,
  Settings,
  SettingsUpdate,
  SystemStatus,
} from "./types";

type ApiErrorBody = {
  error?: { code?: string; message?: string };
  detail?: string | { msg?: string }[];
};

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init.body instanceof File ? {} : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error(`The local API returned an unexpected response (${response.status}).`);
  }
  const body = (await response.json()) as T & ApiErrorBody;
  if (!response.ok) {
    const detail = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg;
    throw new Error(body.error?.message ?? detail ?? `The local API returned ${response.status}.`);
  }
  return body;
}

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  dashboard: () => request<Dashboard>("/api/dashboard"),
  projects: () => request<{ projects: Project[] }>("/api/projects"),
  brands: () => request<{ brands: Brand[] }>("/api/brands"),
  media: () => request<{ media: MediaAsset[] }>("/api/media"),
  settings: () => request<Settings>("/api/settings"),
  system: () => request<SystemStatus>("/api/system/status"),
  providers: () => request<{ providers: ProviderStatus[]; chain: string[]; selected: string; auto_fallback: boolean; free_only: true }>("/api/providers"),
  providerChain: () => request<ProviderChain>("/api/providers/chain"),
  testOllama: (settings: Pick<Settings, "ollama_url" | "ollama_model">) =>
    request<SystemStatus["ollama"] & { selected_model?: string; selected_model_available?: boolean | null }>(
      "/api/system/ollama/test",
      {
        method: "POST",
        body: JSON.stringify({ base_url: settings.ollama_url, model: settings.ollama_model }),
      },
    ),
  openrouterModels: () => request<{ models: FreeModel[]; free_only: true }>("/api/providers/openrouter/models"),
  testOpenRouter: () => request<ProviderStatus>("/api/providers/openrouter/test", { method: "POST", body: "{}" }),
  chat: (payload: ChatRequest) =>
    request<ChatResponse>("/api/ai/chat", { method: "POST", body: JSON.stringify(payload) }),
  createProject: (payload: { name: string; brand_id: string | null; description: string }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(payload) }),
  updateProject: (
    id: string,
    payload: Partial<Pick<Project, "name" | "brand_id" | "description" | "status">>,
  ) => request<Project>(`/api/projects/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteProject: (id: string) => request<{ deleted: boolean }>(`/api/projects/${id}`, { method: "DELETE" }),
  createBrand: (payload: Partial<Brand> & Pick<Brand, "name">) =>
    request<Brand>("/api/brands", { method: "POST", body: JSON.stringify(payload) }),
  updateBrand: (id: string, payload: Partial<Brand>) =>
    request<Brand>(`/api/brands/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteBrand: (id: string) => request<{ deleted: boolean }>(`/api/brands/${id}`, { method: "DELETE" }),
  saveSettings: (payload: SettingsUpdate) =>
    request<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(payload) }),
  upload: (file: File) =>
    request<MediaAsset>("/api/media", {
      method: "PUT",
      headers: {
        "Content-Type": file.type || "application/octet-stream",
        "X-File-Name": encodeURIComponent(file.name),
      },
      body: file,
    }),
};

export function mediaUrl(id: string): string {
  return `/api/media/${id}/content`;
}
