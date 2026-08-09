import { createContext, useContext, useState } from "react";

export const SelectedContext = createContext({
  selected: [],
  selectionNotice: "",
  addSelected: () => {},
  removeSelected: () => {},
  clearSelected: () => {},
  moveSelected: () => {},
  clearSelectionNotice: () => {},
  getFirstSelected: () => null,
  getSelectedForSubmit: () => null,
});

export default function SelectedProvider({ children }) {
  const [selected, setSelected] = useState([]);
  const [selectionNotice, setSelectionNotice] = useState("");

  const addSelected = (frameId) => {
    setSelected((prev) => {
      if (prev.includes(frameId)) return prev;

      if (prev.length > 0) {
        const existingVideoId = prev[0].split("#")[0];
        const newVideoId = frameId.split("#")[0];

        if (existingVideoId !== newVideoId) {
          setSelectionNotice(
            `Current staging is for ${existingVideoId}. Clear it before selecting a frame from ${newVideoId}.`
          );
          return prev;
        }
      }

      setSelectionNotice("");
      return [...prev, frameId];
    });
  };

  const removeSelected = (frameId) => {
    setSelected((prev) => prev.filter((id) => id !== frameId));
    setSelectionNotice("");
  };

  const clearSelected = () => {
    setSelected([]);
    setSelectionNotice("");
  };

  const moveSelected = (fromIndex, toIndex) => {
    setSelected((prev) => {
      if (
        fromIndex < 0 ||
        toIndex < 0 ||
        fromIndex >= prev.length ||
        toIndex >= prev.length ||
        fromIndex === toIndex
      ) {
        return prev;
      }

      const next = [...prev];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
  };

  const clearSelectionNotice = () => setSelectionNotice("");

  const getFirstSelected = () => {
    return selected.length > 0 ? selected[0] : null;
  };

  // External submission is still verified as single-point; retain the legacy helper.
  const getSelectedForSubmit = () => {
    return selected.length > 0 ? selected[0] : null;
  };

  return (
    <SelectedContext.Provider
      value={{
        selected,
        selectionNotice,
        addSelected,
        removeSelected,
        clearSelected,
        moveSelected,
        clearSelectionNotice,
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
    throw new Error("useSelected must be used within a SelectedProvider");
  }
  return context;
}
