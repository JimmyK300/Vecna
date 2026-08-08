import { getAnswers, addAnswer } from "../services/answer.js";

export async function action({ request }) {
  const formData = await request.formData();
  const answer = Object.fromEntries(formData);
  const res = await addAnswer(answer);
  return res;
}

export async function loader() {
  const answers = await getAnswers();
  return answers;
}
