import axios from "axios";
import { EVENT_RETRIEVAL_ENABLED } from "../utils/localMode.js";

function disabledResponse() {
  return { status: 0, data: { description: "External event retrieval is disabled; answers are local-only." } };
}

export async function signIn(username, password) {
  if (!EVENT_RETRIEVAL_ENABLED) return disabledResponse();
  try {
    const res = await axios.post(
      "https://eventretrieval.one/api/v2/login",
      { username: username, password: password },
      { headers: { "Content-Type": "application/json" } },
    );

    return res;
  } catch (err) {
    return err.response;
  }
}

export async function getEvaluationIdAPI(sessionId) {
  if (!EVENT_RETRIEVAL_ENABLED) return disabledResponse();
  try {
    const res = await axios.get(
      "https://eventretrieval.one/api/v2/client/evaluation/list",
      { params: { session: sessionId } },
    );
    return res;
  } catch (err) {
    return err.response;
  }
}

export async function submitAnswerAPI(sessionId, answer) {
  if (!EVENT_RETRIEVAL_ENABLED) return disabledResponse();
  try {
    const answerType = answer.answer ? "qa" : "kis";
    let answerData = {};
    if (answerType === "qa") {
      answerData = {
        answerSets: [
          {
            answers: [
              {
                text: `${answer.answer}-${answer.video_id}-${parseInt(answer.time * 1000)}`,
              },
            ],
          },
        ],
      };
    } else {
      answerData = {
        answerSets: [
          {
            answers: [
              {
                mediaItemName: answer.video_id,
                start: parseInt(answer.time * 1000),
                end: parseInt(answer.time * 1000),
              },
            ],
          },
        ],
      };
    }
    const evaluationId = answer.query_id;
    const res = await axios.post(
      `https://eventretrieval.one/api/v2/submit/${evaluationId}`,
      answerData,
      {
        params: { session: sessionId },
        headers: { "Content-Type": "application/json" },
      },
    );
    return res;
  } catch (err) {
    return err.response;
  }
}
