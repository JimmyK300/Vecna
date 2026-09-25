import axios from "axios";

export async function signIn(username, password) {
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
  try {
    // 1. Resolve Evaluation ID
    let evaluationId = answer.evaluation_id || answer.query_id;
    const symbolicNames = ["TKIS", "VKIS", "QA", "TRAKE", "ACTIVE", "", undefined, null];
    if (symbolicNames.includes(evaluationId) || (evaluationId && String(evaluationId).length < 10)) {
      const evalRes = await getEvaluationIdAPI(sessionId);
      if (evalRes && evalRes.status === 200 && Array.isArray(evalRes.data) && evalRes.data.length > 0) {
        const activeEval = evalRes.data.find(
          (e) => String(e.status).toUpperCase() === "ACTIVE",
        ) || evalRes.data[0];
        if (activeEval && activeEval.id) {
          evaluationId = activeEval.id;
        }
      }
    }

    if (!evaluationId || symbolicNames.includes(evaluationId)) {
      return {
        status: 400,
        data: {
          status: false,
          description:
            "Không tìm thấy phiên thi nào đang 'ACTIVE' trên server DRES! Vui lòng chờ BTC kích hoạt đề thi.",
        },
      };
    }

    // Helper: Clean video ID (strip .mp4, .webm, etc.)
    const cleanVideoId = (vid) => {
      if (!vid) return "";
      const firstVid = String(vid).split(",")[0].trim();
      return firstVid.replace(/\.(mp4|webm|avi|mkv|mov|flv)$/i, "").trim();
    };

    const targetVideo = cleanVideoId(answer.video_id);

    // Calculate time in milliseconds (ms)
    let timeMs = 0;
    if (answer.time !== undefined && answer.time !== null && !isNaN(Number(answer.time))) {
      timeMs = Math.round(Number(answer.time) * 1000);
    } else if (answer.time_ms !== undefined && answer.time_ms !== null && !isNaN(Number(answer.time_ms))) {
      timeMs = Math.round(Number(answer.time_ms));
    } else if (answer.frame_counter !== undefined && answer.frame_counter !== null) {
      const firstFrame = String(answer.frame_counter).split(",")[0].trim();
      const fNum = parseInt(firstFrame, 10);
      if (!isNaN(fNum)) {
        timeMs = Math.round((fNum / 25) * 1000);
      }
    }

    let answerData = {};

    // 2. Identify task type & build payload
    const queryId = String(answer.query_id || "").toUpperCase();
    const isTrake = queryId === "TRAKE" || !!answer.trake;
    const isQa = !isTrake && (queryId === "QA" || (answer.answer && String(answer.answer).trim().length > 0));

    if (isTrake) {
      // Dạng TRAKE: "TR-<VIDEO_ID>-<FRAME_ID1>,<FRAME_ID2>,..."
      let frameList = [];
      if (Array.isArray(answer.frames)) {
        frameList = answer.frames.map((f) => String(f).trim()).filter(Boolean);
      } else if (typeof answer.frames === "string" && answer.frames.trim()) {
        frameList = answer.frames.split(/[,;\s]+/).map((f) => f.trim()).filter(Boolean);
      } else if (answer.frame_counter !== undefined && answer.frame_counter !== null) {
        frameList = String(answer.frame_counter).split(/[,;\s]+/).map((f) => f.trim()).filter(Boolean);
      } else if (answer.raw_selected) {
        const parts = String(answer.raw_selected).split(";");
        parts.forEach((p) => {
          const sub = p.split("#");
          if (sub.length >= 2 && sub[1]) {
            sub[1].split(",").forEach((f) => {
              if (f.trim()) frameList.push(f.trim());
            });
          }
        });
      }

      const text = `TR-${targetVideo}-${frameList.join(",")}`;
      answerData = {
        answerSets: [
          {
            answers: [
              {
                text: text,
              },
            ],
          },
        ],
      };
    } else if (isQa) {
      // Dạng Q&A: "QA-<ANSWER>-<VIDEO_ID>-<TIME(ms)>"
      let rawAns = String(answer.answer || answer.qa_answers || "").trim();
      if (rawAns.toUpperCase().startsWith("QA-")) {
        rawAns = rawAns.slice(3).trim();
      }

      const text = `QA-${rawAns}-${targetVideo}-${timeMs}`;
      answerData = {
        answerSets: [
          {
            answers: [
              {
                text: text,
              },
            ],
          },
        ],
      };
    } else {
      // Dạng KIS (Textual KIS hoặc Video KIS):
      // mediaItemName (không đuôi), start (ms), end (ms)
      const endMs = answer.end_ms !== undefined && !isNaN(Number(answer.end_ms))
        ? Math.round(Number(answer.end_ms))
        : timeMs;

      answerData = {
        answerSets: [
          {
            answers: [
              {
                mediaItemName: targetVideo,
                start: timeMs,
                end: endMs,
              },
            ],
          },
        ],
      };
    }

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
    return err.response || { status: 500, data: { description: err.message } };
  }
}

