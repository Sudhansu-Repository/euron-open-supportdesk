/** Plain-language explanations of the jargon, shown by <Hint term="..."/>. */
export const GLOSSARY = {
  rag: "Retrieval-augmented generation: before answering, the AI looks up the most relevant passages of your knowledge and answers only from them.",
  grounding:
    "An answer is grounded when it cites at least one passage of your knowledge that scored above the relevance threshold. Ungrounded answers are never sent.",
  relevanceThreshold:
    "How closely a passage must match the question before the AI may use it, from 0 to 1. Higher is stricter: fewer answers, fewer mistakes.",
  relevance: "How well a passage answers the question, combining meaning (similarity) and shared words (coverage).",
  similarity: "How close the passage is in meaning to the question, from its embedding.",
  coverage: "How many of the question's important words the passage contains.",
  semanticCache:
    "Reuses an earlier answer when a new question means the same thing, even worded differently. Costs zero tokens. Cleared when your knowledge changes.",
  exactCache: "Reuses an earlier answer to the very same question (after normalising case and spacing). Costs zero tokens.",
  sla: "Service level agreement: your target time to first reply and to resolve, per priority. Conversations near or past the target are flagged.",
  csat: "Customer satisfaction: the 1 to 5 rating customers give after a conversation is resolved.",
  aiResolution: "A conversation the AI answered from your knowledge and the customer did not need a person for.",
  extractive: "Zero-API-key mode: the AI quotes the best passage of your docs instead of writing text. No model, no tokens, no network.",
  tokens: "The unit language models bill by, roughly three quarters of a word. Input (question and passages) and output (the answer) both count.",
  kbVersion: "Goes up every time your knowledge changes, so cached answers from older knowledge are never reused.",
  embedder: "The model that turns text into vectors so passages can be found by meaning. Runs locally by default.",
  triage: "Reads each new message for intent, category, priority and sentiment, before the AI decides anything.",
  identityVerification:
    "Your backend signs each signed-in customer's id with a secret. The widget then cannot be used to impersonate another customer.",
} as const;

export type GlossaryKey = keyof typeof GLOSSARY;
