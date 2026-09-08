import * as Y from 'yjs';

// Change only the edited range, keeping CRDT identities of unchanged text.
export function editText(text: Y.Text, value: string) {
    const before = Array.from(text.toString());
    const after = Array.from(value);
    let start = 0;
    while (start < Math.min(before.length, after.length) && before[start] === after[start]) start++;
    let end = 0;
    while (end < Math.min(before.length, after.length) - start && before[before.length - end - 1] === after[after.length - end - 1]) end++;
    const offset = before.slice(0, start).join('').length;
    const removed = before.slice(start, before.length - end).join('').length;
    const inserted = after.slice(start, after.length - end).join('');
    text.doc!.transact(() => {
        if (removed) text.delete(offset, removed);
        if (inserted) text.insert(offset, inserted);
    }, 'local');
}
