import assert from 'node:assert/strict'
import { File } from 'node:buffer'
import { MAX_FILE_BYTES, validateMaterial, selectMaterials, removeMaterial } from '../src/lib/materialSelection.ts'

const valid = new File(['test'], 'lecture.PDF', { type: 'application/pdf' })
assert.equal(validateMaterial(valid), null)
assert.match(validateMaterial(new File(['test'], 'program.exe')), /Choose/)
assert.match(validateMaterial(new File(['test'], 'notes.pdf', { type: 'image/png' })), /do not match/)
assert.match(validateMaterial({ name: 'lecture.pdf', type: 'application/pdf', size: MAX_FILE_BYTES + 1 }), /100 MB/)
const result = selectMaterials([valid, valid])
assert.equal(result.accepted.length, 2)
assert.notEqual(result.accepted[0].id, result.accepted[1].id)
assert.equal(removeMaterial(result.accepted, result.accepted[0].id).length, 1)
assert.equal(result.accepted.length, 2)
console.log('PASS: file selection validation, independent IDs and removal without mutation.')
