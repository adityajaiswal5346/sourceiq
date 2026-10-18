/**
 * DocuMind — App Root
 * Routes between LoginPage and QueryInterface based on auth state.
 */

import { AuthProvider, useAuth } from "./context/AuthContext";
import LoginPage      from "./pages/LoginPage";
import QueryInterface from "./components/QueryInterface";
import { Spinner }    from "./components/ui/index";

function AppInner() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        role="status"
        aria-label="Loading…"
        className="flex items-center justify-center h-screen bg-surface-0
                   text-text-tertiary"
      >
        <Spinner size={20} />
      </div>
    );
  }

  return user !== null ? <QueryInterface /> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}
