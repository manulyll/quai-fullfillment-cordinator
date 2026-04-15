import { config } from "./config";
import type { LocationOptionsResponse, ShortageReportResponse, UserInfo } from "./types";

const withAuthHeaders = (token: string): HeadersInit => ({
  "Content-Type": "application/json",
  Authorization: `Bearer ${token}`
});

const apiUrl = (path: string): string => {
  if (!config.apiBaseUrl) {
    return path;
  }
  return `${config.apiBaseUrl}${path}`;
};

const fetchJson = async <T>(url: string, token: string): Promise<T> => {
  const response = await fetch(url, {
    method: "GET",
    headers: withAuthHeaders(token)
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return (await response.json()) as T;
};

const toQuery = (params: Record<string, string | number | undefined>): string => {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      query.set(key, String(value));
    }
  });
  const encoded = query.toString();
  return encoded ? `?${encoded}` : "";
};

export const apiClient = {
  getMe: (token: string): Promise<UserInfo> => fetchJson<UserInfo>(apiUrl("/api/me"), token),
  getLocations: (token: string): Promise<LocationOptionsResponse> =>
    fetchJson<LocationOptionsResponse>(apiUrl("/api/shortages/locations"), token),
  getShortages: (
    token: string,
    filters: { locationId?: number; startDate?: string; endDate?: string }
  ): Promise<ShortageReportResponse> =>
    fetchJson<ShortageReportResponse>(
      apiUrl(`/api/shortages/report${toQuery(filters)}`),
      token
    )
};
