"use strict";

const fs = require("node:fs");
const path = require("node:path");
const solc = require("solc");

const packageRoot = path.resolve(__dirname, "..");
const sourceName = "NeuroProofReceiptAnchor.sol";
const sourcePath = path.join(packageRoot, "contracts", sourceName);

function compileAnchor() {
  const input = {
    language: "Solidity",
    sources: {
      [sourceName]: { content: fs.readFileSync(sourcePath, "utf8") },
    },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": { "*": ["abi", "evm.bytecode.object"] },
      },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((entry) => entry.severity === "error");
  if (errors.length > 0) {
    throw new Error(errors.map((entry) => entry.formattedMessage).join("\n"));
  }

  const contract = output.contracts?.[sourceName]?.NeuroProofReceiptAnchor;
  if (!contract?.evm?.bytecode?.object) {
    throw new Error("NeuroProofReceiptAnchor compilation produced no bytecode.");
  }

  return {
    abi: contract.abi,
    bytecode: `0x${contract.evm.bytecode.object}`,
    compilerVersion: solc.version(),
  };
}

if (require.main === module) {
  const compiled = compileAnchor();
  process.stdout.write(
    `NeuroProofReceiptAnchor compiled with solc ${compiled.compilerVersion}\n`,
  );
}

module.exports = { compileAnchor };
