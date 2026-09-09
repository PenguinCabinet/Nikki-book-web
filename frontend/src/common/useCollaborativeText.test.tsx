// @vitest-environment jsdom
import 'fake-indexeddb/auto';
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as Y from 'yjs';
import { useCollaborativeText } from './useCollaborativeText';
import { editText } from './crdtText';

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));
let server: Y.Doc;
let offline: boolean;
let path: string;
let count = 0;

beforeEach(() => {
    path = `/nikki/test-${++count}`;
    server = new Y.Doc();
    server.getText('text').insert(0, '日記😀\n');
    offline = false;
    vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
        if (url.endsWith('/sync-identity')) return Response.json({ user_id: 1 });
        if (offline) throw new TypeError('offline');
        Y.applyUpdate(server, new Uint8Array(options.body as ArrayBuffer));
        return new Response(new Uint8Array(Y.encodeStateAsUpdate(server)).buffer);
    }));
});

afterEach(async () => {
    cleanup();
    await new Promise(resolve => setTimeout(resolve, 50));
    vi.unstubAllGlobals();
    server.destroy();
});

it('merges stale PC edits with phone edits and reflects remote changes without reloading', async () => {
    const pc = renderHook(() => useCollaborativeText(path));
    await waitFor(() => expect(pc.result.current.loading).toBe(false));
    const phone = new Y.Doc();
    Y.applyUpdate(phone, Y.encodeStateAsUpdate(server));
    editText(phone.getText('text'), 'スマホ\n日記😀\n');
    Y.applyUpdate(server, Y.encodeStateAsUpdate(phone));
    act(() => pc.result.current.setText('日記😀\nPC'));
    await waitFor(() => expect(pc.result.current.text).toBe('スマホ\n日記😀\nPC'));
    expect(server.getText('text').toString()).toBe(pc.result.current.text);
    phone.destroy();
});

it('persists offline edits through unmount and resends them on reconnect', async () => {
    const first = renderHook(() => useCollaborativeText(path));
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    offline = true;
    act(() => first.result.current.setText('日記😃\n保存待ち'));
    await waitFor(() => expect(first.result.current.status).toContain('再試行'));
    first.unmount();
    await new Promise(resolve => setTimeout(resolve, 50));
    const next = renderHook(() => useCollaborativeText(path));
    await waitFor(() => expect(next.result.current.text).toBe('日記😃\n保存待ち'));
    offline = false;
    act(() => window.dispatchEvent(new Event('online')));
    await waitFor(() => expect(next.result.current.status).toBe('同期済み'));
    expect(server.getText('text').toString()).toBe('日記😃\n保存待ち');
});

it('defers remote updates until Japanese composition finishes', async () => {
    const pc = renderHook(() => useCollaborativeText(path));
    await waitFor(() => expect(pc.result.current.loading).toBe(false));
    act(() => pc.result.current.setComposing(true));
    server.getText('text').insert(0, 'スマホ');
    act(() => window.dispatchEvent(new Event('focus')));
    await new Promise(resolve => setTimeout(resolve, 50));
    expect(pc.result.current.text).toBe('日記😀\n');
    act(() => {
        pc.result.current.setText('日記😀\n日本語');
        pc.result.current.setComposing(false);
    });
    await waitFor(() => expect(pc.result.current.text).toBe('スマホ日記😀\n日本語'));
});

it('does not apply a delayed response to a different date', async () => {
    const pc = renderHook(({ date }) => useCollaborativeText(date), { initialProps: { date: path } });
    await waitFor(() => expect(pc.result.current.loading).toBe(false));
    const originalFetch = globalThis.fetch;
    let release: (() => void) | undefined;
    vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
        if (url.endsWith(`${path}/sync`)) await new Promise<void>(resolve => { release = resolve; });
        return originalFetch(url, options);
    }));
    act(() => window.dispatchEvent(new Event('focus')));
    await waitFor(() => expect(release).toBeDefined());
    pc.rerender({ date: `${path}-next` });
    await waitFor(() => expect(pc.result.current.loading).toBe(false));
    await act(async () => { release!(); });
    expect(pc.result.current.text).toBe('日記😀\n');
});
