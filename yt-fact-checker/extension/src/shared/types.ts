export type Verdict =
  | "false"
  | "potentially_false"
  | "misleading"
  | "supported"
  | "context_needed"
  | "couldnt_verify";

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
}

export interface Evidence {
  title: string;
  publisher: string;
  url: string;
  sourceType: "primary" | "fact_checker" | "journalism" | "reference";
}

export interface Claim {
  id: string;
  text: string;
  startSeconds: number;
  endSeconds: number;
  verdict: Verdict;
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
  warnings: string[];
}

export interface SessionState {
  video?: VideoMetadata;
  status: AnalysisStatus;
  claims: Claim[];
  warnings: string[];
  mode?: "demo" | "live";
  selectedClaimId?: string;
  error?: string;
}

export type RuntimeMessage =
  | { type: "CHECK_STARTED"; video: VideoMetadata }
  | { type: "TRANSCRIPT_READY"; video: VideoMetadata; transcript: TranscriptSegment[] }
  | { type: "NO_TRANSCRIPT"; video: VideoMetadata }
  | { type: "VIDEO_CHANGED"; video: VideoMetadata | null }
  | { type: "MARKER_CLICK"; claimId: string; startSeconds: number }
  | { type: "GET_STATE" }
  | { type: "START_CHECK" }
  | { type: "SEEK_TO"; seconds: number };
