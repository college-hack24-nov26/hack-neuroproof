#!/usr/bin/env node
/* Build an explicitly development-only Groth16 artifact set outside Git. */

import crypto from "node:crypto";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "circuits", "quantized_update_chunk_v1.circom");
const circuitVersion = "quantized-update-chunk-v1";
const publicSignalNames = [
  "round_context",
  "model_context",
  "artifact_context",
  "chunk_index",
  "chunk_count",
  "chunk_commitment",
  "binding_commitment",
];

function requiredOutputDirectory() {
  const argumentsList = process.argv.slice(2);
  if (argumentsList.length !== 2 || argumentsList[0] !== "--output") {
    throw new Error("usage: build-dev-artifacts.mjs --output ABSOLUTE_DIRECTORY");
  }
  const output = path.resolve(argumentsList[1]);
  if (!path.isAbsolute(output)) throw new Error("output directory must be absolute");
  return output;
}

function executable(environmentName, bundledName, fallback) {
  const configured = process.env[environmentName];
  if (configured) return configured;
  const bundled = path.join(root, "node_modules", ".bin", bundledName);
  return fs.existsSync(bundled) ? bundled : fallback;
}

function run(command, argumentsList) {
  execFileSync(command, argumentsList, { stdio: "inherit", env: process.env });
}

function capture(command, argumentsList) {
  return execFileSync(command, argumentsList, { encoding: "utf8", env: process.env });
}

function digest(filePath) {
  return crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function entropy() {
  return crypto.randomBytes(32).toString("hex");
}

function main() {
  process.umask(0o077);
  const output = requiredOutputDirectory();
  if (fs.existsSync(output) && fs.readdirSync(output).length !== 0) {
    throw new Error("refusing to overwrite an existing artifact directory");
  }
  fs.mkdirSync(output, { recursive: true, mode: 0o700 });
  const snarkjs = executable("CEREBRACHAIN_SNARKJS_BIN", "snarkjs", "snarkjs");
  const circom = executable("CEREBRACHAIN_CIRCOM_BIN", "circom", "circom");
  const circomlib = process.env.CEREBRACHAIN_CIRCOMLIB_DIR
    ? path.resolve(process.env.CEREBRACHAIN_CIRCOMLIB_DIR)
    : path.join(root, "node_modules", "circomlib", "circuits");
  const r1cs = path.join(output, "quantized_update_chunk_v1.r1cs");
  const wasmDirectory = path.join(output, "quantized_update_chunk_v1_js");
  const wasm = path.join(wasmDirectory, "quantized_update_chunk_v1.wasm");
  const ptau0 = path.join(output, "powersoftau_0000.ptau");
  const ptau1 = path.join(output, "powersoftau_0001.ptau");
  const ptauFinal = path.join(output, "powersoftau_final.ptau");
  const zkey0 = path.join(output, "quantized_update_chunk_v1_0000.zkey");
  const zkey = path.join(output, "quantized_update_chunk_v1_final.zkey");
  const verificationKey = path.join(output, "verification_key.json");

  run(circom, [source, "--r1cs", "--wasm", "--sym", "--O1", "-l", circomlib, "-o", output]);
  run(snarkjs, ["powersoftau", "new", "bn128", "12", ptau0]);
  run(snarkjs, [
    "powersoftau",
    "contribute",
    ptau0,
    ptau1,
    "--name=V2-development-contribution",
    `-e=${entropy()}`,
  ]);
  run(snarkjs, ["powersoftau", "prepare", "phase2", ptau1, ptauFinal]);
  run(snarkjs, ["groth16", "setup", r1cs, ptauFinal, zkey0]);
  run(snarkjs, [
    "zkey",
    "contribute",
    zkey0,
    zkey,
    "--name=V2-development-contribution",
    `-e=${entropy()}`,
  ]);
  run(snarkjs, ["zkey", "export", "verificationkey", zkey, verificationKey]);
  run(snarkjs, ["zkey", "verify", r1cs, ptauFinal, zkey]);
  const info = capture(snarkjs, ["r1cs", "info", r1cs]);
  const constraints = Number(/# of Constraints:\s+(\d+)/.exec(info)?.[1]);
  if (!Number.isSafeInteger(constraints) || constraints <= 0) {
    throw new Error("could not determine circuit constraint count");
  }
  const manifest = {
    circuit_version: circuitVersion,
    development_only: true,
    curve: "bn128",
    circom_version: "2.2.2",
    snarkjs_version: "0.7.6",
    constraint_count: constraints,
    quantization: { scale: 16, signed_min: -128, signed_max: 127, chunk_size: 8 },
    public_signal_names: publicSignalNames,
    r1cs_sha256: digest(r1cs),
    wasm_sha256: digest(wasm),
    verification_key_sha256: digest(verificationKey),
    proving_key_sha256: digest(zkey),
    ptau_sha256: digest(ptauFinal),
  };
  fs.writeFileSync(path.join(output, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`, { mode: 0o600 });
  for (const entry of fs.readdirSync(output)) {
    const target = path.join(output, entry);
    if (fs.statSync(target).isFile()) fs.chmodSync(target, 0o600);
  }
  process.stdout.write(`development artifacts created in ${output}\n`);
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.message : "artifact build failed"}\n`);
  process.exitCode = 1;
}
