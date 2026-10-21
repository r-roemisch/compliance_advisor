// Mirrors backend/src/compliance_advisor/schemas.py.

export type Passage = {
  n: number;
  passage_id: string;
  source_id: string;
  source_title: string;
  short_title: string;
  regime: string;
  layer: string;
  issuer: string;
  language: string;
  url: string;
  score: number;
  text: string;
};

export type AskResponse = {
  question: string;
  answer: string;
  passages: Passage[];
  cited: number[];
  model: string;
  usage: { input_tokens: number; output_tokens: number };
  disclaimer: string;
};

export type SourceInfo = {
  id: string;
  title: string;
  short_title: string;
  regime: string;
  layer: string;
  issuer: string;
  language: string;
  url: string;
  passages: number;
};

export type SourcesResponse = { sources: SourceInfo[]; disclaimer: string };
