#!/usr/bin/env node
/* Compute only public Poseidon chunk commitments for trusted server code. */

import { buildPoseidon } from "circomlibjs";

const CHUNK_SIZE = 8;

function fail(message) {
  process.stderr.write(`${message}\n`);
  process.exitCode = 2;
}

async function readInput() {
  let source = "";
  for await (const part of process.stdin) source += part;
  if (Buffer.byteLength(source, "utf8") > 512 * 1024) throw new Error("input is too large");
  return JSON.parse(source);
}

function encodedValue(value) {
  if (typeof value !== "string" || !/^(0|[1-9][0-9]*)$/.test(value)) {
    throw new Error("encoded chunk value is invalid");
  }
  const parsed = BigInt(value);
  if (parsed > 255n) throw new Error("encoded chunk value is out of range");
  return parsed;
}

async function main() {
  const request = await readInput();
  if (!request || !Array.isArray(request.chunks) || request.chunks.length > 4096) {
    throw new Error("chunks are invalid");
  }
  const poseidon = await buildPoseidon();
  const commitments = request.chunks.map((chunk) => {
    if (!Array.isArray(chunk) || chunk.length !== CHUNK_SIZE) {
      throw new Error("chunk length is invalid");
    }
    return poseidon.F.toString(poseidon(chunk.map(encodedValue)));
  });
  process.stdout.write(JSON.stringify({ commitments }) + "\n");
}

main().catch((error) => fail(error instanceof Error ? error.message : "invalid input"));
