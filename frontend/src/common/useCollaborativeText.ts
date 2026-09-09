import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as Y from 'yjs';
import { IndexeddbPersistence } from 'y-indexeddb';
import { editText } from './crdtText';

export function useCollaborativeText(path: string) {
    const navigate = useNavigate();
    const [view, setView] = useState({ path: '', text: '', ready: false, status: '読み込み中…' });
    const editor = useRef<{ edit: (value: string) => void; compose: (active: boolean) => void } | null>(null);

    useEffect(() => {
        const doc = new Y.Doc();
        const text = doc.getText('text');
        let persistence: IndexeddbPersistence | undefined;
        let stopped = false;
        let ready = false;
        let busy = false;
        let initializing = false;
        let disposed = false;
        let storageReady = false;
        let userId: number;
        let composing = false;
        let revision = 0;
        let timer: ReturnType<typeof setTimeout> | undefined;
        let status = '読み込み中…';
        const origin = import.meta.env.VITE_BACKEND_ORIGIN ?? '';
        const dispose = async () => {
            if (disposed || busy || initializing) return;
            disposed = true;
            doc.off('update', changed);
            await persistence?.destroy();
            doc.destroy();
        };
        const publish = () => {
            if (!stopped) setView({ path, text: text.toString(), ready, status });
        };
        const schedule = () => {
            if (stopped) return;
            clearTimeout(timer);
            timer = setTimeout(() => void sync(), 400);
        };
        const changed = (_update: Uint8Array, source: unknown) => {
            if (source !== 'server') {
                revision++;
                status = '未同期の変更があります';
                if (ready) schedule();
            }
            publish();
        };
        doc.on('update', changed);
        async function sync() {
            if (disposed || busy || composing || !persistence || !storageReady) return;
            busy = true;
            const sentRevision = revision;
            try {
                const response = await fetch(`${origin}${path}/sync`, {
                    method: 'POST', credentials: 'include',
                    headers: { 'Content-Type': 'application/octet-stream', 'X-Sync-User': String(userId) },
                    body: new Uint8Array(Y.encodeStateAsUpdate(doc)).buffer,
                    signal: AbortSignal.timeout(15000),
                });
                if (response.status === 401 || response.status === 403) {
                    ready = false;
                    if (!stopped) navigate('/login');
                    throw new Error('ログインが必要です');
                }
                if (!response.ok) throw new Error(`同期に失敗しました (${response.status})`);
                const update = new Uint8Array(await response.arrayBuffer());
                // Do not change the textarea underneath an active Japanese IME.
                if (composing) return;
                Y.applyUpdate(doc, update, 'server');
                await persistence.set('initialized', 1);
                ready = true;
                status = revision === sentRevision ? '同期済み' : '未同期の変更があります';
                if (revision !== sentRevision) schedule();
            } catch (error) {
                status = error instanceof Error && error.message === 'ログインが必要です'
                    ? error.message : '同期できません。端末内の変更を保持して再試行します';
            } finally {
                busy = false;
                publish();
                if (stopped) void dispose();
            }
        }
        async function start() {
            if (initializing || stopped) return;
            initializing = true;
            try {
                const response = await fetch(`${origin}/sync-identity`, {
                    credentials: 'include', cache: 'no-store', signal: AbortSignal.timeout(15000),
                });
                if (response.status === 401) {
                    if (!stopped) navigate('/login');
                    return;
                }
                if (!response.ok) throw new Error('identity');
                const identity: { user_id: number } = await response.json();
                userId = identity.user_id;
                if (stopped) return;
                // Never share cached diaries across accounts or backend servers.
                persistence = new IndexeddbPersistence(`nikki-crdt-v1:${origin}:${identity.user_id}:${path}`, doc);
                await persistence.whenSynced;
                if (stopped) return;
                ready = (await persistence.get('initialized')) === 1;
                storageReady = true;
                publish();
                await sync();
            } catch {
                status = '読み込みに失敗しました。接続を確認して再試行してください';
                publish();
            } finally {
                initializing = false;
                if (stopped) void dispose();
            }
        }
        const reconnect = () => {
            if (stopped) return;
            if (persistence) void sync();
            else void start();
        };
        editor.current = {
            edit: value => { if (ready) editText(text, value); },
            compose: active => { composing = active; if (!active) schedule(); },
        };
        void start();
        const interval = setInterval(reconnect, 2000);
        window.addEventListener('online', reconnect);
        window.addEventListener('focus', reconnect);
        document.addEventListener('visibilitychange', reconnect);
        const beforeUnload = (event: BeforeUnloadEvent) => {
            if (status !== '同期済み') event.preventDefault();
        };
        window.addEventListener('beforeunload', beforeUnload);
        return () => {
            stopped = true;
            editor.current = null;
            clearTimeout(timer);
            clearInterval(interval);
            window.removeEventListener('online', reconnect);
            window.removeEventListener('focus', reconnect);
            document.removeEventListener('visibilitychange', reconnect);
            window.removeEventListener('beforeunload', beforeUnload);
            // The IndexedDB update listener has already queued every local edit.
            // A final send is best effort; unsent edits merge on the next visit.
            void sync().finally(() => dispose());
        };
    }, [path, navigate]);

    return {
        text: view.path === path ? view.text : '',
        loading: view.path !== path || !view.ready,
        status: view.path === path ? view.status : '読み込み中…',
        setText: (value: string) => editor.current?.edit(value),
        setComposing: (active: boolean) => editor.current?.compose(active),
    };
}
