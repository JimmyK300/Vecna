import { useLoaderData, Outlet } from "react-router-dom";

import VideoProvider from "../components/VideoPlayer.jsx";
import SelectedProvider from "../components/SelectedProvider.jsx";
import AuthProvider from "../components/AuthProvider.jsx";

import AnswerSidebar from "../components/Answer.jsx";
import SearchParams from "../components/SearchParams.jsx";
import { getTargetFeatures } from "../services/search.js";

export async function loader() {
  try {
    const data = await getTargetFeatures();
    return { targetFeatureOptions: data.target_features || [] };
  } catch (error) {
    console.error('Failed to load target features:', error);
    return { targetFeatureOptions: [] };
  }
}
export default function Root() {
  const { targetFeatureOptions } = useLoaderData();
  return (
    <AuthProvider>
      <SelectedProvider>
        <VideoProvider>
          <div className="app-shell">
            <div className="workspace-controls">
              <SearchParams />
            </div>
            <main className="workspace-main">
              <Outlet context={{ targetFeatureOptions }} />
            </main>
            <section className="candidate-dock" aria-label="Candidate staging and submissions">
              <AnswerSidebar />
            </section>
          </div>
      </VideoProvider>
      </SelectedProvider>
    </AuthProvider>
  );
}
