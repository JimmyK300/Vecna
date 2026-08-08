import { createContext, useContext, useState } from "react";

export const SelectedContext = createContext({
  selected: [],
  viewed: [],
  submitted: [],
  addSelected: () => {},
  removeSelected: () => {},
  clearSelected: () => {},
  markViewed: () => {},
  markSubmitted: () => {},
  getFirstSelected: () => null,
  getSelectedForSubmit: () => null,
});

export default function SelectedProvider({ children }) {
  const [selected, setSelected] = useState([]);
  const [viewed, setViewed] = useState([]);
  const [submitted, setSubmitted] = useState([]);

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

  const markSubmitted = (frameIds) => {
    const ids = Array.isArray(frameIds) ? frameIds : [frameIds];
    setSubmitted((prev) => [...new Set([...prev, ...ids])]);
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
        submitted,
        addSelected,
        removeSelected,
        clearSelected,
        markViewed,
        markSubmitted,
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
