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
  provision: string;
  provision_title: string;
  link: string;
  legal_status: string;
  version: string;
  as_of: string;
  score: number;
  text: string;
};

export type ToolRun = {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
};

export type FirmProfile = {
  firm_type: string;
  size: string;
  customers: string;
  activities: string[];
};

export type Preset = { id: string; label: { de: string; en: string }; profile: FirmProfile };

export type AskResponse = {
  question: string;
  redactions: string[];
  answer: string;
  passages: Passage[];
  cited: number[];
  tools: ToolRun[];
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
