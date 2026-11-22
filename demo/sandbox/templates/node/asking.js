// The asking program of a sandbox copy (JavaScript). Ours, and the same for every library.
//
//     node asking.js <library folder> <asking code folder> verify|info        (JSON on stdin, JSON on stdout)
//
// It reads one question and writes one answer. It holds no cryptography and knows no library: the part that does is
// asking_code.js in the folder named second. That file exports one function, which is handed `load(name)` (it loads a
// package of the copy, and nothing else) and gives back { ownRefusals: [...], checkSignature(publicKey, message,
// signature) }, made of straight-line calls into the library.
//
// How a "no" is reported, as for every wrapper (docs/ADAPTER.md): any error raised while the library checks a signature
// means "not accepted": {"valid": false}. One of the library's own refusals adds no note; any other error adds
// "general error: <ClassName>". Only the library's own true counts as accepted. The right answers are never given to
// this program. What the copy says it is was read from the package's own package.json when the copy was made.
'use strict';
const fs = require('fs');
const path = require('path');

const COMMANDS = ['verify', 'info'];
const USAGE = 'usage: asking.js <library folder> <asking code folder> ' + COMMANDS.join('|') + '  (JSON on stdin, JSON on stdout)';

function cmdInfo(libraryDir) {
  const says = JSON.parse(fs.readFileSync(libraryDir.replace(/\/+$/, '') + '.says.json', 'utf8'));
  return { name: String(says.name), version: String(says.version), algorithm: 'ECDSA P-256', hash: 'SHA-256', signature_format: 'DER',
    public_key_format: 'uncompressed point, hex (04 || X || Y)', commands: COMMANDS,
    library: `${says.package} ${says.version} on Node ${process.version}` };
}

function hex(text) {
  if (typeof text !== 'string' || text.length % 2 !== 0 || !/^[0-9a-fA-F]*$/.test(text)) throw new Error('bad hex');
  return Buffer.from(text, 'hex');
}

function cmdVerify(libraryDir, codeDir, req) {
  const point = hex(req.public_key);
  const message = hex(req.message);
  const signature = hex(req.signature);
  if (point.length !== 65 || point[0] !== 4) return { valid: false, note: 'not an uncompressed P-256 point' };
  const modules = path.join(libraryDir, 'node_modules');
  const load = (name) => {
    if (typeof name !== 'string' || !/^(@[a-z0-9][a-z0-9._-]*\/)?[A-Za-z0-9][A-Za-z0-9._-]*$/.test(name)) throw new Error('not a package name');
    return require(path.join(modules, name));
  };
  let asking;
  try {
    asking = require(path.join(codeDir, 'asking_code.js'))(load);
  } catch (e) {
    return { error: 'the asking code could not be loaded: ' + (e && e.constructor ? e.constructor.name : 'Error') };
  }
  const own = Array.isArray(asking.ownRefusals) ? asking.ownRefusals : [];
  try {
    return { valid: asking.checkSignature(point, message, signature) === true };
  } catch (e) {
    const name = e && e.constructor ? e.constructor.name : 'Error';
    if (own.some((refusal) => (typeof refusal === 'function' ? e instanceof refusal && e.constructor === refusal : name === refusal))) return { valid: false };
    return { valid: false, note: 'general error: ' + name };
  }
}

function main(argv) {
  if (argv.length !== 5 || !COMMANDS.includes(argv[4])) {
    console.log(JSON.stringify({ error: USAGE }));
    return 2;
  }
  let out;
  try {
    const text = fs.readFileSync(0, 'utf8');
    const req = text.trim() ? JSON.parse(text) : {};
    if (req === null || typeof req !== 'object' || Array.isArray(req)) throw new Error('input must be a JSON object');
    out = argv[4] === 'info' ? cmdInfo(argv[2]) : cmdVerify(argv[2], argv[3], req);
  } catch (e) {
    console.log(JSON.stringify({ error: 'bad input: ' + (e && e.constructor ? e.constructor.name : 'Error') }));
    return 1;
  }
  console.log(JSON.stringify(out));
  return 0;
}

process.exitCode = main(process.argv);
