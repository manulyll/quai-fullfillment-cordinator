import { useEffect, useState } from "react";
import { getCurrentSession, signIn, signOut, type AuthSession } from "../lib/auth";

type AuthState = {
  session: AuthSession | null;
  loading: boolean;
};

export const useAuth = () => {
  const [state, setState] = useState<AuthState>({ session: null, loading: true });

  useEffect(() => {
    void getCurrentSession().then((session) => setState({ session, loading: false }));
  }, []);

  const login = async (username: string, password: string): Promise<void> => {
    const session = await signIn(username, password);
    setState({ session, loading: false });
  };

  const logout = (): void => {
    signOut();
    setState({ session: null, loading: false });
  };

  return {
    ...state,
    login,
    logout
  };
};
