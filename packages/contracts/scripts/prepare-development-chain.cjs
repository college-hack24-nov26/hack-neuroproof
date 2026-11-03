"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { Wallet } = require("ethers");

function requiredStateDirectory() {
  const index = process.argv.indexOf("--state-dir");
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value || !path.isAbsolute(value)) {
    throw new Error("An absolute --state-dir outside the repository is required.");
  }
  return path.resolve(value);
}

function writeNewFile(target, content, mode) {
  const descriptor = fs.openSync(target, "wx", mode);
  try {
    fs.writeFileSync(descriptor, content, { encoding: "utf8" });
  } finally {
    fs.closeSync(descriptor);
  }
  fs.chmodSync(target, mode);
}

function main() {
  const stateDirectory = requiredStateDirectory();
  const parentDirectory = path.dirname(stateDirectory);
  if (!fs.existsSync(parentDirectory)) {
    throw new Error("The approved parent state directory does not exist.");
  }
  if (fs.existsSync(stateDirectory)) {
    throw new Error("Refusing to reuse or overwrite an existing development-chain state directory.");
  }

  fs.mkdirSync(stateDirectory, { mode: 0o700 });
  fs.chmodSync(stateDirectory, 0o700);
  const wallet = Wallet.createRandom();
  const mnemonic = wallet.mnemonic?.phrase;
  if (!mnemonic) throw new Error("Could not create development-only mnemonic material.");

  try {
    writeNewFile(path.join(stateDirectory, "mnemonic"), `${mnemonic}\n`, 0o600);
    writeNewFile(
      path.join(stateDirectory, "receipt-replay.json"),
      `${JSON.stringify({ version: 1, receipts: [] }, null, 2)}\n`,
      0o600,
    );
    writeNewFile(
      path.join(stateDirectory, "recovery-plan.json"),
      `${JSON.stringify({
        version: 1,
        strategy: "deterministic_replay",
        chainId: 31337,
        rpcBinding: "127.0.0.1:18545",
        deploymentMetadata: "deployment.json",
        receiptReplayManifest: "receipt-replay.json",
        limitations: [
          "Hardhat node state is memory-only and is not durable across process restarts.",
          "Replay must use the same protected mnemonic and an empty owner nonce before deployment.",
          "Transaction hashes and block numbers may differ after recovery.",
        ],
      }, null, 2)}\n`,
      0o600,
    );
  } catch (error) {
    throw new Error("Development-chain account preparation did not complete safely.", { cause: error });
  }

  process.stdout.write("Protected development-chain account material prepared.\n");
}

try {
  main();
} catch (error) {
  process.stderr.write(`Development-chain preparation failed: ${error.message}\n`);
  process.exitCode = 1;
}
