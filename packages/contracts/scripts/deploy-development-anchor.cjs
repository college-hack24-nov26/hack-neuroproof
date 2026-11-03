"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { ethers } = require("ethers");
const { compileAnchor } = require("./compile.cjs");

const ABI_VERSION = "neuroproof-receipt-anchor-v1";
const EXPECTED_CHAIN_ID = 31337;
const RECEIPT_DOMAIN = "cerebrachain-v2:proof-receipt-anchor:v1";

function requiredArgument(name) {
  const index = process.argv.indexOf(name);
  const value = index >= 0 ? process.argv[index + 1] : undefined;
  if (!value) throw new Error(`${name} is required.`);
  return value;
}

function requiredLoopbackRpcUrl() {
  const value = requiredArgument("--rpc-url");
  if (value !== "http://127.0.0.1:18545") {
    throw new Error("Only the approved loopback development RPC URL is permitted.");
  }
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

function writeDeploymentMetadata(stateDirectory, metadata) {
  const target = path.join(stateDirectory, "deployment.json");
  if (fs.existsSync(target)) {
    throw new Error("Refusing to overwrite existing deployment metadata.");
  }
  const descriptor = fs.openSync(target, "wx", 0o600);
  try {
    fs.writeFileSync(descriptor, `${JSON.stringify(metadata, null, 2)}\n`, { encoding: "utf8" });
  } finally {
    fs.closeSync(descriptor);
  }
  fs.chmodSync(target, 0o600);
}

async function main() {
  const rpcUrl = requiredLoopbackRpcUrl();
  const stateDirectory = requiredStateDirectory();
  const replayManifest = path.join(stateDirectory, "receipt-replay.json");
  if (!fs.existsSync(replayManifest)) {
    throw new Error("Approved replay metadata is missing from the state directory.");
  }

  const provider = new ethers.JsonRpcProvider(
    rpcUrl,
    { chainId: EXPECTED_CHAIN_ID, name: "hardhat" },
    { staticNetwork: true },
  );
  const chainId = Number((await provider.getNetwork()).chainId);
  if (chainId !== EXPECTED_CHAIN_ID) throw new Error("Unexpected development chain ID.");

  const owner = await provider.getSigner(0);
  const anchorer = await provider.getSigner(1);
  const ownerAddress = await owner.getAddress();
  const anchorerAddress = await anchorer.getAddress();
  if (ownerAddress.toLowerCase() === anchorerAddress.toLowerCase()) {
    throw new Error("Owner and anchoring accounts must be distinct.");
  }
  if (await provider.getTransactionCount(ownerAddress, "latest") !== 0) {
    throw new Error("Owner account nonce is not zero; refusing non-deterministic deployment replay.");
  }

  const compiled = compileAnchor();
  const factory = new ethers.ContractFactory(compiled.abi, compiled.bytecode, owner);
  const contract = await factory.deploy(anchorerAddress);
  const deploymentTransaction = contract.deploymentTransaction();
  if (!deploymentTransaction) throw new Error("Deployment transaction metadata is unavailable.");
  const deploymentReceipt = await deploymentTransaction.wait();
  if (!deploymentReceipt || deploymentReceipt.status !== 1) {
    throw new Error("Deployment transaction did not succeed.");
  }

  const contractAddress = await contract.getAddress();
  const runtimeCode = await provider.getCode(contractAddress);
  if (runtimeCode === "0x") throw new Error("No runtime bytecode was deployed.");
  const runtimeCodeSha256 = sha256Hex(Buffer.from(runtimeCode.slice(2), "hex"));
  const source = fs.readFileSync(path.join(__dirname, "..", "contracts", "NeuroProofReceiptAnchor.sol"));
  const expectedDomain = ethers.keccak256(ethers.toUtf8Bytes(RECEIPT_DOMAIN));
  const deployedOwner = await contract.owner();
  const anchorerAuthorized = await contract.isAnchoringAccount(anchorerAddress);
  const deployedDomain = await contract.RECEIPT_DOMAIN();
  if (deployedOwner.toLowerCase() !== ownerAddress.toLowerCase()) {
    throw new Error("Deployed contract owner does not match development account 0.");
  }
  if (!anchorerAuthorized) throw new Error("Development account 1 was not authorized as anchorer.");
  if (deployedDomain.toLowerCase() !== expectedDomain.toLowerCase()) {
    throw new Error("Deployed contract ABI/domain compatibility check failed.");
  }

  const metadata = {
    version: 1,
    environment: "localhost-development-only",
    createdAt: new Date().toISOString(),
    chainId,
    rpcUrl,
    contract: {
      name: "NeuroProofReceiptAnchor",
      address: contractAddress,
      abiVersion: ABI_VERSION,
      sourceSha256: sha256Hex(source),
      creationBytecodeSha256: sha256Hex(Buffer.from(compiled.bytecode.slice(2), "hex")),
      runtimeCodeSha256,
      receiptDomain: deployedDomain,
    },
    authorization: {
      owner: ownerAddress,
      authorizedAnchoringAccount: anchorerAddress,
      ownerMatchesAccountZero: true,
      anchoringAccountAuthorized: true,
    },
    deployment: {
      transactionHash: deploymentTransaction.hash,
      blockNumber: Number(deploymentReceipt.blockNumber),
      status: "succeeded",
    },
    tooling: {
      node: process.version,
      ethers: ethers.version,
      hardhat: require("hardhat/package.json").version,
      solc: compiled.compilerVersion,
    },
    recovery: {
      strategy: "deterministic_replay",
      receiptReplayManifest: "receipt-replay.json",
      limitations: "Hardhat memory state is not durable; re-run deployment first with the same mnemonic and zero owner nonce.",
    },
  };
  writeDeploymentMetadata(stateDirectory, metadata);
  process.stdout.write(`${JSON.stringify({
    chainId,
    contractAddress,
    runtimeCodeSha256,
    owner: ownerAddress,
    authorizedAnchoringAccount: anchorerAddress,
    deploymentTransactionHash: deploymentTransaction.hash,
    deploymentBlockNumber: Number(deploymentReceipt.blockNumber),
    abiVersion: ABI_VERSION,
  })}\n`);
}

main().catch((error) => {
  process.stderr.write(`Development deployment failed: ${error.message}\n`);
  process.exitCode = 1;
});
