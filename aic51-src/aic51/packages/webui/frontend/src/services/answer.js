import localforage from "localforage";

export function processAnswer(answer) {
  if ("time" in answer) answer.time = parseFloat(answer.time);
  if ("frame_counter" in answer) {
    if (typeof answer.frame_counter === "string" && answer.frame_counter.includes(",")) {
      answer.frame_counter = answer.frame_counter
        .split(",")
        .map((fc) => fc.trim())
        .filter(Boolean);
    } else {
      answer.frame_counter = [answer.frame_counter];
    }
  }

  // Preserve the operator's staged order. Sorting here used to erase the
  // explicit order maintained by the selection UI and could silently change CSV output.
  if ("correct" in answer) answer.correct = parseInt(answer.correct);
  answer.frame_id = answer.frame_id || answer.frame_counter[0];
  return answer;
}

export async function getAnswers() {
  const answers = await localforage.getItem("answers");
  let res = null;
  if (!answers) {
    res = [];
  } else {
    res = answers;
  }
  return res;
}
export async function getAnswersByIds(ids) {
  const answers = await localforage.getItem("answers");
  if (!answers) {
    return [];
  }
  return answers.filter((answer) => ids.includes(answer.id));
}

export async function addAnswer(answer) {
  const answers = await getAnswers();
  processAnswer(answer);
  let id = parseInt((await localforage.getItem("id_ptr")) || 0);
  await localforage.setItem("answers", [
    ...answers,
    { id: id, submitted: new Date().toLocaleString(), ...answer },
  ]);
  const res = await localforage.getItem("answers");
  await localforage.setItem("id_ptr", id + 1);
  return res;
}

export async function updateAnswer(id, new_answer) {
  const answers = await getAnswers();
  processAnswer(new_answer);
  const updatedAnswer = answers.map((answer) => {
    if (answer.id === parseInt(id)) {
      return {
        id: parseInt(id),
        submitted: answer.submitted,
        frame_id: answer.frame_id,
        ...new_answer,
      };
    } else {
      return answer;
    }
  });
  await localforage.setItem("answers", updatedAnswer);
  return await localforage.getItem("answers");
}

export async function deleteAnswer(id) {
  const answers = await getAnswers();
  const newAnswers = answers.filter(
    (answer) => parseInt(answer.id) !== parseInt(id),
  );
  await localforage.setItem("answers", newAnswers);
  return await localforage.getItem("answers");
}

export function formatCleanInteger(val) {
  if (val === null || val === undefined) return "0";
  const num = typeof val === "number" ? val : parseFloat(String(val).replace(/e.*/i, ""));
  if (isNaN(num)) return String(val).trim();
  return String(Math.round(num));
}

export function getCSV(answer, n = 1, step = 1) {
  const cleanVideoId = String(answer.video_id || "").trim();

  if (answer.frame_counter && typeof answer.frame_counter === "string" && answer.frame_counter.includes(",")) {
    const frameCounters = answer.frame_counter.split(",").map((fc) => formatCleanInteger(fc));
    return `${cleanVideoId},${frameCounters.join(",")}`;
  }

  let fileData = "";
  let rawCenters = Array.isArray(answer.frame_counter) ? answer.frame_counter : [answer.frame_id || 0];
  let centers = rawCenters.map((e) => parseInt(formatCleanInteger(e), 10));

  const parsedN = parseInt(n, 10) || 1;
  const parsedStep = parseInt(step, 10) || 1;

  for (
    let offset = 0, i = 0, left = false;
    i < parsedN;
    offset += !left ? parsedStep : 0, ++i, left = !left
  ) {
    let curFrames = centers.map((center) => {
      const calc = left ? Math.round(center - offset) : Math.round(center + offset);
      return formatCleanInteger(Math.max(0, calc));
    });

    if (fileData !== "") fileData += "\n";
    if (answer.answer && String(answer.answer).trim().length > 0)
      fileData += `${cleanVideoId},${curFrames.join(",")},${String(answer.answer).trim()}`;
    else fileData += `${cleanVideoId},${curFrames.join(",")}`;
  }
  return fileData;
}

export function exportAllAnswersCSV(answers) {
  if (!answers || !answers.length) return "";
  return answers.map((ans) => getCSV(ans, 1, 1)).filter(Boolean).join("\n");
}
