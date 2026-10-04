import type { SessionState } from "./types";

export function textSummary(state: SessionState) {
  const counts = Object.fromEntries(["supported", "false", "potentially_false", "misleading", "context_needed", "couldnt_verify"]
    .map(verdict => [verdict, state.claims.filter(claim => claim.verdict === verdict).length]));
  const sources = new Set(state.claims.flatMap(claim => claim.evidence.map(item => item.url.replace(/\/$/, "")))).size;
  const total = state.claims.length;
  const incomplete = state.warnings.some(warning => !warning.startsWith("Only the selected fragment was analysed"));
  const meta = `Twierdzenia: ${total} · Źródła: ${sources}`;
  const pending = !["complete", "no_claims", "failed"].includes(state.status);
  let title = "Sprawdzam…";
  let body = state.status === "gathering_evidence" ? "Szukam źródeł dotyczących zaznaczonego fragmentu."
    : state.status === "reviewing_results" ? "Porównuję twierdzenia z dowodami i sprawdzam cytaty."
    : "Wyodrębniam twierdzenia, które można sprawdzić.";
  let tone = "neutral";
  if (state.status === "failed") {
    title = "Nie udało się zakończyć sprawdzania";
    body = state.mode === "demo" ? "Weryfikacja zaznaczenia wymaga włączenia trybu live w backendzie."
      : "Analiza jest niepełna. Spróbuj ponownie lub sprawdź szczegóły błędu.";
  } else if (!pending) {
    if (!total) {
      title = "Brak rozstrzygnięcia";
      body = "Nie uzyskano oceny sprawdzalnych twierdzeń w tym fragmencie. Nie oznacza to potwierdzenia jego treści.";
    } else if (counts.false || counts.potentially_false || counts.misleading) {
      tone = counts.false ? "danger" : "caution";
      title = counts.supported ? "Mieszane wyniki — zachowaj ostrożność" : "Fragment budzi zastrzeżenia";
      const parts = [counts.false ? `fałszywe: ${counts.false}` : "", counts.potentially_false ? `wątpliwe: ${counts.potentially_false}` : "",
        counts.misleading ? `mylące: ${counts.misleading}` : "", counts.supported ? `potwierdzone: ${counts.supported}` : "",
        counts.context_needed + counts.couldnt_verify ? `bez pełnego rozstrzygnięcia: ${counts.context_needed + counts.couldnt_verify}` : ""].filter(Boolean);
      body = `Wśród sprawdzonych twierdzeń — ${parts.join(", ")}. Sprawdź uzasadnienia przed wyciągnięciem wniosków o całym fragmencie.`;
    } else if (counts.context_needed || counts.couldnt_verify || incomplete) {
      title = counts.supported ? "Potwierdzenie z ograniczeniami" : "Brakuje dowodów lub kontekstu";
      tone = "caution";
      body = `Potwierdzone twierdzenia: ${counts.supported} z ${total}. Pozostałe wyniki lub ograniczenia analizy wymagają sprawdzenia w szczegółach.`;
    } else {
      title = "Sprawdzone twierdzenia są potwierdzone";
      tone = "positive";
      body = `Znalezione źródła potwierdzają sprawdzone twierdzenia (${total}). Ocena dotyczy wyłącznie tego, co udało się zweryfikować.`;
    }
  }
  const signal = !pending && state.signals.some(item => item.severity !== "low")
    ? "Wykryto też sygnały perswazji — zobacz szczegóły." : "";
  return { title, body, tone, meta, pending, signal };
}
