const MVP_USERNAME = "frontend quai";
const MVP_PASSWORD = "admin";
const MVP_TOKEN = "quai-mvp-token";
const MVP_STORAGE_KEY = "quai-mvp-session";

export type AuthSession = {
  idToken: string;
  accessToken: string;
};

export const signIn = async (username: string, password: string): Promise<AuthSession> => {
  const normalizedUsername = username.trim().toLowerCase();
  if (normalizedUsername !== MVP_USERNAME || password !== MVP_PASSWORD) {
    throw new Error("Invalid credentials");
  }
  const session: AuthSession = { idToken: MVP_TOKEN, accessToken: MVP_TOKEN };
  localStorage.setItem(MVP_STORAGE_KEY, JSON.stringify(session));
  return session;
};

export const getCurrentSession = async (): Promise<AuthSession | null> => {
  const raw = localStorage.getItem(MVP_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as AuthSession;
    if (parsed.idToken !== MVP_TOKEN || parsed.accessToken !== MVP_TOKEN) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

export const signOut = (): void => {
  localStorage.removeItem(MVP_STORAGE_KEY);
};
