// @vitest-environment jsdom
import 'fake-indexeddb/auto';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as Y from 'yjs';
import Habit from '../habit';
import { useCollaborativeHabitKeywords } from './useCollaborativeHabitKeywords';

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
let server: Y.Doc;
let userId = 100;
let nextId: number;
let ids: Map<string, number>;
let offline: boolean;
let holdNextResponse: boolean;
let releaseResponse: (() => void) | undefined;

beforeEach(() => {
  userId++;
  server = new Y.Doc();
  nextId = 1;
  ids = new Map();
  offline = false;
  holdNextResponse = false;
  releaseResponse = undefined;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
    if (url.endsWith('/sync-identity')) return Response.json({ user_id: userId });
    if (offline) throw new TypeError('offline');
    expect(url.endsWith('/habit/v2/sync')).toBe(true);
    Y.applyUpdate(server, new Uint8Array(options.body as ArrayBuffer));
    const rows = server.getMap<Y.Map<unknown>>('habits');
    const metadata = server.getMap('habitMetadata');
    server.transact(() => {
      for (const [key, row] of rows) {
        if (!ids.has(key)) ids.set(key, nextId++);
        const value = { habitKeywordId: ids.get(key) ?? null, totalCount: 0 };
        if (JSON.stringify(metadata.get(key)) !== JSON.stringify(value)) metadata.set(key, value);
      }
      for (const key of metadata.keys()) if (!rows.has(key)) metadata.delete(key);
    });
    const response = new Response(new Uint8Array(Y.encodeStateAsUpdate(server)).buffer);
    if (holdNextResponse) {
      holdNextResponse = false;
      await new Promise<void>(resolve => { releaseResponse = resolve; });
    }
    return response;
  }));
});

afterEach(async () => {
  releaseResponse?.();
  cleanup();
  await new Promise(resolve => setTimeout(resolve, 50));
  vi.unstubAllGlobals();
  server.destroy();
});

it('keeps multiple empty added rows through synchronization and metadata updates', async () => {
  const hook = renderHook(() => useCollaborativeHabitKeywords());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  const requestsBeforeAdd = vi.mocked(fetch).mock.calls.length;
  act(() => {
    hook.result.current.addKeyword();
    hook.result.current.addKeyword();
  });
  expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(requestsBeforeAdd);
  const rowIds = hook.result.current.keywords.map(row => row.id);
  expect(new Set(rowIds).size).toBe(2);
  await waitFor(() => expect(hook.result.current.status).toBe('同期済み'));
  expect(hook.result.current.keywords.map(row => row.habitKeywordId)).toEqual([1, 2]);
  act(() => hook.result.current.updateKeyword(rowIds[0], { keyword: '読書' }));
  await waitFor(() => expect(hook.result.current.keywords[0].habitKeywordId).toBe(1));
  expect(hook.result.current.keywords.map(row => row.id)).toEqual(rowIds);
  expect(hook.result.current.keywords[1].keyword).toBe('');
  expect(nextId).toBe(3);
});

it('keeps focus, the latest input and blank rows when an older create response arrives', async () => {
  render(<Habit />);
  const add = screen.getByRole('button', { name: '+' });
  await waitFor(() => expect((add as HTMLButtonElement).disabled).toBe(false));
  holdNextResponse = true;
  fireEvent.click(add);
  const input = screen.getByRole('textbox', { name: 'キーワード' }) as HTMLInputElement;
  input.focus();
  fireEvent.change(input, { target: { value: '読' } });
  await waitFor(() => expect(releaseResponse).toBeDefined());
  fireEvent.change(input, { target: { value: '読書😀' } });
  fireEvent.click(add);
  await act(async () => releaseResponse!());
  await waitFor(() => expect(
    Array.from(server.getMap<Y.Map<unknown>>('habits').values())
      .some(row => row.get('keyword') === '読書😀'),
  ).toBe(true));
  expect(screen.queryByRole('status')).toBeNull();
  expect(screen.getAllByRole('textbox')).toHaveLength(2);
  expect(screen.getAllByRole('textbox')[0]).toBe(input);
  expect(input.value).toBe('読書😀');
  expect(document.activeElement).toBe(input);
  expect(ids.size).toBe(2);
  expect(nextId).toBe(3);
});

it('preserves IDs for duplicate keywords, renames and clearing a saved keyword', async () => {
  const hook = renderHook(() => useCollaborativeHabitKeywords());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  act(() => { hook.result.current.addKeyword(); hook.result.current.addKeyword(); });
  const [a, b] = hook.result.current.keywords.map(row => row.id);
  act(() => {
    hook.result.current.updateKeyword(a, { keyword: '読書' });
    hook.result.current.updateKeyword(b, { keyword: '読書' });
  });
  await waitFor(() => expect(hook.result.current.status).toBe('同期済み'));
  const databaseIds = hook.result.current.keywords.map(row => row.habitKeywordId);
  expect(new Set(databaseIds).size).toBe(2);
  expect(databaseIds).not.toContain(null);
  act(() => hook.result.current.updateKeyword(a, { keyword: '' }));
  await waitFor(() => expect(hook.result.current.status).toBe('同期済み'));
  expect(hook.result.current.keywords.map(row => row.habitKeywordId)).toEqual(databaseIds);
  act(() => hook.result.current.updateKeyword(a, { keyword: '運動' }));
  await waitFor(() => expect(hook.result.current.status).toBe('同期済み'));
  expect(hook.result.current.keywords.map(row => row.habitKeywordId)).toEqual(databaseIds);
});

it('restores offline drafts and edits from IndexedDB and assigns IDs once on retry', async () => {
  const first = renderHook(() => useCollaborativeHabitKeywords());
  await waitFor(() => expect(first.result.current.loading).toBe(false));
  offline = true;
  act(() => { first.result.current.addKeyword(); first.result.current.addKeyword(); });
  const rowIds = first.result.current.keywords.map(row => row.id);
  act(() => first.result.current.updateKeyword(rowIds[0], { keyword: '読書' }));
  await waitFor(() => expect(first.result.current.status).toContain('再試行'));
  first.unmount();
  await new Promise(resolve => setTimeout(resolve, 50));
  const next = renderHook(() => useCollaborativeHabitKeywords());
  await waitFor(() => expect(next.result.current.keywords.map(row => row.id)).toEqual(rowIds));
  expect(next.result.current.keywords.map(row => row.keyword)).toEqual(['読書', '']);
  offline = false;
  act(() => window.dispatchEvent(new Event('online')));
  await waitFor(() => expect(next.result.current.status).toBe('同期済み'));
  expect(next.result.current.keywords.map(row => row.id)).toEqual(rowIds);
  expect(nextId).toBe(3);
});

it('merges another device adding a row while the local row is edited', async () => {
  const hook = renderHook(() => useCollaborativeHabitKeywords());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  act(() => hook.result.current.addKeyword());
  const id = hook.result.current.keywords[0].id;
  act(() => hook.result.current.updateKeyword(id, { keyword: '読書' }));
  await waitFor(() => expect(hook.result.current.status).toBe('同期済み'));
  const phone = new Y.Doc();
  Y.applyUpdate(phone, Y.encodeStateAsUpdate(server));
  phone.getMap('habits').set('phone', new Y.Map<unknown>([
    ['keyword', '運動'], ['isPublic', false], ['order', 2],
  ]));
  Y.applyUpdate(server, Y.encodeStateAsUpdate(phone));
  act(() => hook.result.current.updateKeyword(id, { isPublic: true }));
  await waitFor(() => expect(hook.result.current.keywords).toHaveLength(2));
  expect(hook.result.current.keywords[0]).toMatchObject({ id, keyword: '読書', isPublic: true });
  expect(hook.result.current.keywords[1].keyword).toBe('運動');
  phone.destroy();
});

it('does not resurrect a deleted row after a delayed create response', async () => {
  const hook = renderHook(() => useCollaborativeHabitKeywords());
  await waitFor(() => expect(hook.result.current.loading).toBe(false));
  holdNextResponse = true;
  act(() => hook.result.current.addKeyword());
  const id = hook.result.current.keywords[0].id;
  act(() => hook.result.current.updateKeyword(id, { keyword: '読書' }));
  await waitFor(() => expect(releaseResponse).toBeDefined());
  act(() => hook.result.current.deleteKeyword(id));
  await act(async () => releaseResponse!());
  await waitFor(() => expect(hook.result.current.status).toBe('同期済み'));
  expect(hook.result.current.keywords).toEqual([]);
  expect(server.getMap('habits').size).toBe(0);
});
