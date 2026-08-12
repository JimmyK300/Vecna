import { useState, createContext, useRef, useEffect } from "react";
import { useFetcher } from "react-router-dom";
import {
  signIn,
  getEvaluationIdAPI,
} from "../services/auth.js";
import localforage from "localforage";
import { EVENT_RETRIEVAL_ENABLED } from "../utils/localMode.js";

export const AuthContext = createContext({
  username: "",
  password: "",
  updateAuth: null,
  evaluationIds: [],
  submitAnswer: null,
});

export default function AuthProvider({ children }) {
  const fetcher = useFetcher({ key: "answers" });
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [evaluationIds, setEvaluationIds] = useState([]);

  const sessionId = useRef(undefined);
  useEffect(() => {
    if (!EVENT_RETRIEVAL_ENABLED) return undefined;
    const fetchEval = async () => {
      const localSessionId = await localforage.getItem("sessionId");
      if (localSessionId) {
        sessionId.current = localSessionId;
      }
      const evalRes = await getEvaluationIdAPI(sessionId.current);
      if (evalRes?.status === 200) {
        const evalIds = [];
        for (const e of evalRes.data) {
          evalIds.push({
            id: e["id"],
            name: e["name"],
          });
        }
        setEvaluationIds(evalIds);
      }
    };
    fetchEval();
  }, []);
  const updateAuth = async (username, password) => {
    if (!EVENT_RETRIEVAL_ENABLED) {
      setUsername(username);
      setPassword(password);
      alert("External event retrieval is disabled; answers remain local-only.");
      return;
    }
    setUsername(username);
    setPassword(password);
    const res = await signIn(username, password);
    if (res?.status === 200) {
      sessionId.current = res.data["sessionId"];
      await localforage.setItem("sessionId", sessionId.current);

      alert("Login successfully");
      const evalRes = await getEvaluationIdAPI(sessionId.current);
      if (evalRes?.status === 200) {
        const evalIds = [];
        for (const e of evalRes.data) {
          evalIds.push({
            id: e["id"],
            name: e["name"],
          });
        }
        setEvaluationIds(evalIds);
      }
    } else {
      alert(res?.data?.["description"] || "Login failed");
    }
  };

  const submitAnswer = async (answer) => {
    fetcher.submit(
      { correct: 0, ...answer },
      { method: "POST", action: "/answers" },
    );
  };

  return (
    <AuthContext.Provider
      value={{ username, password, updateAuth, evaluationIds, submitAnswer }}
    >
      {children}
    </AuthContext.Provider>
  );
}
