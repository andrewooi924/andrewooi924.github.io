import {test} from 'node:test';
import assert from 'node:assert/strict';
// @ts-expect-error Browser module is deliberately dependency-free JavaScript.
import {collectionHistory} from '../../cloud/valuation.js';
test('historical holdings never count a missing card price as zero',()=>{
 const values=collectionHistory([{id:'a',quantity:2},{id:'b',quantity:1}],{a:[['2026-09-16',100],['2026-09-17',120]],b:[['2026-09-17',50]]});
 assert.equal(values[0].complete,false);assert.equal(values[1].complete,true);assert.equal(values[1].value,290);
});
test('history rejects invalid or negative observations',()=>{
 assert.deepEqual(collectionHistory([{id:'a'}],{a:[['garbage',2],['2026-09-17',-3]]}),[]);
});
