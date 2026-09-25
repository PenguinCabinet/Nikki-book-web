import { useEffect, useState } from 'react';

import { useCollaborativeText } from './useCollaborativeText';

export type HabitKeyword = {
  id: number;
  habitKeywordId: number | null;
  isPublic: boolean;
  keyword: string;
  totalCount: number;
};

const createKeyword = (id: number): HabitKeyword => ({
  id,
  habitKeywordId: null,
  isPublic: false,
  keyword: '',
  totalCount: 0,
});

function parseHabitKeywords(text: string): HabitKeyword[] {
  if (!text) return [];

  try {
    const value: unknown = JSON.parse(text);
    if (!Array.isArray(value)) return [];

    return value.flatMap((item, index) => {
      if (typeof item !== 'object' || item === null) return [];
      const record = item as Record<string, unknown>;
      const keyword = typeof record.keyword === 'string' ? record.keyword : '';
      if (!keyword.trim()) return [];

      return [{
        id: typeof record.id === 'number' ? record.id : index + 1,
        habitKeywordId: typeof record.habitKeywordId === 'number'
          ? record.habitKeywordId
          : null,
        isPublic: record.isPublic === true,
        keyword,
        totalCount: typeof record.totalCount === 'number'
          ? record.totalCount
          : typeof record.continueCount === 'number'
            ? record.continueCount
            : 0,
      }];
    });
  } catch {
    return [];
  }
}

function serializeHabitKeywords(keywords: HabitKeyword[]) {
  return JSON.stringify(
    keywords.filter((habitKeyword) => habitKeyword.keyword.trim()),
  );
}

export function useCollaborativeHabitKeywords() {
  const sync = useCollaborativeText('/habit');
  const [keywords, setKeywords] = useState<HabitKeyword[]>([createKeyword(1)]);
  const [nextId, setNextId] = useState(2);

  useEffect(() => {
    if (sync.loading) return;

    const syncedKeywords = parseHabitKeywords(sync.text);
    setKeywords(syncedKeywords.length > 0 ? syncedKeywords : [createKeyword(1)]);
    setNextId(
      Math.max(2, ...syncedKeywords.map((habitKeyword) => habitKeyword.id + 1)),
    );
  }, [sync.loading, sync.text]);

  const persistKeywords = (nextKeywords: HabitKeyword[]) => {
    sync.setText(serializeHabitKeywords(nextKeywords));
  };

  const updateKeyword = (
    id: number,
    update: Partial<Omit<HabitKeyword, 'id'>>,
  ) => {
    const updatedKeywords = keywords.map((habitKeyword) =>
      habitKeyword.id === id ? { ...habitKeyword, ...update } : habitKeyword,
    );
    setKeywords(updatedKeywords);
    persistKeywords(updatedKeywords);
  };

  const addKeyword = () => {
    const updatedKeywords = [...keywords, createKeyword(nextId)];
    setKeywords(updatedKeywords);
    setNextId((currentId) => currentId + 1);
    persistKeywords(updatedKeywords);
  };

  const deleteKeyword = (id: number) => {
    const updatedKeywords = keywords.filter((habitKeyword) => habitKeyword.id !== id);
    setKeywords(updatedKeywords.length > 0 ? updatedKeywords : [createKeyword(nextId)]);
    if (updatedKeywords.length === 0) {
      setNextId((currentId) => currentId + 1);
    }
    persistKeywords(updatedKeywords);
  };

  return {
    keywords,
    loading: sync.loading,
    updateKeyword,
    addKeyword,
    deleteKeyword,
  };
}
