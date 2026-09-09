// Used by backend/test_sync.py to verify the real Yjs/pycrdt wire format.
import * as Y from 'yjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input);
const doc = new Y.Doc();
Y.applyUpdate(doc, Buffer.from(request.update, 'base64'));
const text = doc.getText('text');
if (request.append) text.insert(text.length, request.append);
process.stdout.write(JSON.stringify({ text: text.toString(), update: Buffer.from(Y.encodeStateAsUpdate(doc)).toString('base64') }));
