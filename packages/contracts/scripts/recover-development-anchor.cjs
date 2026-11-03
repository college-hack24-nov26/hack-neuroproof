"use strict";

/**
 * Read-only recovery for a deployment that succeeded before its metadata write.
 * It sends no transactions and refuses ambiguity rather than guessing an address.
 */
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const solc = require("solc");
const { ethers } = require("ethers");

const ABI_VERSION = "neuroproof-receipt-anchor-v1";
const EXPECTED_CHAIN_ID = 31337;
const APPROVED_RPC_URL = "http://127.0.0.1:18545";
const RECEIPT_DOMAIN = "cerebrachain-v2:proof-receipt-anchor:v1";
const DERIVATION_ROOT = "m/44'/60'/0'/0/";
const packageRoot = path.resolve(__dirname, "..");
const sourcePath = path.join(packageRoot, "contracts", "NeuroProofReceiptAnchor.sol");

function requiredArgument(name) {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

function requiredStateDirectory() {
  const value = requiredArgument("--state-dir");
  if (!path.isAbsolute(value)) throw new Error("--state-dir must be absolute.");
  return path.resolve(value);
}

function sha256Hex(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function assertSecretFile(secretPath) {
  const stat = fs.statSync(secretPath);
  if (!stat.isFile() || (stat.mode & 0o077) !== 0) {
    throw new Error("The development mnemonic must be a regular file with 0600 permissions.");
  }
}

function compileAnchorWithRuntime() {
  const source = fs.readFileSync(sourcePath, "utf8");
  const input = {
    language: "Solidity",
    sources: { "NeuroProofReceiptAnchor.sol": { content: source } },
    settings: {
      optimizer: { enabled: true, runs: 200 },
      outputSelection: {
        "*": { "*": ["abi", "evm.bytecode.object", "evm.deployedBytecode.object"] },
      },
    },
  };
  const output = JSON.parse(solc.compile(JSON.stringify(input)));
  const errors = (output.errors || []).filter((entry) => entry.severity === "error");
  if (errors.length > 0) throw new Error(errors.map((entry) => entry.formattedMessage).join("\n"));

  const contract = output.contracts?.["NeuroProofReceiptAnchor.sol"]?.NeuroProofReceiptAnchor;
  const creation = contract?.evm?.bytecode?.object;
  const runtime = contract?.evm?.deployedBytecode?.object;
  if (!contract?.abi || !creation || !runtime) {
    throw new Error("Compilation did not produce the required V2 ABI and bytecode.");
  }
  return {
    abi: contract.abi,
    creationBytecode: `0x${creation}`,
    runtimeBytecode: `0x${runtime}`,
    compilerVersion: solc.version(),
    source,
  };
}

function packageVersion(packageName) {
  let directory = path.dirname(require.resolve(packageName));
  while (directory !== path.dirname(directory)) {
    const candidate = path.join(directory, "package.json");
    if (fs.existsSync(candidate)) {
      const metadata = JSON.parse(fs.readFileSync(candidate, "utf8"));
      if (metadata.name === packageName) return metadata.version;
    }
    directory = path.dirname(directory);
  }
  throw new Error(`Could not determine ${packageName} version.`);
}

function writeRecoveredMetadata(stateDirectory, metadata) {
  const target = path.join(stateDirectory, "deployment.json");
  if (fs.existsSync(target)) throw new Error("Refusing to overwrite existing deployment metadata.");
  const descriptor = fs.openSync(target, "wx", 0o600);
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify(metadata, null, 2)}\n`, "utf8");
  } finally {
    fs.closeSync(descriptor);
  }
  fs.chmodSync(target, 0o600);
}

function deriveDevelopmentAddresses(stateDirectory) {
  const mnemonicPath = path.join(stateDirectory, "mnemonic");
  assertSecretFile(mnemonicPath);
  const phrase = fs.readFileSync(mnemonicPath, "utf8").trim();
  if (!phrase) throw new Error("Development mnemonic file is empty.");
  const owner = ethers.HDNodeWallet.fromPhrase(phrase, undefined, `${DERIVATION_ROOT}0`).address;
  const anchorer = ethers.HDNodeWallet.fromPhrase(phrase, undefined, `${DERIVATION_ROOT}1`).address;
  if (owner.toLowerCase() === anchorer.toLowerCase()) {
    throw new Error("Development owner and anchoring addresses must be distinct.");
  }
  return { owner, anchorer };
}

async function allCreationTransactions(provider, latestBlock) {
  const creations = [];
  for (let blockNumber = 0; blockNumber <= latestBlock; blockNumber += 1) {
    const block = await provider.send("eth_getBlockByNumber", [ethers.toQuantity(blockNumber), true]);
    if (!block) throw new Error(`Block ${blockNumber} could not be read.`);
    for (const transaction of block.transactions || []) {
      if (transaction.to !== null) continue;
      const receipt = await provider.send("eth_getTransactionReceipt", [transaction.hash]);
      if (!receipt) throw new Error(`Creation transaction ${transaction.hash} has no receipt.`);
      if (receipt.status === "0x1" && receipt.contractAddress) {
        creations.push({ transaction, receipt });
      }
    }
  }
  return creations;
}

async function transactionsToAddress(provider, latestBlock, address) {
  const matches = [];
  for (let blockNumber = 0; blockNumber <= latestBlock; blockNumber += 1) {
    const block = await provider.send("eth_getBlockByNumber", [ethers.toQuantity(blockNumber), true]);
    if (!block) throw new Error(`Block ${blockNumber} could not be read.`);
    for (const transaction of block.transactions || []) {
      if (transaction.to?.toLowerCase() === address.toLowerCase()) matches.push(transaction);
    }
  }
  return matches;
}

async function main() {
  const rpcUrl = requiredArgument("--rpc-url");
  if (rpcUrl !== APPROVED_RPC_URL) throw new Error("Only the approved loopback development RPC URL is permitted.");
  const stateDirectory = requiredStateDirectory();
  const replayManifest = path.join(stateDirectory, "receipt-replay.json");
  if (!fs.existsSync(replayManifest)) throw new Error("Approved replay metadata is missing.");
  if (fs.existsSync(path.join(stateDirectory, "deployment.json"))) {
    throw new Error("Deployment metadata already exists; recovery is not needed.");
  }

  const provider = new ethers.JsonRpcProvider(
    rpcUrl,
    { chainId: EXPECTED_CHAIN_ID, name: "hardhat" },
    { staticNetwork: true },
  );
  const chainId = Number((await provider.getNetwork()).chainId);
  if (chainId !== EXPECTED_CHAIN_ID) throw new Error("Unexpected development chain ID.");
  const latestBlock = await provider.getBlockNumber();
  const { owner: expectedOwner, anchorer: expectedAnchorer } = deriveDevelopmentAddresses(stateDirectory);
  const compiled = compileAnchorWithRuntime();

  const creations = await allCreationTransactions(provider, latestBlock);
  if (creations.length !== 1) {
    throw new Error(`Expected exactly one successful contract-creation transaction, found ${creations.length}.`);
  }
  const { transaction, receipt } = creations[0];
  const contractAddress = ethers.getAddress(receipt.contractAddress);
  const encodedConstructor = ethers.AbiCoder.defaultAbiCoder().encode(["address"], [expectedAnchorer]).slice(2);
  const expectedDeploymentInput = `${compiled.creationBytecode}${encodedConstructor}`.toLowerCase();
  const transactionInput = String(transaction.input ?? transaction.data ?? "").toLowerCase();
  if (transaction.from?.toLowerCase() !== expectedOwner.toLowerCase()) {
    throw new Error("Creation transaction sender does not match development account 0.");
  }
  if (transactionInput !== expectedDeploymentInput) {
    throw new Error("Creation transaction bytecode or constructor arguments do not match the V2 contract.");
  }

  const runtimeCode = await provider.getCode(contractAddress);
  if (runtimeCode === "0x") throw new Error("Recovered address has no runtime bytecode.");
  if (runtimeCode.toLowerCase() !== compiled.runtimeBytecode.toLowerCase()) {
    throw new Error("Deployed runtime bytecode does not exactly match the compiled V2 contract.");
  }
  const runtimeCodeSha256 = sha256Hex(Buffer.from(runtimeCode.slice(2), "hex"));

  const contract = new ethers.Contract(contractAddress, compiled.abi, provider);
  const [owner, anchorerAuthorized, receiptDomain, emptyReceiptExists] = await Promise.all([
    contract.owner(),
    contract.isAnchoringAccount(expectedAnchorer),
    contract.RECEIPT_DOMAIN(),
    contract.receiptExists(ethers.ZeroHash),
  ]);
  if (owner.toLowerCase() !== expectedOwner.toLowerCase()) {
    throw new Error("Recovered contract owner does not match development account 0.");
  }
  if (!anchorerAuthorized) throw new Error("Development account 1 is not authorized to anchor receipts.");
  if (receiptDomain.toLowerCase() !== ethers.keccak256(ethers.toUtf8Bytes(RECEIPT_DOMAIN)).toLowerCase()) {
    throw new Error("Recovered contract has an incompatible receipt domain.");
  }
  if (emptyReceiptExists) throw new Error("Unexpected zero receipt state was found.");

  const callsToContract = await transactionsToAddress(provider, latestBlock, contractAddress);
  if (callsToContract.length !== 0) {
    throw new Error(`Found ${callsToContract.length} unexpected state-changing transaction(s) to the recovered contract.`);
  }

  const metadata = {
    version: 1,
    recoveryVerificationStatus: "verified-from-read-only-chain-inspection",
    environment: "localhost-development-only",
    recoveredAt: new Date().toISOString(),
    chainId,
    rpcUrl,
    contract: {
      name: "NeuroProofReceiptAnchor",
      address: contractAddress,
      abiVersion: ABI_VERSION,
      sourceSha256: sha256Hex(compiled.source),
      creationBytecodeSha256: sha256Hex(Buffer.from(compiled.creationBytecode.slice(2), "hex")),
      runtimeCodeSha256,
      receiptDomain,
      runtimeMatchesCompiledSource: true,
    },
    authorization: {
      owner,
      authorizedAnchoringAccount: expectedAnchorer,
      ownerMatchesAccountZero: true,
      anchoringAccountAuthorized: true,
    },
    deployment: {
      transactionHash: transaction.hash,
      blockNumber: Number(receipt.blockNumber),
      status: "succeeded",
      creationTransactionMatchesExpectedV2BytecodeAndConstructor: true,
    },
    chainInspection: {
      inspectedAtBlock: latestBlock,
      successfulCreationTransactions: creations.length,
      stateChangingTransactionsToContract: callsToContract.length,
      receiptAnchoringTransactions: 0,
    },
    tooling: {
      node: process.version,
      ethers: ethers.version,
      hardhat: packageVersion("hardhat"),
      solc: compiled.compilerVersion,
    },
    recovery: {
      strategy: "deterministic_replay",
      receiptReplayManifest: "receipt-replay.json",
      limitations: "Hardhat memory state is not durable; deterministic replay requires the same protected mnemonic and an empty owner nonce.",
    },
  };
  writeRecoveredMetadata(stateDirectory, metadata);

  process.stdout.write(`${JSON.stringify({
    chainId,
    currentBlock: latestBlock,
    contractAddress,
    runtimeCodeSha256,
    owner,
    authorizedAnchoringAccount: expectedAnchorer,
    deploymentTransactionHash: transaction.hash,
    deploymentBlockNumber: Number(receipt.blockNumber),
    abiVersion: ABI_VERSION,
    recoveredMetadata: true,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`Development deployment recovery failed: ${error.message}\n`);
  process.exitCode = 1;
});
