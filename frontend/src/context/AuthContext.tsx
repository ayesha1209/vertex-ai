import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { checkAuth, adminLogout } from "../lib/api";

interface AuthContextValue {
  isAuthenticated: boolean;
  checking: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  isAuthenticated: false,
  checking: true,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);

  // On mount, ask the backend if we have a valid session cookie
  useEffect(() => {
    checkAuth()
      .then(setIsAuthenticated)
      .catch(() => setIsAuthenticated(false))
      .finally(() => setChecking(false));
  }, []);

  const login = useCallback(() => setIsAuthenticated(true), []);

  const logout = useCallback(() => {
    adminLogout().catch(() => {});
    setIsAuthenticated(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isAuthenticated, checking, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
