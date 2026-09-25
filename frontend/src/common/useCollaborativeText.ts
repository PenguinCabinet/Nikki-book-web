import type { Doc } from 'yjs';
import { editText } from './crdtText';
import { useCollaborativeDocument } from './useCollaborativeDocument';

const readText = (doc: Doc) => doc.getText('text').toString();

export function useCollaborativeText(path: string) {
    const sync = useCollaborativeDocument(path, readText, '');
    return {
        text: sync.value,
        loading: sync.loading,
        status: sync.status,
        setText: (value: string) => sync.change(doc => editText(doc.getText('text'), value)),
        setComposing: sync.setComposing,
    };
}
