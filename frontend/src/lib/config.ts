type RuntimeConfig = {
  API_BASE_URL?: string;
  COGNITO_USER_POOL_ID?: string;
  COGNITO_CLIENT_ID?: string;
  COGNITO_REGION?: string;
};

declare global {
  interface Window {
    __APP_CONFIG__?: RuntimeConfig;
  }
}

const runtimeConfig: RuntimeConfig = window.__APP_CONFIG__ ?? {};

const fromRuntimeOrBuild = (runtimeKey: keyof RuntimeConfig, buildKey: string): string => {
  const runtimeValue = runtimeConfig[runtimeKey];
  if (runtimeValue) {
    return runtimeValue;
  }
  const value = import.meta.env[buildKey];
  return value ?? "";
};

const required = (runtimeKey: keyof RuntimeConfig, buildKey: string): string => {
  const value = fromRuntimeOrBuild(runtimeKey, buildKey);
  if (!value) {
    throw new Error(`Missing configuration value: ${runtimeKey}`);
  }
  return value;
};

const optional = (runtimeKey: keyof RuntimeConfig, buildKey: string, fallback: string): string => {
  const value = fromRuntimeOrBuild(runtimeKey, buildKey);
  return value || fallback;
};

export const config = {
  apiBaseUrl: optional("API_BASE_URL", "VITE_API_BASE_URL", ""),
  cognitoUserPoolId: required("COGNITO_USER_POOL_ID", "VITE_COGNITO_USER_POOL_ID"),
  cognitoClientId: required("COGNITO_CLIENT_ID", "VITE_COGNITO_CLIENT_ID"),
  cognitoRegion: required("COGNITO_REGION", "VITE_COGNITO_REGION")
};
