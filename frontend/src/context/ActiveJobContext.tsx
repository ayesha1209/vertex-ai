import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { getActiveJobId, setActiveJobId as persistActiveJobId } from "../hooks/useJobStream";

type ActiveJobContextValue = {
  activeJobId: string | null;
  setActiveJobId: (id: string | null) => void;
};

const ActiveJobContext = createContext<ActiveJobContextValue | null>(null);

export function ActiveJobProvider({ children }: { children: React.ReactNode }) {
  const [activeJobId, setState] = useState<string | null>(() => getActiveJobId());

  const setActiveJobId = useCallback((id: string | null) => {
    persistActiveJobId(id);
    setState(id);
  }, []);

  const value = useMemo(
    () => ({ activeJobId, setActiveJobId }),
    [activeJobId, setActiveJobId]
  );

  return (
    <ActiveJobContext.Provider value={value}>
      {children}
    </ActiveJobContext.Provider>
  );
}

export function useActiveJob() {
  const ctx = useContext(ActiveJobContext);
  if (!ctx) throw new Error("useActiveJob must be used within ActiveJobProvider");
  return ctx;
}
