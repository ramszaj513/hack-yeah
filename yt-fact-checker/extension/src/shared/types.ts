export type Verdict =
  | "false"
  | "potentially_false"
  | "misleading"
  | "supported"
  | "context_needed"
  | "couldnt_verify";

export type UnverifiedReason =
  | "no_evidence_found"
  | "sources_conflict"
  | "evidence_not_specific"
  | "citation_unverifiable"
  | "provider_error"
  | "claim_ambiguous";

export type ClaimType =
  | "definitional"
  | "statistical"
  | "scientific"
  | "historical"
  | "political"
  | "general";

export type SourceType =
  | "primary"
  | "academic"
  | "fact_checker"
  | "journalism"
  | "reference"
  | "web";

export type Technique =
  | "undisclosed_ad"
  | "emotional_manipulation"
  | "loaded_language"
  | "logical_fallacy"
  | "cherry_picking"
  | "conspiracy_framing"
  | "political_framing"
  | "unfalsifiable";

export interface Signal {
  id: string;
  quote: string;
  startSeconds: number;
  endSeconds: number;
  technique: Technique;
  severity: "low" | "medium" | "high";
  note: string;
}

/** Viewer preferences, stored locally. */
export interface Settings {
  /** Raise a notice over the player as playback reaches a flagged moment. */
  popups: boolean;
  /** Supported claims are already in the video; hiding them leaves the problems. */
  hideSupported: boolean;
  /** The rhetorical pass: manipulation, hidden ads, framing. */
  showSignals: boolean;
  /** Ignore minor rhetorical observations. */
  strongSignalsOnly: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  popups: true,
  hideSupported: false,
  showSignals: true,
  strongSignalsOnly: false,
};

export type AnalysisStatus =
  | "ready"
  | "loading_transcript"
  | "extracting_claims"
  | "gathering_evidence"
  | "reviewing_results"
  | "complete"
  | "no_transcript"
  | "no_claims"
  | "unsupported"
  | "failed";

export interface TranscriptSegment {
  text: string;
  start: number;
  duration: number;
}

export interface VideoMetadata {
  id: string;
  title: string;
  description: string;
  language: string;
  /** ISO date the video was published. Relative times in the transcript are
   *  relative to this, not to whenever someone runs the check. */
  publishedAt: string;
}

export interface Evidence {
  title: string;
  publisher: string;
  url: string;
  sourceType: SourceType;
  /** Span the model attributed to this source. */
  snippet: string;
  /** true = quote found on the page, false = fetched but absent, null = could not fetch. */
  quoteVerified: boolean | null;
  supports: "supports" | "contradicts" | "context";
}

export interface Claim {
  id: string;
  text: string;
  /** Verbatim transcript span the claim came from. */
  quote: string;
  startSeconds: number;
  endSeconds: number;
  verdict: Verdict;
  claimType: ClaimType;
  unverifiedReason: UnverifiedReason | null;
  confidence: number;
  basis: string;
  evidence: Evidence[];
  context: {
    country?: string | null;
    timeframe?: string | null;
  };
}

export interface AnalysisResponse {
  analysisId: string;
  status: "complete" | "no_transcript" | "no_claims" | "failed";
  mode: "demo" | "live";
  claims: Claim[];
  signals: Signal[];
  warnings: string[];
}

/** Server-sent events emitted by /api/v1/check/stream. */
export interface Progress {
  stage: "evidence" | "verdicts";
  done: number;
  total: number;
}

export type StreamEvent =
  | { type: "status"; status: AnalysisStatus }
  | ({ type: "progress" } & Progress)
  | { type: "signal"; signal: Signal }
  | { type: "claim"; claim: Claim }
  | { type: "complete"; response: AnalysisResponse }
  | { type: "error"; message: string };

export interface SessionState {
  textRunId?: string;
  textSelection?: TextSelection;
  sourceTabId?: number;
  video?: VideoMetadata;
  status: AnalysisStatus;
  claims: Claim[];
  signals: Signal[];
  warnings: string[];
  mode?: "demo" | "live";
  selectedClaimId?: string;
  error?: string;
  progress?: Progress;
}

export interface TextSelection {
  text: string;
  pageUrl: string;
  pageTitle: string;
  context: string;
}

export type RuntimeMessage =
  | { type: "CHECK_TEXT"; selection: TextSelection }
  | { type: "RETRY_TEXT" }
  | { type: "OPEN_TEXT_DETAILS"; runId: string }
  | { type: "CHECK_STARTED"; video: VideoMetadata; url: string }
  | { type: "TRANSCRIPT_READY"; video: VideoMetadata; url: string; transcript?: TranscriptSegment[] }
  | { type: "VIDEO_CHANGED"; video: VideoMetadata | null }
  | { type: "MARKER_CLICK"; claimId: string; startSeconds: number }
  | { type: "GET_STATE" }
  | { type: "START_CHECK" }
  | { type: "SEEK_TO"; seconds: number }
  | { type: "CLEAR_SESSION" }
  | { type: "GET_SETTINGS" }
  | { type: "SET_SETTINGS"; settings: Settings };
