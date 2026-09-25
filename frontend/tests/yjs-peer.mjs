// Used by backend/test_sync.py to verify the real Yjs/pycrdt wire format.
import * as Y from 'yjs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input);
const doc = new Y.Doc();
Y.applyUpdate(doc, Buffer.from(request.update, 'base64'));
const text = doc.getText('text');
if (request.append) text.insert(text.length, request.append);
if (request.habitKey) doc.getMap('habits').get(request.habitKey).set('keyword', request.keyword);
process.stdout.write(JSON.stringify({
  text: text.toString(),
  habits: doc.getMap('habits').toJSON(),
  habitMetadata: doc.getMap('habitMetadata').toJSON(),
  update: Buffer.from(Y.encodeStateAsUpdate(doc)).toString('base64'),
}));
