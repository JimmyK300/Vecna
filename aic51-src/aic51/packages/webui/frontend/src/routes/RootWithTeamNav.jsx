import React from "react";
import { useLocation, useNavigate } from "react-router-dom";

import Root, { loader } from "./Root.jsx";

export { loader };

export default function RootWithTeamNav() {
  const navigate = useNavigate();
  const location = useLocation();
  const onTeamPage = location.pathname === "/team";

  return (
    <>
      <Root />
      {!onTeamPage && (
        <button
          type="button"
          onClick={() => navigate("/team")}
          className="fixed right-3 top-3 z-50 px-3 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-700 text-white text-xs font-extrabold shadow-lg border border-slate-700"
          title="Open the realtime shared team shortlist without clearing local frame selection"
        >
          Team shortlist
        </button>
      )}
    </>
  );
}
