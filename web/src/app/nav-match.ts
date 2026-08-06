/**
 * The query bar's deterministic intent matcher (Stage D-1).
 *
 * Deliberately generic over `{label, intentKeywords}` and importing NOTHING
 * from `./nav`: it has no way to acquire NAV_GROUPS, so it structurally cannot
 * offer a destination the caller did not already gate. That is api-standards
 * §9f's mistake — a surface borrowing a wider set than its rule allows —
 * foreclosed rather than merely avoided by discipline.
 *
 * Deterministic, explicitly not an LLM and not a fuzzy scorer (master-plan
 * Stage D). A fuzzy match would make *"nothing matches"* impossible to state
 * honestly, and that sentence is the whole point of the refusal state.
 */

/** The minimum shape a destination needs to be matchable. `NavItem` satisfies it. */
export interface Matchable {
  label: string;
  intentKeywords?: string[];
}

/**
 * Strongest first. Exact beats prefix beats substring **regardless of which
 * field matched**: a label and its keywords are two spellings of the same
 * destination, not two levels of authority. So an exact keyword hit ("coa")
 * outranks an incidental label prefix.
 */
export type MatchTier =
  | "label-exact"
  | "keyword-exact"
  | "label-prefix"
  | "keyword-prefix"
  | "label-substring"
  | "keyword-substring";

const TIER_ORDER: MatchTier[] = [
  "label-exact",
  "keyword-exact",
  "label-prefix",
  "keyword-prefix",
  "label-substring",
  "keyword-substring",
];

export interface NavMatch<T extends Matchable> {
  item: T;
  tier: MatchTier;
}

/**
 * Applied identically to the query, to every label and to every keyword — so
 * authored keywords like "COA" and "FMS" match lowercase typing.
 *
 * Deliberately absent, so nobody adds them by reflex: no diacritic folding
 * (interface language is English, ui-standards §5, and folding is a rule that
 * must hold in both directions), no punctuation stripping, no stemming, no
 * minimum length. Whitespace collapse IS included because a pasted
 * "cash  advance" is a real case and it costs nothing.
 */
function normalize(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function tierFor(item: Matchable, query: string): MatchTier | null {
  const label = normalize(item.label);
  if (label === query) return "label-exact";

  const keywords = (item.intentKeywords ?? []).map(normalize);
  if (keywords.some((k) => k === query)) return "keyword-exact";
  if (label.startsWith(query)) return "label-prefix";
  if (keywords.some((k) => k.startsWith(query))) return "keyword-prefix";
  if (label.includes(query)) return "label-substring";
  if (keywords.some((k) => k.includes(query))) return "keyword-substring";
  return null;
}

/**
 * Rank `items` against `query`, strongest tier first.
 *
 * `items` must ALREADY be gated — this function widens nothing and filters
 * nothing beyond the query itself. An empty or whitespace-only query returns
 * `[]`, not everything: returning everything would make the results
 * indistinguishable from the idle page, and the refusal indistinguishable from
 * the idle state.
 *
 * `[]` IS the no-match shape. There is deliberately no
 * `{status, openable}` union — the caller handed us the openable list, so
 * bouncing it back would be its own array returned by a pure function, and it
 * would invite the component to render a list the page never authorized.
 */
export function matchNavItems<T extends Matchable>(
  items: readonly T[],
  query: string,
): NavMatch<T>[] {
  const needle = normalize(query);
  if (needle === "") return [];

  // Bucketed single pass rather than a comparator: each item lands exactly once
  // at its STRONGEST tier, and declaration order survives inside a tier by
  // construction — no reliance on Array.prototype.sort being stable.
  const buckets = new Map<MatchTier, NavMatch<T>[]>(TIER_ORDER.map((t) => [t, []]));
  for (const item of items) {
    const tier = tierFor(item, needle);
    if (tier) buckets.get(tier)!.push({ item, tier });
  }
  return TIER_ORDER.flatMap((tier) => buckets.get(tier)!);
}
