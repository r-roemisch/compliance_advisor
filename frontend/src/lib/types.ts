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
  strategy?: SearchStrategy; // missing on answers stored before Search Strategies existed
  usage: Usage;
  disclaimer: string;
  trace?: Trace | null; // the Answer Trace; missing on answers stored before it existed
  refusal?: "manipulation" | "off_topic" | null; // set when the Pre-Check refused the question
  changed_sources?: SourceChange[]; // when reopened from the history: Sources changed since
  obligations?: ObligationRow[] | null; // when reopened from the history
};

export type FirmProfile = { firm_type: string; size: string; customers: string; activities: string[] };
export type Preset = { id: string; label: Record<Lang, string>; profile: FirmProfile };
export type SearchStrategy = "vector" | "hybrid";
export type TraceHit = { passage_id: string; provision: string; short_title: string; score: number | null; rank: number | null };
export type TranslationTrace = { query: string; language: string; vector: TraceHit[]; keyword: TraceHit[] };
export type Trace = {
  strategy: string;
  named: string[];
  named_hits: TraceHit[];
  vector: TraceHit[];
  keyword: TraceHit[];
  translation?: TranslationTrace | null; // Query Translation; missing on answers stored before it existed
  merged: string[];
  max_per_source: number;
  capped_out: number;
  found_by: Record<string, string>;
  seconds: Record<string, number>;
};
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

export type HistoryItem = { id: string; created_at: string; question: string; model: string; refused?: boolean };

export type User = { id: string; email: string; name: string; profile: FirmProfile | null; operator?: boolean };
export type ApiKey = { id: string; name: string; prefix: string; created_at: string; last_used_at: string | null };

export type QuestionRow = {
  id: string;
  created_at: string;
  question: string;
  model: string;
  regimes: string[];
  tools: string[];
  obligation_count: number;
  refused?: boolean;
};

/** Dashboard period in days; 0 = every question. */
export const PERIODS: Period[] = [7, 30, 90, 0];
export type Period = 7 | 30 | 90 | 0;

export type CitedProvision = { provision: string; title: string; short_title: string; layer: string; link: string; count: number };

/** A Source that applies to the Firm Profile, and how many questions touched it (0 = Blind Spot). */
export type BlindSpot = { short_title: string; regime: string; layer: string; url: string; applies: "yes" | "later" | "check"; questions: number };

export type DashboardData = {
  user: User;
  days: Period;
  stats: { questions: number; refused?: number; questions_total: number; obligations: number };
  activity: { date: string; count: number }[];
  regimes: { regime: string; count: number }[];
  provisions: CitedProvision[];
  blind_spots: BlindSpot[] | null;
  recent: QuestionRow[];
  upcoming: TimelineEntry[];
};

/** What was clicked on the dashboard; narrows the question list. */
export type QuestionFilter = { regime?: string; provision?: string; day?: string; days?: Period };

export type SourceChange = {
  source_id: string;
  short_title: string;
  at: string | null;
  added: number | null;
  removed: number | null;
  changed: number | null;
  answers?: number;
};
export type UpdateRun = {
  id: string;
  started_at: string;
  finished_at: string | null;
  trigger: "scheduled" | "manual";
  checked: number;
  changed: number;
  failed: number;
  notes: { source_id: string; error: string }[];
};
export type ChangeRecord = SourceChange & { id: string; run_id: string; passages_before: number; passages_after: number };
export type UpdateRuns = { running: boolean; scheduled: boolean; hour: number; runs: UpdateRun[]; changes: ChangeRecord[] };
export type OperatorData = {
  days: Period;
  stats: {
    questions: number;
    answered: number;
    refused: number;
    accounts: number;
    guest_questions: number;
    via_api_key: number;
    cost_usd: number;
    errors: number;
    avg_seconds: number | null;
    avg_top_score: number | null;
    cited_share: number | null;
    coverage_full_share: number | null;
  };
  activity: { date: string; count: number }[];
  models: { id: string; questions: number; cost_usd: number }[];
  strategies: { id: string; questions: number; cost_usd: number }[];
  refusals: { reason: string; count: number }[];
  errors: { status: string; count: number }[];
};
export type InventoryRow = ObligationRow & { answer_id: string; question: string; created_at: string };

export type Stage = "precheck" | "search" | "model" | "tools" | "writing";
export type StreamEvent =
  | { stage: Stage; tools?: string[] }
  | { stage: "found"; count: number; sources: string[] }
  | { stage: "refused"; reason: string }
  | { stage: "delta"; text: string }
  | { stage: "done"; result: AskResponse }
  | { stage: "error"; status: number; detail: string };

export type Ref = { provision: string; link: string };

export type ObligationRow = { addressee: string; action: string; deadline: string; provision: string; link: string; passage: number };

export type TimelineEntry = { date: string; status: "past" | "upcoming"; days_from_today: number; source: string; regime: string; what: string; link: string };
