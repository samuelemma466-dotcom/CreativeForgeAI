export type Brand = {
  id: string;
  name: string;
  industry: string;
  business_description: string;
  products_and_services: string;
  target_audience: string;
  brand_voice: string;
  colors: string[];
  contact: Record<string, string>;
  website: string;
  social_links: Record<string, string>;
  preferred_platforms: string[];
  brand_guidelines: string;
  logo_media_id: string | null;
  created_at: string;
  updated_at: string;
};

export type Project = {
  id: string;
  type?: "general" | "design" | "video";
  name: string;
  brand_id: string | null;
  brand_name: string | null;
  campaign_id?: string | null;
  thumbnail_url?: string | null;
  description: string;
  status: "draft" | "active" | "archived";
  created_at: string;
  updated_at: string;
};

export type MediaAsset = {
  id: string;
  original_name: string;
  content_type: string;
  kind?: "image" | "audio" | "video";
  size_bytes: number;
  width?: number | null;
  height?: number | null;
  duration?: number | null;
  created_at: string;
};

export type ProviderId = "openrouter" | "gemini" | "groq" | "ollama";

export type Settings = {
  ollama_url: string;
  ollama_model: string;
  openrouter_model: string;
  openrouter_configured: boolean;
  gemini_model: string;
  gemini_configured: boolean;
  groq_model: string;
  groq_configured: boolean;
  ai_provider: ProviderId;
  provider_priority: ProviderId[];
  auto_fallback: boolean;
  free_only: true;
  theme: "dark" | "light";
};

export type SettingsUpdate = Partial<Omit<Settings, "free_only">> & {
  free_only?: true;
  openrouter_api_key?: string;
  gemini_api_key?: string;
  groq_api_key?: string;
};

export type FreeModel = {
  id: string;
  name: string;
  context_length: number | null;
  pricing: string;
  free?: boolean;
  requires_key?: boolean;
};

export type ProviderStatus = {
  id: ProviderId;
  name: string;
  kind?: string;
  pricing: string;
  capabilities: string[];
  available: boolean;
  configured: boolean;
  model: string | null;
  models?: string[];
  error: string | null;
  requires_key?: boolean;
  limits?: string;
  billing_note?: string;
  last_verified?: string | null;
  last_error?: string | null;
  last_error_kind?: string | null;
  last_attempt?: string | null;
  failures?: number;
  cooldown_seconds?: number;
};

export type ProviderChain = {
  selected: ProviderId;
  chain: ProviderId[];
  auto_fallback: boolean;
  free_only: true;
  providers: Array<{
    id: ProviderId;
    name: string;
    model: string | null;
    configured: boolean;
    available: boolean;
    cooldown_seconds: number;
    last_verified: string | null;
    error: string | null;
  }>;
  note?: string;
};

export type SystemStatus = {
  status?: string;
  version?: string;
  python_version: string;
  platform: string;
  cpu?: string;
  cpu_count?: number;
  memory?: { total_bytes: number; available_bytes: number; swap_total_bytes: number; swap_free_bytes: number };
  disk: { free_bytes: number; total_bytes: number; used_bytes?: number };
  tools: Record<string, boolean>;
  tool_versions?: Record<string, string | null>;
  ollama: {
    id?: string;
    name: string;
    kind?: string;
    pricing: "local";
    free?: true;
    capabilities: string[];
    available: boolean;
    configured?: boolean;
    model?: string;
    base_url?: string;
    selected_model_available?: boolean | null;
    models: string[];
    error: string | null;
  };
  providers?: ProviderStatus[];
  storage?: { media_bytes: number; db_bytes?: number; free_bytes: number; total_bytes: number };
  free_only: true;
};

export type Dashboard = {
  counts: {
    projects: number;
    brands: number;
    media: number;
    exports: number;
    campaigns?: number;
    completed_exports?: number;
    ai_requests?: number;
  };
  storage: { media_bytes: number; free_bytes: number; total_bytes?: number; db_bytes?: number };
  recent_projects: Project[];
  recent_campaigns: Array<{
    id: string;
    name: string;
    platform: string;
    objective: string;
    status: "draft" | "active" | "archived";
    generated_at: string | null;
    created_at: string;
    updated_at: string;
    brand_name: string | null;
  }>;
  recent_exports: Array<{
    id: string;
    project_id: string | null;
    type: string;
    format: string;
    status: string;
    error: string | null;
    created_at: string;
    completed_at: string | null;
    project_name: string | null;
    file_url: string | null;
  }>;
  recent_brands: Array<{ id: string; name: string; industry: string; updated_at: string }>;
};

export type ChatRole = "user" | "assistant";
export type ChatMode = "chat" | "critique" | "ideas" | "rewrite";

export type ChatMessage = {
  role: ChatRole;
  content: string;
};

export type ChatResponse = {
  content: string;
  provider: ProviderId | "chain" | string;
  model: string | null;
  local: boolean;
  processing: "local" | "free cloud" | string;
  duration_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  fallback_used: boolean;
  selected_provider: ProviderId | null;
  chain: ProviderId[];
  attempts: Array<{
    provider: string;
    model: string | null;
    error?: string;
    kind?: string;
    skipped?: boolean;
  }>;
  context: {
    project: { id: string; name: string; type: string } | null;
    brand: { id: string; name: string } | null;
    campaign: { id: string; name: string } | null;
  };
  mode: ChatMode;
  free_only: true;
};

export type ChatRequest = {
  messages: ChatMessage[];
  project_id?: string | null;
  brand_id?: string | null;
  selection?: string | null;
  mode?: ChatMode;
};
