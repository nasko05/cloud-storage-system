interface AppConfig {
  // Base URL of the backend API. Empty string means same-origin, which is the
  // case when the FastAPI server serves this built frontend. For local dev
  // against a separate backend, set VITE_API_ENDPOINT (e.g.
  // http://localhost:8000).
  apiEndpoint: string;
  // Full URL of the co-hosted space-io editor ("My Space"). When set, a link to
  // it appears in the top bar; the shared SSO cookie keeps the user signed in
  // across the jump. Empty hides the link (e.g. when the editor isn't deployed).
  personalAreaUrl: string;
}

export const config: AppConfig = {
  apiEndpoint: import.meta.env.VITE_API_ENDPOINT ?? '',
  personalAreaUrl: import.meta.env.VITE_PERSONAL_AREA_URL ?? ''
};
