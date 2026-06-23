interface AppConfig {
  // Base URL of the backend API. Empty string means same-origin, which is the
  // case when the FastAPI server serves this built frontend. For local dev
  // against a separate backend, set VITE_API_ENDPOINT (e.g.
  // http://localhost:8000).
  apiEndpoint: string;
}

export const config: AppConfig = {
  apiEndpoint: import.meta.env.VITE_API_ENDPOINT ?? ''
};
