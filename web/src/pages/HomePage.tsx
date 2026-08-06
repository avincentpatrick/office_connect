import { useState } from "react";
import { KeyRound } from "lucide-react";
import { EmptyState } from "../components/EmptyState/EmptyState";
import { QueryBar } from "../components/QueryBar/QueryBar";
import { useAuth } from "../app/providers/auth-context";
import { useConfig } from "../app/providers/config-context";
import { visibleNavItems } from "../app/nav";
import { matchNavItems } from "../app/nav-match";
import { emptyLandingState, matchStatusText, openableItems } from "./landing-copy";

/**
 * The platform's front door (Stage D-1). Minimalist by instruction — the
 * master plan's word, and it is a constraint rather than a mood: this is the
 * anti-dashboard. It answers exactly one question, *what can this person
 * open?*, and gives them a deterministic way to get there by typing.
 *
 * **It makes no network requests of its own.** Everything renders from
 * `/config` and `/auth/me`, which the shell has already fetched — so there is
 * no loading state, no count that can go stale, and nothing to reconcile.
 * That is why it needs no §4 layout template (see the §4 template note): a
 * template exists to enforce mandatory loading/empty structure, and this page
 * has none to enforce.
 *
 * Renders inside the App shell as a plain content page — the precedent
 * ui-standards §8 already records for HomePage and the auth screens.
 */
export function HomePage() {
  const { features } = useConfig();
  const { me } = useAuth();
  const [query, setQuery] = useState("");

  const openable = openableItems(visibleNavItems(features, me?.permissions ?? []));
  const matches = matchNavItems(openable, query);

  // ⚠ ONE list on this page, never two. Rendering "results" and "everything you
  // can open" as separate regions would put two nodes with the same href and
  // the same accessible name in the DOM — ui-standards §4's "one node,
  // repositioned, never two copies". Only the heading and contents vary.
  const showingEverything = query.trim() === "" || matches.length === 0;
  const shown = showingEverything ? openable : matches.map((m) => m.item);

  if (openable.length === 0) {
    // A search box over an empty index is furniture that can only ever refuse,
    // so the bar is not rendered at all here. After R-9 this is the COMMON
    // case, not the edge one: the flag says the module exists, the empty grant
    // list says it is not this person's.
    const empty = emptyLandingState(me?.permissions ?? [], me?.email);
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-text">Home</h1>
        <EmptyState icon={KeyRound} title={empty.title} description={empty.description} />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-text">Home</h1>
      <QueryBar
        label="What do you want to open?"
        placeholder="Try “travel”, “cash advance” or “where”"
        value={query}
        onValueChange={setQuery}
        resultsHeading={showingEverything ? "What you can open" : "Matches"}
        statusText={matchStatusText(query, matches.length)}
        results={shown.map((item) => ({
          id: item.to,
          label: item.label,
          to: item.to,
          icon: item.icon,
          meta: item.description,
        }))}
      />
    </div>
  );
}
