import { useAuth } from "./hooks/useAuth";
import { LoginPage } from "./pages/LoginPage";
import { ShortagePage } from "./pages/ShortagePage";

const App = () => {
  const { session, loading, login, logout } = useAuth();

  if (loading) {
    return <main className="centered-page">Loading session...</main>;
  }

  if (!session) {
    return <LoginPage onLogin={login} />;
  }

  return <ShortagePage token={session.idToken} onLogout={logout} />;
};

export default App;
