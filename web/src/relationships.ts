/**
 * Relationships on demand.
 *
 * Today the `/graph` payload carries `relationships` for every person, so the rail renders
 * them straight from the node. A later item makes `/graph` windowed: a person outside the
 * window will arrive with an empty `relationships` array, and computing kinship for all N up
 * front is exactly the cost that item removes. This module bridges the gap — when a person is
 * selected or focused and their relationships are missing, it fetches just that one person's
 * link to the root and caches it, so the rail fills in without the payload ever having to.
 *
 * When the payload already carried relationships (today's behaviour), nothing here runs.
 */
import { api } from './api';
import { person, state } from './state';

/** subject|other|side -> whether a fetch is in flight, so we never issue it twice. */
const inFlight = new Set<string>();

function key(subject: number, other: number, side: string): string {
  return `${subject}:${other}:${side}`;
}

/**
 * Ensure the given person's relationships are populated, fetching them if the payload omitted
 * them. Returns true when a fetch was started (the caller should re-render on completion).
 * A no-op — returning false — when they are already present or a fetch is already running.
 */
export function ensureRelationships(id: number, afterFetch: () => void): boolean {
  const p = person(id);
  const root = state.root;
  if (!p || root === null) return false;
  // Already carried by the payload, or this person IS the root (self needs no fetch).
  if (p.relationships.length > 0 || id === root) return false;

  const k = key(root, id, state.side);
  if (inFlight.has(k)) return false;
  inFlight.add(k);

  void api
    .relationshipTo(root, id, state.side)
    .then((res) => {
      // Mutate the cached node in place so every reader (rail, tree label) sees it.
      const target = person(id);
      if (target) {
        target.relationships = res.Relationships;
        target.seniorityQuestion = res.SeniorityQuestion;
      }
    })
    .catch(() => {
      /* a failed lazy fetch leaves the person unlabelled rather than breaking the page */
    })
    .finally(() => {
      inFlight.delete(k);
      afterFetch();
    });

  return true;
}
