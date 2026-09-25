import * as Y from 'yjs';
import { useCollaborativeDocument } from './useCollaborativeDocument';

export type HabitKeyword = {
  id: string;
  habitKeywordId: number | null;
  isPublic: boolean;
  keyword: string;
  totalCount: number;
};

type HabitMetadata = { habitKeywordId: number | null; totalCount: number };
const emptyKeywords: HabitKeyword[] = [];
let draftSequence = 0;

function readHabitKeywords(doc: Y.Doc): HabitKeyword[] {
  const metadata = doc.getMap<HabitMetadata>('habitMetadata');
  return Array.from(doc.getMap<Y.Map<unknown>>('habits').entries())
    .filter(([, row]) => row instanceof Y.Map)
    .sort(([aId, a], [bId, b]) =>
      Number(a.get('order') ?? 0) - Number(b.get('order') ?? 0) || aId.localeCompare(bId))
    .map(([id, row]) => ({
      id,
      habitKeywordId: metadata.get(id)?.habitKeywordId ?? null,
      totalCount: metadata.get(id)?.totalCount ?? 0,
      keyword: String(row.get('keyword') ?? ''),
      isPublic: row.get('isPublic') === true,
    }));
}

export function useCollaborativeHabitKeywords() {
  const sync = useCollaborativeDocument('/habit/v2', readHabitKeywords, emptyKeywords);

  const addKeyword = () => {
    sync.change(doc => {
      const rows = doc.getMap<Y.Map<unknown>>('habits');
      // A row's identity never changes when the server assigns its database ID.
      const id = typeof crypto.randomUUID === 'function'
        ? crypto.randomUUID()
        : `${doc.clientID}-${Date.now()}-${++draftSequence}`;
      const order = Math.max(0, ...Array.from(rows.values(), row => Number(row.get('order') ?? 0))) + 1;
      const row = new Y.Map<unknown>();
      row.set('keyword', '');
      row.set('isPublic', false);
      row.set('order', order);
      rows.set(id, row);
    });
    sync.syncNow();
  };

  const updateKeyword = (id: string, update: Partial<Pick<HabitKeyword, 'keyword' | 'isPublic'>>) => {
    sync.change(doc => {
      const row = doc.getMap<Y.Map<unknown>>('habits').get(id);
      if (!row) return; // A remotely deleted row must not be recreated by a stale input.
      if (update.keyword !== undefined) row.set('keyword', update.keyword);
      if (update.isPublic !== undefined) row.set('isPublic', update.isPublic);
    });
  };

  const deleteKeyword = (id: string) => sync.change(doc => {
    doc.getMap('habits').delete(id);
  });

  return {
    keywords: sync.value,
    loading: sync.loading,
    status: sync.status,
    setComposing: sync.setComposing,
    updateKeyword,
    addKeyword,
    deleteKeyword,
  };
}
