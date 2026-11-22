// Adapter wrapper for elliptic (npm). The library folder (the first argument) holds its node_modules tree.
//
// It only translates the adapter's JSON to elliptic's own calls and back. Keys and signatures are made and checked
// by elliptic (curve p256, DER signatures); the SHA-256 is hash.js, elliptic's own dependency (elliptic does not
// hash). There is no crypto of our own here, and Node's built-in crypto is not used.
//
//     node elliptic_adapter.js <library folder> [--slow] keygen|sign|verify|info|bench   (JSON on stdin, JSON on stdout)
//
// How a "no" is reported: any error the library raises while checking a signature means "not accepted":
// {"valid": false}. Elliptic's own plain Error ("Signature without r or s") adds no note; TypeError, RangeError
// and ReferenceError add "general error: <ClassName>". --slow is the speed test's control: it adds 6 ms to each
// timed step of bench.
'use strict';
const fs = require('fs');
const path = require('path');

const folder = process.argv[2] || '.';
const modules = path.join(folder, 'node_modules');
const load = (name) => require(path.join(modules, name));
const elliptic = load('elliptic');
const hash = load('hash.js');
const ec = new elliptic.ec('p256');
const COMMANDS = ['keygen', 'sign', 'verify', 'info', 'bench'];
const USAGE = 'usage: elliptic_adapter.js <library folder> [--slow] ' + COMMANDS.join('|') + '  (JSON on stdin, JSON on stdout)';
const SLOW_MS = 6.0;

class BadInput extends Error {}

function hex(text) {
  if (typeof text !== 'string' || text.length % 2 !== 0 || !/^[0-9a-fA-F]*$/.test(text)) throw new BadInput('bad hex');
  return text;
}
const field = (req, name) => hex(req[name]);
const digest = (messageHex) => hash.sha256().update(Array.from(Buffer.from(messageHex, 'hex'))).digest();

function cmdInfo() {
  const version = JSON.parse(fs.readFileSync(path.join(modules, 'elliptic', 'package.json'), 'utf8')).version;
  return { name: 'elliptic', version, algorithm: 'ECDSA P-256', hash: 'SHA-256', signature_format: 'DER',
    public_key_format: 'uncompressed point, hex (04 || X || Y)', commands: COMMANDS,
    library: `elliptic ${version} on Node ${process.version}` };
}

function cmdKeygen(req) {
  const algorithm = (req && typeof req.algorithm === 'string') ? req.algorithm : 'ECDSA P-256';
  if (algorithm !== 'ECDSA P-256') {
    // Phase 4d: asked for another algorithm, answer from the library's own list of the curves it offers.
    const offered = Object.keys(elliptic.curves).sort();
    if (!offered.includes(algorithm)) {
      return { refused: true, note: "not in the library's own list of curves: " + offered.join(', ') };
    }
    return { error: 'bad input: this wrapper only makes ECDSA P-256 keys' };
  }
  const pair = ec.genKeyPair();
  return { private_key: pair.getPrivate('hex').padStart(64, '0'), public_key: pair.getPublic('hex') };
}

function cmdSign(req) {
  const key = ec.keyFromPrivate(field(req, 'private_key'), 'hex');
  return { signature: key.sign(digest(field(req, 'message'))).toDER('hex') };
}

function cmdVerify(req) {
  const publicHex = field(req, 'public_key'), message = field(req, 'message'), signature = field(req, 'signature');
  let key;
  try {
    key = ec.keyFromPublic(publicHex, 'hex');
    if (!key.validate().result) throw new Error('not a point on the curve');
  } catch (e) {
    return { valid: false, note: 'the library refused the public key' };
  }
  try {
    return { valid: key.verify(digest(message), signature) === true };
  } catch (e) {
    if (e instanceof TypeError || e instanceof RangeError || e instanceof ReferenceError) {
      return { valid: false, note: 'general error: ' + e.constructor.name };
    }
    return { valid: false };  // elliptic's own assert: a plain Error
  }
}

function wait(ms) {
  const end = process.hrtime.bigint() + BigInt(Math.round(ms * 1e6));
  while (process.hrtime.bigint() < end) { /* busy-wait: steadier than a timer for a few milliseconds */ }
}

function cmdBench(req, slow) {
  const repeats = req.repeats === undefined ? 100 : req.repeats;
  if (!Number.isInteger(repeats) || repeats < 1 || repeats > 1000) throw new BadInput('repeats');
  const message = digest(field({ message: req.message === undefined ? '' : req.message }, 'message'));
  const pair = req.private_key ? ec.keyFromPrivate(field(req, 'private_key'), 'hex') : ec.genKeyPair();
  const sign = () => pair.sign(message).toDER('hex');
  for (let i = 0; i < 2; i++) pair.verify(message, sign());  // warm-up, not timed
  const signMs = [], verifyMs = [];
  let allVerified = true, signature = '';
  const ms = (a, b) => Math.round(Number(b - a) / 100) / 10000;
  for (let i = 0; i < repeats; i++) {
    const t0 = process.hrtime.bigint();
    if (slow) wait(SLOW_MS);
    signature = sign();
    const t1 = process.hrtime.bigint();
    if (slow) wait(SLOW_MS);
    const ok = pair.verify(message, signature);
    const t2 = process.hrtime.bigint();
    allVerified = allVerified && ok === true;
    signMs.push(ms(t0, t1));
    verifyMs.push(ms(t1, t2));
  }
  return { repeats, warmups: 2, clock: 'process.hrtime.bigint', sign_ms: signMs, verify_ms: verifyMs,
    signature_bytes: signature.length / 2, public_key_bytes: 65, all_verified: allVerified };
}

const HANDLERS = { info: cmdInfo, keygen: cmdKeygen, sign: cmdSign, verify: cmdVerify };

function main() {
  let words = process.argv.slice(3);
  const slow = words[0] === '--slow';
  if (slow) words = words.slice(1);
  if (words.length !== 1 || !COMMANDS.includes(words[0])) {
    console.log(JSON.stringify({ error: USAGE }));
    return 2;
  }
  let out;
  try {
    const text = fs.readFileSync(0, 'utf8');
    const req = text.trim() ? JSON.parse(text) : {};
    if (req === null || typeof req !== 'object' || Array.isArray(req)) throw new BadInput('input must be a JSON object');
    out = words[0] === 'bench' ? cmdBench(req, slow) : HANDLERS[words[0]](req);
  } catch (e) {
    // Never repeat the input here: it may hold a test private key.
    console.log(JSON.stringify({ error: 'bad input: ' + e.constructor.name }));
    return 1;
  }
  console.log(JSON.stringify(out));
  return 0;
}

process.exitCode = main();
