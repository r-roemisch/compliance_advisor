// Mirrors backend/src/compliance_advisor/schemas.py and the Rule Check results in tools.py.

export type Lang = "de" | "en";

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

export type ToolRun = { name: string; arguments: Record<string, unknown>; result: Record<string, unknown> };

export type Usage = { input_tokens: number; output_tokens: number; cost_usd: number };

export type AskResponse = {
  id: string | null;
  created_at: string | null;
  question: string;
  redactions: string[];
  answer: string;
  passages: Passage[];
  cited: number[];
  tools: ToolRun[];
  coverage: "full" | "partial" | "none" | "unknown";
  model: string;
  usage: Usage;
  disclaimer: string;
  obligations?: ObligationRow[] | null; // when reopened from the history
};

export type FirmProfile = { firm_type: string; size: string; customers: string; activities: string[] };
export type Preset = { id: string; label: Record<Lang, string>; profile: FirmProfile };
export type ModelOption = { id: string; label: string; note: Record<string, string>; eu_hosted: boolean };

export type Milestone = { date: string; what: string };
export type SourceInfo = {
  id: string;
  title: string;
  short_title: string;
  regime: string;
  layer: string;
  issuer: string;
  language: string;
  url: string;
  legal_status: string;
  version: string;
  milestones: Milestone[];
  as_of: string;
  passages: number;
};

export type HistoryItem = { id: string; created_at: string; question: string; model: string };

export type Stage = "search" | "model" | "tools" | "writing";
export type StreamEvent =
  | { stage: Stage; tools?: string[]; redactions?: string[] }
  | { stage: "found"; count: number; sources: string[] }
  | { stage: "delta"; text: string }
  | { stage: "done"; result: AskResponse }
  | { stage: "error"; status: number; detail: string };

export type Ref = { provision: string; link: string };

export type ObligationRow = { addressee: string; action: string; deadline: string; provision: string; link: string; passage: number };

export type TimelineEntry = { date: string; status: "past" | "upcoming"; days_from_today: number; source: string; regime: string; what: string; link: string };
