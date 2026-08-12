import { createContext, useContext, useEffect, useState } from "react";
import {
  TRIAGE_STATE_KEY,
  resetTriageState,
  restoreAllRejectedState,
  restoreRejectedState,
  updateTriageState,
} from "../utils/queryState.js";

export const SelectedContext = createContext({
  selected: [],
  viewed: [],
  saved: [],
  triageByQuery: {},
  activeQueryKey: "all",
  addSelected: () => {},
  removeSelected: () => {},
  clearSelected: () => {},
  markViewed: () => {},
  markSaved: () => {},
  setActiveQuery: () => {},
  isShortlisted: () => false,
  isRejected: () => false,
  toggleShortlist: () => {},
  toggleReject: () => {},
  resetTriage: () => {},
  restoreRejected: () => {},
  restoreAllRejected: () => {},
  getFirstSelected: () => null,
  getSelectedForSubmit: () => null,
});

export default function SelectedProvider({ children }) {
  const [selected, setSelected] = useState([]);
  const [viewed, setViewed] = useState([]);
  const [saved, setSaved] = useState([]);
  const [triageByQuery, setTriageByQuery] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(TRIAGE_STATE_KEY) || "{}");
    } catch {
      return {};
    }
  });
  const [activeQueryKey, setActiveQueryKey] = useState("all");

  useEffect(() => {
    localStorage.setItem(TRIAGE_STATE_KEY, JSON.stringify(triageByQuery));
  }, [triageByQuery]);

  const addSelected = (frameId) => {
    setSelected(prev => {
      if (!prev.includes(frameId)) {
        if (prev.length > 0) {
          const existingVideoId = prev[0].split('#')[0];
          const newVideoId = frameId.split('#')[0];
          
          if (existingVideoId !== newVideoId) {
            return prev;
          }
        }
        
        return [...prev, frameId];
      }
      return prev;
    });
  };

  const removeSelected = (frameId) => {
    setSelected(prev => prev.filter(id => id !== frameId));
  };

  const clearSelected = () => {
    setSelected([]);
  };

  const markViewed = (frameId) => {
    setViewed((prev) => (prev.includes(frameId) ? prev : [...prev, frameId]));
  };

  const markSaved = (frameIds) => {
    const ids = Array.isArray(frameIds) ? frameIds : [frameIds];
    setSaved((prev) => [...new Set([...prev, ...ids])]);
  };

  const setActiveQuery = (queryKey) => {
    setActiveQueryKey(queryKey || "all");
  };

  const isShortlisted = (frameId, queryKey = activeQueryKey) =>
    Boolean(triageByQuery[`${queryKey || "all"}::${frameId}`]?.shortlisted);

  const isRejected = (frameId, queryKey = activeQueryKey) =>
    Boolean(triageByQuery[`${queryKey || "all"}::${frameId}`]?.rejected);

  const toggleShortlist = (frameId, queryKey = activeQueryKey) => {
    setTriageByQuery((current) => updateTriageState(current, queryKey, frameId, "shortlist"));
  };

  const toggleReject = (frameId, queryKey = activeQueryKey) => {
    setTriageByQuery((current) => updateTriageState(current, queryKey, frameId, "reject"));
  };

  const resetTriage = (queryKey = activeQueryKey) => {
    setTriageByQuery((current) => resetTriageState(current, queryKey));
  };

  const restoreRejected = (frameId, queryKey = activeQueryKey) => {
    setTriageByQuery((current) => restoreRejectedState(current, queryKey, frameId));
  };

  const restoreAllRejected = (queryKey = activeQueryKey) => {
    setTriageByQuery((current) => restoreAllRejectedState(current, queryKey));
  };

  const getFirstSelected = () => {
    return selected.length > 0 ? selected[0] : null;
  };

  const getSelectedForSubmit = () => {
    return selected.length > 0 ? selected[0] : null;
  };

  return (
    <SelectedContext.Provider
      value={{
        selected,
        viewed,
        saved,
        triageByQuery,
        activeQueryKey,
        addSelected,
        removeSelected,
        clearSelected,
        markViewed,
        markSaved,
        setActiveQuery,
        isShortlisted,
        isRejected,
        toggleShortlist,
        toggleReject,
        resetTriage,
        restoreRejected,
        restoreAllRejected,
        getFirstSelected,
        getSelectedForSubmit,
      }}
    >
      {children}
    </SelectedContext.Provider>
  );
}

export function useSelected() {
  const context = useContext(SelectedContext);
  if (!context) {
    throw new Error('useSelected must be used within a SelectedProvider');
  }
  return context;
}
