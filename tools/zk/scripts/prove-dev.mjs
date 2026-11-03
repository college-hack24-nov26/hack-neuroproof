#!/usr/bin/env node
/*
 * Development-only prover. Its zkey, witness inputs, and output stay outside
 * Git. It proves synthetic or explicitly authorized quantized chunks only.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";

import { buildPoseidon } from "circomlibjs";
import { spawnSync } from "node:child_process";
import os from "node:os";
import { fileURLToPath } from "node:url";

const FIELD_MODULUS = 21888242871839275222246405745257275088548364400416034343698204186575808495617n;
const CHUNK_SIZE = 8;
const REQUIRED_FLAGS = new Set(["--wasm", "--zkey", "--input", "--output"]);

function parseFlags(argumentsList) {
  const values = new Map();
  for (let index = 0; index < argumentsList.length; index += 2) {
    const flag = argumentsList[index];
    const value = argumentsList[index + 1];
    if (!REQUIRED_FLAGS.has(flag) || value === undefined || values.has(flag)) {
      throw new Error("usage: prove-dev.mjs --wasm PATH --zkey PATH --input PATH --output PATH");
    }
    values.set(flag, value);
  }
  if (values.size !== REQUIRED_FLAGS.size) {
    throw new Error("usage: prove-dev.mjs --wasm PATH --zkey PATH --input PATH --output PATH");
  }
  return values;
}

function decimalField(value, name) {
  if (typeof value !== "string" || !/^(0|[1-9][0-9]*)$/.test(value)) {
    throw new Error(`${name} must be a canonical decimal field element`);
  }
  const parsed = BigInt(value);
  if (parsed >= FIELD_MODULUS) throw new Error(`${name} is outside the BN254 scalar field`);
  return parsed;
}

function signedValue(value) {
  if (!Number.isInteger(value) || value < -128 || value > 127) {
    throw new Error("quantized chunk value is outside the signed int8 range");
  }
  return value;
}

function randomSalt() {
  while (true) {
    const candidate = BigInt(`0x${crypto.randomBytes(32).toString("hex")}`);
    if (candidate < FIELD_MODULUS) return candidate;
  }
}

async function main() {
  const flags = parseFlags(process.argv.slice(2));
  const inputPath = path.resolve(flags.get("--input"));
  const outputPath = path.resolve(flags.get("--output"));
  const request = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  if (!request || !Array.isArray(request.chunks) || request.chunks.length === 0 || request.chunks.length > 4096) {
    throw new Error("input chunks are invalid");
  }
  const circuitVersion = request.circuit_version;
  const verificationKeyId = request.verification_key_id;
  if (typeof circuitVersion !== "string" || typeof verificationKeyId !== "string") {
    throw new Error("circuit metadata is invalid");
  }
  const contexts = ["round_context", "model_context", "artifact_context"];
  const contextValues = Object.fromEntries(contexts.map((key) => [key, decimalField(request[key], key)]));
  const salts = request.salts ?? [];
  if (salts.length !== 0 && (!Array.isArray(salts) || salts.length !== request.chunks.length)) {
    throw new Error("salts are invalid");
  }
  const poseidon = await buildPoseidon();
  const proofs = [];
  for (let index = 0; index < request.chunks.length; index += 1) {
    const chunk = request.chunks[index];
    if (!Array.isArray(chunk) || chunk.length !== CHUNK_SIZE) throw new Error("chunk length is invalid");
    const quantized = chunk.map(signedValue);
    const encoded = quantized.map((value) => BigInt(value + 128));
    const chunkCommitment = poseidon(encoded);
    const salt = salts.length ? decimalField(salts[index], "salt") : randomSalt();
    const bindingCommitment = poseidon([
      contextValues.round_context,
      contextValues.model_context,
      contextValues.artifact_context,
      BigInt(index),
      BigInt(request.chunks.length),
      chunkCommitment,
      salt,
    ]);
    const witness = {
      round_context: contextValues.round_context.toString(),
      model_context: contextValues.model_context.toString(),
      artifact_context: contextValues.artifact_context.toString(),
      chunk_index: String(index),
      chunk_count: String(request.chunks.length),
      chunk_commitment: poseidon.F.toString(chunkCommitment),
      binding_commitment: poseidon.F.toString(bindingCommitment),
      q: quantized.map(String),
      salt: salt.toString(),
    };
    // Use bounded snarkjs CLI processes instead of the hanging fullProve API.
    const temporaryDirectory = fs.mkdtempSync(
      path.join(os.tmpdir(), "cerebrachain-groth16-prover-")
    );

    try {
      const witnessInputPath = path.join(temporaryDirectory, "input.json");
      const witnessPath = path.join(temporaryDirectory, "witness.wtns");
      const proofPath = path.join(temporaryDirectory, "proof.json");
      const publicPath = path.join(temporaryDirectory, "public.json");

      fs.writeFileSync(
        witnessInputPath,
        JSON.stringify(witness),
        { mode: 0o600 }
      );

      const snarkjsBinary = path.resolve(
        path.dirname(fileURLToPath(import.meta.url)),
        "../node_modules/.bin/snarkjs"
      );

      const commands = [
        [
          "wtns",
          "calculate",
          path.resolve(flags.get("--wasm")),
          witnessInputPath,
          witnessPath,
        ],
        [
          "groth16",
          "prove",
          path.resolve(flags.get("--zkey")),
          witnessPath,
          proofPath,
          publicPath,
        ],
      ];

      for (const args of commands) {
        const result = spawnSync(snarkjsBinary, args, {
          encoding: "utf8",
          timeout: 30000,
          maxBuffer: 1024 * 1024,
        });

        if (result.error || result.status !== 0) {
          throw new Error(
            `snarkjs ${args[0]} ${args[1]} failed`
          );
        }
      }

      const proof = JSON.parse(fs.readFileSync(proofPath, "utf8"));
      const publicSignals = JSON.parse(
        fs.readFileSync(publicPath, "utf8")
      );

      proofs.push({
        proof,
        public_signals: publicSignals,
      });
    } finally {
      fs.rmSync(temporaryDirectory, {
        recursive: true,
        force: true,
      });
    }
  }
  fs.writeFileSync(
    outputPath,
    JSON.stringify({ circuit_version: circuitVersion, verification_key_id: verificationKeyId, proofs }),
    { mode: 0o600 },
  );
}

main().catch((error) => {
  process.stderr.write("development proof generation failed\n");
  process.exitCode = 1;
});
